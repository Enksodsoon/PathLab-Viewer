import json
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from PIL import Image
from wsi_viewer import alignment_engines
from wsi_viewer.alignment import AlignmentRejected, _structure, map_registration_point
from wsi_viewer.alignment_engines import (
    EngineInput,
    ValisEngine,
    _mark_approximate_engine_map,
    _sample_coordinate_map,
    _scanner_frame_candidate,
    engine_availability,
    merge_component_maps,
    settings_digest,
)


def _tissue() -> np.ndarray:
    image = np.full((240, 320, 3), 255, dtype=np.uint8)
    image[30:210, 40:280] = (175, 90, 130)
    for x in range(60, 270, 30):
        image[60:190:25, x : x + 6] = (30, 20, 70)
    return image


def test_feature_tissue_coverage_ignores_glass_but_counts_unmatched_fragments(monkeypatch):
    mask = np.zeros((240, 320), dtype=np.uint8)
    mask[20:220, 30:40] = 255
    monkeypatch.setattr(alignment_engines, "_structure", lambda _, **kwargs: (None, mask))
    points = np.asarray([[29, 19], [40, 19], [40, 220], [29, 220]], dtype=float)
    rgb = np.zeros((240, 320, 3), dtype=np.uint8)
    assert alignment_engines._feature_tissue_coverage(points, rgb) == 1.0
    mask[20:220, 200:210] = 255
    assert alignment_engines._feature_tissue_coverage(points, rgb) == 0.5
    assert alignment_engines._feature_tissue_coverage(points[:2], rgb) == 0.0
    points[0, 0] = np.nan
    assert alignment_engines._feature_tissue_coverage(points, rgb) == 0.0


def test_component_maps_keep_independent_transforms_and_refuse_glass_between_fragments():
    from copy import deepcopy

    def part(offset):
        return {
            "status": "ready",
            "movingToReference": [[1, 0, offset], [0, 1, 0]],
            "triangles": [
                {
                    "moving": [[0, 0], [10, 0], [0, 10]],
                    "reference": [[offset, 0], [offset + 10, 0], [offset, 10]],
                }
            ],
            "confidence": 0.9,
            "evidence": {"valisLocalEvidenceQualified": True},
        }

    parts = [(part(2), (100, 200, 16), (300, 400, 8)), (part(-3), (500, 600, 32), (700, 800, 16))]
    original = deepcopy(parts)
    result = merge_component_maps(parts)
    assert parts == original
    assert map_registration_point(result, 302, 402) == pytest.approx((104, 202))
    assert map_registration_point(result, 702, 802) == pytest.approx((499, 602))
    assert map_registration_point(result, 499, 602, inverse=True) == pytest.approx((702, 802))
    with pytest.raises(AlignmentRejected, match="outside accepted"):
        map_registration_point(result, 500, 500)
    assert result["movingToReference"] == [[1, 0, -198], [0, 1, -200]]
    assert result["evidence"]["componentCount"] == 2
    approximate = deepcopy(parts)
    approximate[1][0]["status"] = "approximate"
    approximate[1][0]["overviewTriangles"] = approximate[1][0].pop("triangles")
    approximate[1][0]["evidence"]["valisLocalEvidenceQualified"] = False
    mixed = merge_component_maps(approximate)
    assert mixed["evidence"]["localComponentCount"] == 1
    assert mixed["evidence"]["approximateComponentCount"] == 1
    assert "Partial component coverage" in mixed["reason"]
    assert len(mixed["triangles"]) == 1 and len(mixed["overviewTriangles"]) == 1
    for payload, _, _ in parts:
        payload["evidence"]["valisLocalEvidenceQualified"] = False
    with pytest.raises(AlignmentRejected, match="No accepted component"):
        merge_component_maps(parts)


def test_engine_map_uses_same_triangles_for_subpixel_round_trips() -> None:
    image = _tissue()
    offset = np.asarray([13.0, -7.0])
    result = _sample_coordinate_map(
        reference_rgb=image,
        moving_rgb=image,
        map_moving_to_reference=lambda points: points + offset,
        map_reference_to_moving=lambda points: points - offset,
        provenance="test-engine",
    )
    payload = result.as_json()
    assert payload["triangles"]
    triangle = payload["triangles"][0]["moving"]
    point = tuple(np.mean(np.asarray(triangle), axis=0))
    mapped = map_registration_point(payload, *point)
    restored = map_registration_point(payload, *mapped, inverse=True)
    assert np.linalg.norm(np.asarray(restored) - point) < 0.5


