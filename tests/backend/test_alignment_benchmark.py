import json

import pytest


def _scored_row(kind="positive", *, manual=False):
    return {
        "recipe": "native",
        "kind": kind,
        "outcome": "ok",
        "registration": {
            "status": "ready",
            "triangles": [
                {
                    "moving": [[0, 0], [10, 0], [0, 10]],
                    "reference": [[0, 0], [10, 0], [0, 10]],
                }
            ],
        },
        "landmarks": [
            {
                "eligible": True,
                "movingPoint": [1, 1],
                "referencePoint": [1, 1],
                "referenceMicronsPerPixel": [1, 1],
                "wrongStructure": False,
            }
        ]
        if kind == "positive"
        else [],
        "wrongStructure": False,
        "independentlyReviewed": True,
        "landmarksFitFree": True,
        "manualAssistance": manual,
        "coldRuntimeSeconds": 1,
    }


def test_positive_only_recipe_cannot_advance_to_finalists():
    from wsi_viewer.alignment_benchmark import aggregate_results

    result = aggregate_results([_scored_row()])
    assert result["finalists"] == []


def test_reviewed_all_rejected_recipe_with_ground_truth_can_advance_unqualified():
    from wsi_viewer.alignment_benchmark import aggregate_results

    rows = [_scored_row(), _scored_row("negative")]
    for row in rows:
        row.update(outcome="rejected", registration={})
    result = aggregate_results(rows)
    assert result["finalists"] == ["native"]
    assert result["recipes"]["native"]["observedCoverage"] == 0
    assert result["winners"] == {"fast": None, "accurate": None}
    rows[1].pop("wrongStructure")
    assert aggregate_results(rows)["finalists"] == []


def test_manual_only_positive_retains_automatic_denominator_and_separate_score():
    from wsi_viewer.alignment_benchmark import aggregate_results

    result = aggregate_results([_scored_row(), _scored_row(manual=True), _scored_row("negative")])
    report = result["recipes"]["native"]
    assert report["plannedPairs"] == 3
    assert report["positivePairs"] == 2
    assert report["eligibleLandmarks"] == 2
    assert report["calibratedCoverage"] == 0.5
    assert report["unsupportedLandmarks"] == 1
    assert report["manualAssistance"]["calibratedCoverage"] == 1
    assert report["benchmarkQualified"] is False
    assert report["readyQualified"] is False


def test_manual_effort_aggregates_only_reviewed_assisted_measurements():
    from wsi_viewer.alignment_benchmark import aggregate_results

    measured = _scored_row(manual=True)
    measured["manualCorrectionEffort"] = {
        "pointPairs": 2,
        "elapsedSeconds": 14.5,
        "reviewConfirmed": True,
    }
    missing = _scored_row(manual=True)
    result = aggregate_results([measured, missing, _scored_row(), _scored_row("negative")])
    report = result["recipes"]["native"]
    assert report["eligibleLandmarks"] == 3
    assert report["calibratedCoverage"] == pytest.approx(1 / 3)
    assert report["manualCorrectionEffort"] == {
        "measuredPairs": 1,
        "missingPairs": 1,
        "pointPairsTotal": 2,
        "elapsedSecondsTotal": 14.5,
        "elapsedSecondsMedian": 14.5,
        "elapsedSecondsP95": 14.5,
    }
    unmeasured = aggregate_results([missing])["recipes"]["native"]["manualCorrectionEffort"]
    assert unmeasured["measuredPairs"] == 0
    assert unmeasured["missingPairs"] == 1
    assert unmeasured["pointPairsTotal"] is None
    assert unmeasured["elapsedSecondsTotal"] is None
    automatic = aggregate_results([_scored_row()])["recipes"]["native"]["manualCorrectionEffort"]
    assert automatic["measuredPairs"] == automatic["missingPairs"] == 0
    assert automatic["elapsedSecondsTotal"] is None


