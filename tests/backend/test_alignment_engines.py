import numpy as np
import pytest
from wsi_viewer.alignment import AlignmentRejected, map_registration_point
from wsi_viewer.alignment_engines import _sample_coordinate_map, engine_availability


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


def test_availability_always_reports_native_and_explains_optional_engines() -> None:
    availability = engine_availability()
    assert availability["native-v12"]["available"] is True
    for engine in ("hisalign-0.2.1", "valis-1.2.0"):
        assert isinstance(availability[engine]["available"], bool)
        if not availability[engine]["available"]:
            assert availability[engine]["reason"]