def test_engine_map_rejects_inconsistent_inverse() -> None:
    image = _tissue()
    with pytest.raises(AlignmentRejected, match="round-trip"):
        _sample_coordinate_map(
            reference_rgb=image,
            moving_rgb=image,
            map_moving_to_reference=lambda points: points + 10,
            map_reference_to_moving=lambda points: points + 10,
            provenance="broken-engine",
        )


def test_declared_tissue_crop_uses_existing_support_guard_without_coordinate_padding():
    from wsi_viewer.alignment_fast import PreparationCache

    image = np.full((240, 320, 3), (175, 90, 130), dtype=np.uint8)
    image[30:220:20, 20:300:20] = (30, 20, 70)
    with pytest.raises(AlignmentRejected, match="insufficient tissue"):
        _structure(image)
    result = _sample_coordinate_map(
        reference_rgb=image,
        moving_rgb=image,
        map_moving_to_reference=lambda points: points,
        map_reference_to_moving=lambda points: points,
        provenance="declared-crop",
        reference_cropped=True,
        moving_cropped=True,
    )
    assert result.evidence["tissueDice"] == pytest.approx(1)
    assert np.asarray(result.moving_to_reference) == pytest.approx(
        np.asarray([[1, 0, 0], [0, 1, 0]])
    )
    cache = PreparationCache()
    prepared, hit = cache.prepare("crop", Image.fromarray(image), (3200, 2400), cropped=True)
    assert not hit and prepared.full_size == (3200, 2400)
    assert prepared.mask.shape == image.shape[:2]
    _, hit = cache.prepare("crop", Image.fromarray(image), (3200, 2400), cropped=True)
    assert hit
    with pytest.raises(AlignmentRejected, match="insufficient tissue"):
        cache.prepare("crop", Image.fromarray(image), (3200, 2400), cropped=False)


def test_engine_map_handles_fractional_coordinates_at_image_boundary() -> None:
    image = _tissue()
    _, mask = _structure(image)
    x, y, width, height = cv2.boundingRect(cv2.findNonZero(mask))
    offset = np.asarray(
        [image.shape[1] - 0.1 - (x + width - 1), image.shape[0] - 0.1 - (y + height - 1)]
    )
    result = _sample_coordinate_map(
        reference_rgb=image,
        moving_rgb=image,
        map_moving_to_reference=lambda points: points + offset,
        map_reference_to_moving=lambda points: points - offset,
        provenance="fractional-edge",
    )
    assert result.triangles


def test_engine_map_rejects_self_consistent_wrong_tissue_overlap() -> None:
    image = _tissue()
    offset = np.asarray([150.0, 0.0])
    with pytest.raises(AlignmentRejected, match="whole-tissue overlap"):
        _sample_coordinate_map(
            reference_rgb=image,
            moving_rgb=image,
            map_moving_to_reference=lambda points: points + offset,
            map_reference_to_moving=lambda points: points - offset,
            provenance="wrong-anatomy",
        )


