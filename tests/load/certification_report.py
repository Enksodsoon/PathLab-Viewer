#!/usr/bin/env python3
import argparse
import json
import math
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


class ReportError(ValueError):
    pass


SCHEMA_VERSION = 2
ICT = timezone(timedelta(hours=7))
OBSERVER_MAX_GAP_SECONDS = 15
SHARD_START_TOLERANCE_MS = 1_000
EGRESS_BUDGET_BYTES = 9_000_000_000_000
STAGE_SPECS = (
    ("smoke-2", 2, 30, False),
    ("acceptance-100", 100, 600, False),
    ("boundary-300", 300, 600, False),
    ("boundary-600", 600, 600, False),
    ("boundary-900", 900, 600, False),
    ("sustained-1200", 1200, 3_600, True),
    ("headroom-1500", 1500, 600, True),
    ("breakpoint-1750", 1750, 300, False),
    ("breakpoint-2000", 2000, 300, False),
    ("recovery-1200", 1200, 600, False),
)
REQUIRED_JOURNEYS = {
    "presenterSse": (250.0, False),
    "classroomControl": (500.0, False),
    "generalApi": (500.0, False),
    "staticTile": (500.0, True),
    "poster": (1500.0, True),
    "question": (2000.0, False),
}
CONTEXT_FIELDS = {
    "run",
    "deployedSha",
    "browserCi",
    "stages",
    "journeys",
    "realtime",
    "pressure",
    "resources",
    "abort",
    "recovery",
    "fixturePreparation",
    "cleanup",
    "privacy",
    "egress",
    "cost",
    "functionalSentinels",
}
REPORT_FIELDS = {
    "schemaVersion",
    "certified",
    "certifiedTier",
    "release",
    "browserCi",
    "run",
    "stages",
    "journeys",
    "realtime",
    "pressure",
    "resources",
    "abort",
    "recovery",
    "fixturePreparation",
    "cleanup",
    "privacy",
    "egress",
    "cost",
    "functionalSentinels",
    "checks",
    "metrics",
    "browser",
}
CHECK_FIELDS = {
    "requestFailures",
    "tileFailures",
    "tileLatency",
    "posterLatency",
    "cpu",
    "memory",
    "swap",
    "restarts",
    "oom",
    "services",
    "readiness",
    "disk",
    "observerRelease",
    "admin",
    "conversion",
    "browserCleanup",
    "degradedViewer",
    "release",
    "browserCi",
    "stages",
    "shards",
    "journeys",
    "realtime",
    "pressure",
    "resources",
    "abort",
    "recovery",
    "fixturePreparation",
    "cleanup",
    "privacy",
    "egress",
    "cost",
    "functionalSentinels",
}
METRIC_FIELDS = {
    "requestFailureRate",
    "tileFailureRate",
    "tileP95Ms",
    "posterP95Ms",
    "maxCpuPct",
    "maxMemoryPct",
    "swapGrowthBytes",
    "restartGrowth",
    "oomObserved",
    "servicesExact",
    "readinessMaintained",
    "minDiskFreePct",
    "releaseExact",
}
BROWSER_FIELDS = {
    "adminResponsive",
    "conversionSucceeded",
    "cleanupSucceeded",
    "degradedViewerRecovered",
}
OBSERVER_FIELDS = {
    "timestamp",
    "releaseSha",
    "ready",
    "cpuPct",
    "memoryPct",
    "swapUsedBytes",
    "diskFreePct",
    "networkRxBytesDelta",
    "networkTxBytesDelta",
    "diskReadBytesDelta",
    "diskWriteBytesDelta",
    "sockets",
    "fileDescriptors",
    "containerCpuPct",
    "containerMemoryPct",
    "servicesExact",
    "restartCount",
    "classroomRestartCount",
    "oomKilled",
}


def _exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    missing = sorted(fields - value.keys())
    extras = sorted(value.keys() - fields)
    if missing or extras:
        raise ReportError(
            f"{label} fields are invalid: missing={','.join(missing) or 'none'} "
            f"unknown={','.join(extras) or 'none'}"
        )


def _object(parent: dict[str, Any], name: str) -> dict[str, Any]:
    value = parent.get(name)
    if not isinstance(value, dict):
        raise ReportError(f"evidence requires {name} object")
    return value


def _list(parent: dict[str, Any], name: str) -> list[Any]:
    value = parent.get(name)
    if not isinstance(value, list):
        raise ReportError(f"evidence requires {name} array")
    return value


