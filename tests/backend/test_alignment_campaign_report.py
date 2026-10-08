"""Reporting-only safety regressions; run after the frozen compute phase."""

import importlib.util
import json
import os
from pathlib import Path

import pytest


@pytest.fixture
def campaign_report():
    path = Path(__file__).resolve().parents[2] / "scripts/report_alignment_campaign.py"
    spec = importlib.util.spec_from_file_location("alignment_campaign_report", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _reviewed_screening():
    rows = [
        {
            "recipe": "native-overview-v6",
            "kind": "positive" if index < 12 else "negative",
            "outcome": "rejected",
            "failureCategory": "structural-or-correspondence-rejection",
            "repeatComputeReceipts": [
                {"failureCategory": "structural-or-correspondence-rejection"}
            ],
        }
        for index in range(16)
    ]
    report = {
        "screening": True,
        "recipes": {
            "native-overview-v6": {
                "eligibleLandmarks": 947,
                "missingNegativeReviews": 0,
                "confidentWrongStructurePairs": 0,
                "observedCoverage": 0,
                "p95RelativeError": None,
                "coldRuntimeP95Seconds": 2,
            }
        },
    }
    return report, rows


def test_screening_requires_every_planned_negative_fresh_repeat(campaign_report):
    report, rows = _reviewed_screening()
    assert campaign_report.select(report, rows)[0] == ["native-overview-v6"]
    rows[12]["repeatComputeReceipts"] = []
    selected, decisions = campaign_report.select(report, rows)
    assert selected == []
    assert (
        "missing-planned-negative-repeat-receipt"
        in decisions["native-overview-v6"]["exclusionReasons"]
    )


def test_unscored_development_cold_only_does_not_apply_screening_selector(campaign_report):
    report, rows = _reviewed_screening()
    report["screening"] = False
    for row in rows:
        row["repeatComputeReceipts"] = []
    assert campaign_report.select(report, rows) == ([], {})


def test_repeat_acceptance_is_unknown_safety_without_persisted_map_review(campaign_report):
    report, rows = _reviewed_screening()
    rows[12]["repeatComputeReceipts"][0]["failureCategory"] = "accepted-map"
    selected, decisions = campaign_report.select(report, rows)
    assert selected == []
    assert (
        "repeat-negative-map-review-unavailable"
        in decisions["native-overview-v6"]["exclusionReasons"]
    )


def test_negative_image_ceiling_failure_is_unresolved_not_safe_rejection(campaign_report):
    report, rows = _reviewed_screening()
    rows[13]["failureCategory"] = "bounded-image-ceiling"
    selected, decisions = campaign_report.select(report, rows)
    assert selected == []
    assert (
        "unresolved-negative-resource-or-runtime-failure"
        in decisions["native-overview-v6"]["exclusionReasons"]
    )


def test_windows_upstream_cleanup_lock_is_runtime_failure(campaign_report, tmp_path):
    digest = "e" * 64
    (tmp_path / "diagnostics").mkdir()
    (tmp_path / "diagnostics" / f"{digest}.json").write_text(
        json.dumps(
            {
                "exceptionType": "AlignmentRejected",
                "message": (
                    "[WinError 32] The process cannot access the file because it is being used "
                    "by another process: private-elastix-log"
                ),
            }
        )
    )
    assert campaign_report.classify(tmp_path, digest, "rejected") == "upstream-or-runtime-failure"


def test_public_winner_is_suppressed_when_reviewed_safety_is_ineligible(
    campaign_report, tmp_path, monkeypatch
):
    report = {
        "screening": True,
        "rows": [],
        "recipes": {"native-overview-v6": {"benchmarkQualified": True}},
        "winners": {"fast": "native-overview-v6", "accurate": None},
        "qualificationGates": {},
    }

    monkeypatch.setattr(
        campaign_report,
        "select",
        lambda *_: (
            [],
            {
                "native-overview-v6": {
                    "eligibleForUnqualifiedExpansion": False,
                    "exclusionReasons": ["repeat-negative-map-review-unavailable"],
                }
            },
        ),
    )
    result = campaign_report.summarize(report, tmp_path)
    assert result["winners"] == {"fast": None, "accurate": None}
    metrics = result["recipes"]["native-overview-v6"]
    assert metrics["benchmarkQualified"] is True  # Original cold gate evidence retained.
    assert metrics["reviewedSafetyEligible"] is False
    assert metrics["reviewedBenchmarkQualified"] is False
    assert result["winnerReview"]["fast"] == {
        "originalBenchmarkWinner": "native-overview-v6",
        "reportedWinner": None,
        "suppressed": True,
        "suppressionReasons": ["repeat-negative-map-review-unavailable"],
        "scope": "reviewed-negative-cold-and-fresh-repeat-safety-policy",
    }


def test_public_resources_preserve_distinct_job_rss_and_committed_peaks(campaign_report, tmp_path):
    digest = "a" * 64
    (tmp_path / "cache").mkdir()
    resources = {
        "peakMemoryBytes": 200,
        "peakCommittedMemoryBytes": 900,
        "committedMemoryLimitBytes": 800,
        "memoryMeasurementScope": "windows-job-sampled-working-set",
        "processContainment": "windows-job-object",
        "privatePath": "private-original",
    }
    (tmp_path / "cache" / f"{digest}.json").write_text(
        json.dumps(
            {
                "registration": {},
                "resourceMetrics": resources,
                "effectiveSettingsDigest": "e" * 64,
                "settingsDigest": "r" * 64,
            }
        )
    )
    report = {
        "screening": False,
        "rows": [
            {
                "digest": digest,
                "recipe": "native-overview-v6",
                "pairIndex": 0,
                "kind": "positive",
                "outcome": "rejected",
                "coldRuntimeSeconds": 1,
                "peakMemoryBytes": 200,
                "resourceMetrics": resources,
            }
        ],
        "recipes": {"native-overview-v6": {}},
        "winners": {"fast": None, "accurate": None},
        "qualificationGates": {},
    }
    result = campaign_report.summarize(report, tmp_path, memory_scope="unrecorded")
    row = result["rows"][0]
    assert row["peakMemoryMeasurementScope"] == "windows-job-sampled-working-set"
    assert row["resourceMetrics"]["peakCommittedMemoryBytes"] == 900
    assert row["effectiveSettingsDigest"] == "e" * 64
    assert result["recipes"]["native-overview-v6"]["peakCommittedMemoryP95Bytes"] == 900
    assert "private-original" not in json.dumps(result)


def _initializer_path(tmp_path, module):
    path = tmp_path / "artifacts" / ("a" * 64) / module.INITIALIZER_ARTIFACT_NAME
    path.parent.mkdir(parents=True)
    return path


def test_initializer_size_is_checked_before_reading(campaign_report, tmp_path, monkeypatch):
    path = _initializer_path(tmp_path, campaign_report)
    path.write_bytes(b"x" * 65)
    monkeypatch.setattr(campaign_report, "MAX_INITIALIZER_ARTIFACT_BYTES", 64)
    original_open = Path.open

    def guarded_open(candidate, *args, **kwargs):
        assert candidate != path, "oversized initializer must not be opened"
        return original_open(candidate, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    with pytest.raises(ValueError, match="size ceiling|exceeds ceiling"):
        campaign_report.stage_metrics(
            tmp_path, {"recipe": "native-wsireg", "digest": "a" * 64}, {}, {}
        )


def test_initializer_read_stays_bounded_if_file_grows_after_stat(
    campaign_report, tmp_path, monkeypatch
):
    path = _initializer_path(tmp_path, campaign_report)
    path.write_bytes(b"x" * 65)
    monkeypatch.setattr(campaign_report, "MAX_INITIALIZER_ARTIFACT_BYTES", 64)
    original_stat = Path.stat

    def smaller_stat(candidate, *args, **kwargs):
        value = original_stat(candidate, *args, **kwargs)
        if candidate == path:
            fields = list(value)
            fields[6] = 0
            return os.stat_result(fields)
        return value

    monkeypatch.setattr(Path, "stat", smaller_stat)
    with pytest.raises(ValueError, match="exceeds ceiling"):
        campaign_report.stage_metrics(
            tmp_path, {"recipe": "native-wsireg", "digest": "a" * 64}, {}, {}
        )


def test_initializer_symlink_is_rejected_before_loading(campaign_report, tmp_path, monkeypatch):
    path = _initializer_path(tmp_path, campaign_report)
    path.write_text(json.dumps({"status": "approximate"}))
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda candidate: candidate == path or original(candidate)
    )
    with pytest.raises(ValueError, match="symlinks"):
        campaign_report.stage_metrics(
            tmp_path, {"recipe": "native-wsireg", "digest": "a" * 64}, {}, {}
        )


def test_public_stage_omits_origins_and_nested_private_geometry(campaign_report):
    stage = {
        "engine": "native-overview-v6",
        "engineVersion": "bounded-overview",
        "settingsDigest": "a" * 64,
        "runtimeSeconds": 1.5,
        "referenceMicronsPerPixel": [0.25, 0.5],
        "movingScale": [8, 8],
        "cropOrigin": {"reference": [120, 300], "moving": [100, 400]},
        "samplingFrames": {"moving": {"cropOrigin": [100, 400]}},
        "referenceScale": {"cropOrigin": [120, 300], "source": "private.svs"},
        "engineSettings": {"landmarks": [[1, 2], [3, 4]]},
    }
    assert campaign_report.public_stage(stage) == {
        "engine": "native-overview-v6",
        "engineVersion": "bounded-overview",
        "settingsDigest": "a" * 64,
        "runtimeSeconds": 1.5,
        "referenceMicronsPerPixel": [0.25, 0.5],
        "movingScale": [8, 8],
    }


def _hybrid_comparison_report(module, hybrid_metrics, first_metrics, second_metrics):
    stages = module.RECIPE_STAGES["native-valis"]
    return {
        "rows": [
            {
                "pairIndex": 3,
                "kind": "positive",
                "recipe": recipe,
                "digest": str(index) * 64,
                "coldRuntimeSeconds": runtime,
                "landmarkMetrics": {"eligibleLandmarks": 80, **metrics},
            }
            for index, (recipe, runtime, metrics) in enumerate(
                [
                    (stages[0], 2, first_metrics),
                    (stages[1], 200, second_metrics),
                    ("native-valis", 218, hybrid_metrics),
                ]
            )
        ]
    }


def test_hybrid_coverage_priority_improvement_labels_error_tradeoff(campaign_report):
    report = _hybrid_comparison_report(
        campaign_report,
        {"observedCoverage": 22 / 80, "medianRelativeError": 0.005, "p95RelativeError": 0.0074},
        {"observedCoverage": 9 / 80, "medianRelativeError": 0.001, "p95RelativeError": 0.0033},
        {"observedCoverage": 21 / 80, "medianRelativeError": 0.004, "p95RelativeError": 0.0064},
    )
    result = campaign_report.hybrid_comparisons(report)[0]
    assert "improvesOnIndividualOutputs" not in result
    assert result["coveragePriorityRankingImprovesOnAllIndividualOutputs"] is True
    assert result["qualificationEvidence"] is False
    for comparison in result["perIndividualComparisons"]:
        assert comparison["classification"] == "coverage-gain-error-tradeoff"
        assert comparison["coverageGain"] > 0
        assert comparison["medianErrorChange"] > 0
        assert comparison["p95ErrorChange"] > 0
        assert comparison["supervisedWallTimeChangeSeconds"] > 0
        assert comparison["accuracyParetoDominates"] is False
        assert comparison["operationalParetoDominates"] is False


def test_hybrid_accuracy_dominance_does_not_imply_runtime_dominance(campaign_report):
    report = _hybrid_comparison_report(
        campaign_report,
        {"observedCoverage": 0.5, "medianRelativeError": 0.001, "p95RelativeError": 0.003},
        {"observedCoverage": 0.3, "medianRelativeError": 0.002, "p95RelativeError": 0.005},
        {"observedCoverage": 0.4, "medianRelativeError": 0.003, "p95RelativeError": 0.006},
    )
    result = campaign_report.hybrid_comparisons(report)[0]
    assert all(
        item["accuracyParetoDominates"] is True for item in result["perIndividualComparisons"]
    )
    assert all(
        item["operationalParetoDominates"] is False for item in result["perIndividualComparisons"]
    )


def test_hybrid_missing_error_observation_is_never_pareto_evidence(campaign_report):
    report = _hybrid_comparison_report(
        campaign_report,
        {"observedCoverage": 0.5, "medianRelativeError": 0.001, "p95RelativeError": 0.003},
        {"observedCoverage": 0, "medianRelativeError": None, "p95RelativeError": None},
        {"observedCoverage": 0.4, "medianRelativeError": 0.003, "p95RelativeError": 0.006},
    )
    comparison = campaign_report.hybrid_comparisons(report)[0]["perIndividualComparisons"][0]
    assert comparison["coveragePriorityRankingImproves"] is True
    assert comparison["classification"] == "error-change-unmeasured"
    assert comparison["accuracyParetoDominates"] is None
    assert comparison["operationalParetoDominates"] is None


def _accepted_negative_review_fixture(tmp_path):
    digest = "a" * 64
    manifest_sha = "b" * 64
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / f"{digest}.json").write_text(
        json.dumps({"registration": {"confidence": 0.49, "status": "approximate"}})
    )
    review = {
        "pairIndex": 12,
        "recipe": "wsireg-0.3.10",
        "registrationDigest": digest,
        "attempt": "cold",
        "wrongStructure": True,
        "reviewerConfirmed": True,
        "independentActualMapReviewConfirmed": True,
    }
    review_path = tmp_path / "independent-negative-map-reviews.json"
    review_path.write_text(json.dumps({"sourceManifestSha256": manifest_sha, "reviews": [review]}))
    report = {
        "screening": True,
        "recipes": {"wsireg-0.3.10": {"confidentWrongStructurePairs": 0}},
        "winners": {"fast": None, "accurate": None},
        "qualificationGates": {},
        "rows": [
            {
                "pairIndex": 12,
                "recipe": "wsireg-0.3.10",
                "digest": digest,
                "kind": "negative",
                "outcome": "ok",
                "coldRuntimeSeconds": 31.125,
                "repeatComputeReceipts": [{"outcome": "ok", "runtimeSeconds": 31.14}],
            }
        ],
    }
    return report, manifest_sha, review_path, review


