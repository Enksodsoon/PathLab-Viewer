"""Project completed private alignment receipts into reproducible public observations.

Reads existing receipts only. No registration, fitting, review inference or map
promotion occurs. Coordinates, source paths, weights and freeform diagnostics
remain private. Selection follows the independently approved safe expansion
policy; the original calibrated qualification gates stay unchanged.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np
from wsi_viewer.alignment import AlignmentRejected, map_registration_point
from wsi_viewer.alignment_benchmark import _pair_settings, _safe_resource_metrics
from wsi_viewer.alignment_engines import (
    ENGINE_ALIASES,
    INITIALIZER_ARTIFACT_NAME,
    MAX_INITIALIZER_ARTIFACT_BYTES,
    RECIPE_STAGES,
)
from wsi_viewer.alignment_evaluation import evaluate_landmarks


def public_cache_preparation(value):
    if not isinstance(value, dict):
        return None
    result = {
        "policy": "process-cold-generated-regional-cache-empty/1",
        "performed": value.get("performed") is True,
        "hostFilesystemCacheState": "unmeasured",
        "sourceKindCounts": {},
    }
    for key in ("wallSeconds", "removedFileCount", "removedBytes"):
        measured = value.get(key)
        result[key] = (
            measured
            if isinstance(measured, (int, float))
            and not isinstance(measured, bool)
            and math.isfinite(measured)
            and measured >= 0
            else None
        )
    counts = value.get("sourceKindCounts", {})
    if isinstance(counts, dict):
        result["sourceKindCounts"] = {
            key: count
            for key, count in counts.items()
            if key
            in {
                "openslide-original",
                "verified-openslide-candidate",
                "copied-dzi",
                "copied-dzi-incomplete",
                "unavailable",
            }
            and type(count) is int
            and count >= 0
        }
    return result


def classify(root, digest, outcome, attempt="cold"):
    if outcome == "ok":
        return "accepted-map"
    if outcome == "unavailable":
        return "unavailable-resource"
    path = Path(root) / "diagnostics" / f"{digest}.json"
    if not path.is_file():
        return "unknown-failure"
    detail = json.loads(path.read_text())
    items = [p for p in detail.get("attempts", []) if p.get("attempt") == attempt]
    detail = items[-1] if items else (detail if attempt == "cold" else {})
    message = str(detail.get("message", "")).lower()
    kind = str(detail.get("exceptionType", ""))
    if any(x in message for x in ["timeout", "time budget", "pair budget", "time ceiling"]):
        return "bounded-timeout"
    if any(
        x in message
        for x in [
            "memory ceiling",
            "memory budget",
            "memory limit",
            "memory allocation",
            "out of memory",
        ]
    ):
        return "bounded-memory-failure"
    if "image ceiling" in message:
        return "bounded-image-ceiling"
    if any(
        x in message for x in ["[winerror", "being used by another process", "permission denied"]
    ):
        return "upstream-or-runtime-failure"
    if any(
        x in message
        for x in [
            "process ended without",
            "missing-validation-evidence",
            "did not produce validation evidence",
            "upstream registration failed",
            "not installed",
            "unavailable",
        ]
    ):
        return "upstream-or-runtime-failure"
    if kind not in {"AlignmentRejected", "RejectedRegistration"}:
        return "upstream-or-runtime-failure"
    anatomical = [
        "insufficient tissue",
        "no moving tissue support",
        "insufficient distributed tissue support",
        "whole-tissue overlap validation",
        "tissue support or round-trip validation",
        "no non-folded supported cells",
        "no accepted component correspondence",
        "no accepted local feature correspondence",
        "too few",
        "not enough",
        "insufficient matches",
        "insufficient feature matches",
        "no reliable",
        "no corresponding",
        "unreliable alignment",
        "no partial component proposals",
        "needs refinement",
        "no overlapping",
        "nonlinear inverse rejected a folded",
        "invalid forward coordinates",
        "invalid inverse coordinates",
        "stable affine overview",
    ]
    if any(x in message for x in anatomical):
        return "structural-or-correspondence-rejection"
    return "unknown-failure"


def negative_review_value(category):
    if category == "accepted-map":
        return True
    if category == "structural-or-correspondence-rejection":
        return False
    return None


POLICY = {
    "version": "reviewed-safe-expansion/1",
    "approvedBeforeResumedComparisons": True,
    "maximumRecipes": 4,
    "negativePolicy": (
        "all planned cold and fresh-repeat negatives must have reviewed structural rejection; "
        "an accepted cold absent-organ map is unsafe; an accepted repeat without persisted map "
        "has unknown map review and is excluded; any resource/runtime/unknown negative failure "
        "is unresolved"
    ),
    "positivePolicy": (
        "execution failures stay planned landmark denominator and failure rate; "
        "do not exclude entire recipe solely for per-pair positive failures"
    ),
    "ranking": [
        "observed-landmark-coverage-descending",
        "relative-or-micrometer-p95-ascending",
        "supervised-wall-p95-ascending",
    ],
    "qualification": (
        "unchanged calibrated gates; advancement is research observation, "
        "never qualification or activation"
    ),
}


def select(report, rows):
    if not report.get("screening"):
        return [], {}
    decisions = {}
    eligible = []
    for recipe, metrics in report["recipes"].items():
        selected = [r for r in rows if r["recipe"] == recipe]
        negatives = [r for r in selected if r["kind"] == "negative"]
        reasons = []
        if len(selected) != 16 or len(negatives) != 4:
            reasons.append("incomplete-planned-screening")
        if any(len(n.get("repeatComputeReceipts") or []) != 1 for n in negatives):
            reasons.append("missing-planned-negative-repeat-receipt")
        if metrics.get("eligibleLandmarks", 0) <= 0:
            reasons.append("independent-positive-ground-truth-unavailable")
        if metrics.get("missingNegativeReviews", 0):
            reasons.append("missing-independent-negative-review")
        if metrics.get("confidentWrongStructurePairs", 0):
            reasons.append("accepted-wrong-structure-negative")
        if selected and all(r["outcome"] == "unavailable" for r in selected):
            reasons.append("global-runtime-unavailable")
        all_negative_categories = [n["failureCategory"] for n in negatives] + [
            r["failureCategory"] for n in negatives for r in n.get("repeatComputeReceipts", [])
        ]
        if any(n["failureCategory"] == "accepted-map" for n in negatives):
            reasons.append("accepted-absent-organ-negative-cold")
        if any(
            r["failureCategory"] == "accepted-map"
            for n in negatives
            for r in n.get("repeatComputeReceipts", [])
        ):
            reasons.append("repeat-negative-map-review-unavailable")
        if any(
            c not in ["structural-or-correspondence-rejection", "accepted-map"]
            for c in all_negative_categories
        ):
            reasons.append("unresolved-negative-resource-or-runtime-failure")
        decisions[recipe] = {
            "eligibleForUnqualifiedExpansion": not reasons,
            "exclusionReasons": sorted(set(reasons)),
            "positiveFailureCategories": {},
        }
        for row in selected:
            if row["kind"] == "positive" and row["failureCategory"] != "accepted-map":
                counts = decisions[recipe]["positiveFailureCategories"]
                counts[row["failureCategory"]] = counts.get(row["failureCategory"], 0) + 1
        if not reasons:
            key = "p95ErrorUm" if metrics.get("rankingErrorUnit") == "um" else "p95RelativeError"
            eligible.append(
                (
                    recipe,
                    (
                        -metrics.get("observedCoverage", 0),
                        metrics.get(key) if metrics.get(key) is not None else float("inf"),
                        metrics.get("coldRuntimeP95Seconds")
                        if metrics.get("coldRuntimeP95Seconds") is not None
                        else float("inf"),
                    ),
                )
            )
    return [r for r, _ in sorted(eligible, key=lambda item: item[1])[:4]], decisions


METRICS = [
    "eligibleLandmarks",
    "invalidLandmarks",
    "unsupportedLandmarks",
    "observedLandmarks",
    "approximateLandmarks",
    "relativeLandmarks",
    "medianRelativeError",
    "p95RelativeError",
    "medianErrorUm",
    "p95ErrorUm",
    "coverage",
    "observedCoverage",
    "calibratedCoverage",
    "readyQualified",
    "benchmarkQualified",
    "qualified",
    "missingNegativeReviews",
    "confidentWrongStructurePairs",
    "negativePairs",
    "positivePairs",
    "plannedPairs",
    "missingGroundTruthPairs",
    "manualOnlyPairs",
    "manualCorrectionEffort",
    "manualAssistance",
]


def percentile(values, q):
    return float(np.percentile(values, q)) if values else None


def safe_digest(value):
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
    ):
        raise ValueError("registration digest must be a lowercase SHA256 basename")
    return value


def public_stage(stage):
    """Expose physical metadata without numeric origins or nested private geometry."""
    result = {
        key: stage[key]
        for key in [
            "engine",
            "engineVersion",
            "buildVersion",
            "settingsDigest",
            "status",
            "coordinateFrame",
        ]
        if isinstance(stage.get(key), str)
    }
    runtime = stage.get("runtimeSeconds")
    if (
        isinstance(runtime, (int, float))
        and not isinstance(runtime, bool)
        and math.isfinite(runtime)
    ):
        result["runtimeSeconds"] = runtime
    for key in [
        "referenceMicronsPerPixel",
        "movingMicronsPerPixel",
        "referenceScale",
        "movingScale",
    ]:
        value = stage.get(key)
        if (
            isinstance(value, (list, tuple))
            and len(value) == 2
            and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(item)
                and item > 0
                for item in value
            )
        ):
            result[key] = list(value)
    return result


def independent_map_reviews(root, manifest_sha256):
    result = {}
    for name in ["independent-negative-map-reviews.json", "independent-positive-map-reviews.json"]:
        path = root / name
        if not path.is_file():
            continue
        value = json.loads(path.read_text())
        if manifest_sha256 is None or value.get("sourceManifestSha256") != manifest_sha256:
            raise ValueError("independent map reviews require the matching frozen source manifest")
        for item in value.get("reviews", []):
            accepted_flag = type(item.get("wrongStructure")) is bool
            uncertain_positive = (
                name == "independent-positive-map-reviews.json"
                and item.get("wrongStructure") is None
                and item.get("reviewStatus") == "uncertain / visualization insufficient"
            )
            if (
                item.get("attempt") == "cold"
                and item.get("reviewerConfirmed") is True
                and item.get("independentActualMapReviewConfirmed") is True
                and (accepted_flag or uncertain_positive)
            ):
                result[
                    (item.get("recipe"), item.get("pairIndex"), item.get("registrationDigest"))
                ] = item
    return result


def summarize(report, root, *, manifest_sha256=None, memory_scope="unrecorded"):
    independent_reviews = independent_map_reviews(root, manifest_sha256)
    public_rows = []
    for row in report["rows"]:
        safe_digest(row["digest"])
        receipt = json.loads((root / "cache" / f"{row['digest']}.json").read_text())
        registration = receipt.get("registration", {})
        evidence = registration.get("evidence", {})
        resources = _safe_resource_metrics(receipt.get("resourceMetrics", {}))
        row_memory_scope = resources.get("memoryMeasurementScope", memory_scope)
        stages = [public_stage(stage) for stage in registration.get("recipeStages", [])]
        review = independent_reviews.get((row["recipe"], row["pairIndex"], row["digest"]), {})
        public_rows.append(
            {
                **{
                    k: row.get(k)
                    for k in [
                        "pairIndex",
                        "recipe",
                        "digest",
                        "kind",
                        "outcome",
                        "reasonCode",
                        "coldRuntimeSeconds",
                        "peakMemoryBytes",
                        "cached",
                        "manualAssistance",
                        "manualCorrectionEffort",
                    ]
                },
                **(
                    {
                        "cachePreparation": public_cache_preparation(
                            receipt.get("cachePreparation")
                        ),
                        "runtimeCoreSeconds": receipt.get("runtimeCoreSeconds"),
                        "inputAdmissionSeconds": receipt.get("inputAdmissionSeconds"),
                        "grantedChildBudgetSeconds": receipt.get("grantedChildBudgetSeconds"),
                        "requestedTotalBudgetSeconds": receipt.get("requestedTotalBudgetSeconds"),
                        "containmentCleanupSeconds": None,
                        "supervisedChildExecutionSeconds": None,
                        "runtimeCoreScope": (
                            "supervised-child-startup-execution-and-mandatory-containment-cleanup"
                        ),
                        "endToEndPreparationAndRuntimeSeconds": receipt.get(
                            "endToEndPreparationAndRuntimeSeconds"
                        ),
                        "coldTimingScope": (
                            "process-cold-generated-regional-cache-empty-"
                            "host-filesystem-cache-unmeasured"
                        ),
                    }
                    if "cachePreparation" in receipt
                    else {}
                ),
                "landmarkMetrics": {
                    k: row.get("landmarkMetrics", {}).get(k)
                    for k in METRICS
                    if k in row.get("landmarkMetrics", {})
                },
                "repeatComputeReceipts": [
                    {
                        **{
                            k: r.get(k)
                            for k in ["runtimeSeconds", "outcome", "peakMemoryBytes", "timingScope"]
                        },
                        "failureCategory": classify(
                            root, row["digest"], r["outcome"], f"repeat-{i}"
                        ),
                        "landmarkMetrics": None,
                        "mapReviewStatus": "unavailable / repeat map not persisted"
                        if r["outcome"] == "ok"
                        else "no-accepted-map",
                        "resourceMetrics": _safe_resource_metrics(r.get("resourceMetrics", {})),
                        "peakMemoryMeasurementScope": r.get("resourceMetrics", {}).get(
                            "memoryMeasurementScope", row_memory_scope
                        ),
                        "effectiveSettingsDigest": r.get("effectiveSettingsDigest"),
                    }
                    for i, r in enumerate(row.get("repeatComputeReceipts", []))
                ],
                "registrationStatus": registration.get("status"),
                "peakMemoryMeasurementScope": row_memory_scope,
                "resourceMetrics": resources,
                "effectiveSettingsDigest": receipt.get("effectiveSettingsDigest"),
                "requestedSettingsDigest": receipt.get("settingsDigest"),
                "engineBuild": receipt.get("engineBuild"),
                "runtimeVersions": receipt.get("runtimeVersions"),
                "confidence": registration.get("confidence"),
                "wrongStructure": review.get("wrongStructure", row.get("wrongStructure")),
                "reviewerConfirmed": bool(review),
                "reviewStatus": "uncertain / visualization insufficient"
                if review.get("reviewStatus") == "uncertain / visualization insufficient"
                else ("confirmed" if review else "not-confirmed"),
                "anatomicalCorrespondenceConfirmed": review.get(
                    "anatomicalCorrespondenceConfirmed"
                ),
                "acceptedRepeatMapSafetyUnknownCount": sum(
                    r.get("outcome") == "ok" for r in row.get("repeatComputeReceipts", [])
                )
                if row["kind"] == "negative"
                else 0,
                "failureCategory": classify(root, row["digest"], row["outcome"]),
                "adapterRuntimeSeconds": registration.get("runtimeSeconds"),
                "supervisorOutsideAdapterSeconds": max(
                    0.0,
                    row.get("runtimeCoreSeconds", row["coldRuntimeSeconds"])
                    - registration["runtimeSeconds"],
                )
                if row.get("coldRuntimeSeconds") is not None
                and registration.get("runtimeSeconds") is not None
                else None,
                "preparationSeconds": evidence.get("preparationSeconds"),
                "queueLatencySeconds": None,
                "browserLatencySeconds": None,
                "warmWorkerRuntimeSeconds": None,
                "stageTimestamps": [
                    {k: event.get(k) for k in ["stage", "elapsedSeconds"]}
                    for event in row.get("stageTimings", [])
                ],
                "recipeStages": stages,
            }
        )
    recipes = {}
    for recipe, original in report["recipes"].items():
        rows = [r for r in public_rows if r["recipe"] == recipe]
        cold = [r["coldRuntimeSeconds"] for r in rows if r["coldRuntimeSeconds"] is not None]
        memory = [r["peakMemoryBytes"] for r in rows if r["peakMemoryBytes"] is not None]
        repeats = [r for row in rows for r in row["repeatComputeReceipts"]]
        repeat_times = [r["runtimeSeconds"] for r in repeats if r["runtimeSeconds"] is not None]
        repeat_memory = [r["peakMemoryBytes"] for r in repeats if r["peakMemoryBytes"] is not None]
        committed = [
            r["resourceMetrics"]["peakCommittedMemoryBytes"]
            for r in rows
            if "peakCommittedMemoryBytes" in r["resourceMetrics"]
        ]
        measured_scopes = sorted({r["peakMemoryMeasurementScope"] for r in rows})
        recipes[recipe] = {
            **{k: original.get(k) for k in METRICS},
            "outcomes": dict(Counter(r["outcome"] for r in rows)),
            "reviewedWrongStructurePairs": sum(
                r["reviewerConfirmed"] and r["wrongStructure"] is True for r in rows
            ),
            "acceptedNegativeColdMapsWithoutConfirmedReview": sum(
                r["kind"] == "negative" and r["outcome"] == "ok" and not r["reviewerConfirmed"]
                for r in rows
            ),
            "acceptedRepeatMapSafetyUnknownCount": sum(
                r["acceptedRepeatMapSafetyUnknownCount"] for r in rows
            ),
            "failureCategories": dict(Counter(r["failureCategory"] for r in rows)),
            "coldRuntimeMedianSeconds": percentile(cold, 50),
            "coldRuntimeP95Seconds": percentile(cold, 95),
            "coldTimingMeasuredPairs": len(cold),
            "freshRepeatRuntimeMedianSeconds": percentile(repeat_times, 50),
            "freshRepeatRuntimeP95Seconds": percentile(repeat_times, 95),
            "freshRepeatOutcomes": dict(Counter(r["outcome"] for r in repeats)),
            "freshRepeatFailureCategories": dict(Counter(r["failureCategory"] for r in repeats)),
            "peakMemoryMedianBytes": percentile(memory, 50),
            "peakMemoryP95Bytes": percentile(memory, 95),
            "peakMemoryMeasuredPairs": len(memory),
            "peakMemoryMeasurementScope": measured_scopes[0]
            if len(measured_scopes) == 1
            else ("mixed-scopes" if measured_scopes else memory_scope),
            "peakMemoryMeasurementScopes": measured_scopes,
            "peakCommittedMemoryMedianBytes": percentile(committed, 50),
            "peakCommittedMemoryP95Bytes": percentile(committed, 95),
            "peakCommittedMemoryMeasuredPairs": len(committed),
            "freshRepeatPeakMemoryMedianBytes": percentile(repeat_memory, 50),
            "freshRepeatPeakMemoryP95Bytes": percentile(repeat_memory, 95),
            "queueLatencySeconds": None,
            "browserLatencySeconds": None,
            "warmWorkerRuntimeSeconds": None,
        }
        if any("cachePreparation" in row for row in rows):
            core = [
                row["runtimeCoreSeconds"]
                for row in rows
                if row.get("runtimeCoreSeconds") is not None
            ]
            prep = [
                row["cachePreparation"]["wallSeconds"]
                for row in rows
                if row.get("cachePreparation", {}).get("wallSeconds") is not None
            ]
            recipes[recipe].update(
                runtimeCoreMedianSeconds=percentile(core, 50),
                runtimeCoreP95Seconds=percentile(core, 95),
                cachePreparationMedianSeconds=percentile(prep, 50),
                cachePreparationP95Seconds=percentile(prep, 95),
                cacheRemovedFileCount=sum(
                    row.get("cachePreparation", {}).get("removedFileCount") or 0 for row in rows
                ),
                cacheRemovedBytes=sum(
                    row.get("cachePreparation", {}).get("removedBytes") or 0 for row in rows
                ),
            )
    finalists, decisions = select(report, public_rows)
    winners = {
        role: winner
        if not report.get("screening")
        or decisions.get(winner, {}).get("eligibleForUnqualifiedExpansion", False)
        else None
        for role, winner in report["winners"].items()
    }
    winner_review = {
        role: {
            "originalBenchmarkWinner": winner,
            "reportedWinner": winners[role],
            "suppressed": winner != winners[role],
            "suppressionReasons": decisions.get(winner, {}).get(
                "exclusionReasons", ["reviewed-safety-eligibility-unavailable"]
            )
            if winner != winners[role]
            else [],
            "scope": "reviewed-negative-cold-and-fresh-repeat-safety-policy",
        }
        for role, winner in report["winners"].items()
    }
    for recipe, metrics in recipes.items():
        safety = decisions.get(recipe, {}).get("eligibleForUnqualifiedExpansion")
        metrics["reviewedSafetyEligible"] = safety
        metrics["reviewedBenchmarkQualified"] = (
            bool(metrics.get("benchmarkQualified") and safety)
            if report.get("screening")
            else metrics.get("benchmarkQualified")
        )
    start_path = root / "process-start.json"
    start = json.loads(start_path.read_text()) if start_path.is_file() else {}
    safety_totals = {
        key: sum(metrics[key] for metrics in recipes.values())
        for key in [
            "reviewedWrongStructurePairs",
            "acceptedNegativeColdMapsWithoutConfirmedReview",
            "acceptedRepeatMapSafetyUnknownCount",
        ]
    }
    return {
        **safety_totals,
        "sourceFreeze": start.get("sourceFreeze"),
        "sourceManifestSha256": manifest_sha256,
        "campaignStartedAt": start.get("startedAt"),
        "reportingScriptSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "selectionPolicy": POLICY,
        "selectionDecisions": decisions,
        "expansionShortfall": max(0, 4 - len(finalists)) if report.get("screening") else None,
        "schema": "pathlab-public-campaign-observations/1",
        "screening": report["screening"],
        "recipes": recipes,
        "rows": public_rows,
        "finalists": finalists,
        "winners": winners,
        "winnerReview": winner_review,
        "qualificationGates": report["qualificationGates"],
        "timingScope": (
            "supervised-request-wall-time including child startup, image preparation, adapter, "
            "cleanup and supervisor; fresh process repeat; excludes queue/browser"
        ),
        "accuracyScope": (
            "fit-free landmarks where present; no accuracy claim for unscored development pairs"
        ),
    }


def paired_landmark_comparison(left, right, landmarks):
    """Measure saved maps on identical supported landmarks; expose aggregates only."""
    if not isinstance(left, dict) or not isinstance(right, dict):
        return {
            "status": "unmeasured",
            "reason": "saved-map-unavailable",
            "commonSupportedLandmarks": None,
            "onlyLeftSupportedLandmarks": None,
            "onlyRightSupportedLandmarks": None,
            "errorsByUnit": None,
        }
    groups = {}
    invalid = 0
    for record in landmarks:
        if record.get("eligible") is not True:
            continue
        try:
            moving = np.asarray(record["movingPoint"], dtype=float)
            reference = np.asarray(record["referencePoint"], dtype=float)
            if (
                moving.shape != (2,)
                or reference.shape != (2,)
                or not np.isfinite(moving).all()
                or not np.isfinite(reference).all()
            ):
                raise ValueError("invalid landmark coordinates")
            calibration = record.get("referenceMicronsPerPixel")
            if calibration is None:
                size = np.asarray(record["referenceSize"], dtype=float)
                if size.shape != (2,) or not np.isfinite(size).all() or np.any(size <= 0):
                    raise ValueError("invalid relative frame")
                scale = np.ones(2) / np.linalg.norm(size)
                unit = "reference-image-diagonal"
            else:
                scale = np.asarray(calibration, dtype=float)
                if scale.shape != (2,) or not np.isfinite(scale).all() or np.any(scale <= 0):
                    raise ValueError("invalid calibration")
                unit = "um"
            group = groups.setdefault(
                unit, {"left": [], "right": [], "onlyLeft": 0, "onlyRight": 0, "neither": 0}
            )

            def error(registration, moving=moving, reference=reference, scale=scale):
                approximate = registration.get("status") == "approximate"
                cells = registration.get("triangles") or (
                    registration.get("overviewTriangles") if approximate else []
                )
                if registration.get("status") not in ("ready", "approximate") or not cells:
                    return None
                try:
                    mapped = np.asarray(map_registration_point({"triangles": cells}, *moving))
                except AlignmentRejected:
                    return None
                value = float(np.linalg.norm((mapped - reference) * scale))
                if not np.isfinite(value):
                    raise ValueError("nonfinite saved-map coordinates")
                return value

            left_error, right_error = error(left), error(right)
            if left_error is not None and right_error is not None:
                group["left"].append(left_error)
                group["right"].append(right_error)
            elif left_error is not None:
                group["onlyLeft"] += 1
            elif right_error is not None:
                group["onlyRight"] += 1
            else:
                group["neither"] += 1
        except (KeyError, TypeError, ValueError, IndexError):
            invalid += 1
    errors = {}
    for unit, group in groups.items():
        left_values, right_values = group["left"], group["right"]
        left_p95, right_p95 = percentile(left_values, 95), percentile(right_values, 95)
        errors[unit] = {
            "commonSupportedLandmarks": len(left_values),
            "onlyLeftSupportedLandmarks": group["onlyLeft"],
            "onlyRightSupportedLandmarks": group["onlyRight"],
            "neitherSupportedLandmarks": group["neither"],
            "medianPairedErrorDelta": percentile(
                [a - b for a, b in zip(left_values, right_values, strict=True)], 50
            ),
            "leftMedianErrorOnCommonSet": percentile(left_values, 50),
            "rightMedianErrorOnCommonSet": percentile(right_values, 50),
            "leftP95ErrorOnCommonSet": left_p95,
            "rightP95ErrorOnCommonSet": right_p95,
            "p95ErrorDeltaOnCommonSet": left_p95 - right_p95
            if left_p95 is not None and right_p95 is not None
            else None,
        }
    if not groups:
        return {
            "status": "unmeasured",
            "reason": "eligible-independent-landmarks-unavailable",
            "commonSupportedLandmarks": None,
            "onlyLeftSupportedLandmarks": None,
            "onlyRightSupportedLandmarks": None,
            "invalidLandmarks": invalid,
            "errorsByUnit": None,
        }
    return {
        "status": "measured" if groups else "unmeasured",
        "reason": None if groups else "eligible-independent-landmarks-unavailable",
        "commonSupportedLandmarks": sum(len(group["left"]) for group in groups.values()),
        "onlyLeftSupportedLandmarks": sum(group["onlyLeft"] for group in groups.values()),
        "onlyRightSupportedLandmarks": sum(group["onlyRight"] for group in groups.values()),
        "invalidLandmarks": invalid,
        "errorsByUnit": errors,
        "pairedErrorDeltaSign": "left-minus-right / negative-is-lower-error",
        "scope": "same-fit-free-published-landmarks-supported-by-both-saved-original-frame-maps",
        "fitPerformed": False,
        "qualificationEvidence": False,
    }


def pair_landmarks(pair, manifest, recipe):
    alias = next((a for a, b in ENGINE_ALIASES.items() if b == recipe), recipe)
    cohort = manifest.get("settings", {}).get(recipe, manifest.get("settings", {}).get(alias, {}))
    settings = _pair_settings(pair, recipe, cohort)
    return [
        {
            "referenceSize": pair["reference"]["size"],
            **(
                {"referenceMicronsPerPixel": settings["referenceMicronsPerPixel"]}
                if settings.get("referenceMicronsPerPixel") is not None
                else {}
            ),
            **landmark,
        }
        for landmark in pair.get("landmarks", [])
    ]


def saved_registration(root, row):
    if row is None or row.get("outcome") != "ok":
        return None
    safe_digest(row["digest"])
    return json.loads((root / "cache" / f"{row['digest']}.json").read_text()).get("registration")


def stage_metrics(root, row, pair, manifest):
    if row["recipe"] not in RECIPE_STAGES:
        return None
    safe_digest(row["digest"])
    path = root / "artifacts" / row["digest"] / INITIALIZER_ARTIFACT_NAME
    if any(candidate.is_symlink() for candidate in (path, path.parent, root / "artifacts")):
        raise ValueError("initializer sidecar symlinks are unsupported")
    if not path.is_file():
        return {"status": "unmeasured", "reason": "initializer-artifact-unavailable"}
    if path.stat().st_size > MAX_INITIALIZER_ARTIFACT_BYTES:
        raise ValueError("initializer sidecar exceeds ceiling")
    with path.open("rb") as source:
        content = source.read(MAX_INITIALIZER_ARTIFACT_BYTES + 1)
    if len(content) > MAX_INITIALIZER_ARTIFACT_BYTES:
        raise ValueError("initializer sidecar exceeds ceiling")
    digest = hashlib.sha256(content).hexdigest()
    receipt = json.loads((root / "cache" / f"{row['digest']}.json").read_text())
    descriptor = receipt.get("registration", {}).get("initializerArtifact")
    if descriptor is not None and (
        descriptor.get("name") != INITIALIZER_ARTIFACT_NAME or descriptor.get("sha256") != digest
    ):
        raise ValueError("initializer provenance differs from final receipt")
    initializer = json.loads(content)
    landmarks = pair_landmarks(pair, manifest, row["recipe"])
    if not landmarks:
        return {
            "status": "unscored",
            "reason": "independent-landmarks-unavailable",
            "initializerArtifactSha256": digest,
        }
    engine_metrics = evaluate_landmarks(
        [{**p, "registration": initializer} for p in landmarks], measure_approximate=True
    )
    # Keep exactly the engine's supported source cells; project their reference
    # vertices through the affine actually applied to image warping.
    affine = np.asarray(initializer.get("movingToReference"), dtype=float)
    applied = None
    projected = None
    if affine.shape == (2, 3) and np.isfinite(affine).all():
        projected = {"status": initializer.get("status")}
        for key in ["triangles", "overviewTriangles"]:
            projected[key] = [
                {
                    **cell,
                    "reference": (
                        np.asarray(cell["moving"]) @ affine[:, :2].T + affine[:, 2]
                    ).tolist(),
                }
                for cell in initializer.get(key, [])
            ]
        applied = evaluate_landmarks(
            [{**p, "registration": projected} for p in landmarks], measure_approximate=True
        )
    final = receipt.get("registration") if row.get("outcome") == "ok" else None
    return {
        "status": "measured",
        "initializerArtifactSha256": digest,
        "initializerCoordinateFrame": "original-moving-to-reference-level-zero",
        "initializerEngineOutputMetrics": engine_metrics,
        "appliedAffineProjectionWithinInitializerSupportedCellsMetrics": applied,
        "finalVsInitializerEngineOutputCommonLandmarkComparison": paired_landmark_comparison(
            final, initializer, landmarks
        ),
        "finalVsAppliedAffineProjectionCommonLandmarkComparison": paired_landmark_comparison(
            final, projected, landmarks
        ),
        "pairedComparisonDirection": (
            "left=final-hybrid / right=initializer-or-explicit-affine-projection"
        ),
        "appliedAffineScope": "only-initializer-engine-supported-source-cells",
        "wholeInitializerPiecewiseMapAppliedToWarp": False,
        "residualFrameAccuracy": None,
        "residualFrameAccuracyReason": (
            "warped-moving-reference-frame-is-not-original-source-frame"
        ),
    }


def hybrid_comparisons(report, root=None, manifest=None):
    indexed = {(r["recipe"], r["pairIndex"]): r for r in report["rows"]}
    results = []
    for row in report["rows"]:
        stages = RECIPE_STAGES.get(row["recipe"])
        if not stages or row["kind"] != "positive":
            continue
        combined = row.get("landmarkMetrics", {})
        originals = [indexed.get((stage, row["pairIndex"])) for stage in stages]
        metrics = [
            original.get("landmarkMetrics", {}) if original else None for original in originals
        ]
        key = (
            "p95ErrorUm"
            if combined.get("p95ErrorUm") is not None
            or any(m and m.get("p95ErrorUm") is not None for m in metrics)
            else "p95RelativeError"
        )
        coverage = "calibratedCoverage" if key == "p95ErrorUm" else "observedCoverage"

        def rank(m, coverage_metric=coverage, error_metric=key):
            return (
                -m.get(coverage_metric, 0),
                m.get(error_metric) if m.get(error_metric) is not None else float("inf"),
            )

        comparable = (
            all(m is not None and m.get("eligibleLandmarks", 0) > 0 for m in metrics)
            and combined.get("eligibleLandmarks", 0) > 0
        )
        improves = all(rank(combined) < rank(m) for m in metrics) if comparable else None
        median_key = "medianErrorUm" if key == "p95ErrorUm" else "medianRelativeError"
        landmarks = (
            pair_landmarks(manifest["pairs"][row["pairIndex"]], manifest, row["recipe"])
            if manifest is not None
            else []
        )
        final = saved_registration(root, row) if root is not None else None
        comparisons = []
        for stage, original, individual in zip(stages, originals, metrics, strict=True):
            if individual is None or not comparable:
                comparisons.append(
                    {
                        "individualRecipe": stage,
                        "status": "unmeasured",
                        "reason": "independent-individual-ground-truth-observation-unavailable",
                    }
                )
                continue

            def change(metric, combined=combined, individual=individual):
                left, right = combined.get(metric), individual.get(metric)
                return left - right if left is not None and right is not None else None

            coverage_gain = change(coverage)
            median_change = change(median_key)
            p95_change = change(key)
            hybrid_runtime = row.get("coldRuntimeSeconds")
            individual_runtime = original.get("coldRuntimeSeconds") if original else None
            runtime_change = (
                hybrid_runtime - individual_runtime
                if hybrid_runtime is not None and individual_runtime is not None
                else None
            )
            error_changes = [median_change, p95_change]
            measured = coverage_gain is not None and all(
                value is not None for value in error_changes
            )
            dominates = (
                bool(
                    coverage_gain >= 0
                    and all(value <= 0 for value in error_changes)
                    and (coverage_gain > 0 or any(value < 0 for value in error_changes))
                )
                if measured
                else None
            )
            if measured and coverage_gain > 0 and any(value > 0 for value in error_changes):
                classification = "coverage-gain-error-tradeoff"
            elif dominates:
                classification = "accuracy-pareto-improvement"
            elif (
                measured
                and coverage_gain <= 0
                and all(value >= 0 for value in error_changes)
                and (coverage_gain < 0 or any(value > 0 for value in error_changes))
            ):
                classification = "accuracy-pareto-regression"
            elif measured and coverage_gain == 0 and all(value == 0 for value in error_changes):
                classification = "equal-measured-accuracy"
            elif measured:
                classification = "mixed-accuracy-tradeoff"
            else:
                classification = "error-change-unmeasured"
            original_map = saved_registration(root, original) if root is not None else None
            comparisons.append(
                {
                    "individualRecipe": stage,
                    "status": "measured",
                    "coverageGain": coverage_gain,
                    "medianErrorChange": median_change,
                    "p95ErrorChange": p95_change,
                    "fullSubsetErrorComparisonScope": (
                        "each-method-own-supported-subset / not-paired-error-improvement"
                    ),
                    "supervisedWallTimeChangeSeconds": runtime_change,
                    "coveragePriorityRankingImproves": rank(combined) < rank(individual),
                    "accuracyParetoDominates": dominates,
                    "operationalParetoDominates": bool(dominates and runtime_change <= 0)
                    if dominates is not None and runtime_change is not None
                    else None,
                    "classification": classification,
                    "errorChangeSign": "negative-is-lower-error",
                    "runtimeChangeSign": "negative-is-faster",
                    "commonSupportedLandmarkErrorComparison": paired_landmark_comparison(
                        final, original_map, landmarks
                    ),
                    "pairedComparisonDirection": "left=hybrid / right=individual-method-output",
                }
            )
        results.append(
            {
                "pairIndex": row["pairIndex"],
                "hybridRecipe": row["recipe"],
                "hybridRegistrationDigest": row["digest"],
                "individualRecipes": list(stages),
                "individualRegistrationDigests": [
                    r.get("digest") if r else None for r in originals
                ],
                "errorMetric": key,
                "medianErrorMetric": median_key,
                "coverageMetric": coverage,
                "hybridMetrics": combined,
                "individualMetrics": metrics,
                "coveragePriorityRankingImprovesOnAllIndividualOutputs": improves,
                "perIndividualComparisons": comparisons,
                "qualificationEvidence": False,
                "scope": (
                    "individual-method-outputs-not-equivalent-to-initializer-stage-"
                    "or-clinical-qualification"
                ),
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, required=True, help="Private completed benchmark output"
    )
    parser.add_argument(
        "--output-dir", type=Path, required=True, help="Sanitized report destination"
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Optional frozen private manifest for original-frame stage evaluation",
    )
    parser.add_argument(
        "--memory-scope",
        choices=["unrecorded", "root_process_sampled_working_set", "descendant_tree_sampled_rss"],
        default="unrecorded",
        help="Scope established by independent supervisor review; never inferred from peak values",
    )
    args = parser.parse_args()
    root = args.directory.resolve()
    raw = json.loads((root / "report.json").read_text())
    manifest_bytes = args.manifest.read_bytes() if args.manifest else None
    result = summarize(
        raw,
        root,
        manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest()
        if manifest_bytes is not None
        else None,
        memory_scope=args.memory_scope,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "observations.json").write_text(
        json.dumps(result, indent=2, sort_keys=True), encoding="utf-8"
    )
    if args.manifest:
        manifest = json.loads(manifest_bytes)
        stage = {
            "schema": "pathlab-hybrid-stage-observations/1",
            "rows": [
                {
                    "pairIndex": row["pairIndex"],
                    "recipe": row["recipe"],
                    "registrationDigest": row["digest"],
                    "stageContribution": stage_metrics(
                        root, row, manifest["pairs"][row["pairIndex"]], manifest
                    ),
                }
                for row in raw["rows"]
                if row["recipe"] in RECIPE_STAGES
            ],
            "hybridVsIndividuals": hybrid_comparisons(raw, root, manifest),
        }
        (args.output_dir / "stage-contribution.json").write_text(
            json.dumps(stage, indent=2, sort_keys=True), encoding="utf-8"
        )
    print(
        json.dumps(
            {
                "rows": len(result["rows"]),
                "reviewedSafeFinalists": result["finalists"],
                "winners": result["winners"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
