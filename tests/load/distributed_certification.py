"""Fail-closed planning and aggregation for the six-runner capacity workflow.

This module never handles credentials or participant-level observations.  Its inputs and
outputs are deliberately limited to synthetic run identifiers and aggregate measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, cast

ICT = timezone(timedelta(hours=7))
SHARD_COUNT = 6
SHARD_START_TOLERANCE_MS = 1_000
ADMISSION_SECONDS = 60
TRANSITION_SECONDS = 30
POST_RUN_BUFFER_SECONDS = 900
STAGE_SPECS = (
    ("smoke-2", 2, 30, False),
    ("acceptance-100", 100, 600, False),
    ("boundary-300", 300, 600, False),
    ("boundary-600", 600, 600, False),
    ("boundary-900", 900, 600, False),
    ("sustained-1200", 1_200, 3_600, True),
    ("headroom-1500", 1_500, 600, True),
    ("breakpoint-1750", 1_750, 300, False),
    ("breakpoint-2000", 2_000, 300, False),
    ("recovery-1200", 1_200, 600, False),
)
SAFE_ID = re.compile(r"^[a-z0-9-]{1,64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")


class CertificationError(ValueError):
    """Raised when capacity evidence cannot support a certification claim."""


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _targets(total: int) -> list[int]:
    quotient, remainder = divmod(total, SHARD_COUNT)
    return [quotient + (1 if index < remainder else 0) for index in range(SHARD_COUNT)]


def _iso(epoch_ms: int) -> str:
    return datetime.fromtimestamp(epoch_ms / 1_000, ICT).isoformat()


def build_plan(
    *,
    run_id: str,
    workflow_sha: str,
    browser_ci_run_id: int,
    start_epoch_ms: int,
    now_epoch_ms: int | None = None,
) -> dict[str, object]:
    """Build the immutable public schedule shared by all six shards."""
    now = int(time.time() * 1_000) if now_epoch_ms is None else now_epoch_ms
    if not SAFE_ID.fullmatch(run_id):
        raise CertificationError("run ID must be a safe aggregate identifier")
    if not SHA.fullmatch(workflow_sha):
        raise CertificationError("workflow SHA must be a full lowercase commit SHA")
    if not isinstance(browser_ci_run_id, int) or browser_ci_run_id < 1:
        raise CertificationError("browser CI run ID must be positive")
    if start_epoch_ms < now + 120_000:
        raise CertificationError("a future start epoch at least 120 seconds away is required")
    start = datetime.fromtimestamp(start_epoch_ms / 1_000, ICT)
    if start.hour < 2 or start.hour >= 5:
        raise CertificationError("the start epoch must be inside 02:00-05:00 ICT")

    cursor = start_epoch_ms
    stages: list[dict[str, object]] = []
    for name, users, duration, strict in STAGE_SPECS:
        hold_start = cursor + ADMISSION_SECONDS * 1_000
        hold_end = hold_start + duration * 1_000
        transition_end = hold_end + TRANSITION_SECONDS * 1_000
        stages.append(
            {
                "name": name,
                "targetUsers": users,
                "durationSeconds": duration,
                "strictGate": strict,
                # startEpochMs remains the synchronized measured start for v1
                # consumers; admission and cleanup are explicit so it cannot be
                # mistaken for the start of ramp-up.
                "startEpochMs": hold_start,
                "admissionStartEpochMs": cursor,
                "holdStartEpochMs": hold_start,
                "holdEndEpochMs": hold_end,
                "transitionEndEpochMs": transition_end,
                "shardTargets": _targets(users),
            }
        )
        cursor = transition_end
    end_with_buffer = datetime.fromtimestamp(
        (cursor + POST_RUN_BUFFER_SECONDS * 1_000) / 1_000, ICT
    )
    if end_with_buffer.date() != start.date() or end_with_buffer.hour >= 5:
        raise CertificationError(
            "the run and its post-run restoration buffer must finish inside 02:00-05:00 ICT"
        )
    unsigned: dict[str, object] = {
        "schemaVersion": 1,
        "runId": run_id,
        "workflowSha": workflow_sha,
        "browserCiRunId": browser_ci_run_id,
        "window": "02:00-05:00 ICT",
        "startEpochMs": start_epoch_ms,
        "stages": stages,
    }
    return {**unsigned, "planDigest": _digest(unsigned)}


def _require_dict(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise CertificationError(f"{label} must be an object")
    return value


def _require_exact(value: dict[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise CertificationError(f"{label} fields are incomplete or contain private data")


def validate_plan(plan: dict[str, object]) -> None:
    """Require the immutable plan's exact fields and self-authenticating digest."""
    _require_exact(
        plan,
        {
            "schemaVersion",
            "runId",
            "workflowSha",
            "browserCiRunId",
            "window",
            "startEpochMs",
            "stages",
            "planDigest",
        },
        "capacity plan",
    )
    unsigned = {key: value for key, value in plan.items() if key != "planDigest"}
    if plan["planDigest"] != _digest(unsigned):
        raise CertificationError("capacity plan digest is invalid")