def test_low_confidence_reviewed_wrong_structure_map_is_reported(campaign_report, tmp_path):
    report, manifest_sha, _, _ = _accepted_negative_review_fixture(tmp_path)
    result = campaign_report.summarize(report, tmp_path, manifest_sha256=manifest_sha)
    metrics = result["recipes"]["wsireg-0.3.10"]
    assert metrics["confidentWrongStructurePairs"] == 0
    assert metrics["reviewedWrongStructurePairs"] == 1
    assert metrics["acceptedRepeatMapSafetyUnknownCount"] == 1
    assert metrics["acceptedNegativeColdMapsWithoutConfirmedReview"] == 0
    assert result["rows"][0]["wrongStructure"] is True
    assert result["rows"][0]["reviewerConfirmed"] is True
    assert result["rows"][0]["confidence"] == 0.49
    assert result["finalists"] == []


def test_stale_review_digest_does_not_confirm_a_new_map(campaign_report, tmp_path):
    report, manifest_sha, review_path, review = _accepted_negative_review_fixture(tmp_path)
    review["registrationDigest"] = "c" * 64
    review_path.write_text(json.dumps({"sourceManifestSha256": manifest_sha, "reviews": [review]}))
    result = campaign_report.summarize(report, tmp_path, manifest_sha256=manifest_sha)
    assert result["recipes"]["wsireg-0.3.10"]["reviewedWrongStructurePairs"] == 0
    assert result["recipes"]["wsireg-0.3.10"]["acceptedNegativeColdMapsWithoutConfirmedReview"] == 1
    assert result["rows"][0]["wrongStructure"] is None
    assert result["rows"][0]["reviewerConfirmed"] is False


