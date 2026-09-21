import math
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw
from wsi_viewer.alignment_pyramid import (
    _candidate_component_pairs,
    _component_identity_is_clear,
    _ComponentMap,
    _expand_verified_support,
    _feature_identity_evidence,
    _flow_cell_evidence,
    _flow_refined_controls,
    _layout_consistency,
    read_region,
)


def _pyramid(path: Path, image: Image.Image) -> dict[int, Image.Image]:
    path.mkdir()
    tile_size, overlap = 128, 1
    (path / "slide.dzi").write_text(
        f'<Image TileSize="{tile_size}" Overlap="{overlap}" Format="png" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        f'<Size Width="{image.width}" Height="{image.height}" /></Image>'
    )
    maximum = math.ceil(math.log2(max(image.size)))
    levels = {}
    for downsample in (1, 2, 4, 8):
        level = maximum - int(math.log2(downsample))
        resized = image.resize(
            (math.ceil(image.width / downsample), math.ceil(image.height / downsample))
        )
        levels[downsample] = resized
        root = path / "slide_files" / str(level)
        root.mkdir(parents=True)
        for y in range(math.ceil(resized.height / tile_size)):
            for x in range(math.ceil(resized.width / tile_size)):
                resized.crop(
                    (
                        max(0, x * tile_size - overlap),
                        max(0, y * tile_size - overlap),
                        min(resized.width, (x + 1) * tile_size + overlap),
                        min(resized.height, (y + 1) * tile_size + overlap),
                    )
                ).save(root / f"{x}_{y}.png")
    return levels


@pytest.mark.parametrize(
    "bounds,limit", [((117, 123, 899, 777), 512), ((1000, 701, 1301, 901), 256)]
)
def test_region_preserves_pixels_and_exact_coordinate_frame(tmp_path, bounds, limit):
    image = Image.fromarray(
        np.random.default_rng(7).integers(0, 256, (901, 1301, 3), dtype=np.uint8)
    )
    levels = _pyramid(tmp_path / "slide", image)
    region, (x, y, divisor) = read_region(tmp_path / "slide", bounds, limit)
    assert max(region.size) <= limit
    assert x == bounds[0] // divisor * divisor
    assert y == bounds[1] // divisor * divisor
    expected = levels[divisor].crop(
        (x // divisor, y // divisor, math.ceil(bounds[2] / divisor), math.ceil(bounds[3] / divisor))
    )
    np.testing.assert_array_equal(region, expected)


def test_region_does_not_read_unrelated_tiles(tmp_path):
    image = Image.new("RGB", (1301, 901), (91, 40, 121))
    _pyramid(tmp_path / "slide", image)
    # Remove a far-away tile. This bounded request must still succeed.
    (tmp_path / "slide" / "slide_files" / "11" / "9_6.png").unlink()
    region, frame = read_region(tmp_path / "slide", (0, 0, 200, 200))
    assert frame == (0, 0, 1)
    assert region.getpixel((100, 100)) == (91, 40, 121)


def test_region_materializes_missing_local_openslide_tiles(tmp_path, monkeypatch):
    from wsi_viewer import tile_routes

    root = tmp_path / "slide"
    root.mkdir()
    (root / "slide.dzi").write_text(
        '<Image TileSize="128" Overlap="0" Format="jpg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        '<Size Width="512" Height="256" /></Image>',
        encoding="utf-8",
    )
    (root / ".openslide-source.json").write_text("{}", encoding="utf-8")
    requested = []

    def materialize(path, slide_id, relative):
        requested.append((path, slide_id, relative))
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (128, 128), (77, 31, 102)).save(target, "JPEG")
        return target

    monkeypatch.setattr(tile_routes, "materialize_local_openslide_tile_from_root", materialize)
    region, frame = read_region(root, (0, 0, 128, 128))

    assert frame == (0, 0, 1)
    assert requested == [(root, "slide", "slide_files/9/0_0.jpg")]
    assert region.getpixel((64, 64)) == pytest.approx((77, 31, 102), abs=3)


def test_region_rejects_outside_bounds_and_unbounded_allocations(tmp_path):
    _pyramid(tmp_path / "slide", Image.new("RGB", (600, 400)))
    with pytest.raises(ValueError, match="outside"):
        read_region(tmp_path / "slide", (-1, 0, 100, 100))
    with pytest.raises(ValueError, match="limit"):
        read_region(tmp_path / "slide", (0, 0, 600, 400), maximum=20000)