def _validate_strict_measurements(raw: object, label: str) -> None:
    measurements = _require_dict(raw, label)
    _require_exact(measurements, {"journeys", "realtime", "pressure"}, label)
    journeys = _require_dict(measurements["journeys"], f"{label} journeys")
    _require_exact(
        journeys,
        {"presenterSse", "classroomControl", "generalApi", "staticTile", "poster", "question"},
        f"{label} journeys",
    )
    for name, raw_journey in journeys.items():
        journey = _require_dict(raw_journey, f"journey {name}")
        fields = {"requests", "failures", "failureRate", "latencyMs"}
        if name == "presenterSse":
            fields.add("fanout")
        _require_exact(journey, fields, f"journey {name}")
        if name == "presenterSse":
            fanout = _require_dict(journey["fanout"], f"journey {name} fanout")
            _require_exact(fanout, {"sentEpochMs", "receivedEpochMs"}, "presenter fanout")
            for field in ("sentEpochMs", "receivedEpochMs"):
                values = _require_dict(fanout[field], f"presenter fanout {field}")
                if len(values) > 128 or not all(
                    isinstance(key, str) and key.isdigit() and isinstance(value, int)
                    for key, value in values.items()
                ):
                    raise CertificationError("presenter fanout timestamps are invalid")
        latency = _require_dict(journey["latencyMs"], f"journey {name} latency")
        _require_exact(latency, {"p50", "p95", "p99"}, f"journey {name} latency")
    realtime = _require_dict(measurements["realtime"], f"{label} realtime")
    _require_exact(
        realtime,
        {
            "converged",
            "expected",
            "reconnectsSucceeded",
            "reconnectsExpected",
            "lostCriticalEvents",
            "unexpectedDisconnects",
            "queueOverflows",
        },
        f"{label} realtime",
    )
    if realtime["unexpectedDisconnects"] != 0 or realtime["queueOverflows"] != 0:
        raise CertificationError(f"{label} contains realtime failures")
    pressure = _require_dict(measurements["pressure"], f"{label} pressure")
    _require_exact(
        pressure,
        {
            "queueMaxDepth",
            "queueCapacity",
            "eventLoopP99Ms",
            "poolWaitP95Ms",
            "poolTimeouts",
            "sqliteLockErrors",
        },
        f"{label} pressure",
    )


