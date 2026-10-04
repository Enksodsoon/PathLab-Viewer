import pytest
from wsi_viewer.alignment_evaluation import evaluate_landmarks


def _record(error: float = 0, **overrides):
    return {
        "eligible": True,
        "movingPoint": [100, 100],
        "referencePoint": [110 + error, 120],
        "referenceMicronsPerPixel": [1, 2],
        "wrongStructure": False,
        "registration": {
            "status": "ready",
            "triangles": [
                {
                    "moving": [[0, 0], [1000, 0], [0, 1000]],
                    "reference": [[10, 20], [1010, 20], [10, 1020]],
                }
            ],
        },
        **overrides,
    }


def test_landmark_evaluation_reports_accuracy_coverage_and_acceptance():
    report = evaluate_landmarks(
        [
            _record(20),
            _record(40),
            _record(80),
            _record(movingPoint=[900, 900]),
            _record(eligible=False),
        ]
    )
    assert report["eligibleLandmarks"] == 4
    assert report["evaluatedLandmarks"] == 3
    assert report["coverage"] == 0.75
    assert report["medianErrorUm"] == 40
    assert report["p95ErrorUm"] == 76
    assert report["unsupportedLandmarks"] == 1
    assert report["qualified"] is False


def test_anisotropic_calibration_and_actual_map_override_preentered_error():
    report = evaluate_landmarks([_record(referencePoint=[113, 124], errorUm=0)])
    assert report["medianErrorUm"] == pytest.approx((3**2 + 8**2) ** 0.5)
    assert report["qualified"] is True


def test_confident_wrong_structure_match_blocks_acceptance():
    report = evaluate_landmarks([_record(10), _record(20, wrongStructure=True)])
    assert report["wrongStructureMatches"] == 1
    assert report["qualified"] is False


@pytest.mark.parametrize("review", [None, 0, "false", "missing"])
def test_missing_or_non_boolean_wrong_structure_review_blocks_acceptance(review):
    record = _record(wrongStructure=review)
    if review == "missing":
        del record["wrongStructure"]
    report = evaluate_landmarks([record])
    assert report["invalidLandmarks"] == 1
    assert report["evaluatedLandmarks"] == 0
    assert report["qualified"] is False


def test_preentered_errors_and_invalid_calibration_cannot_qualify():
    report = evaluate_landmarks(
        [{"eligible": True, "errorUm": 0}, _record(referenceMicronsPerPixel=[float("nan"), 1])]
    )
    assert report["invalidLandmarks"] == 2
    assert report["evaluatedLandmarks"] == 0
    assert report["qualified"] is False


def test_approximate_outline_is_not_counted_as_anatomical_coverage():
    report = evaluate_landmarks(
        [
            _record(
                registration={
                    "status": "approximate",
                    "movingToReference": [[1, 0, 10], [0, 1, 20]],
                }
            )
        ]
    )
    assert report["unsupportedLandmarks"] == 1
    assert report["qualified"] is False


def test_approximate_map_measured_without_promoting_status():
    record = _record(
        registration={
            "status": "approximate",
            "overviewTriangles": [
                {
                    "moving": [[0, 0], [1000, 0], [0, 1000]],
                    "reference": [[10, 20], [1010, 20], [10, 1020]],
                }
            ],
        }
    )
    report = evaluate_landmarks([record], measure_approximate=True)
    assert report["medianErrorUm"] == 0
    assert report["observedLandmarks"] == 1
    assert report["approximateLandmarks"] == 1
    assert report["qualified"] is False
    assert record["registration"]["status"] == "approximate"


def test_uncalibrated_relative_observations_have_separate_denominator():
    record = _record(referenceSize=[1000, 1000])
    del record["referenceMicronsPerPixel"]
    report = evaluate_landmarks([record, _record()], measure_approximate=True)
    assert report["relativeLandmarks"] == 1
    assert report["medianRelativeError"] == 0
    assert report["calibratedCoverage"] == 0.5
    assert report["qualified"] is False


def test_approximate_observations_cannot_hide_ready_map_error_gate():
    records = [_record(60) for _ in range(45)] + [_record(0) for _ in range(35)]
    approximate = _record(0)
    approximate["registration"]["status"] = "approximate"
    approximate["registration"]["overviewTriangles"] = approximate["registration"].pop("triangles")
    records += [approximate] * 20
    result = evaluate_landmarks(records, measure_approximate=True)
    assert result["medianErrorUm"] == 0
    assert result["coverage"] == 0.8
    assert result["qualified"] is False


def _tiered_registration():
    return {
        "status": "ready",
        "sourceVersion": "moving-bytes",
        "anchorVersion": "reference-bytes",
        "anchorSlideId": "reference",
        "triangles": [{"moving": [[0, 0], [2, 0], [0, 2]], "reference": [[5, 7], [7, 7], [5, 9]]}],
        "overviewTriangles": [
            {"moving": [[0, 0], [40, 0], [0, 40]], "reference": [[5, 7], [45, 7], [5, 47]]}
        ],
    }


