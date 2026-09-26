import pytest
from wsi_viewer.study_pack_contract import score_task


@pytest.mark.parametrize("point", [(0.2, 0.3), (0.59, 0.49), (0.19, 0.29)])
def test_spatial_target_accepts_box_and_tolerance(point: tuple[float, float]) -> None:
    task = {
        "type": "spatial", "targetX": 0.2, "targetY": 0.3,
        "targetWidth": 0.4, "targetHeight": 0.2, "tolerance": 0.02,
    }
    assert score_task(task, {"x": point[0], "y": point[1]})


def test_spatial_target_rejects_points_outside_box_tolerance() -> None:
    task = {
        "type": "spatial", "targetX": 0.2, "targetY": 0.3,
        "targetWidth": 0.4, "targetHeight": 0.2, "tolerance": 0.02,
    }
    assert not score_task(task, {"x": 0.17, "y": 0.3})