def _number(
    value: Any,
    label: str,
    *,
    minimum: float = 0,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ReportError(f"{label} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ReportError(f"{label} must be finite")
    if result < minimum or (maximum is not None and result > maximum):
        raise ReportError(f"{label} is outside its physical range")
    return result


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReportError(f"{label} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        raise ReportError(f"{label} is outside its physical range")
    return int(value)


def _boolean(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ReportError(f"{label} must be boolean")
    return value


def _timestamp(value: Any, label: str, *, ict: bool = False) -> datetime:
    if not isinstance(value, str) or not value or len(value) > 40:
        raise ReportError(f"{label} must be a bounded ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ReportError(f"{label} must be a valid ISO-8601 timestamp") from error
    if parsed.tzinfo is None:
        raise ReportError(f"{label} must include a timezone")
    if ict and parsed.utcoffset() != timedelta(hours=7):
        raise ReportError(f"{label} must use the ICT +07:00 offset")
    return parsed


def _safe_id(value: Any, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-z0-9-]{1,64}", value) is None:
        raise ReportError(f"{label} must be a safe aggregate identifier")
    return value


def _validate_shards(
    shards: Any,
    *,
    stage_index: int,
    stage_target: int,
    stage_achieved: int,
    stage_started: datetime,
) -> None:
    label = f"stages[{stage_index}].shards"
    if not isinstance(shards, list) or len(shards) != 6:
        raise ReportError(f"{label} requires exactly six shards")
    ids: set[str] = set()
    targets: list[int] = []
    achieved: list[int] = []
    starts: list[int] = []
    stage_epoch_ms = int(stage_started.timestamp() * 1000)
    shard_fields = {
        "shardId",
        "targetUsers",
        "achievedUsers",
        "healthy",
        "startEpochMs",
        "maxTimingDriftMs",
        "timingWithinTolerance",
        "generator",
    }
    generator_fields = {
        "cpuPctMax",
        "memoryPctMax",
        "droppedIterations",
        "saturated",
    }
    for index, shard in enumerate(shards):
        shard_label = f"{label}[{index}]"
        if not isinstance(shard, dict):
            raise ReportError(f"{shard_label} must be an object")
        _exact_fields(shard, shard_fields, shard_label)
        shard_id = _safe_id(shard["shardId"], f"{shard_label}.shardId")
        if shard_id in ids:
            raise ReportError(f"{label} shard IDs must be unique")
        ids.add(shard_id)
        targets.append(_integer(shard["targetUsers"], f"{shard_label}.targetUsers", maximum=2000))
        achieved.append(
            _integer(shard["achievedUsers"], f"{shard_label}.achievedUsers", maximum=2000)
        )
        _boolean(shard["healthy"], f"{shard_label}.healthy")
        start = _integer(shard["startEpochMs"], f"{shard_label}.startEpochMs", minimum=1)
        starts.append(start)
        drift = _number(
            shard["maxTimingDriftMs"],
            f"{shard_label}.maxTimingDriftMs",
            maximum=60_000,
        )
        if drift != abs(start - stage_epoch_ms):
            raise ReportError(f"{shard_label}.maxTimingDriftMs is not derived from start")
        within = _boolean(shard["timingWithinTolerance"], f"{shard_label}.timingWithinTolerance")
        if within is not (drift <= SHARD_START_TOLERANCE_MS):
            raise ReportError(f"{shard_label}.timingWithinTolerance is inconsistent")
        generator = shard["generator"]
        if not isinstance(generator, dict):
            raise ReportError(f"{shard_label}.generator must be an object")
        _exact_fields(generator, generator_fields, f"{shard_label}.generator")
        _number(generator["cpuPctMax"], f"{shard_label}.generator.cpuPctMax", maximum=100)
        _number(
            generator["memoryPctMax"],
            f"{shard_label}.generator.memoryPctMax",
            maximum=100,
        )
        _integer(
            generator["droppedIterations"],
            f"{shard_label}.generator.droppedIterations",
            maximum=1_000_000_000,
        )
        _boolean(generator["saturated"], f"{shard_label}.generator.saturated")
    quotient, remainder = divmod(stage_target, 6)
    expected_targets = sorted(quotient + (1 if index < remainder else 0) for index in range(6))
    if sorted(targets) != expected_targets or sum(targets) != stage_target:
        raise ReportError(f"{label} targets do not reconcile to the stage target")
    if sum(achieved) != stage_achieved:
        raise ReportError(f"{label} achieved users do not reconcile to the stage")
    if max(starts) - min(starts) > SHARD_START_TOLERANCE_MS:
        raise ReportError(f"{label} starts are not synchronized")


def _validate_context(context: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise ReportError("evidence context must be an object")
    _exact_fields(context, CONTEXT_FIELDS, "evidence context")
    deployed_sha = context["deployedSha"]
    if not isinstance(deployed_sha, str) or re.fullmatch(r"[0-9a-f]{40}", deployed_sha) is None:
        raise ReportError("deployedSha must be a full lowercase commit SHA")

    run = _object(context, "run")
    _exact_fields(run, {"runId", "startedAt", "endedAt", "window"}, "run")
    _safe_id(run["runId"], "run.runId")
    if not isinstance(run["window"], str) or run["window"].count("/") != 1:
        raise ReportError("run.window must be an explicit ICT start/end interval")
    window_start_raw, window_end_raw = run["window"].split("/", 1)
    window_start = _timestamp(window_start_raw, "run.window start", ict=True)
    window_end = _timestamp(window_end_raw, "run.window end", ict=True)
    if window_end - window_start != timedelta(hours=3):
        raise ReportError("run.window must be exactly three hours")
    run_started = _timestamp(run["startedAt"], "run.startedAt", ict=True)
    run_ended = _timestamp(run["endedAt"], "run.endedAt", ict=True)
    if run_ended <= run_started:
        raise ReportError("run timestamps must be ordered")
    if run_started < window_start or run_ended > window_end:
        raise ReportError("run falls outside the protected ICT window")

    browser_ci = _object(context, "browserCi")
    _exact_fields(browser_ci, {"name", "headSha", "conclusion", "runId"}, "browserCi")
    if browser_ci["name"] != "browser":
        raise ReportError("browserCi.name must be browser")
    if (
        not isinstance(browser_ci["headSha"], str)
        or re.fullmatch(r"[0-9a-f]{40}", browser_ci["headSha"]) is None
    ):
        raise ReportError("browserCi.headSha must be a full lowercase commit SHA")
    if browser_ci["conclusion"] not in {
        "success",
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "neutral",
        "skipped",
        "stale",
        "startup_failure",
    }:
        raise ReportError("browserCi.conclusion is invalid")
    _integer(browser_ci["runId"], "browserCi.runId", minimum=1)

    stages = _list(context, "stages")
    if len(stages) != len(STAGE_SPECS):
        raise ReportError("evidence requires the complete ten-stage progression")
    stage_fields = {
        "name",
        "targetUsers",
        "achievedUsers",
        "startedAt",
        "endedAt",
        "durationSeconds",
        "strictGate",
        "outcome",
        "abortCauses",
        "shards",
    }
    cursor = run_started
    for index, (spec, stage) in enumerate(zip(STAGE_SPECS, stages, strict=True)):
        if not isinstance(stage, dict):
            raise ReportError(f"stages[{index}] must be an object")
        _exact_fields(stage, stage_fields, f"stages[{index}]")
        expected_name, expected_target, expected_duration, expected_strict = spec
        if (
            stage["name"] != expected_name
            or stage["targetUsers"] != expected_target
            or stage["durationSeconds"] != expected_duration
            or stage["strictGate"] is not expected_strict
        ):
            raise ReportError(f"stages[{index}] does not match the exact stage contract")
        achieved_users = _integer(
            stage["achievedUsers"], f"stages[{index}].achievedUsers", maximum=2000
        )
        outcome = stage["outcome"]
        abort_causes = stage["abortCauses"]
        if outcome not in {"passed", "protected-early-stop", "skipped"}:
            raise ReportError(f"stages[{index}].outcome is invalid")
        if not isinstance(abort_causes, list) or not all(
            isinstance(item, str) for item in abort_causes
        ):
            raise ReportError(f"stages[{index}].abortCauses is invalid")
        breakpoint = expected_name.startswith("breakpoint-")
        if outcome == "passed" and (achieved_users < expected_target or abort_causes):
            raise ReportError(f"stages[{index}] did not pass its target cleanly")
        if outcome == "protected-early-stop" and (not breakpoint or not abort_causes):
            raise ReportError(f"stages[{index}] is not an approved protected stop")
        if outcome == "skipped" and (not breakpoint or abort_causes != ["escalation-blocked"]):
            raise ReportError(f"stages[{index}] is not an approved skipped stress stage")
        started = _timestamp(stage["startedAt"], f"stages[{index}].startedAt", ict=True)
        ended = _timestamp(stage["endedAt"], f"stages[{index}].endedAt", ict=True)
        if not (
            cursor <= started <= cursor + timedelta(seconds=150)
            and ended - started == timedelta(seconds=expected_duration)
        ):
            raise ReportError(f"stages[{index}] timestamps do not match measured holds")
        _validate_shards(
            stage["shards"],
            stage_index=index,
            stage_target=expected_target,
            stage_achieved=achieved_users,
            stage_started=started,
        )
        cursor = ended

    journey_fields = {"requests", "failureRate", "latencyMs"}
    latency_fields = {"p50", "p95", "p99"}
    journeys = _object(context, "journeys")
    _exact_fields(journeys, set(REQUIRED_JOURNEYS), "journeys")
    for name, journey in journeys.items():
        if not isinstance(journey, dict):
            raise ReportError(f"journeys.{name} must be an object")
        _exact_fields(journey, journey_fields, f"journeys.{name}")
        _integer(journey["requests"], f"journeys.{name}.requests", minimum=1)
        _number(journey["failureRate"], f"journeys.{name}.failureRate", maximum=1)
        latency = journey["latencyMs"]
        if not isinstance(latency, dict):
            raise ReportError(f"journeys.{name}.latencyMs must be an object")
        _exact_fields(latency, latency_fields, f"journeys.{name}.latencyMs")
        values = [
            _number(latency[key], f"journeys.{name}.latencyMs.{key}", maximum=600_000)
            for key in ("p50", "p95", "p99")
        ]
        if values != sorted(values):
            raise ReportError(f"journeys.{name} latency percentiles are not ordered")

    realtime = _object(context, "realtime")
    _exact_fields(
        realtime,
        {
            "sseConvergencePct",
            "reconnectSuccessPct",
            "lostCriticalEvents",
            "unexpectedDisconnects",
            "queueOverflows",
        },
        "realtime",
    )
    _number(realtime["sseConvergencePct"], "realtime.sseConvergencePct", maximum=100)
    _number(realtime["reconnectSuccessPct"], "realtime.reconnectSuccessPct", maximum=100)
    _integer(realtime["lostCriticalEvents"], "realtime.lostCriticalEvents")
    _integer(realtime["unexpectedDisconnects"], "realtime.unexpectedDisconnects")
    _integer(realtime["queueOverflows"], "realtime.queueOverflows")

    functional = _object(context, "functionalSentinels")
    _exact_fields(
        functional,
        {"uploadConversion", "annotations", "libraryShare", "dynamicViewer", "desktop"},
        "functionalSentinels",
    )
    for name, value in functional.items():
        _boolean(value, f"functionalSentinels.{name}")

    pressure = _object(context, "pressure")
    pressure_fields = {
        "queueMaxDepth",
        "queueCapacity",
        "eventLoopP99Ms",
        "poolWaitP95Ms",
        "poolTimeouts",
        "sqliteLockErrors",
    }
    _exact_fields(pressure, pressure_fields, "pressure")
    _integer(pressure["queueMaxDepth"], "pressure.queueMaxDepth", maximum=1_000_000)
    _integer(pressure["queueCapacity"], "pressure.queueCapacity", minimum=1, maximum=1_000_000)
    _number(pressure["eventLoopP99Ms"], "pressure.eventLoopP99Ms", maximum=600_000)
    _number(pressure["poolWaitP95Ms"], "pressure.poolWaitP95Ms", maximum=600_000)
    _integer(pressure["poolTimeouts"], "pressure.poolTimeouts")
    _integer(pressure["sqliteLockErrors"], "pressure.sqliteLockErrors")

    resources = _object(context, "resources")
    resource_fields = {
        "socketsPeak",
        "fileDescriptorsPeak",
        "containerCpuPctMax",
        "containerMemoryPctMax",
        "protectedHeavyHostCpuPctMax",
        "protectedHeavyHostMemoryPctMax",
        "containerRestarts",
        "oomKills",
        "diskReadBytes",
        "diskWriteBytes",
        "diskFreePctMin",
        "networkRxBytes",
        "networkTxBytes",
    }
    _exact_fields(resources, resource_fields, "resources")
    for name in ("socketsPeak", "fileDescriptorsPeak"):
        _integer(resources[name], f"resources.{name}", maximum=10_000_000)
    for name in (
        "containerCpuPctMax",
        "containerMemoryPctMax",
        "protectedHeavyHostCpuPctMax",
        "protectedHeavyHostMemoryPctMax",
        "diskFreePctMin",
    ):
        _number(resources[name], f"resources.{name}", maximum=100)
    for name in (
        "containerRestarts",
        "oomKills",
        "diskReadBytes",
        "diskWriteBytes",
        "networkRxBytes",
        "networkTxBytes",
    ):
        _integer(resources[name], f"resources.{name}", maximum=10**15)

    abort = _object(context, "abort")
    _exact_fields(abort, {"aborted", "cause"}, "abort")
    _boolean(abort["aborted"], "abort.aborted")
    if abort["cause"] is not None:
        _safe_id(abort["cause"], "abort.cause")

    recovery = _object(context, "recovery")
    _exact_fields(
        recovery, {"attempted", "succeeded", "readinessRestored", "usersAchieved"}, "recovery"
    )
    for name in ("attempted", "succeeded", "readinessRestored"):
        _boolean(recovery[name], f"recovery.{name}")
    _integer(recovery["usersAchieved"], "recovery.usersAchieved", maximum=2000)

    fixture_preparation = _object(context, "fixturePreparation")
    fixture_fields = {
        "prepared",
        "encrypted",
        "syntheticOnly",
        "identifiersIncluded",
        "endpointsValidated",
    }
    _exact_fields(fixture_preparation, fixture_fields, "fixturePreparation")
    for name in ("prepared", "encrypted", "syntheticOnly", "identifiersIncluded"):
        _boolean(fixture_preparation[name], f"fixturePreparation.{name}")
    _integer(
        fixture_preparation["endpointsValidated"],
        "fixturePreparation.endpointsValidated",
        maximum=100,
    )

    cleanup = _object(context, "cleanup")
    cleanup_fields = {
        "startedAt",
        "completedAt",
        "attempted",
        "succeeded",
        "configurationRestored",
        "fixturesRemoved",
        "bastionSessionsRemaining",
    }
    _exact_fields(cleanup, cleanup_fields, "cleanup")
    cleanup_started = _timestamp(cleanup["startedAt"], "cleanup.startedAt", ict=True)
    cleanup_completed = _timestamp(cleanup["completedAt"], "cleanup.completedAt", ict=True)
    if not (
        cursor <= cleanup_started <= cursor + timedelta(minutes=5)
        and timedelta(seconds=1) <= cleanup_completed - cleanup_started <= timedelta(minutes=5)
    ):
        raise ReportError("cleanup timestamps are not ordered and bounded")
    if cleanup_completed != run_ended:
        raise ReportError("run.endedAt must equal cleanup.completedAt")
    for name in ("attempted", "succeeded", "configurationRestored", "fixturesRemoved"):
        _boolean(cleanup[name], f"cleanup.{name}")
    _integer(
        cleanup["bastionSessionsRemaining"],
        "cleanup.bastionSessionsRemaining",
        maximum=1_000_000,
    )

    privacy = _object(context, "privacy")
    _exact_fields(
        privacy, {"aggregateOnly", "credentialsMasked", "syntheticFixturesOnly"}, "privacy"
    )
    for name in privacy:
        _boolean(privacy[name], f"privacy.{name}")

    egress = _object(context, "egress")
    egress_fields = {
        "measuredRunBytes",
        "projectedMonthlyRuns",
        "projectedBytes",
        "budgetBytes",
        "withinBudget",
    }
    _exact_fields(egress, egress_fields, "egress")
    measured = _integer(egress["measuredRunBytes"], "egress.measuredRunBytes", maximum=10**15)
    runs = _integer(
        egress["projectedMonthlyRuns"], "egress.projectedMonthlyRuns", minimum=1, maximum=10_000
    )
    projected = _integer(egress["projectedBytes"], "egress.projectedBytes", maximum=10**18)
    budget = _integer(egress["budgetBytes"], "egress.budgetBytes", minimum=1, maximum=10**18)
    within = _boolean(egress["withinBudget"], "egress.withinBudget")
    if measured != resources["networkTxBytes"] or projected != measured * runs:
        raise ReportError("egress projection is not derived from measured network bytes")
    if budget != EGRESS_BUDGET_BYTES or within is not (projected < budget):
        raise ReportError("egress budget proof is inconsistent")

    cost = _object(context, "cost")
    cost_fields = {
        "currency",
        "existingMonthlyAmount",
        "projectedMonthlyAmount",
        "amount",
        "permanentResourcesAdded",
        "computeOcpus",
        "memoryGb",
        "storageGb",
        "shapeCompliant",
    }
    _exact_fields(cost, cost_fields, "cost")
    if cost["currency"] != "SGD":
        raise ReportError("cost.currency must be SGD")
    existing = _number(cost["existingMonthlyAmount"], "cost.existingMonthlyAmount", maximum=10**9)
    projected_cost = _number(
        cost["projectedMonthlyAmount"], "cost.projectedMonthlyAmount", maximum=10**9
    )
    amount = _number(cost["amount"], "cost.amount", maximum=10**9)
    _boolean(cost["permanentResourcesAdded"], "cost.permanentResourcesAdded")
    ocpus = _integer(cost["computeOcpus"], "cost.computeOcpus", minimum=1, maximum=160)
    memory_gb = _number(cost["memoryGb"], "cost.memoryGb", minimum=1, maximum=2048)
    storage_gb = _integer(cost["storageGb"], "cost.storageGb", minimum=1, maximum=1_000_000)
    shape = _boolean(cost["shapeCompliant"], "cost.shapeCompliant")
    if amount != projected_cost - existing:
        raise ReportError("cost.amount is not derived from monthly accounting inputs")
    if shape is not (ocpus == 2 and memory_gb == 12 and storage_gb == 200):
        raise ReportError("cost.shapeCompliant is inconsistent with the host shape")

    return {name: deepcopy(context[name]) for name in CONTEXT_FIELDS}


def validate_context_for_run(
    context: dict[str, Any], *, commit_sha: str, browser_ci_run_id: int
) -> None:
    validated = _validate_context(context)
    if validated["deployedSha"] != commit_sha:
        raise ReportError("evidence context deployed SHA does not match the workflow")
    browser_ci = validated["browserCi"]
    if browser_ci["headSha"] != commit_sha or browser_ci["runId"] != browser_ci_run_id:
        raise ReportError("evidence context browser check identity does not match the workflow")


def _validate_observer(
    observer: list[dict[str, Any]], *, run: dict[str, Any], commit_sha: str
) -> dict[str, Any]:
    if len(observer) < 2:
        raise ReportError("host observation requires continuous samples")
    run_started = _timestamp(run["startedAt"], "run.startedAt", ict=True)
    run_ended = _timestamp(run["endedAt"], "run.endedAt", ict=True)
    timestamps: list[datetime] = []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(observer):
        label = f"observer[{index}]"
        if not isinstance(item, dict):
            raise ReportError(f"{label} must be an object")
        _exact_fields(item, OBSERVER_FIELDS, label)
        timestamps.append(_timestamp(item["timestamp"], f"{label}.timestamp"))
        if (
            not isinstance(item["releaseSha"], str)
            or re.fullmatch(r"[0-9a-f]{40}", item["releaseSha"]) is None
        ):
            raise ReportError(f"{label}.releaseSha is invalid")
        for name in ("ready", "servicesExact", "oomKilled"):
            _boolean(item[name], f"{label}.{name}")
        for name in ("cpuPct", "memoryPct", "diskFreePct", "containerCpuPct", "containerMemoryPct"):
            _number(item[name], f"{label}.{name}", maximum=100)
        for name in (
            "swapUsedBytes",
            "networkRxBytesDelta",
            "networkTxBytesDelta",
            "restartCount",
            "classroomRestartCount",
            "diskReadBytesDelta",
            "diskWriteBytesDelta",
            "sockets",
            "fileDescriptors",
        ):
            _integer(item[name], f"{label}.{name}", maximum=10**15)
        normalized.append(deepcopy(item))
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise ReportError("observer timestamps must be strictly ordered")
    # Observation intentionally continues into cleanup. Validate every sample,
    # but compute certification metrics only through the scheduled run boundary.
    bounded = [
        (timestamp, item)
        for timestamp, item in zip(timestamps, normalized, strict=True)
        if timestamp <= run_ended
    ]
    if not bounded:
        raise ReportError("observer coverage does not include the complete run")
    timestamps = [timestamp for timestamp, _ in bounded]
    normalized = [item for _, item in bounded]
    leading = (run_started - timestamps[0]).total_seconds()
    trailing = (run_ended - timestamps[-1]).total_seconds()
    if not (-OBSERVER_MAX_GAP_SECONDS <= leading <= OBSERVER_MAX_GAP_SECONDS) or not (
        0 <= trailing <= OBSERVER_MAX_GAP_SECONDS
    ):
        raise ReportError("observer coverage does not bound the complete run")
    if any(
        (current - previous).total_seconds() > OBSERVER_MAX_GAP_SECONDS
        for previous, current in zip(timestamps, timestamps[1:], strict=False)
    ):
        raise ReportError("observer coverage has an unbounded sample gap")
    if any(item["releaseSha"] != commit_sha for item in normalized):
        raise ReportError("observer release does not match the workflow")
    return {"items": normalized, "timestamps": timestamps}


def _metric(summary: dict[str, Any], name: str, field: str, *, maximum: float) -> float:
    try:
        value = summary["metrics"][name]["values"][field]
    except (KeyError, TypeError) as error:
        raise ReportError(f"k6 summary is missing {name}.{field}") from error
    return _number(value, f"k6.{name}.{field}", maximum=maximum)


def _context_checks(context: dict[str, Any], commit_sha: str) -> dict[str, bool]:
    browser_ci = context["browserCi"]
    stages = context["stages"]
    journeys = context["journeys"]
    realtime = context["realtime"]
    pressure = context["pressure"]
    resources = context["resources"]
    abort = context["abort"]
    recovery = context["recovery"]
    fixture_preparation = context["fixturePreparation"]
    cleanup = context["cleanup"]
    privacy = context["privacy"]
    egress = context["egress"]
    cost = context["cost"]
    functional = context["functionalSentinels"]
    journey_ok = all(
        journey["failureRate"] < 0.001
        and (
            journey["latencyMs"]["p95"] < limit if strict else journey["latencyMs"]["p95"] <= limit
        )
        for name, (limit, strict) in REQUIRED_JOURNEYS.items()
        for journey in (journeys[name],)
    )
    queue_capacity = pressure["queueCapacity"]
    return {
        "release": context["deployedSha"] == commit_sha,
        "browserCi": browser_ci["headSha"] == commit_sha and browser_ci["conclusion"] == "success",
        "stages": all(
            stage["outcome"] == "passed"
            or (
                stage["name"].startswith("breakpoint-")
                and stage["outcome"] in {"protected-early-stop", "skipped"}
            )
            for stage in stages
        ),
        "shards": all(
            shard["healthy"]
            and (
                shard["achievedUsers"] >= shard["targetUsers"]
                or stage["outcome"] in {"protected-early-stop", "skipped"}
            )
            and shard["timingWithinTolerance"]
            and not shard["generator"]["saturated"]
            and shard["generator"]["droppedIterations"] == 0
            for stage in stages
            for shard in stage["shards"]
        ),
        "journeys": journey_ok,
        "realtime": realtime["sseConvergencePct"] == 100
        and realtime["reconnectSuccessPct"] == 100
        and realtime["lostCriticalEvents"] == 0
        and realtime["unexpectedDisconnects"] == 0
        and realtime["queueOverflows"] == 0,
        "functionalSentinels": all(functional.values()),
        "pressure": queue_capacity == 512
        and pressure["queueMaxDepth"] < queue_capacity * 0.75
        and pressure["eventLoopP99Ms"] <= 250
        and pressure["poolTimeouts"] == 0
        and pressure["sqliteLockErrors"] == 0,
        "resources": resources["containerCpuPctMax"] < 80
        and resources["containerMemoryPctMax"] < 85
        and resources["containerRestarts"] == 0
        and resources["oomKills"] == 0
        and resources["diskFreePctMin"] >= 10,
        "abort": not abort["aborted"] and abort["cause"] is None,
        "recovery": recovery["attempted"]
        and recovery["succeeded"]
        and recovery["readinessRestored"]
        and recovery["usersAchieved"] >= 1200,
        "fixturePreparation": fixture_preparation["prepared"]
        and fixture_preparation["encrypted"]
        and fixture_preparation["syntheticOnly"]
        and not fixture_preparation["identifiersIncluded"]
        and fixture_preparation["endpointsValidated"] >= 4,
        "cleanup": cleanup["attempted"]
        and cleanup["succeeded"]
        and cleanup["configurationRestored"]
        and cleanup["fixturesRemoved"]
        and cleanup["bastionSessionsRemaining"] == 0,
        "privacy": privacy["aggregateOnly"]
        and privacy["credentialsMasked"]
        and privacy["syntheticFixturesOnly"],
        "egress": egress["withinBudget"] and egress["projectedBytes"] < EGRESS_BUDGET_BYTES,
        "cost": cost["existingMonthlyAmount"] == 0
        and cost["projectedMonthlyAmount"] == 0
        and cost["amount"] == 0
        and not cost["permanentResourcesAdded"]
        and cost["shapeCompliant"],
    }


def _artifact_checks(report: dict[str, Any]) -> dict[str, bool]:
    metrics = report["metrics"]
    browser = report["browser"]
    context = {name: deepcopy(report[name]) for name in CONTEXT_FIELDS if name != "deployedSha"}
    context["deployedSha"] = report["release"]["deployedSha"]
    return {
        "requestFailures": metrics["requestFailureRate"] < 0.001,
        "tileFailures": metrics["tileFailureRate"] < 0.001,
        "tileLatency": metrics["tileP95Ms"] < 500,
        "posterLatency": metrics["posterP95Ms"] < 1500,
        "cpu": metrics["maxCpuPct"] < 80,
        "memory": metrics["maxMemoryPct"] < 85,
        "swap": metrics["swapGrowthBytes"] == 0,
        "restarts": metrics["restartGrowth"] == 0,
        "oom": not metrics["oomObserved"],
        "services": metrics["servicesExact"],
        "readiness": metrics["readinessMaintained"],
        "disk": metrics["minDiskFreePct"] >= 10,
        "observerRelease": metrics["releaseExact"],
        "admin": browser["adminResponsive"],
        "conversion": browser["conversionSucceeded"],
        "browserCleanup": browser["cleanupSucceeded"],
        "degradedViewer": browser["degradedViewerRecovered"],
        **_context_checks(context, report["release"]["workflowSha"]),
    }


def build_report(
    summary: dict[str, Any],
    observer: list[dict[str, Any]],
    browser: dict[str, Any],
    *,
    commit_sha: str,
    evidence_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if re.fullmatch(r"[0-9a-f]{40}", commit_sha) is None:
        raise ReportError("commit SHA must be a full lowercase commit SHA")
    if evidence_context is None:
        raise ReportError("evidence context is required for schema v2")
    context = _validate_context(evidence_context)
    observer_run = {
        **context["run"],
        "endedAt": context["stages"][-1]["endedAt"],
    }
    observer_data = _validate_observer(observer, run=observer_run, commit_sha=commit_sha)
    _exact_fields(browser, BROWSER_FIELDS, "browser")
    normalized_browser = {
        name: _boolean(browser[name], f"browser.{name}") for name in BROWSER_FIELDS
    }
    items = observer_data["items"]
    baseline_swap = items[0]["swapUsedBytes"]
    baseline_restarts = items[0]["restartCount"]
    metrics = {
        "requestFailureRate": _metric(summary, "http_req_failed", "rate", maximum=1),
        "tileFailureRate": _metric(summary, "tile_failures", "rate", maximum=1),
        "tileP95Ms": _metric(summary, "tile_latency", "p(95)", maximum=600_000),
        "posterP95Ms": _metric(summary, "poster_latency", "p(95)", maximum=600_000),
        "maxCpuPct": max(item["cpuPct"] for item in items),
        "maxMemoryPct": max(item["memoryPct"] for item in items),
        "swapGrowthBytes": max(item["swapUsedBytes"] for item in items) - baseline_swap,
        "restartGrowth": max(item["restartCount"] for item in items) - baseline_restarts,
        "oomObserved": any(item["oomKilled"] for item in items),
        "servicesExact": all(item["servicesExact"] for item in items),
        "readinessMaintained": all(item["ready"] for item in items),
        "minDiskFreePct": min(item["diskFreePct"] for item in items),
        "releaseExact": all(item["releaseSha"] == commit_sha for item in items),
    }
    deployed_sha = context.pop("deployedSha")
    report = {
        "schemaVersion": SCHEMA_VERSION,
        "certified": False,
        "certifiedTier": None,
        "release": {
            "workflowSha": commit_sha,
            "deployedSha": deployed_sha,
            "exact": deployed_sha == commit_sha,
        },
        **context,
        "checks": {},
        "metrics": metrics,
        "browser": normalized_browser,
    }
    report["checks"] = _artifact_checks(report)
    report["certified"] = all(report["checks"].values())
    report["certifiedTier"] = 1200 if report["certified"] else None
    validate_evidence_v2(report)
    return report


def _schema_type_matches(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return False


def _validate_schema_node(
    value: Any, node: dict[str, Any], root: dict[str, Any], path: str
) -> None:
    if "$ref" in node:
        reference = node["$ref"]
        if not isinstance(reference, str) or not reference.startswith("#/"):
            raise ReportError(f"schema v2 has an unsupported reference at {path}")
        target: Any = root
        for part in reference[2:].split("/"):
            target = target[part]
        _validate_schema_node(value, target, root, path)
        return
    if "const" in node and value != node["const"]:
        raise ReportError(f"schema v2 const failed at {path}")
    if "enum" in node and value not in node["enum"]:
        raise ReportError(f"schema v2 enum failed at {path}")
    expected = node.get("type")
    if isinstance(expected, list):
        if not any(_schema_type_matches(value, item) for item in expected):
            raise ReportError(f"schema v2 type failed at {path}")
    elif isinstance(expected, str) and not _schema_type_matches(value, expected):
        raise ReportError(f"schema v2 type failed at {path}")
    if isinstance(value, dict):
        required = set(node.get("required", []))
        missing = required - value.keys()
        if missing:
            raise ReportError(f"schema v2 required fields failed at {path}")
        properties = node.get("properties", {})
        if node.get("additionalProperties") is False:
            extras = value.keys() - properties.keys()
            if extras:
                raise ReportError(f"schema v2 unknown fields failed at {path}")
        for key, child in value.items():
            child_node = properties.get(key)
            if isinstance(child_node, dict):
                _validate_schema_node(child, child_node, root, f"{path}.{key}")
    if isinstance(value, list):
        if len(value) < node.get("minItems", 0) or len(value) > node.get("maxItems", math.inf):
            raise ReportError(f"schema v2 array length failed at {path}")
        item_node = node.get("items")
        if isinstance(item_node, dict):
            for index, child in enumerate(value):
                _validate_schema_node(child, item_node, root, f"{path}[{index}]")
    if isinstance(value, str):
        if len(value) < node.get("minLength", 0) or len(value) > node.get("maxLength", math.inf):
            raise ReportError(f"schema v2 string length failed at {path}")
        pattern = node.get("pattern")
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise ReportError(f"schema v2 pattern failed at {path}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(value):
            raise ReportError(f"schema v2 finite number failed at {path}")
        if "minimum" in node and value < node["minimum"]:
            raise ReportError(f"schema v2 minimum failed at {path}")
        if "maximum" in node and value > node["maximum"]:
            raise ReportError(f"schema v2 maximum failed at {path}")
        if "exclusiveMaximum" in node and value >= node["exclusiveMaximum"]:
            raise ReportError(f"schema v2 exclusive maximum failed at {path}")


def _validate_published_schema(report: dict[str, Any]) -> None:
    schema_path = Path(__file__).with_name("capacity-evidence-schema-v2.json")
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    _validate_schema_node(report, schema, schema, "evidence")


def validate_evidence_v2(report: dict[str, Any]) -> None:
    if not isinstance(report, dict):
        raise ReportError("capacity evidence must be an object")
    _validate_published_schema(report)
    _exact_fields(report, REPORT_FIELDS, "schema v2")
    if report["schemaVersion"] != SCHEMA_VERSION:
        raise ReportError("capacity evidence must use schema version 2")
    release = _object(report, "release")
    _exact_fields(release, {"workflowSha", "deployedSha", "exact"}, "release")
    workflow_sha = release["workflowSha"]
    deployed_sha = release["deployedSha"]
    for label, value in (("workflowSha", workflow_sha), ("deployedSha", deployed_sha)):
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ReportError(f"release.{label} is invalid")
    if release["exact"] is not (workflow_sha == deployed_sha):
        raise ReportError("release.exact is semantically inconsistent")
    context = {name: deepcopy(report[name]) for name in CONTEXT_FIELDS if name != "deployedSha"}
    context["deployedSha"] = deployed_sha
    _validate_context(context)
    metrics = _object(report, "metrics")
    _exact_fields(metrics, METRIC_FIELDS, "metrics")
    for name in (
        "requestFailureRate",
        "tileFailureRate",
        "tileP95Ms",
        "posterP95Ms",
        "maxCpuPct",
        "maxMemoryPct",
        "swapGrowthBytes",
        "restartGrowth",
        "minDiskFreePct",
    ):
        maximum = 1 if "FailureRate" in name else 10**15
        if name in {"maxCpuPct", "maxMemoryPct", "minDiskFreePct"}:
            maximum = 100
        _number(metrics[name], f"metrics.{name}", maximum=maximum)
    for name in ("oomObserved", "servicesExact", "readinessMaintained", "releaseExact"):
        _boolean(metrics[name], f"metrics.{name}")
    browser = _object(report, "browser")
    _exact_fields(browser, BROWSER_FIELDS, "browser")
    for name in browser:
        _boolean(browser[name], f"browser.{name}")
    checks = _object(report, "checks")
    _exact_fields(checks, CHECK_FIELDS, "checks")
    for name in checks:
        _boolean(checks[name], f"checks.{name}")
    recomputed = _artifact_checks(report)
    if checks != recomputed:
        raise ReportError("schema v2 semantic checks do not match recomputed evidence")
    certified = _boolean(report["certified"], "certified")
    if certified is not all(recomputed.values()):
        raise ReportError("certified is semantically inconsistent with checks")
    tier = report["certifiedTier"]
    if tier not in (None, 1200, 1500) or (certified is not (tier is not None)):
        raise ReportError("certifiedTier is semantically inconsistent with certification")


def markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    return "\n".join(
        [
            "# Capacity certification",
            "",
            f"- Workflow commit: `{report['release']['workflowSha']}`",
            f"- Deployed commit: `{report['release']['deployedSha']}`",
            f"- Result: **{'PASS' if report['certified'] else 'FAIL'}**",
            f"- Certified Classroom tier: **{report['certifiedTier'] or 'none'}**",
            "- Evidence schema: v2",
            "",
            "| Measure | Result |",
            "| --- | ---: |",
            f"| Request failures | {metrics['requestFailureRate']:.4%} |",
            f"| Tile p95 | {metrics['tileP95Ms']:.1f} ms |",
            f"| Poster p95 | {metrics['posterP95Ms']:.1f} ms |",
            f"| Peak CPU | {metrics['maxCpuPct']:.1f}% |",
            f"| Peak memory | {metrics['maxMemoryPct']:.1f}% |",
            f"| Swap growth | {metrics['swapGrowthBytes']} bytes |",
            f"| Container restart growth | {metrics['restartGrowth']} |",
            "",
            "Only aggregate, non-identifying measurements are included.",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build sanitized capacity evidence")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--observer", type=Path)
    parser.add_argument("--browser", type=Path)
    parser.add_argument("--evidence-context", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--browser-ci-run-id", type=int, required=True)
    parser.add_argument("--validate-context-only", action="store_true")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--markdown-output", type=Path)
    args = parser.parse_args()
    context = json.loads(args.evidence_context.read_text(encoding="utf-8"))
    validate_context_for_run(
        context, commit_sha=args.commit, browser_ci_run_id=args.browser_ci_run_id
    )
    if args.validate_context_only:
        return
    required_paths = {
        "summary": args.summary,
        "observer": args.observer,
        "browser": args.browser,
        "json-output": args.json_output,
        "markdown-output": args.markdown_output,
    }
    missing = [name for name, value in required_paths.items() if value is None]
    if missing:
        parser.error(f"the following arguments are required: {', '.join(missing)}")
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    observer = [
        json.loads(line)
        for line in args.observer.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    browser = json.loads(args.browser.read_text(encoding="utf-8"))
    report = build_report(
        summary,
        observer,
        browser,
        commit_sha=args.commit,
        evidence_context=context,
    )
    args.json_output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    args.markdown_output.write_text(markdown(report), encoding="utf-8")
    if not report["certified"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