def test_manual_effort_sanitizer_drops_freeform_private_details():
    from wsi_viewer.alignment_benchmark import _manual_effort

    assert _manual_effort(
        {
            "pointPairs": 1,
            "elapsedSeconds": 0,
            "reviewConfirmed": True,
            "privateReviewerName": "private identity",
        }
    ) == {
        "pointPairs": 1,
        "elapsedSeconds": 0.0,
        "reviewConfirmed": True,
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("pointPairs", 0),
        ("pointPairs", 4),
        ("pointPairs", True),
        ("elapsedSeconds", -1),
        ("elapsedSeconds", float("nan")),
        ("elapsedSeconds", float("inf")),
        ("elapsedSeconds", True),
        ("reviewConfirmed", False),
    ],
)
def test_manifest_rejects_invalid_manual_effort(tmp_path, field, value):
    from wsi_viewer.alignment_benchmark import validate_manifest

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
    effort = {"pointPairs": 1, "elapsedSeconds": 0, "reviewConfirmed": True, field: value}
    pair = {
        "kind": "positive",
        "landmarks": [],
        "manualAssistance": True,
        "manualCorrectionEffort": effort,
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
    }
    with pytest.raises(ValueError, match="manual correction effort"):
        validate_manifest({"pairs": [pair]})


def test_pair_settings_and_calibration_reach_child_and_invalidate_digest(tmp_path, monkeypatch):
    from wsi_viewer import alignment_benchmark as bench

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"pixels")
    pair = {
        "kind": "positive",
        "landmarks": [],
        "reference": {
            "path": str(tmp_path / "reference"),
            "size": [10, 10],
            "micronsPerPixel": [0.25, 0.5],
        },
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10], "micronsPerPixel": [0.5, 1]},
        "settings": {"native": {"iterations": 2}},
    }
    original = bench.pair_digest(pair, "native", {})
    pair["moving"]["tissueCrop"] = True
    crop_digest = bench.pair_digest(pair, "native", {})
    assert crop_digest != original
    original = crop_digest
    calls = []
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"native-overview-v6": {"available": True}}
    )
    monkeypatch.setattr(
        bench,
        "_run_alignment_bounded",
        lambda *_a, **kw: calls.append(kw["engine_settings"]) or {"status": "rejected"},
    )
    bench.run_benchmark(
        {"pairs": [pair], "settings": {"native": {"iterations": 1, "globalOption": True}}},
        tmp_path / "out",
        ["native"],
    )
    assert calls[0]["iterations"] == 2
    assert calls[0]["globalOption"] is True
    assert calls[0]["referenceMicronsPerPixel"] == [0.25, 0.5]
    assert calls[0]["movingMicronsPerPixel"] == [0.5, 1]
    assert calls[0]["movingCropped"] is True
    pair["moving"]["micronsPerPixel"] = [0.75, 1]
    assert bench.pair_digest(pair, "native", {}) != original
    changed = bench.pair_digest(pair, "native", {})
    pair["settings"]["native"]["iterations"] = 3
    assert bench.pair_digest(pair, "native", {}) != changed
    pair["reference"]["micronsPerPixel"] = [0, 1]
    with pytest.raises(ValueError, match="calibration"):
        bench.pair_digest(pair, "native", {})


def test_rejection_diagnostic_is_private_and_report_remains_sanitized(tmp_path, monkeypatch):
    from wsi_viewer import alignment_benchmark as bench
    from wsi_viewer.alignment import AlignmentRejected

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"pixels")
    pair = {
        "kind": "positive",
        "landmarks": [],
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
    }
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"native-overview-v6": {"available": True}}
    )

    def fail(*_a, **_kw):
        raise AlignmentRejected(f"upstream registration failed on {tmp_path}")

    monkeypatch.setattr(bench, "_run_alignment_bounded", fail)
    result = bench.run_benchmark({"pairs": [pair]}, tmp_path / "out", ["native"])
    assert str(tmp_path) not in json.dumps(result)
    key = result["rows"][0]["digest"]
    diagnostic = json.loads((tmp_path / "out" / "diagnostics" / f"{key}.json").read_text())
    assert diagnostic["exceptionType"] == "AlignmentRejected"
    assert str(tmp_path) in diagnostic["message"]


def test_manifest_screening_requires_frozen_positive_negative_counts(tmp_path):
    from wsi_viewer.alignment_benchmark import validate_manifest

    with pytest.raises(ValueError, match="12 positive.*4 negative"):
        validate_manifest({"pairs": []}, screening=True)