def merge_shards(
    plan: dict[str, object], shard_results: Iterable[dict[str, object]]
) -> dict[str, object]:
    """Validate and merge six aggregate shard artifacts into evidence-v2 stages."""
    validate_plan(plan)
    shards = list(shard_results)
    if len(shards) != SHARD_COUNT:
        raise CertificationError("exactly six shard results are required")
    expected_digest = plan.get("planDigest")
    plan_stages = plan.get("stages")
    if not isinstance(expected_digest, str) or not isinstance(plan_stages, list):
        raise CertificationError("the signed plan is incomplete")
    seen: set[int] = set()
    normalized_by_index: dict[int, list[dict[str, Any]]] = {}
    outer_fields = {
        "schemaVersion",
        "runId",
        "workflowSha",
        "planDigest",
        "shardId",
        "shardIndex",
        "stages",
        "sustainedMeasurements",
        "headroomMeasurements",
        "privacy",
    }
    stage_fields = {
        "name",
        "targetUsers",
        "achievedUsers",
        "admissionStartedEpochMs",
        "holdStartedEpochMs",
        "holdEndedEpochMs",
        "completed",
        "stalled",
        "outcome",
        "abortCauses",
        "cleanupSucceeded",
        "generator",
    }
    generator_fields = {"cpuPctMax", "memoryPctMax", "droppedIterations", "saturated"}
    for raw in shards:
        shard = _require_dict(raw, "shard result")
        _require_exact(shard, outer_fields, "shard result")
        index = shard["shardIndex"]
        if not isinstance(index, int) or not 0 <= index < SHARD_COUNT or index in seen:
            raise CertificationError("shard indexes must uniquely cover zero through five")
        seen.add(index)
        if shard["schemaVersion"] != 1 or shard["runId"] != plan.get("runId"):
            raise CertificationError("shard result is not bound to this run")
        if shard["workflowSha"] != plan.get("workflowSha"):
            raise CertificationError("shard workflow SHA does not match the plan")
        if shard["planDigest"] != expected_digest:
            raise CertificationError("shard plan digest does not match the plan")
        if shard["shardId"] != f"linux-{index + 1}":
            raise CertificationError("shard ID does not match its matrix index")
        privacy = _require_dict(shard["privacy"], "shard privacy")
        _require_exact(
            privacy,
            {"aggregateOnly", "credentialsMasked", "syntheticFixturesOnly"},
            "shard privacy",
        )
        if not all(privacy.values()):
            raise CertificationError("shard privacy boundary was not satisfied")
        _validate_strict_measurements(shard["sustainedMeasurements"], "sustained measurements")
        _validate_strict_measurements(shard["headroomMeasurements"], "headroom measurements")
        records = shard["stages"]
        if not isinstance(records, list) or len(records) != len(plan_stages):
            raise CertificationError("shard result requires every planned stage")
        normalized: list[dict[str, Any]] = []
        heavy_escalation_blocked = False
        for position, (record_raw, spec_raw) in enumerate(zip(records, plan_stages, strict=True)):
            record = _require_dict(record_raw, f"shard stage {position}")
            spec = _require_dict(spec_raw, f"plan stage {position}")
            _require_exact(record, stage_fields, f"shard stage {position}")
            generator = _require_dict(record["generator"], "generator")
            _require_exact(generator, generator_fields, "generator")
            target = spec["shardTargets"][index]
            if record["name"] != spec["name"] or record["targetUsers"] != target:
                raise CertificationError("shard stage does not match its planned target")
            outcome = record["outcome"]
            abort_causes = record["abortCauses"]
            is_breakpoint = str(spec["name"]).startswith("breakpoint-")
            if not isinstance(abort_causes, list) or not all(
                isinstance(item, str) for item in abort_causes
            ):
                raise CertificationError("shard abort causes are invalid")
            if outcome == "passed":
                if heavy_escalation_blocked and is_breakpoint:
                    raise CertificationError("blocked heavy escalation was attempted")
                if record["achievedUsers"] < target:
                    raise CertificationError("shard missed achieved-user target")
                if record["completed"] is not True or abort_causes:
                    raise CertificationError("shard stage did not complete")
            elif outcome == "protected-early-stop":
                if not is_breakpoint or record["completed"] is not False or not abort_causes:
                    raise CertificationError("early stop is permitted only for a heavy stage")
                if not set(abort_causes).issubset(
                    {
                        "cpu-sustained",
                        "memory",
                        "queue-pressure",
                        "event-loop",
                        "failure-rate",
                        "pool-timeout",
                        "sqlite-lock",
                        "latency",
                    }
                ):
                    raise CertificationError("heavy stage abort cause is not approved")
                heavy_escalation_blocked = True
            elif outcome == "skipped":
                if (
                    not is_breakpoint
                    or not heavy_escalation_blocked
                    or record["completed"] is not False
                    or abort_causes != ["escalation-blocked"]
                    or record["achievedUsers"] != 0
                ):
                    raise CertificationError("stage skip is not an approved heavy transition")
            else:
                raise CertificationError("shard stage outcome is invalid")
            if record["stalled"] is not False:
                raise CertificationError("shard stage stalled")
            if record["cleanupSucceeded"] is not True:
                raise CertificationError("synthetic stage cleanup did not succeed")
            drift = abs(record["holdStartedEpochMs"] - spec["holdStartEpochMs"])
            if drift > SHARD_START_TOLERANCE_MS:
                raise CertificationError("shard timing drift exceeded 1000 ms")
            admission_drift = abs(record["admissionStartedEpochMs"] - spec["admissionStartEpochMs"])
            if admission_drift > SHARD_START_TOLERANCE_MS:
                raise CertificationError("shard admission timing drift exceeded 1000 ms")
            held_ms = record["holdEndedEpochMs"] - record["holdStartedEpochMs"]
            if outcome == "passed" and held_ms < spec["durationSeconds"] * 1_000:
                raise CertificationError("shard did not sustain the full planned hold")
            if generator["saturated"] is not False:
                raise CertificationError("shard generator saturated")
            if generator["droppedIterations"] != 0:
                raise CertificationError("shard generator dropped iterations")
            if not 0 <= generator["cpuPctMax"] <= 100 or not 0 <= generator["memoryPctMax"] <= 100:
                raise CertificationError("shard generator resource measurements are invalid")
            normalized.append(record)
        normalized_by_index[index] = normalized

    merged: list[dict[str, object]] = []
    for position, spec_raw in enumerate(plan_stages):
        spec = _require_dict(spec_raw, f"plan stage {position}")
        stage_shards = []
        for index in range(SHARD_COUNT):
            record = normalized_by_index[index][position]
            drift = abs(record["holdStartedEpochMs"] - spec["holdStartEpochMs"])
            stage_shards.append(
                {
                    "shardId": f"linux-{index + 1}",
                    "targetUsers": record["targetUsers"],
                    "achievedUsers": record["achievedUsers"],
                    "healthy": True,
                    "startEpochMs": record["holdStartedEpochMs"],
                    "maxTimingDriftMs": drift,
                    "timingWithinTolerance": True,
                    "generator": record["generator"],
                }
            )
        outcomes = {
            item["outcome"]
            for item in (normalized_by_index[index][position] for index in range(SHARD_COUNT))
        }
        if len(outcomes) != 1:
            raise CertificationError("all shards must agree on the stage outcome")
        outcome = outcomes.pop()
        end_epoch_ms = spec["holdEndEpochMs"]
        merged.append(
            {
                "name": spec["name"],
                "targetUsers": spec["targetUsers"],
                "achievedUsers": sum(item["achievedUsers"] for item in stage_shards),
                "startedAt": _iso(spec["holdStartEpochMs"]),
                "endedAt": _iso(end_epoch_ms),
                "durationSeconds": spec["durationSeconds"],
                "strictGate": spec["strictGate"],
                "outcome": outcome,
                "abortCauses": sorted(
                    {
                        cause
                        for index in range(SHARD_COUNT)
                        for cause in normalized_by_index[index][position]["abortCauses"]
                    }
                ),
                "shards": stage_shards,
            }
        )
    return {
        "stages": merged,
        "sustainedMeasurements": [
            shards_by_index["sustainedMeasurements"]
            for shards_by_index in sorted(shards, key=lambda item: cast(int, item["shardIndex"]))
        ],
        "headroomMeasurements": [
            shards_by_index["headroomMeasurements"]
            for shards_by_index in sorted(shards, key=lambda item: cast(int, item["shardIndex"]))
        ],
    }


