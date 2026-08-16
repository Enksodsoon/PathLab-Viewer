"""Build the signed provisional capacity tier decision before final restoration."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from distributed_certification import validate_plan
from validate_sentinel_evidence import validate as validate_sentinel_evidence

JOURNEY_LIMITS = {
    "presenterSse": (250.0, False),
    "classroomControl": (500.0, False),
    "generalApi": (500.0, False),
    "staticTile": (500.0, True),
    "poster": (1500.0, True),
    "question": (2000.0, False),
}
OBSERVER_MAX_GAP_SECONDS = 15


def host_evidence_passes(
    plan: dict[str, Any],
    samples: list[dict[str, Any]],
    fault: dict[str, Any],
    merged_stages: list[dict[str, Any]] | None = None,
) -> bool:
    """Validate continuous host evidence, allowing only the bound recovery fault."""
    if len(samples) < 2:
        return False
    try:
        starts = [
            datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00"))
            for item in samples
        ]
        plan_start = datetime.fromtimestamp(plan["startEpochMs"] / 1000, starts[0].tzinfo)
        final = plan["stages"][-1]
        plan_end = datetime.fromtimestamp(
            final["transitionEndEpochMs"] / 1000,
            starts[0].tzinfo,
        )
        recovery_hold_start = datetime.fromtimestamp(
            final["holdStartEpochMs"] / 1000, starts[0].tzinfo
        )
        recovery_hold_end = datetime.fromtimestamp(final["holdEndEpochMs"] / 1000, starts[0].tzinfo)
        fault_start = datetime.fromisoformat(str(fault["startedAt"]).replace("Z", "+00:00"))
        fault_end = datetime.fromisoformat(str(fault["completedAt"]).replace("Z", "+00:00"))
        if not recovery_hold_start < fault_start <= fault_end <= recovery_hold_end:
            return False
        protected = {
            item["name"]: set(item.get("abortCauses", []))
            for item in (merged_stages or [])
            if item.get("outcome") == "protected-early-stop"
        }
        stage_windows = {
            item["name"]: (
                datetime.fromtimestamp(item["holdStartEpochMs"] / 1000, starts[0].tzinfo),
                datetime.fromtimestamp(item["holdEndEpochMs"] / 1000, starts[0].tzinfo),
            )
            for item in plan["stages"]
            if item["name"].startswith("breakpoint-")
        }

        def protected_at(timestamp: datetime, cause: str) -> bool:
            return any(
                cause in protected.get(name, set()) and begin <= timestamp <= end
                for name, (begin, end) in stage_windows.items()
            )

        if starts != sorted(starts) or len(set(starts)) != len(starts):
            return False
        if abs((plan_start - starts[0]).total_seconds()) > OBSERVER_MAX_GAP_SECONDS:
            return False
        if abs((starts[-1] - plan_end).total_seconds()) > OBSERVER_MAX_GAP_SECONDS:
            return False
        if any(
            (right - left).total_seconds() > OBSERVER_MAX_GAP_SECONDS
            for left, right in zip(starts, starts[1:], strict=False)
        ):
            return False
        if any(item.get("releaseSha") != plan["workflowSha"] for item in samples):
            return False
        if any(item.get("oomKilled") is not False for item in samples):
            return False
        if any(
            float(item.get("memoryPct", 101)) >= 85 and not protected_at(timestamp, "memory")
            for item, timestamp in zip(samples, starts, strict=True)
        ):
            return False
        if any(
            all(float(item.get("cpuPct", 101)) >= 80 for item in samples[index : index + 3])
            and not all(
                protected_at(timestamp, "cpu-sustained") for timestamp in starts[index : index + 3]
            )
            for index in range(max(0, len(samples) - 2))
        ):
            return False
        baseline_swap = int(samples[0]["swapUsedBytes"])
        if any(
            int(item.get("swapUsedBytes", baseline_swap + 1)) > baseline_swap for item in samples
        ):
            return False
        first_post_fault_index = next(
            (index for index, timestamp in enumerate(starts) if timestamp > fault_end), None
        )
        for index, (item, timestamp) in enumerate(zip(samples, starts, strict=True)):
            healthy = item.get("ready") is True and item.get("servicesExact") is True
            if healthy or fault_start <= timestamp <= fault_end:
                continue
            if index == first_post_fault_index and timestamp <= fault_end + timedelta(
                seconds=OBSERVER_MAX_GAP_SECONDS
            ):
                continue
            return False
        baseline_restarts = int(samples[0]["restartCount"])
        baseline_classroom_restarts = int(samples[0]["classroomRestartCount"])
        restart_values = [int(item.get("restartCount", baseline_restarts + 2)) for item in samples]
        first_change = next(
            (
                timestamp
                for value, timestamp in zip(restart_values, starts, strict=True)
                if value != baseline_restarts
            ),
            None,
        )
        classroom_values = [int(item["classroomRestartCount"]) for item in samples]
        first_classroom_change = next(
            (
                timestamp
                for value, timestamp in zip(classroom_values, starts, strict=True)
                if value != baseline_classroom_restarts
            ),
            None,
        )
        observed_fault_deadline = fault_end + timedelta(seconds=OBSERVER_MAX_GAP_SECONDS)
        if (
            len(set(restart_values)) != 2
            or len(set(classroom_values)) != 2
            or restart_values[-1] - baseline_restarts != 1
            or classroom_values[-1] - baseline_classroom_restarts != 1
            or first_change != first_classroom_change
            or first_change is None
            or not fault_start <= first_change <= observed_fault_deadline
        ):
            return False
        if samples[-1].get("ready") is not True or samples[-1].get("servicesExact") is not True:
            return False
        if fault.get("classroomOnly") is not True or fault.get("generalApiResponsive") is not True:
            return False
    except (KeyError, TypeError, ValueError, OverflowError):
        return False
    return True


def strict_stage_passes(measurements: list[dict[str, Any]]) -> bool:
    if not measurements:
        return False
    journey_totals = {name: {"requests": 0, "failures": 0} for name in JOURNEY_LIMITS}
    for measurement in measurements:
        try:
            journeys = measurement["journeys"]
            realtime = measurement["realtime"]
            pressure = measurement["pressure"]
            for name, (limit, strict) in JOURNEY_LIMITS.items():
                journey = journeys[name]
                requests = journey["requests"]
                failures = journey["failures"]
                if requests < 0 or failures < 0 or failures > requests:
                    return False
                journey_totals[name]["requests"] += requests
                journey_totals[name]["failures"] += failures
                if requests == 0:
                    continue
                if journey["failureRate"] >= 0.001:
                    return False
                p95 = journey["latencyMs"]["p95"]
                if (p95 >= limit) if strict else (p95 > limit):
                    return False
            if (
                realtime["converged"] != realtime["expected"]
                or realtime["reconnectsSucceeded"] != realtime["reconnectsExpected"]
                or realtime["lostCriticalEvents"] != 0
                or pressure["queueCapacity"] != 512
                or pressure["queueMaxDepth"] >= 384
                or pressure["eventLoopP99Ms"] > 250
                or pressure["poolTimeouts"] != 0
                or pressure["sqliteLockErrors"] != 0
            ):
                return False
        except (KeyError, TypeError):
            return False
    return not any(
        total["requests"] < 1 or total["failures"] / total["requests"] >= 0.001
        for total in journey_totals.values()
    )


def presenter_fanout_passes(measurements: list[dict[str, Any]]) -> bool:
    """Require one teacher publisher and timestamp-correlated receipt on all six shards."""
    if len(measurements) != 6:
        return False
    try:
        fanouts = [item["journeys"]["presenterSse"]["fanout"] for item in measurements]
        publishers = [item for item in fanouts if item["sentEpochMs"]]
        if len(publishers) != 1:
            return False
        sent = publishers[0]["sentEpochMs"]
        if not sent or len(sent) > 128:
            return False
        common = set(sent)
        for fanout in fanouts:
            received = fanout["receivedEpochMs"]
            common.intersection_update(received)
        if not common:
            return False
        for fanout in fanouts:
            received = fanout["receivedEpochMs"]
            if any(not 0 <= received[key] - sent[key] <= 250 for key in common):
                return False
    except (KeyError, TypeError, ValueError):
        return False
    return True


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def _load_ndjson(path: Path) -> list[dict[str, Any]]:
    values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not values or not all(isinstance(value, dict) for value in values):
        raise ValueError(f"{path} must contain aggregate NDJSON objects")
    return values


def _stage_statuses(
    stages: list[dict[str, Any]], strict_1200: bool, strict_1500: bool
) -> dict[str, Any]:
    mapping = {
        "smoke-2": "smoke-2",
        "smoke-100": "acceptance-100",
        "boundary-300": "boundary-300",
        "boundary-600": "boundary-600",
        "boundary-900": "boundary-900",
        "certification-1200": "sustained-1200",
        "headroom-1500": "headroom-1500",
        "stress-1750": "breakpoint-1750",
        "stress-2000": "breakpoint-2000",
        "recovery-1200": "recovery-1200",
    }
    indexed = {stage["name"]: stage for stage in stages}
    results: dict[str, Any] = {}
    for output_name, source_name in mapping.items():
        stage = indexed[source_name]
        outcome = stage.get("outcome", "passed")
        passed = stage["achievedUsers"] >= stage["targetUsers"]
        if output_name == "certification-1200":
            passed = strict_1200
        elif output_name == "headroom-1500":
            passed = strict_1500
        elif output_name == "recovery-1200":
            passed = strict_1200 and passed
        if output_name.startswith("stress-") and outcome == "protected-early-stop":
            status = "early-stopped"
        elif output_name.startswith("stress-") and outcome == "skipped":
            status = "skipped"
        else:
            status = (
                "passed"
                if passed
                else ("skipped" if output_name == "recovery-1200" and not strict_1200 else "failed")
            )
        results[output_name] = {
            "durationSeconds": stage["durationSeconds"],
            "status": status,
        }
    return results


def build_decision(
    plan: dict[str, Any],
    merged: dict[str, Any],
    sentinels: dict[str, Any],
    fault: dict[str, Any],
    observer: list[dict[str, Any]],
    accounting: dict[str, Any],
    *,
    nonce: str,
) -> dict[str, Any]:
    validate_sentinel_evidence(sentinels, require_cleanup=True)
    validate_plan(plan)
    expected_binding = {
        "runId": plan["runId"],
        "workflowSha": plan["workflowSha"],
        "planDigest": plan["planDigest"],
    }
    if any(sentinels.get(name) != value for name, value in expected_binding.items()):
        raise ValueError("sentinel evidence is not bound to the capacity plan")
    fault_fields = {
        "schemaVersion",
        "runId",
        "workflowSha",
        "planDigest",
        "startedAt",
        "completedAt",
        "classroomOnly",
        "generalApiResponsive",
        "readinessRecoverySeconds",
        "convergenceSeconds",
        "privacy",
    }
    if set(fault) != fault_fields or any(
        fault.get(name) != value for name, value in expected_binding.items()
    ):
        raise ValueError("fault evidence is incomplete or not plan-bound")
    privacy = fault.get("privacy")
    if (
        not isinstance(privacy, dict)
        or set(privacy) != {"aggregateOnly", "credentialsMasked", "syntheticFixturesOnly"}
        or not all(privacy.values())
    ):
        raise ValueError("fault evidence privacy boundary failed")
    functional = sentinels.get("functionalSentinels")
    if not isinstance(functional, dict) or set(functional) != {
        "uploadConversion",
        "annotations",
        "libraryShare",
        "dynamicViewer",
        "desktop",
    }:
        raise ValueError("functional sentinel evidence is incomplete")
    sentinels_pass = all(value is True for value in functional.values())
    frontend = sentinels.get("frontend", {})
    cross_browser = sentinels.get("crossBrowser", {})
    sentinels_pass = sentinels_pass and (
        frontend.get("clsMax", 1) <= 0.1
        and frontend.get("lcpMsMax", 999999) <= 2500
        and all(
            frontend.get(name) == 0 for name in ("consoleErrors", "networkErrors", "blankCanvases")
        )
        and frontend.get("mobilePassed") is True
        and cross_browser.get("approved") is True
        and cross_browser.get("projects") == ["chromium", "firefox", "webkit", "mobile-chromium"]
        and cross_browser.get("ciRunId") == plan["browserCiRunId"]
    )
    recovery_pass = (
        fault.get("classroomOnly") is True
        and fault.get("generalApiResponsive") is True
        and 0 <= fault.get("readinessRecoverySeconds", 999) <= 90
        and 0 <= fault.get("convergenceSeconds", 999) <= 30
    )
    accounting_pass = (
        set(accounting)
        == {
            "currency",
            "monthToDateCost",
            "projectedMonthlyEgressBytes",
            "projectedMonthlyRuns",
            "permanentResourcesAdded",
            "computeOcpus",
            "memoryGb",
            "storageGb",
            "observedResourceCount",
            "approvedResourceCount",
            "observedInventoryDigest",
            "approvedInventoryDigest",
        }
        and accounting.get("currency") == "SGD"
        and accounting.get("monthToDateCost") == 0
        and accounting.get("projectedMonthlyEgressBytes", 9_000_000_000_000) < 9_000_000_000_000
        and accounting.get("permanentResourcesAdded") is False
        and accounting.get("observedResourceCount") == accounting.get("approvedResourceCount")
        and accounting.get("observedInventoryDigest") == accounting.get("approvedInventoryDigest")
        and isinstance(accounting.get("observedInventoryDigest"), str)
        and len(accounting["observedInventoryDigest"]) == 64
        and (
            accounting.get("computeOcpus"),
            accounting.get("memoryGb"),
            accounting.get("storageGb"),
        )
        == (2, 12, 200)
    )
    host_pass = host_evidence_passes(plan, observer, fault, merged["stages"]) and accounting_pass
    strict_1200 = (
        strict_stage_passes(merged["sustainedMeasurements"])
        and presenter_fanout_passes(merged["sustainedMeasurements"])
        and host_pass
    )
    strict_1200 = strict_1200 and sentinels_pass and recovery_pass
    strict_1500 = (
        strict_1200
        and strict_stage_passes(merged["headroomMeasurements"])
        and presenter_fanout_passes(merged["headroomMeasurements"])
    )
    try:
        started = int(
            datetime.fromisoformat(observer[0]["timestamp"].replace("Z", "+00:00")).timestamp()
        )
        completed = int(
            datetime.fromisoformat(observer[-1]["timestamp"].replace("Z", "+00:00")).timestamp()
        )
    except (IndexError, KeyError, TypeError, ValueError):
        # Preserve a structurally explicit NOT CERTIFIED decision. Never
        # substitute scheduled timestamps for missing observations.
        started = 0
        completed = 0
    ict = ZoneInfo("Asia/Bangkok")
    started_ict = datetime.fromtimestamp(started, ict)
    completed_ict = datetime.fromtimestamp(completed, ict)
    within_window = (
        plan.get("window") == "02:00-05:00 ICT"
        and started > 0
        and completed > 0
        and started_ict.date() == completed_ict.date()
        and 2 <= started_ict.hour < 5
        and 2 <= completed_ict.hour < 5
        and host_pass
    )
    digest = hashlib.sha256(
        json.dumps(
            {
                "plan": plan["planDigest"],
                "merged": merged,
                "sentinels": sentinels,
                "fault": fault,
                "observer": observer,
                "accounting": accounting,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return {
        "certification": {
            "schemaVersion": 2,
            "candidateSha": plan["workflowSha"],
            "runId": plan["runId"],
            "nonce": nonce,
            "startedAt": started,
            "completedAt": completed,
            "withinAuthorizedIctWindow": within_window,
            "allPreflightGatesPassed": host_pass and isinstance(plan.get("browserCiRunId"), int),
            "fixtureCleanupSucceeded": sentinels.get("cleanupSucceeded") is True,
            "evidenceDigest": digest,
            "strictStages": {
                "1200": {"durationSeconds": 3600, "passed": strict_1200},
                "1500": {"durationSeconds": 600, "passed": strict_1500},
            },
            "stageResults": _stage_statuses(merged["stages"], strict_1200, strict_1500),
            "functionalSentinels": functional,
            "verdict": "CERTIFIED" if strict_1200 else "NOT CERTIFIED",
            "selectedCapacity": 1500 if strict_1500 else (1200 if strict_1200 else 300),
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build signed capacity tier decision")
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--merged-shards", required=True, type=Path)
    parser.add_argument("--sentinels", required=True, type=Path)
    parser.add_argument("--fault", required=True, type=Path)
    parser.add_argument("--observer", required=True, type=Path)
    parser.add_argument("--accounting", required=True, type=Path)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--key-file", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--signature-output", required=True, type=Path)
    args = parser.parse_args()
    decision = build_decision(
        _load(args.plan),
        _load(args.merged_shards),
        _load(args.sentinels),
        _load(args.fault),
        _load_ndjson(args.observer),
        _load(args.accounting),
        nonce=args.nonce,
    )
    payload = json.dumps(decision, sort_keys=True, separators=(",", ":")).encode()
    key = args.key_file.read_bytes().strip()
    signature = hmac.new(key, payload, hashlib.sha256).hexdigest()
    args.output.write_text(json.dumps(decision, indent=2) + "\n", encoding="utf-8")
    args.signature_output.write_text(signature + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
