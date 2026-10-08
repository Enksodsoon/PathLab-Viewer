# SPDX-License-Identifier: Apache-2.0
"""Project existing two-invocation warm receipts; never runs registration or fits maps."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path

if __package__:
    from .alignment_warm_report_stage import STAGES, measurement
else:
    from alignment_warm_report_stage import STAGES, measurement

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = "same-contained-process-two-invocations/1"
MAX_BYTES = 64 * 1024**2
MEMORY_KEYS = (
    "peakMemoryBytes",
    "peakCommittedMemoryBytes",
    "kernelReportedPeakJobMemoryBytes",
    "sampledPeakPrivateCommittedMemoryBytes",
    "peakContainedProcesses",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def digest(value):
    if not isinstance(value, str) or not re.fullmatch("[0-9a-f]{64}", value):
        raise ValueError("SHA256 required")
    return value


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None


def percentile(values, q):
    values = sorted(v for v in values if number(v) is not None)
    if not values:
        return None
    p = (len(values) - 1) * q / 100
    low, high = math.floor(p), math.ceil(p)
    return values[low] + (values[high] - values[low]) * (p - low)


def metric(values):
    valid = [v for v in values if number(v) is not None]
    return {
        "measuredCount": len(valid),
        "median": percentile(valid, 50),
        "p95": percentile(valid, 95),
    }


def read(path, snapshots, maximum=MAX_BYTES):
    path = Path(path).absolute()
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError("links/junctions unsupported")
    if path.stat().st_size > maximum:
        raise ValueError("receipt exceeds byte ceiling")
    with path.open("rb") as stream:
        content = stream.read(maximum + 1)
    if len(content) > maximum:
        raise ValueError("receipt exceeds byte ceiling")
    snapshots[path] = sha(content)
    return json.loads(
        content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON"))
    )


def privacy(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in {
                "path",
                "sourcepath",
                "pid",
                "childpid",
                "landmarks",
                "coordinates",
                "movingpoint",
                "referencepoint",
                "triangles",
                "controlpoints",
                "cookie",
            }:
                raise ValueError("private field")
            privacy(child)
    elif isinstance(value, list):
        for child in value:
            privacy(child)
    elif isinstance(value, str) and re.search(
        r"[A-Za-z]:[\\/]|/(?:Users|home)/|Bearer\s|token=", value
    ):
        raise ValueError("private string")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("nonfinite output")


def recipes_from_source():
    tree = ast.parse((ROOT / "scripts/benchmark_alignment_warm_process.py").read_text())
    return list(
        next(
            ast.literal_eval(n.value)
            for n in tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "RECIPES" for t in n.targets)
        )
    )


def engine_identity(source_head):
    """Version registry from frozen source, without importing any engine/model."""
    modules = (
        "scripts/benchmark_alignment_warm_process.py",
        "server/wsi_viewer/alignment_warm.py",
        "server/wsi_viewer/alignment_engines.py",
        "server/wsi_viewer/alignment_evaluation.py",
        "server/wsi_viewer/alignment_recipes.py",
        "server/wsi_viewer/alignment_geometry.py",
        "server/wsi_viewer/alignment_benchmark.py",
        "server/wsi_viewer/worker.py",
        "scripts/report_alignment_campaign.py",
    )
    fingerprints, registry = {}, {}
    for name in modules:
        frozen = subprocess.check_output(
            ["git", "show", f"{source_head}:{name}"], cwd=ROOT, timeout=10
        )
        if (ROOT / name).read_bytes().replace(b"\r\n", b"\n") != frozen.replace(b"\r\n", b"\n"):
            raise ValueError("current helper differs from execution freeze")
        fingerprints[name] = sha(frozen)
        if name.endswith("alignment_engines.py"):
            tree = ast.parse(frozen)
            for node in tree.body:
                if (
                    not isinstance(node, ast.Assign)
                    or len(node.targets) != 1
                    or not isinstance(node.targets[0], ast.Name)
                ):
                    continue
                name = node.targets[0].id
                if name.startswith("ENGINE_") and isinstance(node.value, ast.Constant):
                    registry[name] = ast.literal_eval(node.value)
                elif name in {"RECIPE_STAGES", "ENGINE_VERSIONS", "ADAPTER_VERSIONS"}:

                    def literal(value):
                        if isinstance(value, ast.Name):
                            return registry[value.id]
                        if isinstance(value, ast.Constant):
                            return value.value
                        if isinstance(value, ast.Tuple):
                            return tuple(literal(v) for v in value.elts)
                        if isinstance(value, ast.Dict):
                            return {
                                literal(k): literal(v)
                                for k, v in zip(value.keys, value.values, strict=True)
                            }
                        raise ValueError("version registry must use static literals")

                    registry[name] = literal(node.value)
            for recipe, components in registry["RECIPE_STAGES"].items():
                registry["ENGINE_VERSIONS"][recipe] = "+".join(
                    registry["ENGINE_VERSIONS"][c] for c in components
                )
                registry["ADAPTER_VERSIONS"][recipe] = (
                    "pathlab-recipe-v5-effective-stage-provenance:"
                    + "+".join(registry["ADAPTER_VERSIONS"][c] for c in components)
                )
    return fingerprints, registry


def settings_identity(recipe, settings, registry):
    return sha(
        canonical(
            {
                "engine": recipe,
                "buildVersion": registry["ENGINE_VERSIONS"][recipe],
                "adapterVersion": registry["ADAPTER_VERSIONS"][recipe],
                "settings": settings or {},
            }
        )
    )


def classification(call):
    if call is None:
        return "missing-ordinal"
    result = call.get("result") or {}
    if result.get("ok") is True:
        reg = result.get("result") or {}
        return (
            "accepted-supported-map"
            if reg.get("status") in {"ready", "approximate"}
            and (reg.get("triangles") or reg.get("overviewTriangles"))
            else "returned-unusable-map"
        )
    if result.get("type") == "MissingInvocationReceipt":
        return (
            "missing-result-after-start"
            if call.get("invocationExecutionPhaseStarted") is True
            else "not-executed"
        )
    if call.get("invocationExecuted") is False:
        return "not-executed"
    message = str(result.get("error", "")).lower()
    if any(
        s in message for s in ("memory limit", "memory ceiling", "memory budget", "out of memory")
    ):
        return "bounded-memory-failure"
    if any(s in message for s in ("timeout", "time budget", "deadline", "time ceiling")):
        return "bounded-timeout"
    if any(s in message for s in ("not installed", "unavailable", "missing resource", "weights")):
        return "unavailable-resource-or-runtime"
    return (
        "registration-rejection"
        if result.get("type") in {"AlignmentRejected", "RejectedRegistration"}
        else "runtime-or-unknown-failure"
    )


def artifact_proof(campaign, row, call, snapshots):
    """The chosen attempt is explicit in the cache, never newest-file guessing."""
    attempt = row.get("historicalInterruptedAttempts")
    if type(attempt) is not int or not 0 <= attempt < 10000:
        raise ValueError("bounded attempt ordinal required")
    base = campaign / "artifacts" / digest(row["digest"]) / f"attempt-{attempt + 1:04d}"
    ordinal = call["invocationOrdinal"]
    expected = call.get("artifactSha256")
    if expected is not None:
        path = base / f"invocation-{ordinal}.json"
        value = read(path, snapshots)
        if snapshots[path.absolute()] != digest(expected) or value != {
            k: v for k, v in call.items() if k != "artifactSha256"
        }:
            raise ValueError("atomic invocation differs from cached receipt")
        if (
            value.get("schema") != PROTOCOL
            or value.get("verifiedInputDigests") != row["inputDigests"]
        ):
            raise ValueError("invocation protocol/input mismatch")
        return base, value.get("childPid"), snapshots[path.absolute()]
    if call.get("invocationExecutionPhaseStarted") is True:
        path = base / f"invocation-{ordinal}-started.json"
        started = read(path, snapshots, 65536)
        if (
            started.get("invocationOrdinal") != ordinal
            or started.get("verifiedInputDigests") != row["inputDigests"]
        ):
            raise ValueError("started marker differs from admitted inputs")
        return base, started.get("childPid"), snapshots[path.absolute()]
    return base, None, None


def stages(registration):
    result = []
    for row in registration.get("recipeStages", registration.get("stageProvenance", [])):
        if not isinstance(row, dict):
            raise ValueError("invalid stage receipt")
        safe = {}
        for key in ("engine", "buildVersion", "engineVersion", "coordinateFrame", "status"):
            value = row.get(key)
            if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._/ -]{1,160}", value):
                safe[key] = value
        if row.get("settingsDigest") is not None:
            safe["settingsDigest"] = digest(row["settingsDigest"])
        safe["runtimeSeconds"] = number(row.get("runtimeSeconds"))
        result.append(safe)
    return result


def score(records):
    # Imported only during explicitly requested post-terminal evaluation; no fitting.
    from wsi_viewer.alignment_evaluation import evaluate_landmarks

    result = evaluate_landmarks(records, measure_approximate=True)
    return {
        key: result[key]
        for key in (
            "eligibleLandmarks",
            "observedLandmarks",
            "unsupportedLandmarks",
            "invalidLandmarks",
            "observedCoverage",
            "medianRelativeError",
            "p95RelativeError",
            "supportTierCounts",
            "supportMappingPolicy",
        )
    }


def build(campaign, manifest_path, source_head, evaluate=False):
    snapshots = {}
    manifest = read(manifest_path, snapshots)
    recipes = recipes_from_source()
    pairs = manifest.get("pairs", [])
    if (
        len(pairs) != 16
        or len(recipes) != 9
        or Counter(p["kind"] for p in pairs) != {"positive": 12, "negative": 4}
    ):
        raise ValueError("fixed 16x9 cohort required")
    eligible = sum(
        sum(p.get("eligible") is True for p in pair.get("landmarks", [])) for pair in pairs
    )
    if eligible != 947 or any(
        p.get("landmarks") and p.get("landmarksFitFree") is not True for p in pairs
    ):
        raise ValueError("947 fixed fit-free published landmarks required")
    if not re.fullmatch("[0-9a-f]{40}", source_head):
        raise ValueError("actual final full source HEAD required")
    if manifest.get("sourceAdmission", {}).get("sourceFreezeHead") != source_head:
        raise ValueError("manifest source freeze differs")
    module_hashes, registry = engine_identity(source_head)
    manifest_hash = snapshots[Path(manifest_path).absolute()]
    report_path = campaign / "report.json"
    report = read(report_path, snapshots) if report_path.is_file() else {"rows": []}
    if report_path.is_file() and report.get("schema") != PROTOCOL:
        raise ValueError("wrong campaign schema")
    indexed = {}
    for row in report["rows"]:
        key = row.get("pairIndex"), row.get("recipe")
        if key in indexed or key[0] not in range(16) or key[1] not in recipes:
            raise ValueError("duplicate/unplanned row")
        cached = read(campaign / "cache" / (digest(row["digest"]) + ".json"), snapshots)
        protocol = cached.get("protocol") or {}
        if (
            cached.get("digest") != row["digest"]
            or (cached.get("pairIndex"), cached.get("recipe")) != key
            or protocol.get("policy") != PROTOCOL
            or protocol.get("sourceHead") != source_head
            or protocol.get("frozenManifestSha256") != manifest_hash
            or protocol.get("plannedInvocations") != 2
            or protocol.get("memoryBytes") != 7 * 1024**3
            or protocol.get("sharedTotalSeconds") != 600
            or cached.get("inputDigests") != pairs[key[0]]["inputDigests"]
        ):
            raise ValueError("cache/manifest/protocol identity mismatch")
        indexed[key] = cached
    public_rows, scored, stage_rows, stage_scored = [], {}, [], {}
    for recipe in recipes:
        for pair_index, pair in enumerate(pairs):
            raw = indexed.get((pair_index, recipe))
            calls = {}
            if raw:
                for call in raw.get("invocations", []):
                    ordinal = call.get("invocationOrdinal")
                    if ordinal not in (1, 2) or ordinal in calls:
                        raise ValueError("duplicate/unplanned invocation ordinal")
                    calls[ordinal] = call
            proofs = {
                ordinal: artifact_proof(campaign, raw, call, snapshots)
                for ordinal, call in calls.items()
            }
            pids = [proofs.get(i, (None, None, None))[1] for i in (1, 2)]
            same_process = bool(
                all(type(p) is int and p > 0 for p in pids)
                and pids[0] == pids[1]
                and all(
                    (calls.get(i) or {}).get("invocationExecuted") is True
                    or (calls.get(i) or {}).get("invocationExecutionPhaseStarted") is True
                    for i in (1, 2)
                )
            )
            for ordinal in (1, 2):
                call = calls.get(ordinal)
                reg = ((call or {}).get("result") or {}).get("result") or {}
                if ((call or {}).get("result") or {}).get("ok") is not True:
                    reg = {}
                evidence = reg.get("evidence") or {}
                status = classification(call)
                rows = [
                    {**landmark, "referenceSize": pair["reference"]["size"], "registration": reg}
                    for landmark in pair.get("landmarks", [])
                ]
                # This frozen cohort is uncalibrated. Never infer Âµm from coordinate sizes.
                if any(r.get("referenceMicronsPerPixel") is not None for r in rows):
                    raise ValueError(
                        "unexpected calibrated cohort requires separate reviewed projection"
                    )
                scored.setdefault((recipe, ordinal), []).extend(rows)
                stage = stages(reg)
                proof = proofs.get(ordinal, (None, None, None))
                initializer = reg.get("initializerArtifact")
                initializer_hash = None
                initializer_map = None
                if initializer:
                    if initializer.get("name") != "initializer-coordinate-map.json":
                        raise ValueError("unexpected initializer basename")
                    path = proof[0] / f"invocation-{ordinal}" / initializer["name"]
                    initializer_map = read(path, snapshots, 16 * 1024**2)
                    initializer_hash = snapshots[path.absolute()]
                    if initializer_hash != digest(initializer.get("sha256")):
                        raise ValueError("initializer provenance mismatch")
                public = {
                    "pairOrdinal": pair_index + 1,
                    "recipe": recipe,
                    "invocationOrdinal": ordinal,
                    "pairKind": pair["kind"],
                    "outcome": status,
                    "invocationExecuted": (call or {}).get("invocationExecuted"),
                    "invocationReceiptPresent": call is not None,
                    "atomicReceiptSha256": (call or {}).get("artifactSha256"),
                    "invocationProofSha256": proof[2],
                    "sameContainedProcessProven": same_process,
                    "temperatureScope": "first-in-contained-process"
                    if ordinal == 1
                    else "same-contained-process-repeat"
                    if same_process
                    else "repeat-process-identity-unverified",
                    "invocationWallSeconds": number((call or {}).get("invocationWallSeconds")),
                    "inputAdmissionSeconds": number((call or {}).get("inputAdmissionSeconds")),
                    "childStartupSeconds": number((call or {}).get("childStartupSeconds")),
                    "grantedRemainingBudgetSeconds": number(
                        (call or {}).get("grantedRemainingBudgetSeconds")
                    ),
                    "preparationSeconds": number(evidence.get("preparationSeconds")),
                    "computeSeconds": number(evidence.get("computeSeconds")),
                    "registrationStatus": reg.get("status")
                    if reg.get("status") in {"ready", "approximate", "needs_refinement", "failed"}
                    else None,
                    "registrationCanonicalSha256": sha(canonical(reg)) if reg else None,
                    "requestedSettingsCanonicalSha256": sha(canonical(raw["requestedSettings"]))
                    if raw
                    else None,
                    "requestedSettingsDigest": settings_identity(
                        recipe, raw["requestedSettings"], registry
                    )
                    if raw
                    else None,
                    "engineBuildVersion": registry["ENGINE_VERSIONS"][recipe],
                    "adapterVersion": registry["ADAPTER_VERSIONS"][recipe],
                    "effectiveSettingsCanonicalSha256": sha(canonical(reg["engineSettings"]))
                    if isinstance(reg.get("engineSettings"), dict)
                    else None,
                    "effectiveSettingsDigest": settings_identity(
                        recipe, reg["engineSettings"], registry
                    )
                    if isinstance(reg.get("engineSettings"), dict)
                    else None,
                    "runtimeIdentityCanonicalSha256": sha(
                        canonical(raw["protocol"].get("runtimeIdentity"))
                    )
                    if raw
                    else None,
                    "pairRecipeDigest": raw["digest"] if raw else None,
                    "initializerArtifactSha256": initializer_hash,
                    "registeredInputDigests": [digest(v) for v in pair["inputDigests"]],
                    "stageReceipts": stage,
                    "stageReceiptsCanonicalSha256": sha(canonical(stage)) if stage else None,
                    "supervisedPairWallSeconds": number(raw.get("supervisedTotalWallSeconds"))
                    if raw
                    else None,
                    "sharedPairAdmissionSeconds": number(raw.get("admissionSeconds"))
                    if raw
                    else None,
                    "sharedSupervisorFailureCategory": classification(
                        {"invocationExecuted": True, "result": raw["supervisorFailure"]}
                    )
                    if raw and raw.get("supervisorFailure")
                    else None,
                    "pairResourceMetrics": {
                        k: number((raw.get("resourceMetrics") or {}).get(k)) for k in MEMORY_KEYS
                    }
                    if raw
                    else None,
                    "memoryMeasurementScope": ((raw or {}).get("resourceMetrics") or {}).get(
                        "memoryMeasurementScope"
                    )
                    if ((raw or {}).get("resourceMetrics") or {}).get("memoryMeasurementScope")
                    in {
                        "windows-job-sampled-working-set",
                        "root_process_sampled_working_set",
                        "linux-process-tree-sampled-rss",
                        "linux-owned-session-sampled-rss",
                    }
                    else None,
                    "terminalContainmentVerified": raw.get("terminalContainmentVerified") is True
                    if raw
                    else None,
                    "negativeAcceptedMapRequiresIndependentReview": pair["kind"] == "negative"
                    and status == "accepted-supported-map",
                    "landmarkMetrics": score(rows)
                    if evaluate and pair.get("landmarks")
                    else {
                        "eligibleLandmarks": sum(
                            p.get("eligible") is True for p in pair.get("landmarks", [])
                        ),
                        "observedLandmarks": None,
                        "observedCoverage": None,
                        "medianRelativeError": None,
                        "p95RelativeError": None,
                        "reason": "post-terminal-evaluation-not-requested"
                        if not evaluate
                        else "no-published-positive-ground-truth",
                    },
                    "anatomicalReview": None,
                    "humanCorrectionEffort": None,
                    "qualified": False,
                }
                public_rows.append(public)
                if recipe in STAGES:
                    measured, private_maps = measurement(
                        initializer_map, reg, pair, recipe, evaluate=evaluate
                    )
                    stage_row = {
                        k: public[k]
                        for k in (
                            "pairOrdinal",
                            "recipe",
                            "invocationOrdinal",
                            "registrationCanonicalSha256",
                            "initializerArtifactSha256",
                            "stageReceipts",
                            "stageReceiptsCanonicalSha256",
                        )
                    }
                    stage_row["measurement"] = measured
                    stage_rows.append(stage_row)
                    for variant in ("initializer", "applied"):
                        stage_scored.setdefault((recipe, ordinal, variant), []).extend(
                            {
                                **landmark,
                                "referenceSize": pair["reference"]["size"],
                                "registration": private_maps[variant],
                            }
                            for landmark in pair.get("landmarks", [])
                        )
    summaries = {}
    for recipe in recipes:
        summary = {}
        for ordinal in (1, 2):
            rows = [
                r
                for r in public_rows
                if r["recipe"] == recipe and r["invocationOrdinal"] == ordinal
            ]
            counts = Counter(r["outcome"] for r in rows)
            summary[str(ordinal)] = {
                "plannedPairInvocations": 16,
                "outcomeCounts": dict(sorted(counts.items())),
                "executedCount": sum(r["invocationExecuted"] is True for r in rows),
                "executionUnknownCount": sum(r["invocationExecuted"] is None for r in rows),
                "sameContainedProcessProvenPairs": sum(
                    r["sameContainedProcessProven"] for r in rows
                ),
                "negativeAcceptedMapsPendingReview": sum(
                    r["negativeAcceptedMapRequiresIndependentReview"] for r in rows
                ),
                "timings": {
                    key: metric([r[key] for r in rows])
                    for key in (
                        "invocationWallSeconds",
                        "inputAdmissionSeconds",
                        "preparationSeconds",
                        "computeSeconds",
                    )
                },
                "landmarkMetrics": score(scored[recipe, ordinal])
                if evaluate
                else {
                    "eligibleLandmarks": 947,
                    "observedLandmarks": None,
                    "observedCoverage": None,
                    "reason": "post-terminal-evaluation-not-requested",
                },
            }
        # Shared resources are measured once per two-call supervisor, never per call.
        chosen = [r for r in public_rows if r["recipe"] == recipe and r["invocationOrdinal"] == 1]
        summary["supervisedPairWallSeconds"] = metric(
            [r["supervisedPairWallSeconds"] for r in chosen]
        )
        summary["sharedPairAdmissionSeconds"] = metric(
            [r["sharedPairAdmissionSeconds"] for r in chosen]
        )
        summary["sharedPairResourceMetrics"] = {
            k: metric([(r["pairResourceMetrics"] or {}).get(k) for r in chosen])
            for k in MEMORY_KEYS
        }
        summary["sharedSupervisorFailureCounts"] = dict(
            sorted(
                Counter(
                    r["sharedSupervisorFailureCategory"]
                    for r in chosen
                    if r["sharedSupervisorFailureCategory"]
                ).items()
            )
        )
        summaries[recipe] = summary
    result = {
        "schema": "pathlab.same-process-warm-observations/1",
        "sourceFreezeHead": source_head,
        "sourceModulesGitBlobSha256": module_hashes,
        "manifestSha256": manifest_hash,
        "rawReportSha256": snapshots.get(report_path.absolute()),
        "projectionScriptSha256": sha(Path(__file__).read_bytes()),
        "plannedPairRecipes": 144,
        "presentPairRecipes": len(indexed),
        "plannedInvocations": 288,
        "rows": public_rows,
        "recipes": summaries,
        "executedInvocations": sum(r["invocationExecuted"] is True for r in public_rows),
        "executionUnknownInvocations": sum(r["invocationExecuted"] is None for r in public_rows),
        "missingOrdinalCount": sum(not r["invocationReceiptPresent"] for r in public_rows),
        "plannedEligibleLandmarksPerRecipePerOrdinal": 947,
        "landmarkEvaluationPerformed": evaluate,
        "sharedPairBudgetSeconds": 600,
        "sharedPairMemoryBytes": 7 * 1024**3,
        "stageContribution": {
            "rows": stage_rows,
            "plannedHybridPairInvocations": 96,
            "projectionHelperSha256": sha(
                (Path(__file__).parent / "alignment_warm_report_stage.py").read_bytes()
            ),
            "evaluationPerformed": evaluate,
            "recipes": {
                recipe: {
                    str(ordinal): {
                        "plannedEligibleLandmarks": 947,
                        "initializerEngineOutputMetrics": score(
                            stage_scored[recipe, ordinal, "initializer"]
                        )
                        if evaluate
                        else None,
                        "appliedAffineOnOwnSupportMetrics": score(
                            stage_scored[recipe, ordinal, "applied"]
                        )
                        if evaluate
                        else None,
                        "pairedCommonSupportMetricsScope": (
                            "per-pair rows; quantiles of different pairs are not averaged"
                        ),
                        "stageAvailabilityCounts": dict(
                            sorted(
                                Counter(
                                    r["measurement"].get("reason") or "measured"
                                    for r in stage_rows
                                    if r["recipe"] == recipe and r["invocationOrdinal"] == ordinal
                                ).items()
                            )
                        ),
                    }
                    for ordinal in (1, 2)
                }
                for recipe in STAGES
            },
            "accuracyComparison": "per-pair identical-common-support deltas" if evaluate else None,
            "reason": None if evaluate else "post-terminal-evaluation-not-requested",
            "residualFrameAccuracy": None,
            "qualificationEvidence": False,
        },
        "qualification": {
            "qualified": False,
            "fastWinner": None,
            "accurateWinner": None,
            "calibratedMicrometerAccuracy": None,
            "anatomicalReview": None,
            "humanCorrectionEffort": None,
            "queueSeconds": None,
            "browserApplicationSeconds": None,
            "retainedModelTemperature": "UNVERIFIED",
            "decodedInputCacheState": "UNVERIFIED",
            "hostFilesystemCacheState": "unmeasured",
        },
        "scope": (
            "first-call versus same-contained-process repeat; invocation wall excludes its "
            "input admission and includes engine preparation/compute; shared supervisor includes "
            "startup/both calls/cleanup; no API queue/browser or human effort measurement"
        ),
        "errorComparisonScope": (
            "each map own supported published-landmark subset; planned947 denominator includes "
            "missing/rejected/unsupported; differing supports are not an accuracy winner"
        ),
        "rawReceiptsMutated": False,
    }
    privacy(result)
    for path, expected in snapshots.items():
        verified = {}
        read(path, verified)
        if verified[path] != expected:
            raise ValueError("raw input changed during projection")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evaluate-landmarks", action="store_true")
    args = parser.parse_args()
    output = args.output.absolute()
    if (
        output.exists()
        or output.resolve() != output
        or not output.is_relative_to(ROOT / "var")
        or any(p.is_symlink() or p.is_junction() for p in (output, *output.parents))
    ):
        raise ValueError("fresh ignored output only; publish the sanitized projection separately")
    report = build(
        args.campaign.absolute(),
        args.manifest.absolute(),
        args.source_head,
        args.evaluate_landmarks,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(
            (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
        )
    print(
        json.dumps(
            {
                "plannedInvocations": 288,
                "presentPairRecipes": report["presentPairRecipes"],
                "qualified": False,
                "reportSha256": sha(output.read_bytes()),
            }
        )
    )


if __name__ == "__main__":
    main()
