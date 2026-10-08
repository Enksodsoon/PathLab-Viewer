"""Bound warm receipts and own-stage support without models, fitting or private inputs."""

# SPDX-License-Identifier: Apache-2.0
import copy
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import alignment_warm_report_stage as stage
from scripts import report_alignment_warm_campaign as module

HEAD = "a" * 40
RECIPES = module.recipes_from_source()
REGISTRY = {
    "ENGINE_VERSIONS": {r: "fixture-build" for r in RECIPES},
    "ADAPTER_VERSIONS": {r: "fixture-adapter" for r in RECIPES},
}


class Checks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="alignment-warm-report-selfcheck-")
        self.root = Path(self.temp.name)
        self.campaign = self.root / "campaign"
        (self.campaign / "cache").mkdir(parents=True)
        self.manifest = {
            "sourceAdmission": {"sourceFreezeHead": HEAD},
            "pairs": [
                {
                    "kind": "positive" if i < 12 else "negative",
                    "landmarksFitFree": True,
                    "inputDigests": ["b" * 64, "c" * 64],
                    "reference": {"size": [100, 100]},
                    "landmarks": [
                        {
                            "eligible": True,
                            "movingPoint": [1, 1],
                            "referencePoint": [1, 1],
                            "wrongStructure": False,
                        }
                    ]
                    * (947 if i == 0 else 0),
                }
                for i in range(16)
            ],
        }
        self.manifest_path = self.root / "manifest.json"
        self.manifest_path.write_bytes(module.canonical(self.manifest))
        self.identity = patch.object(module, "engine_identity", return_value=({}, REGISTRY))
        self.identity.start()

    def tearDown(self):
        self.identity.stop()
        self.temp.cleanup()

    def build(self):
        return module.build(self.campaign, self.manifest_path, HEAD)

    def row(self, pids=(123, 123)):
        key = "d" * 64
        base = self.campaign / "artifacts" / key / "attempt-0001"
        base.mkdir(parents=True)
        calls = []
        for ordinal in (1, 2):
            call = {
                "schema": module.PROTOCOL,
                "invocationOrdinal": ordinal,
                "childPid": pids[ordinal - 1],
                "verifiedInputDigests": self.manifest["pairs"][0]["inputDigests"],
                "invocationExecuted": True,
                "invocationWallSeconds": 3 if ordinal == 1 else 1,
                "result": {"ok": False, "type": "AlignmentRejected", "error": "fixture rejection"},
            }
            content = module.canonical(call)
            (base / f"invocation-{ordinal}.json").write_bytes(content)
            calls.append({**call, "artifactSha256": module.sha(content)})
        row = {
            "pairIndex": 0,
            "recipe": RECIPES[0],
            "digest": key,
            "protocol": {
                "policy": module.PROTOCOL,
                "sourceHead": HEAD,
                "frozenManifestSha256": module.sha(self.manifest_path.read_bytes()),
                "plannedInvocations": 2,
                "runtimeIdentity": {},
            },
            "historicalInterruptedAttempts": 0,
            "inputDigests": self.manifest["pairs"][0]["inputDigests"],
            "requestedSettings": {},
            "invocations": calls,
            "supervisedTotalWallSeconds": 5,
            "resourceMetrics": {"peakMemoryBytes": 100},
            "terminalContainmentVerified": True,
        }
        row["protocol"].update(memoryBytes=7 * 1024**3, sharedTotalSeconds=600)
        self.save(row)
        return row

    def save(self, row):
        (self.campaign / "cache" / (row["digest"] + ".json")).write_bytes(module.canonical(row))
        (self.campaign / "report.json").write_bytes(
            module.canonical(
                {
                    "schema": module.PROTOCOL,
                    "rows": [{"pairIndex": 0, "recipe": RECIPES[0], "digest": row["digest"]}],
                }
            )
        )

    def test_missing_full_denominator(self):
        report = self.build()
        self.assertEqual(len(report["rows"]), 288)
        self.assertEqual(report["missingOrdinalCount"], 288)
        self.assertEqual(report["plannedEligibleLandmarksPerRecipePerOrdinal"], 947)
        self.assertIsNone(
            report["recipes"][RECIPES[0]]["1"]["timings"]["invocationWallSeconds"]["median"]
        )

    def test_failure_wall_and_same_pid_are_preserved(self):
        self.row()
        report = self.build()
        self.assertEqual(report["executedInvocations"], 2)
        self.assertTrue(report["rows"][1]["sameContainedProcessProven"])
        self.assertEqual(
            report["recipes"][RECIPES[0]]["1"]["timings"]["invocationWallSeconds"]["median"], 3
        )
        self.assertEqual(
            report["recipes"][RECIPES[0]]["2"]["timings"]["invocationWallSeconds"]["median"], 1
        )
        self.assertFalse(report["qualification"]["qualified"])
        self.assertEqual(report["qualification"]["retainedModelTemperature"], "UNVERIFIED")

    def test_pair_scores_keep_rejected_denominator_and_negative_unknown(self):
        self.row()
        report = module.build(self.campaign, self.manifest_path, HEAD, evaluate=True)
        first = report["rows"][0]["landmarkMetrics"]
        self.assertEqual(first["eligibleLandmarks"], 947)
        self.assertEqual(first["observedLandmarks"], 0)
        self.assertEqual(first["unsupportedLandmarks"], 947)
        negative = next(r for r in report["rows"] if r["pairKind"] == "negative")
        self.assertEqual(negative["landmarkMetrics"]["eligibleLandmarks"], 0)
        self.assertIsNone(negative["landmarkMetrics"]["observedCoverage"])
        self.assertEqual(
            negative["landmarkMetrics"]["reason"], "no-published-positive-ground-truth"
        )

    def test_different_pid_is_not_warm_proof(self):
        self.row((123, 456))
        self.assertFalse(self.build()["rows"][1]["sameContainedProcessProven"])

    def test_tampered_atomic_receipt_rejected(self):
        row = self.row()
        row["invocations"][0]["invocationWallSeconds"] = 8
        self.save(row)
        with self.assertRaisesRegex(ValueError, "atomic invocation"):
            self.build()

    def test_duplicate_ordinal_rejected(self):
        row = self.row()
        row["invocations"].append(copy.deepcopy(row["invocations"][0]))
        self.save(row)
        with self.assertRaisesRegex(ValueError, "duplicate/unplanned invocation"):
            self.build()

    def test_wrong_source_rejected(self):
        row = self.row()
        row["protocol"]["sourceHead"] = "f" * 40
        self.save(row)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.build()

    def test_privacy_and_finite(self):
        for value in (
            {"childPid": 9},
            {"message": "C:/private/image"},
            {"message": "Bearer fixture"},
            {"message": "token=fixture"},
            {"value": float("nan")},
        ):
            with self.assertRaises(ValueError):
                module.privacy(value)

    def test_privacy_rejects_macos_fixture_path(self):
        value = "/".join(("", "Users", "synthetic-fixture", "image"))
        with self.assertRaisesRegex(ValueError, "private string"):
            module.privacy({"message": value})

    def test_privacy_rejects_linux_fixture_path(self):
        value = "/".join(("", "home", "synthetic-fixture", "image"))
        with self.assertRaisesRegex(ValueError, "private string"):
            module.privacy({"message": value})

    def test_percentile_includes_rejected_measured_calls(self):
        self.assertEqual(module.percentile([1, 3, 10], 95), 9.299999999999999)
        self.assertIsNone(module.percentile([None, float("nan")], 50))

    def test_cli_refuses_symlink_output_parent_before_reading_campaign(self):
        owned = self.root / "var"
        owned.mkdir()
        outside = self.root / "outside"
        outside.mkdir()
        link = owned / "linked"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError as error:
            if os.name == "nt" and error.winerror == 1314:
                self.skipTest("Windows host does not permit symlink creation")
            raise
        args = [
            "report_alignment_warm_campaign.py",
            "--campaign",
            str(self.campaign),
            "--manifest",
            str(self.manifest_path),
            "--source-head",
            HEAD,
            "--output",
            str(link / "report.json"),
        ]
        with (
            patch.object(module, "ROOT", self.root),
            patch.object(sys, "argv", args),
            patch.object(module, "build", side_effect=AssertionError("campaign read too early")),
            self.assertRaisesRegex(ValueError, "fresh ignored output"),
        ):
            module.main()
        self.assertFalse((outside / "report.json").exists())

    def test_cli_refuses_resolved_output_escape_before_reading_campaign(self):
        output = self.root / "var" / "linked" / "report.json"
        args = [
            "report_alignment_warm_campaign.py",
            "--campaign",
            str(self.campaign),
            "--manifest",
            str(self.manifest_path),
            "--source-head",
            HEAD,
            "--output",
            str(output),
        ]
        original_resolve = Path.resolve

        def escaped(path, *args, **kwargs):
            if path == output:
                return self.root / "outside" / "report.json"
            return original_resolve(path, *args, **kwargs)

        with (
            patch.object(module, "ROOT", self.root),
            patch.object(sys, "argv", args),
            patch.object(Path, "resolve", escaped),
            patch.object(module, "build", side_effect=AssertionError("campaign read too early")),
            self.assertRaisesRegex(ValueError, "fresh ignored output"),
        ):
            module.main()


