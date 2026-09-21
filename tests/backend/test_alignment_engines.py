import numpy as np
import pytest
from wsi_viewer.alignment import AlignmentRejected, map_registration_point
from wsi_viewer.alignment_engines import (
    _mark_approximate_engine_map,
    _sample_coordinate_map,
    _scanner_frame_candidate,
    engine_availability,
    settings_digest,
)


def _tissue() -> np.ndarray:
    image = np.full((240, 320, 3), 255, dtype=np.uint8)
    image[30:210, 40:280] = (175, 90, 130)
    for x in range(60, 270, 30):
        image[60:190:25, x : x + 6] = (30, 20, 70)
    return image


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

    approximate = _mark_approximate_engine_map(
        result, reason="insufficient distributed features"
    )

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


def test_settings_digest_includes_pathlab_adapter_revision() -> None:
    digest = settings_digest("hisalign-0.2.1")

    assert len(digest) == 64
    assert digest != settings_digest("native-v12")