def test_cache_digest_changes_for_actual_input_bytes_and_settings(tmp_path):
    from wsi_viewer.alignment_benchmark import pair_digest

    first = tmp_path / "a"
    first.mkdir()
    (first / "thumbnail.jpg").write_bytes(b"a")
    second = tmp_path / "b"
    second.mkdir()
    (second / "thumbnail.jpg").write_bytes(b"b")
    pair = {
        "reference": {"path": str(first), "size": [10, 10]},
        "moving": {"path": str(second), "size": [10, 10]},
        "kind": "positive",
        "landmarks": [],
    }
    initial = pair_digest(pair, "native", {})
    assert pair_digest(pair, "native", {"iterations": 2}) != initial
    (second / "thumbnail.jpg").write_bytes(b"c")
    assert pair_digest(pair, "native", {}) != initial


def test_failed_pairs_keep_landmark_denominator_and_no_compute_only_fast_winner():
    from wsi_viewer.alignment_benchmark import aggregate_results

    records = [
        {
            "eligible": True,
            "movingPoint": [1, 1],
            "referencePoint": [1, 1],
            "referenceMicronsPerPixel": [1, 1],
            "wrongStructure": False,
        }
    ]
    local = {
        "status": "ready",
        "triangles": [
            {"moving": [[0, 0], [10, 0], [0, 10]], "reference": [[0, 0], [10, 0], [0, 10]]}
        ],
    }
    rows = [
        {
            "recipe": "native",
            "kind": "positive",
            "outcome": "ok",
            "registration": local,
            "landmarks": records,
            "coldRuntimeSeconds": 0.01,
        },
        {
            "recipe": "native",
            "kind": "positive",
            "outcome": "error",
            "registration": {},
            "landmarks": records,
            "coldRuntimeSeconds": 0.01,
        },
    ]
    report = aggregate_results(rows)
    assert report["recipes"]["native"]["eligibleLandmarks"] == 2
    assert report["recipes"]["native"]["coverage"] == 0.5
    assert report["winners"]["fast"] is None
    assert report["winners"]["accurate"] is None


def test_cached_run_does_not_replace_cold_timing_and_report_omits_private_paths(
    tmp_path, monkeypatch
):
    from wsi_viewer import alignment_benchmark as bench

    for name in ("reference", "moving"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "thumbnail.jpg").write_bytes(b"private pixel digest input")
    pair = {
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
        "kind": "positive",
        "landmarks": [
            {
                "movingPoint": [1, 1],
                "referencePoint": [1, 1],
                "referenceMicronsPerPixel": [1, 1],
                "wrongStructure": False,
                "eligible": True,
            }
        ],
    }
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"native-overview-v6": {"available": True}}
    )
    monkeypatch.setattr(bench, "_run_alignment_bounded", lambda *_a, **_kw: {"status": "rejected"})
    manifest = {"pairs": [pair]}
    out = tmp_path / "out"
    first = bench.run_benchmark(manifest, out, ["native"])
    calls = []
    monkeypatch.setattr(
        bench,
        "_run_alignment_bounded",
        lambda *_a, **_kw: calls.append(True) or {"status": "rejected", "peakMemoryBytes": 1234},
    )
    second = bench.run_benchmark(manifest, out, ["native"], repeat_runs=1)
    assert first["rows"][0]["coldRuntimeSeconds"] == second["rows"][0]["coldRuntimeSeconds"]
    assert second["rows"][0]["cached"] is True
    assert second["rows"][0]["pairIndex"] == 0
    assert second["rows"][0]["landmarkMetrics"]["eligibleLandmarks"] == 1
    assert second["rows"][0]["landmarkMetrics"]["unsupportedLandmarks"] == 1
    assert calls == [True]
    assert len(second["rows"][0]["repeatComputeReceipts"]) == 1
    assert second["rows"][0]["repeatComputeReceipts"][0]["peakMemoryBytes"] == 1234
    assert str(tmp_path) not in json.dumps(second)


def test_unscored_development_never_selects_finalists_or_winners():
    from wsi_viewer.alignment_benchmark import aggregate_results

    result = aggregate_results(
        [
            {
                "recipe": "native",
                "kind": "positive",
                "landmarks": [],
                "registration": {"status": "ready"},
                "outcome": "ok",
                "coldRuntimeSeconds": 0.01,
                "peakMemoryBytes": 1234,
            }
        ]
    )
    assert result["finalists"] == []
    assert result["winners"] == {"fast": None, "accurate": None}
    assert result["recipes"]["native"]["missingGroundTruthPairs"] == 1
    assert result["recipes"]["native"]["peakMemoryP95Bytes"] == 1234