def test_review_source_manifest_binding_is_required(campaign_report, tmp_path):
    report, _, _, _ = _accepted_negative_review_fixture(tmp_path)
    with pytest.raises(ValueError, match="matching frozen source manifest"):
        campaign_report.summarize(report, tmp_path)
    with pytest.raises(ValueError, match="matching frozen source manifest"):
        campaign_report.summarize(report, tmp_path, manifest_sha256="d" * 64)


def test_initializer_digest_cannot_traverse_outside_private_artifacts(campaign_report, tmp_path):
    with pytest.raises(ValueError, match="SHA256 basename"):
        campaign_report.stage_metrics(
            tmp_path, {"recipe": "native-wsireg", "digest": "../../originals"}, {}, {}
        )


def test_positive_visual_uncertainty_is_not_reported_as_zero_wrong_structure(
    campaign_report, tmp_path
):
    report, manifest_sha, review_path, review = _accepted_negative_review_fixture(tmp_path)
    review_path.unlink()
    report["recipes"] = {"deeperhistreg-classical": {}}
    report["rows"][0].update(
        kind="positive", pairIndex=10, recipe="deeperhistreg-classical", wrongStructure=False
    )
    review.update(
        pairIndex=10,
        recipe="deeperhistreg-classical",
        wrongStructure=None,
        anatomicalCorrespondenceConfirmed=False,
        reviewStatus="uncertain / visualization insufficient",
    )
    (tmp_path / "independent-positive-map-reviews.json").write_text(
        json.dumps({"sourceManifestSha256": manifest_sha, "reviews": [review]})
    )
    result = campaign_report.summarize(report, tmp_path, manifest_sha256=manifest_sha)
    row = result["rows"][0]
    assert row["reviewStatus"] == "uncertain / visualization insufficient"
    assert row["reviewerConfirmed"] is True
    assert row["wrongStructure"] is None
    assert row["anatomicalCorrespondenceConfirmed"] is False


