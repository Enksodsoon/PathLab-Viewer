"""Sanitized terminal observations; never substitutes for signed evidence v2."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from certification_report import validate_evidence_v2
from distributed_certification import merge_shards, validate_plan
from validate_postflight_evidence import validate as validate_postflight

JOBS = (
    "preflight",
    "fixtures",
    "arm",
    "shard",
    "sentinels",
    "fault-recovery",
    "decision",
    "cleanup",
    "postflight",
    "aggregate",
)
MEASURED_SHARD_FAILURE_CODES = {
    "participant-errors",
    "task-errors",
    "final-convergence",
    "tile-errors",
    "presenter-http-errors",
    "unexpected-sse-disconnects",
    "queue-overflows",
    "presenter-regression",
    "reconnect-shortfall",
    "presenter-rate-shortfall",
}
MEASURED_REPORT_CHECKS = {
    "requestFailures",
    "tileFailures",
    "tileLatency",
    "posterLatency",
    "cpu",
    "memory",
    "swap",
    "restarts",
    "oom",
    "readiness",
    "disk",
}


def build(
    evidence: Path,
    needs: dict[str, Any],
    *,
    run_id: str,
    sha: str,
    attempt: int,
    started_at: str | None,
    repository: str,
) -> dict[str, Any]:
    results = {
        name: needs[name].get("result", "unknown")
        if isinstance(needs.get(name), dict)
        else "unknown"
        for name in JOBS
    }
    harness: list[str] = []
    workload: list[str] = []

    def read(name: str) -> dict[str, Any]:
        label = name.upper().replace("-", "_").replace(".", "_")
        paths = list(evidence.rglob(name))
        if len(paths) != 1:
            harness.append(f"MISSING_OR_AMBIGUOUS_{label}")
            return {}
        try:
            value = json.loads(paths[0].read_text(encoding="utf-8"))
            if not isinstance(value, dict) or not value:
                raise ValueError("empty evidence")
            return value
        except (OSError, UnicodeError, ValueError):
            harness.append(f"INVALID_{label}")
            return {}

    plan = read("capacity-plan.json")
    digest = plan.get("planDigest")
    plan_bound = (
        plan.get("runId") == run_id
        and plan.get("workflowSha") == sha
        and isinstance(digest, str)
        and re.fullmatch(r"[0-9a-f]{64}", digest)
    )
    try:
        validate_plan(plan)
    except (ValueError, TypeError, KeyError):
        plan_bound = False
    if not plan_bound:
        harness.append("PLAN_IDENTITY_UNPROVED")

    def bound(value: dict[str, Any], *, candidate: bool = False) -> bool:
        return bool(
            plan_bound
            and value.get("runId") == run_id
            and value.get("candidateSha" if candidate else "workflowSha") == sha
            and value.get("planDigest") == digest
        )

    for name in JOBS:
        if results[name] in {"cancelled", "timed_out", "unknown"}:
            harness.append(f"JOB_{name.upper().replace('-', '_')}_{results[name].upper()}")
        elif results[name] == "failure" and name != "shard":
            harness.append(f"JOB_{name.upper().replace('-', '_')}_FAILED")

    completed_shards: list[dict[str, Any]] = []
    for index in range(6):
        shard = read(f"shard-{index}.json")
        if not bound(shard) or shard.get("shardIndex") != index:
            harness.append(f"SHARD_{index}_IDENTITY_UNPROVED")
            continue
        if shard.get("status") == "aborted":
            summary = shard.get("failureSummary")
            if not isinstance(summary, dict):
                harness.append(f"SHARD_{index}_INCOMPLETE")
                continue
            codes = summary.get("failureCodes", [])
            if (
                not isinstance(codes, list)
                or not codes
                or any(
                    not isinstance(code, str) or code not in MEASURED_SHARD_FAILURE_CODES
                    for code in codes
                )
            ):
                harness.append(f"SHARD_{index}_HARNESS_FAILURE")
            else:
                workload.append(f"SHARD_{index}_WORKLOAD_FAILURE")
            if summary.get("cleanupSucceeded") is not True:
                harness.append(f"SHARD_{index}_CLEANUP_UNPROVED")
        elif not isinstance(shard.get("stages"), list) or not shard["stages"]:
            harness.append(f"SHARD_{index}_REPORT_MISSING")
        else:
            completed_shards.append(shard)

    if len(completed_shards) == 6:
        try:
            merge_shards(plan, completed_shards)
        except (ValueError, TypeError, KeyError, IndexError):
            harness.append("COMPLETED_SHARD_EVIDENCE_INVALID")

    cleanup = read("capacity-cleanup.json")
    cleanup_bound = bound(cleanup)
    if (
        not cleanup_bound
        or not all(
            cleanup.get(key) is True
            for key in (
                "succeeded",
                "configurationRestored",
                "fixturesRemoved",
            )
        )
        or type(cleanup.get("bastionSessionsRemaining")) is not int
        or cleanup["bastionSessionsRemaining"] != 0
    ):
        harness.append("CLEANUP_UNPROVED")
    postflight = read("capacity-postflight.json")
    restored = False
    try:
        validate_postflight(postflight)
        restored = (
            bound(postflight)
            and postflight.get("expectedSha") == sha
            and postflight.get("deployedSha") == sha
        )
    except (ValueError, TypeError, KeyError):
        pass
    if not restored:
        harness.append("RESTORATION_UNPROVED")
    manifest = read("capacity-certification.json")
    # Both existing v2 shapes remain readable: full nested release/run evidence
    # and the compact NOT CERTIFIED result produced from a signed floor decision.
    manifest_bound = False
    if "release" in manifest:
        try:
            validate_evidence_v2(manifest)
            manifest_bound = bool(
                plan_bound
                and manifest["run"]["runId"] == run_id
                and manifest["release"]["workflowSha"] == sha
                and manifest["release"]["deployedSha"] == sha
            )
        except (ValueError, TypeError, KeyError):
            pass
    elif (
        manifest.get("schemaVersion") == 2
        and manifest.get("verdict") == "NOT CERTIFIED"
        and manifest.get("certified") is False
        and manifest.get("selectedCapacity") == 300
    ):
        manifest_bound = bound(manifest, candidate=True)
    if not manifest_bound:
        harness.append("RESULT_MANIFEST_UNPROVED")
    elif manifest.get("certified") is False:
        # The compact floor fallback is issued even when no measurements exist.
        # A negative verdict alone cannot distinguish a workload failure from
        # missing sentinel/accounting/host evidence or another failed gate.
        if "release" in manifest:
            measured_failures = [
                name for name in MEASURED_REPORT_CHECKS if manifest["checks"].get(name) is False
            ]
            if measured_failures:
                workload.extend(
                    f"MEASURED_{name.upper()}_FAILED" for name in sorted(measured_failures)
                )
            else:
                harness.append("QUALIFICATION_EVIDENCE_UNPROVED")
        else:
            harness.append("QUALIFICATION_EVIDENCE_UNPROVED")
    succeeded = (
        not harness and not workload and all(result == "success" for result in results.values())
    )
    if not succeeded and not harness and not workload:
        harness.append("JOB_GRAPH_INCOMPLETE")
    category = "HARNESS_FAILURE" if harness else "WORKLOAD_FAILURE" if workload else None
    count = cleanup.get("bastionSessionsRemaining") if cleanup_bound else None
    if type(count) is not int or count < 0:
        count = None
    return {
        "jobId": run_id,
        "kind": "capacity-certification",
        "state": "SUCCEEDED" if succeeded else "FAILED_TERMINAL",
        "releaseSha": sha,
        "startedAt": started_at,
        "finishedAt": datetime.now(UTC).isoformat(),
        "attempt": attempt,
        "progressCounters": results,
        "resultManifest": ("capacity-certification.json" if manifest_bound else None),
        "failureCode": category,
        "failureCategory": category,
        "harnessFailureCodes": harness,
        "workloadFailureCodes": workload,
        "restorationState": "RESTORED" if restored else "UNPROVED",
        "fixtureCount": 0 if cleanup_bound and cleanup.get("fixturesRemoved") is True else None,
        "runOwnedBastionCount": count,
        "logPath": f"https://github.com/{repository}/actions/runs/{run_id}",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--started-at", default=None)
    args = parser.parse_args()
    try:
        needs = json.loads(os.environ.get("JOB_RESULTS", "{}"))
        if not isinstance(needs, dict):
            needs = {}
    except ValueError:
        needs = {}
    value = build(
        args.evidence,
        needs,
        run_id=os.environ["GITHUB_RUN_ID"],
        sha=os.environ["GITHUB_SHA"],
        attempt=int(os.environ["GITHUB_RUN_ATTEMPT"]),
        started_at=args.started_at or None,
        repository=os.environ["GITHUB_REPOSITORY"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    temporary.replace(args.output)


if __name__ == "__main__":
    main()
