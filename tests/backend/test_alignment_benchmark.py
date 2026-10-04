import json

import pytest


def test_cache_retains_effective_provenance_without_exposing_private_settings(
    tmp_path, monkeypatch
):
    from wsi_viewer import alignment_benchmark as bench
    from wsi_viewer.alignment_engines import ENGINE_NATIVE_OVERVIEW, settings_digest

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"pixels")
    pair = {
        "kind": "positive",
        "landmarks": [],
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
    }
    effective = {"inputBlurRadius": 0.6, "resourcePath": str(tmp_path / "private-weights")}
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {ENGINE_NATIVE_OVERVIEW: {"available": True}}
    )
    calls = []
    monkeypatch.setattr(
        bench,
        "_run_alignment_bounded",
        lambda *a, **kw: calls.append(kw) or {"status": "rejected", "engineSettings": effective},
    )
    manifest = {"pairs": [pair], "settings": {"native": {"iterations": 2}}}
    out = tmp_path / "out"
    report = bench.run_benchmark(manifest, out, ["native"])
    receipt = json.loads(next((out / "cache").glob("*.json")).read_text())
    assert receipt["requestedSettingsDigest"] == settings_digest(
        ENGINE_NATIVE_OVERVIEW, {"iterations": 2, "timeoutSeconds": 600}
    )
    assert receipt["effectiveSettings"] == effective
    assert receipt["effectiveSettingsDigest"] == settings_digest(ENGINE_NATIVE_OVERVIEW, effective)
    assert report["rows"][0]["effectiveSettingsDigest"] == receipt["effectiveSettingsDigest"]
    assert str(tmp_path) not in json.dumps(report)
    bench.run_benchmark(manifest, out, ["native"])
    assert len(calls) == 1


def test_resource_rejection_preserves_safe_peak_metrics(tmp_path, monkeypatch):
    from wsi_viewer import alignment_benchmark as bench
    from wsi_viewer.alignment import AlignmentRejected

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"pixels")
    pair = {
        "kind": "negative",
        "landmarks": [],
        "reference": {"path": str(tmp_path / "reference"), "size": [10, 10]},
        "moving": {"path": str(tmp_path / "moving"), "size": [10, 10]},
    }
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"native-overview-v6": {"available": True}}
    )

    def fail(*a, **kw):
        error = AlignmentRejected("memory ceiling on " + str(tmp_path))
        error.resource_metrics = {
            "peakMemoryBytes": 1234,
            "peakCommittedMemoryBytes": 5678,
            "memoryMeasurementScope": "windows-job-sampled-working-set",
            "privatePath": str(tmp_path),
        }
        raise error

    monkeypatch.setattr(bench, "_run_alignment_bounded", fail)
    report = bench.run_benchmark({"pairs": [pair]}, tmp_path / "out", ["native"], repeat_runs=1)
    row = report["rows"][0]
    assert row["peakMemoryBytes"] == 1234
    assert row["resourceMetrics"]["peakCommittedMemoryBytes"] == 5678
    assert row["repeatComputeReceipts"][0]["peakMemoryBytes"] == 1234
    assert str(tmp_path) not in json.dumps(report)


def test_resource_changed_after_admission_is_unavailable_not_anatomical_rejection(
    tmp_path, monkeypatch
):
    from wsi_viewer import alignment_benchmark as bench
    from wsi_viewer.alignment_resources import EngineResourceUnavailable

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

    def unavailable(*args, **kwargs):
        raise EngineResourceUnavailable("verified local weights changed")

    monkeypatch.setattr(bench, "_run_alignment_bounded", unavailable)
    row = bench.run_benchmark({"pairs": [pair]}, tmp_path / "out", ["native"], repeat_runs=1)[
        "rows"
    ][0]
    assert row["outcome"] == "unavailable"
    assert row["repeatComputeReceipts"] == []
    assert row["coldRuntimeSeconds"] is None and row["admissionSeconds"] >= 0


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


