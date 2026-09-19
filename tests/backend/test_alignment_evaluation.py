from wsi_viewer.alignment_evaluation import evaluate_landmarks


def test_landmark_evaluation_reports_accuracy_coverage_and_acceptance() -> None:
    report = evaluate_landmarks(
        [
            {"eligible": True, "errorUm": 20, "wrongStructure": False},
            {"eligible": True, "errorUm": 40, "wrongStructure": False},
            {"eligible": True, "errorUm": 80, "wrongStructure": False},
            {"eligible": True, "errorUm": None, "wrongStructure": False},
            {"eligible": False, "errorUm": None, "wrongStructure": False},
        ]
    )

    assert report["eligibleLandmarks"] == 4
    assert report["evaluatedLandmarks"] == 3
    assert report["coverage"] == 0.75
    assert report["medianErrorUm"] == 40
    assert report["p95ErrorUm"] == 76
    assert report["qualified"] is False


def test_confident_wrong_structure_match_blocks_acceptance() -> None:
    report = evaluate_landmarks(
        [
            {"eligible": True, "errorUm": 10, "wrongStructure": False},
            {"eligible": True, "errorUm": 20, "wrongStructure": True},
        ]
    )

    assert report["wrongStructureMatches"] == 1
    assert report["qualified"] is False