PAIR = {
    "reference": {"size": [100, 100]},
    "moving": {"size": [100, 100]},
    "landmarksFitFree": True,
    "landmarks": [
        {
            "eligible": True,
            "movingPoint": [1, 1],
            "referencePoint": [2, 1],
            "wrongStructure": False,
        },
        {
            "eligible": True,
            "movingPoint": [20, 20],
            "referencePoint": [21, 20],
            "wrongStructure": False,
        },
        {
            "eligible": True,
            "movingPoint": [90, 90],
            "referencePoint": [91, 90],
            "wrongStructure": False,
        },
    ],
}


def registration(engine, *, extent=10, translation=1, analysis=25):
    geometry = {
        "schema": "pathlab-sampling-frame/1",
        "kind": "immutable-overview",
        "sourceSize": [100, 100],
        "analysisSize": [analysis, analysis],
        "coordinateFrameSize": [100, 100],
        "samplingScale": [100 / analysis] * 2,
        "cropOrigin": [0, 0],
        "snapshotPixelSha256": "a" * 64,
    }
    source = [[0, 0], [extent, 0], [0, extent]]
    target = [[p[0] + translation, p[1]] for p in source]
    return {
        "engine": engine,
        "status": "ready",
        "samplingGeometryApplied": True,
        "samplingGeometryDigest": hashlib.sha256(
            stage.canonical({"reference": geometry, "moving": geometry})
        ).hexdigest(),
        "engineSettings": {
            "referenceGeometry": geometry,
            "movingGeometry": copy.deepcopy(geometry),
        },
        "movingToReference": [[1, 0, translation], [0, 1, 0]],
        "triangles": [{"moving": source, "reference": target}],
        "overviewTriangles": [],
    }