def test_runtime_identity_binds_loaded_opencv_and_contrib_distribution(monkeypatch):
    import cv2
    from wsi_viewer import alignment_benchmark as benchmark

    monkeypatch.setattr(
        benchmark.importlib.metadata,
        "version",
        lambda name: "4.11" if name == "opencv-python-headless" else "4.9",
    )
    monkeypatch.setattr(cv2, "__version__", "4.9.0")
    first = benchmark._runtime_versions()
    assert first["opencv-contrib-python-headless"] == "4.9"
    assert first["loaded-cv2"] == "4.9.0"
    monkeypatch.setattr(cv2, "__version__", "4.11.0")
    assert benchmark._runtime_versions() != first


def test_generated_cache_reset_preserves_bound_inputs_and_copied_pyramids(tmp_path):
    from wsi_viewer.alignment_cache import reset_generated_regional_cache

    from tests.backend.test_alignment_immutable_inputs import snapshot

    root = tmp_path / "sources" / "a"
    root.parent.mkdir()
    value = snapshot(root)
    candidate = root / "original.tif"
    candidate.write_bytes(b"original")
    dzi = root / "slide.dzi"
    dzi.write_bytes(b"descriptor")

    def sha(p):
        return __import__("hashlib").sha256(p.read_bytes()).hexdigest()

    (root / ".openslide-source.json").write_text(
        json.dumps({"source": str(candidate.resolve()), "tileSize": 512, "quality": 92})
    )
    value["regionSource"] = {
        "available": True,
        "kind": "openslide-original",
        "file": "original.tif",
        "sha256": sha(candidate),
        "descriptorSha256": sha(dzi),
        "rendering": {"tileSize": 512, "quality": 92},
        "tileCacheLimitBytes": 999999,
    }
    (root / "immutable-overview.json").write_text(json.dumps(value))
    tile = root / "slide_files" / "2" / "0_0.jpg"
    tile.parent.mkdir(parents=True)
    tile.write_bytes(b"generated")
    bound_before = {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    result = reset_generated_regional_cache([root, root], tmp_path)
    assert result["removedFileCount"] == 1 and result["removedBytes"] == 9
    assert result["sourceKindCounts"] == {"openslide-original": 1}
    assert not tile.exists()
    assert bound_before == {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}
    tile.write_bytes(b"copied")
    value["regionSource"] = {
        "available": True,
        "kind": "copied-dzi",
        "files": [{"name": "slide_files/2/0_0.jpg", "sha256": sha(tile)}],
    }
    (root / "immutable-overview.json").write_text(json.dumps(value))
    assert reset_generated_regional_cache([root], tmp_path)["removedFileCount"] == 0
    assert tile.read_bytes() == b"copied"


def test_generated_cache_reset_rejects_outside_workspace_and_reparse_parent(tmp_path, monkeypatch):
    from wsi_viewer import alignment_cache

    from tests.backend.test_alignment_immutable_inputs import snapshot

    root = tmp_path / "a"
    snapshot(root)
    with pytest.raises(ValueError, match="workspace"):
        alignment_cache.reset_generated_regional_cache([root], tmp_path / "other")
    monkeypatch.setattr(alignment_cache, "_is_reparse", lambda path: path == tmp_path)
    with pytest.raises(ValueError, match="reparse"):
        alignment_cache.reset_generated_regional_cache([root], tmp_path)


def test_cold_cache_protocol_invalidates_old_receipt_and_resume_does_not_reset(
    tmp_path, monkeypatch
):
    from wsi_viewer import alignment_benchmark as bench

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"pixels")
    pair = {
        "kind": "positive",
        "landmarks": [],
        **{s: {"path": str(tmp_path / s), "size": [10, 10]} for s in ("reference", "moving")},
    }
    monkeypatch.setattr(
        bench, "engine_availability", lambda: {"native-overview-v6": {"available": True}}
    )
    calls, resets = [], []
    monkeypatch.setattr(
        bench, "_run_alignment_bounded", lambda *a, **kw: calls.append(kw) or {"status": "rejected"}
    )

    def reset(roots, workspace):
        resets.append((roots, workspace))
        return {
            "policy": "process-cold-generated-regional-cache-empty/1",
            "performed": True,
            "wallSeconds": 7.0,
            "removedFileCount": 2,
            "removedBytes": 123,
            "sourceKindCounts": {"openslide-original": 1, "verified-openslide-candidate": 1},
            "hostFilesystemCacheState": "unmeasured",
        }

    monkeypatch.setattr(bench, "reset_generated_regional_cache", reset)
    manifest, out = {"pairs": [pair]}, tmp_path / "out"
    old = bench.run_benchmark(manifest, out, ["native"])
    report = bench.run_benchmark(
        manifest,
        out,
        ["native"],
        reset_immutable_regional_cache=True,
        immutable_input_root=tmp_path,
    )
    row = report["rows"][0]
    assert row["digest"] != old["rows"][0]["digest"]
    assert row["cachePreparation"]["removedBytes"] == 123
    assert row["coldRuntimeSeconds"] == row["runtimeCoreSeconds"] + 7
    assert row["endToEndPreparationAndRuntimeSeconds"] == row["coldRuntimeSeconds"]
    assert len(resets) == 1 and len(calls) == 2
    resumed = bench.run_benchmark(
        manifest,
        out,
        ["native"],
        reset_immutable_regional_cache=True,
        immutable_input_root=tmp_path,
    )
    assert resumed["rows"][0]["cached"] is True
    assert len(resets) == 1 and len(calls) == 2
    with pytest.raises(ValueError, match="protocol"):
        bench.run_benchmark(
            manifest,
            out,
            ["native"],
            reset_immutable_regional_cache=True,
            immutable_input_root=tmp_path,
            repeat_runs=1,
        )


