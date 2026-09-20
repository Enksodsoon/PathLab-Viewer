import math
from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image
from wsi_viewer.alignment_pyramid import _flow_refined_controls, read_region


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
    assert result[1]


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