def test_reviewed_approximate_recipe_can_qualify_without_ready_promotion():
    from wsi_viewer.alignment_benchmark import aggregate_results

    registration = {
        "status": "approximate",
        "confidence": 0.4,
        "overviewTriangles": [
            {"moving": [[0, 0], [10, 0], [0, 10]], "reference": [[0, 0], [10, 0], [0, 10]]}
        ],
    }
    rows = [
        {
            "recipe": "wsireg",
            "kind": "positive",
            "outcome": "ok",
            "registration": registration,
            "coldRuntimeSeconds": 1,
            "independentlyReviewed": True,
            "landmarksFitFree": True,
            "landmarks": [
                {
                    "eligible": True,
                    "movingPoint": [1, 1],
                    "referencePoint": [1, 1],
                    "referenceMicronsPerPixel": [1, 1],
                    "wrongStructure": False,
                }
            ],
        },
        {
            "recipe": "wsireg",
            "kind": "negative",
            "outcome": "ok",
            "registration": {"status": "rejected", "confidence": 0},
            "landmarks": [],
            "coldRuntimeSeconds": 1,
            "wrongStructure": False,
            "independentlyReviewed": True,
            "landmarksFitFree": True,
        },
    ]
    rows[1]["outcome"] = "rejected"
    report = aggregate_results(rows)
    assert report["recipes"]["wsireg"]["benchmarkQualified"] is True
    assert report["recipes"]["wsireg"]["readyQualified"] is False
    assert report["winners"]["accurate"] == "wsireg"
    assert report["winners"]["fast"] is None
    assert registration["status"] == "approximate"
    rows[1]["registration"] = {"status": "approximate", "confidence": 0.49}
    rows[1]["wrongStructure"] = True
    unsafe = aggregate_results(rows)
    assert unsafe["recipes"]["wsireg"]["benchmarkQualified"] is False


def test_missing_learned_weights_are_runtime_unavailable_not_registration_failure(
    tmp_path, monkeypatch
):
    from wsi_viewer import alignment_benchmark as bench

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"input")
    pair = {
        "kind": "positive",
        "landmarks": [],
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
    }
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"deeperhistreg-learned": {"available": True}}
    )
    monkeypatch.setattr(
        bench,
        "_run_alignment_bounded",
        lambda *_a, **_kw: pytest.fail("missing research weights must not launch a child"),
    )
    result = bench.run_benchmark({"pairs": [pair]}, tmp_path / "out", ["deeperhistreg-learned"])
    assert result["rows"][0]["outcome"] == "unavailable"
    assert result["rows"][0]["reasonCode"] == "verified-research-weights-unavailable"
    assert result["rows"][0]["coldRuntimeSeconds"] is None


def test_registration_change_invalidates_negative_and_latency_reviews(tmp_path, monkeypatch):
    from wsi_viewer import alignment_benchmark as bench

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"input")
    pair = {
        "kind": "negative",
        "landmarks": [],
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
    }
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"native-overview-v6": {"available": True}}
    )
    monkeypatch.setattr(bench, "_run_alignment_bounded", lambda *_a, **_kw: {"status": "rejected"})
    manifest = {"pairs": [pair]}
    first = bench.run_benchmark(manifest, tmp_path / "out", ["native"])
    pair["reviews"] = {
        "native": {
            "registrationDigest": first["rows"][0]["digest"],
            "wrongStructure": False,
            "frontendLatencySeconds": 1,
            "frontendLatencyScope": "foreground-open-to-sync",
            "frontendLatencyReviewed": True,
        }
    }
    reviewed = bench.run_benchmark(manifest, tmp_path / "out", ["native"])
    assert reviewed["rows"][0]["wrongStructure"] is False
    assert reviewed["rows"][0]["frontendLatencyReviewed"] is True
    manifest["settings"] = {"native": {"changed": True}}
    changed = bench.run_benchmark(manifest, tmp_path / "out", ["native"])
    assert changed["rows"][0]["wrongStructure"] is None
    assert changed["rows"][0]["frontendLatencyReviewed"] is False
    assert changed["recipes"]["native-overview-v6"]["missingNegativeReviews"] == 1