def _supported_map(source_cells, translation):
    return {
        "status": "approximate",
        "overviewTriangles": [
            {"moving": cell, "reference": [[x + translation, y] for x, y in cell]}
            for cell in source_cells
        ],
    }


def _paired_landmarks(calibration=None):
    return [
        {
            "eligible": True,
            "wrongStructure": False,
            "movingPoint": point,
            "referencePoint": point,
            "referenceSize": [100, 100],
            **({"referenceMicronsPerPixel": calibration} if calibration is not None else {}),
        }
        for point in [[1, 1], [2, 2], [6, 1], [20, 20]]
    ]


@pytest.mark.parametrize(
    "calibration,unit,error_scale",
    [(None, "reference-image-diagonal", 1 / (20000**0.5)), ([0.5, 1], "um", 0.5)],
)
def test_paired_errors_use_only_identical_common_supported_landmarks(
    campaign_report, calibration, unit, error_scale
):
    left = _supported_map([[[0, 0], [10, 0], [0, 10]]], 1)
    right = _supported_map([[[0, 0], [5, 0], [0, 5]], [[19, 19], [22, 19], [19, 22]]], 3)
    result = campaign_report.paired_landmark_comparison(left, right, _paired_landmarks(calibration))
    assert result["commonSupportedLandmarks"] == 2
    assert result["onlyLeftSupportedLandmarks"] == 1
    assert result["onlyRightSupportedLandmarks"] == 1
    values = result["errorsByUnit"][unit]
    assert values["medianPairedErrorDelta"] == pytest.approx(-2 * error_scale)
    assert values["leftP95ErrorOnCommonSet"] == pytest.approx(error_scale)
    assert values["rightP95ErrorOnCommonSet"] == pytest.approx(3 * error_scale)
    assert values["p95ErrorDeltaOnCommonSet"] == pytest.approx(-2 * error_scale)
    assert result["qualificationEvidence"] is False
    assert result["fitPerformed"] is False
    assert "Point" not in json.dumps(result)
    assert "publishedLandmarkOrdinal" not in json.dumps(result)