def _textured_tissue():
    from PIL import ImageDraw

    image = Image.new("RGB", (700, 600), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse((60, 70, 640, 530), fill=(223, 150, 180))
    rng = np.random.default_rng(21)
    for _ in range(120):
        x, y = int(rng.integers(130, 570)), int(rng.integers(150, 450))
        r = int(rng.integers(3, 13))
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(75, 40, 110))
    return image


def test_component_maps_use_full_slide_coordinates_and_round_trip(tmp_path):
    from wsi_viewer.alignment import map_registration_point
    from wsi_viewer.alignment_pyramid import register_components

    tissue = _textured_tissue()
    reference = Image.new("RGB", (1400, 1000), "white")
    moving = Image.new("RGB", reference.size, "white")
    reference.paste(tissue, (170, 90))
    moving.paste(tissue, (430, 220))
    _pyramid(tmp_path / "r", reference)
    _pyramid(tmp_path / "m", moving)
    progress = []
    result = register_components(
        tmp_path / "r",
        tmp_path / "m",
        reference,
        moving,
        reference.size,
        moving.size,
        lambda done, total: progress.append((done, total)),
    )
    assert result.status == "ready"
    assert result.evidence["acceptedComponents"] == 1
    assert progress[-1] == (1, 1)
    for triangle in result.triangles:
        source = np.mean(triangle["moving"], axis=0)
        target = map_registration_point(result.as_json(), *source)
        np.testing.assert_allclose(target, source - np.array([260, 130]), atol=2)
        restored = map_registration_point(result.as_json(), *target, inverse=True)
        np.testing.assert_allclose(restored, source, atol=0.5)


def test_identical_repeated_fragments_remain_explicitly_approximate(tmp_path):
    from wsi_viewer.alignment import map_registration_point
    from wsi_viewer.alignment_pyramid import register_components

    tissue = _textured_tissue()
    image = Image.new("RGB", (1800, 1000), "white")
    image.paste(tissue, (100, 150))
    image.paste(tissue, (950, 150))
    _pyramid(tmp_path / "r", image)
    _pyramid(tmp_path / "m", image)
    result = register_components(
        tmp_path / "r", tmp_path / "m", image, image, image.size, image.size
    )
    assert result.status == "approximate"
    assert result.triangles == []
    assert result.overview_triangles
    assert result.evidence["anatomicalMatchCount"] == 0
    cell = result.overview_triangles[0]
    source = np.mean(cell["moving"], axis=0)
    overview_map = {**result.as_json(), "triangles": result.overview_triangles}
    mapped = map_registration_point(overview_map, *source)
    restored = map_registration_point(overview_map, *mapped, inverse=True)
    np.testing.assert_allclose(restored, source, atol=0.5)


def test_unique_component_can_use_patch_verified_structural_flow(tmp_path, monkeypatch):
    from wsi_viewer import alignment_pyramid
    from wsi_viewer.alignment import RegistrationResult

    tissue = _textured_tissue()
    _pyramid(tmp_path / "r", tissue)
    _pyramid(tmp_path / "m", tissue)

    def no_feature_result(*_args, **_kwargs):
        return RegistrationResult(
            status="approximate",
            moving_to_reference=[[1, 0, 0], [0, 1, 0]],
            reference_support=(0, 0, tissue.width, tissue.height),
            moving_support=(0, 0, tissue.width, tissue.height),
            confidence=0,
            inlier_count=0,
            match_count=0,
            median_error_pixels=-1,
        )

    monkeypatch.setattr(alignment_pyramid, "register_pair", no_feature_result)
    result = alignment_pyramid.register_components(
        tmp_path / "r", tmp_path / "m", tissue, tissue, tissue.size, tissue.size
    )

    assert result.status == "ready"
    assert result.triangles
    assert result.evidence["acceptedStructuralComponents"] == 1
    assert result.evidence["withheldCheck"] == "pending-independent-landmarks"


def _component_candidate(identity: float, layout: float) -> _ComponentMap:
    return _ComponentMap(
        transform=[[1, 0, 0], [0, 1, 0]],
        overview_cells=[],
        verified_cells=[{}] * round(identity * 100),
        supported_cells=[],
        intensity_score=0,
        overlap=0,
        flow_control_count=100,
        flow_cycle_p95=0,
        patch_ncc_median=0,
        patch_discrimination_median=0,
        layout_score=layout,
    )