def test_ready_local_miss_uses_own_overview_per_point_without_ready_relabel():
    registration = _tiered_registration()
    report = evaluate_landmarks(
        [
            _record(movingPoint=[0.5, 0.5], referencePoint=[5.5, 7.5], registration=registration),
            _record(movingPoint=[10, 10], referencePoint=[15, 17], registration=registration),
        ],
        measure_approximate=True,
    )
    assert report["observedLandmarks"] == 2
    assert report["coverage"] == 0.5
    assert report["approximateLandmarks"] == 1
    assert report["supportTierCounts"] == {"ready-local": 1, "own-overview": 1}
    assert report["qualified"] is False
    assert registration["status"] == "ready"


def test_local_support_has_priority_over_disagreeing_overview():
    registration = _tiered_registration()
    registration["overviewTriangles"][0]["reference"] = [[100, 100], [140, 100], [100, 140]]
    report = evaluate_landmarks(
        [_record(movingPoint=[0.5, 0.5], referencePoint=[5.5, 7.5], registration=registration)],
        measure_approximate=True,
    )
    assert report["medianErrorUm"] == 0
    assert report["supportTierCounts"] == {"ready-local": 1}


def test_bound_native_overview_fallback_is_scored_after_own_cell_miss():
    registration = _tiered_registration()
    fallback = {**registration, "status": "approximate", "triangles": []}
    registration["overviewTriangles"] = []
    registration["overviewFallback"] = fallback
    report = evaluate_landmarks(
        [_record(movingPoint=[10, 10], referencePoint=[15, 17], registration=registration)],
        measure_approximate=True,
    )
    assert report["observedLandmarks"] == 1
    assert report["approximateLandmarks"] == 1
    assert report["coverage"] == 0
    assert report["supportTierCounts"] == {"overview-fallback": 1}
    assert report["qualified"] is False


def test_strict_evaluation_refuses_own_overview_and_bound_fallback():
    registration = _tiered_registration()
    registration["overviewFallback"] = {**registration, "status": "approximate"}
    report = evaluate_landmarks(
        [_record(movingPoint=[10, 10], referencePoint=[15, 17], registration=registration)]
    )
    assert report["observedLandmarks"] == 0
    assert report["unsupportedLandmarks"] == 1
    assert report["supportTierCounts"] == {}


@pytest.mark.parametrize("mismatch", ["sourceVersion", "anchorVersion", "anchorSlideId"])
def test_fallback_with_different_source_binding_is_not_scored(mismatch):
    registration = _tiered_registration()
    fallback = {**registration, "status": "approximate", mismatch: "other"}
    registration["overviewTriangles"] = []
    registration["overviewFallback"] = fallback
    report = evaluate_landmarks(
        [_record(movingPoint=[10, 10], referencePoint=[15, 17], registration=registration)],
        measure_approximate=True,
    )
    assert report["observedLandmarks"] == 0
    assert report["qualified"] is False


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nonfinite_cell_cannot_produce_an_observed_landmark(bad):
    registration = _tiered_registration()
    registration["triangles"][0]["moving"][1][0] = bad
    registration["overviewTriangles"] = []
    report = evaluate_landmarks(
        [_record(movingPoint=[0.5, 0.5], referencePoint=[5.5, 7.5], registration=registration)],
        measure_approximate=True,
    )
    assert report["observedLandmarks"] == 0
    assert report["qualified"] is False


def test_reflected_cell_is_not_usable_navigation_evidence():
    registration = _tiered_registration()
    registration["triangles"][0]["reference"] = [[5, 7], [3, 7], [5, 9]]
    registration["overviewTriangles"] = []
    report = evaluate_landmarks(
        [_record(movingPoint=[0.5, 0.5], referencePoint=[4.5, 7.5], registration=registration)],
        measure_approximate=True,
    )
    assert report["observedLandmarks"] == 0
    assert report["qualified"] is False


def test_fallback_coordinate_reference_identity_must_agree():
    registration = _tiered_registration()
    registration["coordinateReferenceId"] = "reference-frame"
    fallback = {**registration, "status": "approximate", "coordinateReferenceId": "other-frame"}
    registration["overviewTriangles"] = []
    registration["overviewFallback"] = fallback
    report = evaluate_landmarks(
        [_record(movingPoint=[10, 10], referencePoint=[15, 17], registration=registration)],
        measure_approximate=True,
    )
    assert report["observedLandmarks"] == 0


def test_affine_only_map_never_extrapolates_landmark_support():
    registration = {"status": "ready", "movingToReference": [[1, 0, 10], [0, 1, 20]]}
    report = evaluate_landmarks([_record(registration=registration)], measure_approximate=True)
    assert report["observedLandmarks"] == 0