def test_no_common_support_keeps_paired_error_measurements_null(campaign_report):
    left = _supported_map([[[0, 0], [10, 0], [0, 10]]], 1)
    right = _supported_map([[[19, 19], [22, 19], [19, 22]]], 3)
    result = campaign_report.paired_landmark_comparison(left, right, _paired_landmarks())
    assert result["commonSupportedLandmarks"] == 0
    values = result["errorsByUnit"]["reference-image-diagonal"]
    assert values["medianPairedErrorDelta"] is None
    assert values["leftP95ErrorOnCommonSet"] is None
    assert values["rightP95ErrorOnCommonSet"] is None


def test_common_support_uses_pointwise_local_then_overview(campaign_report):
    left = _supported_map([[[0, 0], [10, 0], [0, 10]]], 1)
    left["status"] = "ready"
    left["triangles"] = _supported_map([[[0, 0], [3, 0], [0, 3]]], 2)["overviewTriangles"]
    right = _supported_map([[[0, 0], [10, 0], [0, 10]]], 3)
    result = campaign_report.paired_landmark_comparison(left, right, _paired_landmarks())
    assert result["commonSupportedLandmarks"] == 3
    assert result["supportMappingPolicy"] == "pointwise-supported-cells/2"
    assert result["supportTierCounts"] == {
        "left": {"ready-local": 1, "own-overview": 2},
        "right": {"own-overview": 3},
    }