def test_fragment_layout_resolves_only_a_real_internal_evidence_margin():
    preferred = _component_candidate(0.32, 0.91)
    weaker_wrong_fragment = _component_candidate(0.26, 0.10)
    identical_wrong_fragment = _component_candidate(0.32, 0.10)

    assert _component_identity_is_clear(preferred, [weaker_wrong_fragment])
    assert not _component_identity_is_clear(preferred, [identical_wrong_fragment])


def test_repeated_fragment_with_strong_runner_up_remains_ambiguous():
    apparent_winner = _component_candidate(0.75, 0.95)
    plausible_other_core = _component_candidate(0.52, 0.10)
    decisive_winner = _component_candidate(0.90, 0.95)
    weaker_other_core = _component_candidate(0.45, 0.10)

    assert not _component_identity_is_clear(apparent_winner, [plausible_other_core])
    assert _component_identity_is_clear(decisive_winner, [weaker_other_core])


def test_fragment_pairing_marks_only_displaced_unambiguous_layout() -> None:
    reference = Image.new("RGB", (1000, 600), "white")
    moving = Image.new("RGB", reference.size, "white")
    for image, boxes in (
        (reference, [(100, 100, 300, 500), (700, 100, 900, 500)]),
        (moving, [(125, 100, 325, 500), (675, 100, 875, 500)]),
    ):
        draw = ImageDraw.Draw(image)
        for box in boxes:
            draw.ellipse(box, fill=(150, 80, 120))
    pairs, resolved = _candidate_component_pairs(
        reference,
        moving,
        [(100, 100, 300, 500), (700, 100, 900, 500)],
        [(125, 100, 325, 500), (675, 100, 875, 500)],
        reference.size,
        moving.size,
    )
    assert pairs == [(0, 0), (1, 1)]
    assert resolved == {(0, 0), (1, 1)}

    _, unchanged = _candidate_component_pairs(
        reference,
        reference,
        [(100, 100, 300, 500), (700, 100, 900, 500)],
        [(100, 100, 300, 500), (700, 100, 900, 500)],
        reference.size,
        reference.size,
    )
    assert unchanged == set()


def test_fragment_pairing_does_not_swap_repeated_components_for_outline_score() -> None:
    reference = Image.new("RGB", (1000, 600), "white")
    moving = Image.new("RGB", reference.size, "white")
    reference_boxes = [(90, 120, 260, 480), (690, 80, 930, 520)]
    moving_boxes = [(120, 90, 360, 530), (740, 120, 910, 480)]
    reference_draw = ImageDraw.Draw(reference)
    moving_draw = ImageDraw.Draw(moving)
    reference_draw.ellipse(reference_boxes[0], fill=(150, 80, 120))
    reference_draw.ellipse(reference_boxes[1], fill=(150, 80, 120))
    # The large and small outlines trade sides, which tempts a whole-mask fit
    # to rotate 180 degrees. Scanner-order pairing must keep left with left.
    moving_draw.ellipse(moving_boxes[0], fill=(150, 80, 120))
    moving_draw.ellipse(moving_boxes[1], fill=(150, 80, 120))

    pairs, _ = _candidate_component_pairs(
        reference,
        moving,
        reference_boxes,
        moving_boxes,
        reference.size,
        moving.size,
    )

    assert pairs == [(0, 0), (1, 1)]


def test_optical_density_kaze_prefers_same_structure_across_stain_hues():
    rng = np.random.default_rng(42)
    reference = np.full((600, 700, 3), 250, dtype=np.uint8)
    for _ in range(140):
        x, y = (int(value) for value in rng.integers([60, 60], [640, 540]))
        radius = int(rng.integers(4, 18))
        cv2.circle(reference, (x, y), radius, (95, 55, 135), -1)
    mask = np.zeros(reference.shape[:2], dtype=np.uint8)
    cv2.ellipse(mask, (350, 300), (300, 240), 0, 0, 360, 255, -1)
    reference[mask == 0] = 255
    moving = np.full_like(reference, 255)
    density = 255 - cv2.cvtColor(reference, cv2.COLOR_RGB2GRAY)
    moving[:, :, 0] = 255 - density // 3
    moving[:, :, 1] = 255 - density
    moving[:, :, 2] = 255 - density // 2
    moving[mask == 0] = 255

    same_inliers, same_spread = _feature_identity_evidence(
        reference, mask, moving, mask, np.asarray([[1, 0, 0], [0, 1, 0]], dtype=float)
    )
    unrelated = np.roll(moving, 230, axis=0)
    wrong_inliers, wrong_spread = _feature_identity_evidence(
        reference, mask, unrelated, mask, np.asarray([[1, 0, 0], [0, 1, 0]], dtype=float)
    )

    assert same_inliers >= 20
    assert same_spread >= 0.25
    assert (same_inliers * same_spread) > (wrong_inliers * wrong_spread) * 1.5