def test_scanner_frame_candidate_recovers_stain_shift_without_false_rotation() -> None:
    reference = _tissue()
    moving = np.full_like(reference, 255)
    moving[:, 13:] = reference[:, :-13]
    density = 255 - np.min(moving, axis=2)
    moving[:, :, 0] = np.where(density > 8, 242 - density // 8, 255)
    moving[:, :, 1] = np.where(density > 8, 238 - density // 7, 255)
    moving[:, :, 2] = np.where(density > 8, 247 - density // 6, 255)

    candidate = _scanner_frame_candidate(reference, moving)

    assert candidate is not None
    transform, score, overlap = candidate
    assert transform[0, 2] == pytest.approx(-13, abs=3)
    assert transform[1, 2] == pytest.approx(0, abs=3)
    assert abs(np.degrees(np.arctan2(transform[1, 0], transform[0, 0]))) < 0.5
    assert score >= 0.45
    assert overlap >= 0.5


def test_dense_engine_map_without_feature_evidence_is_overview_only() -> None:
    image = _tissue()
    result = _sample_coordinate_map(
        reference_rgb=image,
        moving_rgb=image,
        map_moving_to_reference=lambda points: points,
        map_reference_to_moving=lambda points: points,
        provenance="dense-flow",
    ).as_json()

    approximate = _mark_approximate_engine_map(result, reason="insufficient distributed features")

    assert approximate["status"] == "approximate"
    assert approximate["triangles"] == []
    assert approximate["overviewTriangles"]
    assert approximate["controlPoints"] == []
    assert approximate["evidence"]["mode"] == "approximate-overview"
    assert approximate["evidence"]["withheldCheck"] == (
        "insufficient-distributed-anatomical-features"
    )


def test_availability_always_reports_native_and_explains_optional_engines() -> None:
    availability = engine_availability()
    assert availability["native-v12"]["available"] is True
    for engine in ("hisalign-0.2.1", "valis-1.2.0"):
        assert isinstance(availability[engine]["available"], bool)
        if not availability[engine]["available"]:
            assert availability[engine]["reason"]


@pytest.mark.parametrize("dice", [None, 0.492022, 0.649999, float("nan")])
def test_unqualified_dense_map_cannot_publish_weak_overview(dice: float | None) -> None:
    with pytest.raises(AlignmentRejected, match="insufficient tissue support"):
        _mark_approximate_engine_map(
            {"evidence": {"tissueDice": dice}}, reason="insufficient distributed features"
        )


def test_feature_support_requires_every_vertex_on_both_slides() -> None:
    matches = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
    supported = {"moving": [[0, 0], [5, 0], [0, 5]], "reference": [[0, 0], [5, 0], [0, 5]]}
    outside = {**supported, "reference": [[0, 0], [11, 0], [0, 5]]}
    cells = [supported, outside]
    assert alignment_engines._feature_supported_triangles(cells, matches, matches) == [supported]
    assert alignment_engines._feature_supported_triangles(cells, matches[:2], matches) == []
    assert cells == [supported, outside]


def test_settings_digest_includes_pathlab_adapter_revision() -> None:
    digest = settings_digest("hisalign-0.2.1")

    assert len(digest) == 64
    assert digest != settings_digest("native-v12")
    assert settings_digest("valis-1.2.0", {"rigidMatcher": "vgg"}) != settings_digest("valis-1.2.0")
    assert settings_digest("valis-1.2.0", {"inputBlurRadius": 0.6}) != settings_digest(
        "valis-1.2.0"
    )


@pytest.mark.parametrize(
    "profile,limit,blur,residual",
    [
        ("default", None, 0.6, 0),
        ("vgg", None, 0.6, 0),
        ("disk", None, 0.6, 0),
        ("default", 1536, 0.6, 0),
        ("disk", 1536, 0.6, 0),
        ("default", 1536, 0, 0),
        ("default", 1536, 0, 40),
    ],
)
def test_valis_artifact_preserves_final_approximate_qualification(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    profile: str,
    limit: int | None,
    blur: float,
    residual: float,
) -> None:
    slide = SimpleNamespace(warp_xy_from_to=lambda points, target: points)
    qualified = profile == "default" and limit == 1536
    if qualified:
        points = np.array(
            [
                [50, 50],
                [200, 50],
                [200, 180],
                [50, 180],
                [100, 50],
                [200, 100],
                [100, 180],
                [50, 100],
            ],
            dtype=float,
        )
        slide.xy_matched_to_prev = points
        slide.xy_in_prev = points + [residual, 0]
        slide.slide_dimensions_wh = [[320, 240]]
        slide.processed_img_shape_rc = (240, 320)
    registrar = SimpleNamespace(
        rigid_reg_kwargs={
            "matcher": SimpleNamespace(
                feature_detector=SimpleNamespace(detect_and_compute=lambda image: None)
            )
        },
        register=lambda: (
            None,
            None,
            SimpleNamespace(
                to_dict=lambda **kwargs: (
                    [{"from": "01-moving.png", "non_rigid_rTRE": 0.001}] if qualified else []
                )
            ),
        ),
        get_slide=lambda name: slide,
    )
    matcher = object()

    def create(*args, **kwargs):
        assert (kwargs.get("matcher") is matcher) == (profile == "vgg" or limit is not None)
        assert (kwargs.get("matcher_for_sorting") is matcher) == (profile == "disk")
        return registrar

    registration = SimpleNamespace(
        Valis=create, DEFAULT_MATCHER_FOR_SORTING=matcher, DEFAULT_MATCHER=matcher
    )

    def bounded_matcher(**kwargs):
        assert kwargs["feature_detector"].limit == limit
        assert kwargs["match_filter_method"] == "RANSAC"
        return matcher

    modules = {
        "valis.registration": registration,
        "valis.feature_detectors": SimpleNamespace(
            DiskFD=lambda num_features: SimpleNamespace(limit=num_features)
        ),
        "valis.feature_matcher": SimpleNamespace(
            LightGlueMatcher=bounded_matcher, DEFAULT_RANSAC_NAME="RANSAC"
        ),
    }
    original_import = alignment_engines.importlib.import_module
    monkeypatch.setattr(ValisEngine, "available", lambda self: (True, None))
    monkeypatch.setattr(
        alignment_engines.importlib,
        "import_module",
        lambda name: modules[name] if name in modules else original_import(name),
    )
    image = Image.fromarray(_tissue())
    original_pixels = image.tobytes()
    run = ValisEngine().register(
        EngineInput(
            image,
            image,
            image.size,
            image.size,
            tmp_path,
            settings={"rigidMatcher": profile, "inputBlurRadius": blur, "maxFeatures": limit},
        ),
        lambda value: None,
    )
    qualified = qualified and residual == 0
    assert run.registration["status"] == ("ready" if qualified else "approximate")
    assert run.registration["evidence"]["coordinateGridSize"] == 49
    if qualified:
        vertices = {tuple(p) for cell in run.registration["triangles"] for p in cell["moving"]}
        assert all(tuple(p["moving"]) in vertices for p in run.registration["controlPoints"])
        assert run.registration["inlierCount"] == len(run.registration["controlPoints"])
        assert len(run.registration["triangles"]) < len(run.registration["overviewTriangles"])
    assert image.tobytes() == original_pixels
    with Image.open(tmp_path / "valis-input" / "00-reference.png") as prepared:
        assert prepared.size == image.size
        assert (prepared.tobytes() != original_pixels) == bool(blur)
    assert run.artifact_path is not None
    assert json.loads(run.artifact_path.read_text()) == run.registration


def test_valis_rigid_only_shim_allows_pinned_upstream_cleanup() -> None:
    detector = SimpleNamespace(detect_and_compute=lambda image: None)
    registrar = SimpleNamespace(
        rigid_reg_kwargs={"matcher": SimpleNamespace(feature_detector=detector)},
    )

    def register():
        # Pinned Valis.register's cleanup accesses this even when its rigid-only
        # constructor skipped initializing it, after successful error measurement.
        registrar.non_rigid_reg_kwargs["non_rigid_registrar_cls"] = None
        return None, None, "measured-error-evidence"

    registrar.register = register
    result = alignment_engines._register_valis_bounded(registrar, 896, rigid_only=True)
    assert result[2] == "measured-error-evidence"
    existing = {"keep": "existing nonrigid options"}
    registrar.non_rigid_reg_kwargs = existing
    alignment_engines._register_valis_bounded(registrar, 896, rigid_only=True)
    assert registrar.non_rigid_reg_kwargs is existing


def test_valis_rejects_expanded_feature_canvas_and_restores_detector() -> None:
    calls = []
    detector = SimpleNamespace(detect_and_compute=lambda image: calls.append(image.shape))
    original = detector.detect_and_compute
    registrar = SimpleNamespace(
        rigid_reg_kwargs={"matcher": SimpleNamespace(feature_detector=detector)},
        register=lambda: detector.detect_and_compute(SimpleNamespace(shape=(6135, 5960, 3))),
    )
    with pytest.raises(AlignmentRejected, match="rematching canvas"):
        alignment_engines._register_valis_bounded(registrar, 896)
    assert calls == []
    assert detector.detect_and_compute is original
    registrar.register = lambda: detector.detect_and_compute(SimpleNamespace(shape=(1070, 979, 3)))
    alignment_engines._register_valis_bounded(registrar, 896)
    assert calls == [(1070, 979, 3)]
    assert detector.detect_and_compute is original

    def swallowed_rejection():
        try:
            detector.detect_and_compute(SimpleNamespace(shape=(6135, 5960, 3)))
        except AlignmentRejected:
            return None, None, None

    registrar.register = swallowed_rejection
    with pytest.raises(AlignmentRejected, match="rematching canvas"):
        alignment_engines._register_valis_bounded(registrar, 896)
    assert detector.detect_and_compute is original


def test_dense_engine_mesh_preserves_curved_transform_at_held_out_points():
    image = _tissue()

    def forward(points):
        mapped = points.copy()
        mapped[:, 0] += 4 * np.sin(points[:, 1] / 10)
        return mapped

    def inverse(points):
        restored = points.copy()
        restored[:, 0] -= 4 * np.sin(points[:, 1] / 10)
        return restored

    errors = []
    for grid_size in (25, 49):
        result = _sample_coordinate_map(
            reference_rgb=image,
            moving_rgb=image,
            map_moving_to_reference=forward,
            map_reference_to_moving=inverse,
            provenance="curved-transform-test",
            grid_size=grid_size,
        )
        source = np.asarray([np.mean(cell["moving"], axis=0) for cell in result.triangles])
        interpolated = np.asarray([np.mean(cell["reference"], axis=0) for cell in result.triangles])
        errors.append(
            float(np.percentile(np.linalg.norm(forward(source) - interpolated, axis=1), 95))
        )
    assert errors[1] < errors[0] * 0.6
    assert errors[1] < 0.3


@pytest.mark.parametrize("retry_succeeds", [False, True])
def test_valis_retries_only_missing_evidence_with_input_blur(monkeypatch, tmp_path, retry_succeeds):
    calls = []
    image = Image.fromarray(_tissue())
    original = image.tobytes()
    slide = SimpleNamespace(warp_xy_from_to=lambda points, target: points)

    def create(source, output, **kwargs):
        with Image.open(Path(source) / "01-moving.png") as prepared:
            calls.append(prepared.tobytes())
        evidence = (
            SimpleNamespace(to_dict=lambda **kwargs: [])
            if retry_succeeds and len(calls) == 2
            else None
        )
        return SimpleNamespace(
            rigid_reg_kwargs={
                "matcher": SimpleNamespace(
                    feature_detector=SimpleNamespace(detect_and_compute=lambda image: None)
                )
            },
            register=lambda: (None, None, evidence),
            get_slide=lambda name: slide,
        )

    original_import = alignment_engines.importlib.import_module
    monkeypatch.setattr(ValisEngine, "available", lambda self: (True, None))
    monkeypatch.setattr(
        alignment_engines.importlib,
        "import_module",
        lambda name: (
            SimpleNamespace(Valis=create) if name == "valis.registration" else original_import(name)
        ),
    )
    inputs = EngineInput(image, image, image.size, image.size, tmp_path)
    progress = []
    if retry_succeeds:
        run = ValisEngine().register(inputs, progress.append)
        assert run.registration["status"] == "approximate"
        assert run.registration["evidence"]["valisInitialFailure"] == "missing-validation-evidence"
        assert run.registration["evidence"]["valisInputBlurRadius"] == 0.6
        assert run.artifact_sha256 == alignment_engines._hash_file(run.artifact_path)
        assert json.loads(run.artifact_path.read_text()) == run.registration
        assert run.runtime_seconds > 0
    else:
        with pytest.raises(AlignmentRejected, match="validation evidence"):
            ValisEngine().register(inputs, progress.append)
    assert len(calls) == 2
    assert calls[0] == original and calls[1] != original
    assert image.tobytes() == original and inputs.settings is None
    assert any(event["stage"] == "valis-input-blur-fallback" for event in progress)