def test_generated_cache_reparse_entry_prevents_any_file_deletion(tmp_path, monkeypatch):
    import hashlib

    from wsi_viewer import alignment_cache

    from tests.backend.test_alignment_immutable_inputs import snapshot

    root = tmp_path / "a"
    value = snapshot(root)
    (root / "original.tif").write_bytes(b"original")
    (root / "slide.dzi").write_bytes(b"descriptor")

    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()

    (root / ".openslide-source.json").write_text(
        json.dumps(
            {"source": str((root / "original.tif").resolve()), "tileSize": 512, "quality": 92}
        )
    )
    value["regionSource"] = {
        "available": True,
        "kind": "openslide-original",
        "file": "original.tif",
        "sha256": sha(root / "original.tif"),
        "descriptorSha256": sha(root / "slide.dzi"),
        "rendering": {"tileSize": 512, "quality": 92},
    }
    (root / "immutable-overview.json").write_text(json.dumps(value))
    cache = root / "slide_files"
    cache.mkdir()
    regular, linked = cache / "0_0.jpg", cache / "1_0.jpg"
    regular.write_bytes(b"first generated tile")
    linked.write_bytes(b"simulated reparse entry")
    original_check = alignment_cache._is_reparse
    monkeypatch.setattr(
        alignment_cache, "_is_reparse", lambda path: path == linked or original_check(path)
    )
    with pytest.raises(ValueError, match="reparse"):
        alignment_cache.reset_generated_regional_cache([root], tmp_path)
    assert regular.read_bytes() == b"first generated tile"
    assert linked.exists()


def test_cold_cache_protocol_fatal_containment_loss_cannot_start_next_recipe(tmp_path, monkeypatch):
    from wsi_viewer import alignment_benchmark as bench

    for side in ("reference", "moving"):
        (tmp_path / side).mkdir()
        (tmp_path / side / "thumbnail.jpg").write_bytes(b"pixels")
    pair = {
        "kind": "positive",
        "landmarks": [],
        **{s: {"path": str(tmp_path / s), "size": [10, 10]} for s in ("reference", "moving")},
    }
    monkeypatch.setattr(
        bench,
        "engine_availability",
        lambda: {r: {"available": True} for r in ("native-overview-v6", "hisalign-0.2.1")},
    )
    resets = []
    monkeypatch.setattr(
        bench, "reset_generated_regional_cache", lambda *a: resets.append(a) or {"wallSeconds": 0.0}
    )

    def lost(*a, **kw):
        raise SystemExit("containment lost")

    monkeypatch.setattr(bench, "_run_alignment_bounded", lost)
    with pytest.raises(SystemExit, match="containment lost"):
        bench.run_benchmark(
            {"pairs": [pair]},
            tmp_path / "out",
            ["native", "hisalign"],
            reset_immutable_regional_cache=True,
            immutable_input_root=tmp_path,
        )
    assert len(resets) == 1