def test_layout_consistency_checks_all_large_fragments():
    reference = [(100, 100, 300, 500), (800, 150, 1000, 550)]
    moving = [(130, 120, 330, 520), (830, 170, 1030, 570)]
    coherent = _layout_consistency(
        [[1, 0, -30], [0, 1, -20]], reference, moving, (1200, 700)
    )
    one_fragment_only = _layout_consistency(
        [[1, 0, -730], [0, 1, -20]], reference, moving, (1200, 700)
    )

    assert coherent > 0.99
    assert one_fragment_only < 0.2


def test_support_expansion_adds_only_edge_adjacent_low_residual_cells():
    verified = {
        "moving": [[0, 0], [10, 0], [0, 10]],
        "reference": [[0, 0], [10, 0], [0, 10]],
        "maxResidualPixels": 1.0,
    }
    adjacent = {
        "moving": [[10, 0], [0, 10], [10, 10]],
        "reference": [[10, 0], [0, 10], [10, 10]],
        "maxResidualPixels": 2.0,
    }
    point_touching = {
        "moving": [[10, 10], [20, 10], [10, 20]],
        "reference": [[10, 10], [20, 10], [10, 20]],
        "maxResidualPixels": 1.0,
    }
    unstable = {
        "moving": [[10, 0], [0, 10], [15, 15]],
        "reference": [[10, 0], [0, 10], [15, 15]],
        "maxResidualPixels": 8.0,
    }

    expanded = _expand_verified_support(
        [verified, adjacent, point_touching, unstable], [verified]
    )

    assert expanded == [verified, adjacent]


def test_distributed_patch_evidence_fills_connected_flow_support():
    cells = [
        {
            "moving": [[index, 0], [index + 1, 0], [index + 2, 0]],
            "reference": [[index, 0], [index + 1, 0], [index + 2, 0]],
            "maxResidualPixels": 1.0,
        }
        for index in range(10)
    ]
    # Give the verified subset non-zero two-dimensional extent while keeping
    # the same shared-edge chain topology.
    for index, cell in enumerate(cells):
        cell["moving"][2][1] = index % 2 + 1
        cell["reference"][2][1] = index % 2 + 1
        if index:
            cell["moving"][:2] = cells[index - 1]["moving"][1:]
            cell["reference"][:2] = cells[index - 1]["reference"][1:]

    expanded = _expand_verified_support(cells, cells[:8])

    assert expanded == cells


def test_component_refinement_keeps_valid_tissue_touching_crop_edge():
    from PIL import ImageDraw
    from wsi_viewer.alignment_pyramid import _approximate_component_map

    reference = Image.new("RGB", (500, 500), "white")
    draw = ImageDraw.Draw(reference)
    draw.ellipse((-30, 40, 430, 470), fill=(220, 150, 180))
    for x in range(20, 420, 40):
        for y in range(80, 440, 40):
            draw.ellipse((x, y, x + 10, y + 10), fill=(60, 45, 100))
    moving = reference.rotate(4, resample=Image.Resampling.BICUBIC, fillcolor="white")

    result = _approximate_component_map(reference, moving, (0, 0, 1), (0, 0, 1))

    assert result is not None
    assert result.overview_cells