def early_stop_causes(measurement: dict[str, float | int]) -> list[str]:
    """Return every approved heavy-stage early-stop cause, never a relaxed subset."""
    causes: list[str] = []
    if measurement.get("cpuPct", 0) >= 80 and measurement.get("cpuDurationSeconds", 0) >= 30:
        causes.append("cpu-sustained")
    if measurement.get("memoryPct", 0) >= 85:
        causes.append("memory")
    capacity = measurement.get("queueCapacity", 0)
    if capacity and measurement.get("queueDepth", 0) >= capacity * 0.75:
        causes.append("queue-pressure")
    if measurement.get("eventLoopP99Ms", 0) > 250:
        causes.append("event-loop")
    if measurement.get("failureRate", 0) >= 0.005:
        causes.append("failure-rate")
    if measurement.get("poolTimeouts", 0) > 0:
        causes.append("pool-timeout")
    if measurement.get("sqliteLockErrors", 0) > 0:
        causes.append("sqlite-lock")
    if measurement.get("latencyRatio", 0) > 2 and measurement.get("latencyBreachSeconds", 0) >= 120:
        causes.append("latency")
    return causes


def _load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CertificationError(f"{path} must contain an object")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description="Distributed capacity evidence tooling")
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--run-id", required=True)
    plan_parser.add_argument("--workflow-sha", required=True)
    plan_parser.add_argument("--browser-ci-run-id", required=True, type=int)
    plan_parser.add_argument("--start-epoch-ms", required=True, type=int)
    plan_parser.add_argument("--output", required=True, type=Path)
    merge_parser = subparsers.add_parser("merge")
    merge_parser.add_argument("--plan", required=True, type=Path)
    merge_parser.add_argument("--shard", action="append", required=True, type=Path)
    merge_parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command == "plan":
        result = build_plan(
            run_id=args.run_id,
            workflow_sha=args.workflow_sha,
            browser_ci_run_id=args.browser_ci_run_id,
            start_epoch_ms=args.start_epoch_ms,
        )
    else:
        result = merge_shards(_load(args.plan), [_load(path) for path in args.shard])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