class StageChecks(unittest.TestCase):
    def test_direct_script_stage_scoring_with_only_server_pythonpath(self):
        root = Path(__file__).resolve().parents[2]
        initial = registration("native-overview-v6")
        final = registration("native-wsireg", extent=50)
        code = (
            f"import sys; sys.path.insert(0, {str(root / 'scripts')!r}); "
            "import alignment_warm_report_stage as stage; "
            f"result, _ = stage.measurement({initial!r}, {final!r}, {PAIR!r}, "
            "'native-wsireg', evaluate=True); "
            "assert result['finalVsInitializerCommonSupport']['commonSupportedLandmarks'] == 1"
        )
        env = {**os.environ, "PYTHONPATH": str(root / "server")}
        with tempfile.TemporaryDirectory() as cwd:
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_module_and_direct_cli_help_without_engine_imports(self):
        root = Path(__file__).resolve().parents[2]
        for args in (
            [str(root / "scripts/report_alignment_warm_campaign.py"), "--help"],
            ["-m", "scripts.report_alignment_warm_campaign", "--help"],
        ):
            completed = subprocess.run(
                [sys.executable, *args],
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(root / "server")},
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertIn("--evaluate-landmarks", completed.stdout)

    def test_no_evaluation_without_explicit_switch(self):
        with (
            patch.object(stage, "original_frame_proof", side_effect=AssertionError("not released")),
            patch.object(stage, "metrics", side_effect=AssertionError("not released")),
        ):
            result, maps = stage.measurement({}, {}, PAIR, "native-wsireg")
        self.assertIsNone(result["initializerEngineOutputMetrics"])
        self.assertEqual(maps, {"initializer": {}, "applied": {}})

    def test_legacy_geometry_absence_does_not_invent_original_frame(self):
        initial = registration("native-overview-v6")
        del initial["samplingGeometryApplied"]
        result, maps = stage.measurement(initial, {}, PAIR, "native-wsireg", evaluate=True)
        self.assertEqual(result["reason"], "initializer-original-frame-or-engine-not-proven")
        self.assertEqual(maps["initializer"], {})

    def test_geometry_digest_and_actual_source_dimensions_are_required(self):
        initial = registration("native-overview-v6")
        initial["samplingGeometryDigest"] = "b" * 64
        self.assertFalse(stage.original_frame_proof(initial, PAIR))
        initial = registration("native-overview-v6")
        different = copy.deepcopy(PAIR)
        different["moving"]["size"] = [101, 100]
        self.assertFalse(stage.original_frame_proof(initial, different))

    def test_wrong_initializer_engine_is_not_stage_proof(self):
        result, _ = stage.measurement(
            registration("native-v12"), {}, PAIR, "native-wsireg", evaluate=True
        )
        self.assertEqual(result["reason"], "initializer-original-frame-or-engine-not-proven")

    def test_same_original_sizes_allow_different_bounded_analysis(self):
        initial = registration("native-overview-v6", analysis=25)
        final = registration("native-wsireg", extent=50, translation=2, analysis=50)
        result, _ = stage.measurement(initial, final, PAIR, "native-wsireg", evaluate=True)
        paired = result["finalVsInitializerCommonSupport"]
        self.assertEqual(paired["commonSupportedLandmarks"], 1)
        self.assertEqual(paired["onlyLeftSupportedLandmarks"], 1)
        self.assertEqual(paired["onlyRightSupportedLandmarks"], 0)
        unit = paired["errorsByUnit"]["reference-image-diagonal"]
        self.assertEqual(unit["neitherSupportedLandmarks"], 1)
        self.assertAlmostEqual(unit["medianPairedErrorDelta"], 1 / (20000**0.5))
        self.assertFalse(result["qualified"])
        self.assertIsNone(result["residualFrameAccuracy"])

    def test_final_frame_missing_keeps_initializer_but_no_paired_delta(self):
        result, _ = stage.measurement(
            registration("native-overview-v6"), {}, PAIR, "native-wsireg", evaluate=True
        )
        self.assertEqual(result["initializerEngineOutputMetrics"]["observedLandmarks"], 1)
        self.assertIsNone(result["finalVsInitializerCommonSupport"])
        self.assertEqual(
            result["pairedComparisonUnavailableReason"], "final-map-or-original-frame-unavailable"
        )

    def test_retained_fallback_cannot_supply_stage_support(self):
        initial = registration("native-overview-v6")
        initial["overviewFallback"] = registration("native-overview-v6", extent=99, translation=0)
        result, _ = stage.measurement(initial, {}, PAIR, "native-wsireg", evaluate=True)
        self.assertEqual(result["initializerEngineOutputMetrics"]["observedLandmarks"], 1)
        self.assertEqual(result["initializerEngineOutputMetrics"]["unsupportedLandmarks"], 2)

    def test_947_denominator_includes_unsupported_landmarks(self):
        pair = copy.deepcopy(PAIR)
        pair["landmarks"] = [pair["landmarks"][0]] + [pair["landmarks"][2]] * 946
        result, _ = stage.measurement(
            registration("native-overview-v6"), {}, pair, "native-wsireg", evaluate=True
        )
        self.assertEqual(result["initializerEngineOutputMetrics"]["eligibleLandmarks"], 947)
        self.assertEqual(result["initializerEngineOutputMetrics"]["observedLandmarks"], 1)
        self.assertEqual(result["initializerEngineOutputMetrics"]["unsupportedLandmarks"], 946)

    def test_reflected_cells_remain_unsupported(self):
        initial = registration("native-overview-v6")
        initial["triangles"][0]["reference"].reverse()
        result, _ = stage.measurement(initial, {}, PAIR, "native-wsireg", evaluate=True)
        self.assertEqual(result["initializerEngineOutputMetrics"]["observedLandmarks"], 0)
        self.assertIsNone(result["initializerEngineOutputMetrics"]["medianRelativeError"])

    def test_nonfinite_or_out_of_original_bounds_is_not_stage_frame(self):
        for value in (float("nan"), 100):
            initial = registration("native-overview-v6")
            initial["triangles"][0]["moving"][0][0] = value
            self.assertFalse(stage.original_frame_proof(initial, PAIR))

    def test_affine_projection_is_distinct_and_never_extends_source_support(self):
        initial = registration("native-overview-v6")
        initial["movingToReference"][0][2] = 3
        result, maps = stage.measurement(initial, {}, PAIR, "native-wsireg", evaluate=True)
        self.assertEqual(
            maps["initializer"]["triangles"][0]["moving"], maps["applied"]["triangles"][0]["moving"]
        )
        self.assertEqual(result["initializerEngineOutputMetrics"]["observedLandmarks"], 1)
        self.assertEqual(result["appliedAffineOnOwnSupportMetrics"]["observedLandmarks"], 1)
        self.assertEqual(result["initializerEngineOutputMetrics"]["medianRelativeError"], 0)
        self.assertGreater(result["appliedAffineOnOwnSupportMetrics"]["medianRelativeError"], 0)
        self.assertFalse(result["wholeInitializerPiecewiseMapAppliedToWarp"])