def test_same_scanner_frame_does_not_invent_mask_axis_rotation():
    from PIL import ImageDraw
    from wsi_viewer.alignment_pyramid import _approximate_component_map

    reference = Image.new("RGB", (720, 520), "white")
    draw = ImageDraw.Draw(reference)
    draw.ellipse((70, 60, 650, 480), fill=(218, 145, 178))
    draw.rectangle((330, 35, 390, 465), fill=(130, 70, 105))
    draw.ellipse((410, 250, 625, 455), fill=(95, 48, 88))
    for x in range(100, 620, 55):
        for y in range(90, 450, 50):
            draw.ellipse((x, y, x + 12, y + 9), fill=(70, 45, 95))

    # Preserve the scanner frame and internal geometry while changing the
    # stain intensity substantially. The broad asymmetric mask has an oblique
    # PCA axis, which must not become an invented slide rotation.
    moving = Image.new("RGB", reference.size, "white")
    source = np.asarray(reference)
    density = 255 - np.min(source, axis=2)
    pale = np.full_like(source, 255)
    pale[:, :, 0] = np.where(density > 8, 238 - density // 7, 255)
    pale[:, :, 1] = np.where(density > 8, 239 - density // 8, 255)
    pale[:, :, 2] = np.where(density > 8, 246 - density // 5, 255)
    moving.paste(Image.fromarray(pale), (7, -5))

    result = _approximate_component_map(reference, moving, (0, 0, 1), (0, 0, 1))

    assert result is not None
    linear = np.asarray(result.transform)[:, :2]
    rotation = math.degrees(math.atan2(linear[1, 0], linear[0, 0]))
    assert abs(rotation) < 2
    assert result.intensity_score >= 0.45


def test_whole_slide_shape_fallback_survives_fragmented_pale_ihc(tmp_path, monkeypatch):
    from wsi_viewer import alignment_pyramid

    reference = Image.new("RGB", (700, 520), "white")
    draw = ImageDraw.Draw(reference)
    draw.ellipse((80, 70, 650, 540), fill=(225, 155, 190))
    for x in range(145, 610, 58):
        for y in range(135, 455, 61):
            draw.ellipse((x, y, x + 15, y + 11), fill=(92, 51, 103))
    moving = Image.new("RGB", reference.size, "white")
    pale = Image.new("RGB", reference.size, "white")
    pale_draw = ImageDraw.Draw(pale)
    pale_draw.ellipse((80, 70, 650, 540), fill=(244, 238, 245))
    for x in range(145, 610, 58):
        for y in range(135, 455, 61):
            pale_draw.ellipse((x, y, x + 15, y + 11), fill=(192, 178, 205))
    moving.paste(pale, (8, -5))
    _pyramid(tmp_path / "r", reference)
    _pyramid(tmp_path / "m", moving)
    original_approximate = alignment_pyramid._approximate_component_map
    monkeypatch.setattr(
        alignment_pyramid,
        "register_pair",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            alignment_pyramid.AlignmentRejected("no local anatomy")
        ),
    )
    monkeypatch.setattr(
        alignment_pyramid,
        "_approximate_component_map",
        lambda fixed, floating, fixed_frame, floating_frame, **kwargs: (
            original_approximate(fixed, floating, fixed_frame, floating_frame)
            if fixed.size == reference.size and floating.size == moving.size
            else None
        ),
    )

    result = alignment_pyramid.register_components(
        tmp_path / "r", tmp_path / "m", reference, moving, reference.size, moving.size
    )

    assert result.status == "approximate"
    assert result.triangles == []
    assert result.overview_triangles
    assert result.evidence["source"] == "bounded-pyramid-whole-slide-structure"


def test_whole_slide_structural_fallback_recovers_real_rotation(tmp_path, monkeypatch):
    from PIL import ImageDraw
    from wsi_viewer import alignment_pyramid

    reference = Image.new("RGB", (760, 560), "white")
    draw = ImageDraw.Draw(reference)
    draw.ellipse((80, 70, 660, 500), fill=(221, 151, 181))
    draw.rectangle((150, 120, 235, 440), fill=(120, 65, 105))
    draw.ellipse((430, 260, 625, 455), fill=(88, 45, 91))
    for x in range(270, 610, 45):
        for y in range(105, 440, 52):
            draw.ellipse((x, y, x + 13, y + 9), fill=(67, 43, 96))
    moving = reference.rotate(8, resample=Image.Resampling.BICUBIC, fillcolor="white")
    _pyramid(tmp_path / "r", reference)
    _pyramid(tmp_path / "m", moving)
    monkeypatch.setattr(
        alignment_pyramid,
        "register_pair",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            alignment_pyramid.AlignmentRejected("no local anatomy")
        ),
    )
    monkeypatch.setattr(
        alignment_pyramid,
        "_approximate_component_map",
        lambda *_args, **_kwargs: None,
    )

    result = alignment_pyramid.register_components(
        tmp_path / "r", tmp_path / "m", reference, moving, reference.size, moving.size
    )

    assert result.status == "approximate"
    assert result.evidence["source"] == "bounded-pyramid-whole-slide-structure"
    assert result.evidence["wholeSlideTransformKind"] == "structure-affine"
    assert abs(abs(result.evidence["wholeSlideRotationDegrees"]) - 8) < 2


def test_whole_slide_structural_fallback_rejects_unrelated_same_size_tissue(
    tmp_path, monkeypatch
):
    from PIL import ImageDraw
    from wsi_viewer import alignment_pyramid

    reference = _textured_tissue()
    moving = Image.new("RGB", reference.size, "white")
    draw = ImageDraw.Draw(moving)
    draw.rectangle((80, 80, 620, 520), fill=(226, 162, 186))
    for index in range(12):
        x = 105 + index * 43
        draw.line((x, 95, 620 - index * 17, 505), fill=(73, 42, 102), width=11)
    _pyramid(tmp_path / "r", reference)
    _pyramid(tmp_path / "m", moving)
    monkeypatch.setattr(
        alignment_pyramid,
        "register_pair",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            alignment_pyramid.AlignmentRejected("no local anatomy")
        ),
    )
    monkeypatch.setattr(
        alignment_pyramid,
        "_approximate_component_map",
        lambda *_args, **_kwargs: None,
    )

    with pytest.raises(alignment_pyramid.AlignmentRejected):
        alignment_pyramid.register_components(
            tmp_path / "r", tmp_path / "m", reference, moving, reference.size, moving.size
        )