def test_missing_map_or_independent_landmarks_is_unmeasured(campaign_report):
    map_value = _supported_map([[[0, 0], [10, 0], [0, 10]]], 1)
    for left, right, records in [
        (None, map_value, _paired_landmarks()),
        (map_value, map_value, []),
    ]:
        result = campaign_report.paired_landmark_comparison(left, right, records)
        assert result["status"] == "unmeasured"
        assert result["commonSupportedLandmarks"] is None
        assert result["errorsByUnit"] is None


def test_preserved_wsireg_upstream_failure_is_unknown_negative_safety(campaign_report, tmp_path):
    (tmp_path / "diagnostics").mkdir()
    digest = "a" * 64
    (tmp_path / "diagnostics" / (digest + ".json")).write_text(
        json.dumps(
            {
                "exceptionType": "AlignmentRejected",
                "message": (
                    "wsireg upstream registration failed (RuntimeError): Internal elastix error"
                ),
            }
        )
    )
    category = campaign_report.classify(tmp_path, digest, "rejected")
    assert category == "upstream-or-runtime-failure"
    assert campaign_report.negative_review_value(category) is None


def test_cache_preparation_public_projection_keeps_only_measured_safe_fields(campaign_report):
    value = {
        "policy": "private/path",
        "performed": True,
        "wallSeconds": 1.25,
        "removedFileCount": 2,
        "removedBytes": 12,
        "sourceKindCounts": {"openslide-original": 1, "/private/source": 99},
        "privatePath": "/secret",
        "coordinates": [1, 2],
    }
    public = campaign_report.public_cache_preparation(value)
    assert public["wallSeconds"] == 1.25 and public["removedBytes"] == 12
    assert public["sourceKindCounts"] == {"openslide-original": 1}
    assert "private" not in json.dumps(public) and "coordinates" not in public
    value["wallSeconds"] = float("nan")
    assert campaign_report.public_cache_preparation(value)["wallSeconds"] is None