def test_flow_refinement_returns_cycle_consistent_local_controls():
    reference = np.full((512, 512), 245, dtype=np.uint8)
    rng = np.random.default_rng(91)
    for _ in range(180):
        x, y = (int(value) for value in rng.integers(55, 457, 2))
        radius = int(rng.integers(3, 14))
        cv2.circle(reference, (x, y), radius, int(rng.integers(30, 180)), -1)
    mask = np.zeros_like(reference)
    cv2.ellipse(mask, (256, 256), (215, 190), 0, 0, 360, 255, -1)
    rows, columns = np.mgrid[0:512, 0:512].astype(np.float32)
    moving = cv2.remap(
        reference,
        columns + 6 * np.sin(rows / 75),
        rows + 4 * np.sin(columns / 90),
        cv2.INTER_LINEAR,
        borderValue=245,
    )

    controls, cycle_p95 = _flow_refined_controls(
        reference,
        mask,
        moving,
        mask,
        np.asarray([[1, 0, 0], [0, 1, 0]], dtype=np.float32),
    )

    assert len(controls) >= 12
    assert 0 <= cycle_p95 <= 4
    assert np.median(
        [
            np.linalg.norm(np.asarray(control["reference"]) - control["moving"])
            for control in controls
        ]
    ) > 1


def test_flow_refinement_rejects_textureless_tissue():
    blank = np.full((384, 384), 128, dtype=np.uint8)
    mask = np.full_like(blank, 255)

    controls, cycle_p95 = _flow_refined_controls(
        blank,
        mask,
        blank,
        mask,
        np.asarray([[1, 0, 0], [0, 1, 0]], dtype=np.float32),
    )

    assert controls == []
    assert cycle_p95 == -1


def test_flow_cell_evidence_requires_local_patch_agreement_and_discrimination():
    rng = np.random.default_rng(144)
    reference = rng.integers(0, 256, (512, 512), dtype=np.uint8)
    cell = {
        "moving": [[120.0, 120.0], [420.0, 120.0], [120.0, 420.0]],
        "reference": [[120.0, 120.0], [420.0, 120.0], [120.0, 420.0]],
    }

    verified, ncc, discrimination = _flow_cell_evidence([cell], reference, reference.copy())
    unrelated = rng.integers(0, 256, reference.shape, dtype=np.uint8)
    rejected, _, _ = _flow_cell_evidence([cell], reference, unrelated)

    assert len(verified) == 1
    assert ncc > 0.99
    assert discrimination > 0.8
    assert rejected == []
