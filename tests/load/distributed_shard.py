"""Run one of six synchronized aggregate-only Classroom load shards."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, cast

import httpx
from classroom_sse import stage_credentials
from distributed_certification import CertificationError, validate_plan


class ShardCancelled(RuntimeError):
    """Raised inside the main thread so signal cancellation can be persisted."""


def cancellation_handler(signum: int, _frame: object) -> None:
    raise ShardCancelled(f"signal {signum}")


def atomic_write_json(path: Path, value: dict[str, object]) -> None:
    """Replace a shard artifact atomically so cancellation cannot truncate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def partial_shard_result(
    plan: dict[str, Any],
    shard_index: int,
    completed_stages: list[dict[str, Any]],
    *,
    abort_cause: str,
    failure_summary: dict[str, object] | None = None,
) -> dict[str, object]:
    """Build a sanitized, run-bound progress artifact after an interrupted shard."""
    if not abort_cause or len(abort_cause) > 128:
        raise CertificationError("a bounded abort cause is required")
    result: dict[str, object] = {
        "schemaVersion": 1,
        "status": "aborted",
        "abortCause": abort_cause,
        "runId": plan["runId"],
        "workflowSha": plan["workflowSha"],
        "planDigest": plan["planDigest"],
        "shardId": f"linux-{shard_index + 1}",
        "shardIndex": shard_index,
        "completedStages": completed_stages,
        "privacy": {
            "aggregateOnly": True,
            "credentialsMasked": True,
            "syntheticFixturesOnly": True,
        },
    }
    if failure_summary is not None:
        result["failureSummary"] = failure_summary
    return result


def safe_harness_failure_summary(
    stage: dict[str, Any], execution: dict[str, Any], shard_index: int
) -> dict[str, object]:
    """Classify a failed harness using aggregate, non-identifying fields only."""
    report = execution.get("report")
    report = report if isinstance(report, dict) else {}
    convergence = report.get("finalConvergence")
    convergence = convergence if isinstance(convergence, dict) else {}
    participant_errors = report.get("participantErrors")
    task_errors = report.get("taskErrors")
    participant_error_count = len(participant_errors) if isinstance(participant_errors, list) else 0
    task_error_count = len(task_errors) if isinstance(task_errors, list) else 0
    codes: list[str] = []
    if not report:
        codes.append("report-missing")
    if execution.get("stalled") is True:
        codes.append("harness-stalled")
    if participant_error_count:
        codes.append("participant-errors")
    if task_error_count:
        codes.append("task-errors")
    if convergence.get("converged") != convergence.get("expected"):
        codes.append("final-convergence")
    if int(report.get("tileErrors", 0)) > 0:
        codes.append("tile-errors")
    if int(report.get("presenterHttpErrors", 0)) > 0:
        codes.append("presenter-http-errors")
    if int(report.get("unexpectedSseDisconnects", 0)) > 0:
        codes.append("unexpected-sse-disconnects")
    if int(report.get("queueOverflows", 0)) > 0:
        codes.append("queue-overflows")
    if int(report.get("stalePresenterIncidents", 0)) > 0:
        codes.append("presenter-regression")
    if int(report.get("successfulReconnects", 0)) != int(report.get("expectedReconnects", 0)):
        codes.append("reconnect-shortfall")
    if int(report.get("presenterSendSuccesses", 0)) < int(
        report.get("expectedPresenterUpdates", 0)
    ):
        codes.append("presenter-rate-shortfall")
    if execution.get("exitCode") != 0 and not codes:
        codes.append("unclassified-nonzero-exit")
    return {
        "stage": str(stage["name"]),
        "targetUsers": int(stage["shardTargets"][shard_index]),
        "exitCode": int(execution.get("exitCode", 1)),
        "privateErrorPresent": execution.get("privateErrorPresent") is True,
        "cleanupSucceeded": execution.get("cleanupSucceeded") is True,
        "participantErrorCount": participant_error_count,
        "taskErrorCount": task_error_count,
        "participants": int(report.get("participants", 0)),
        "finalConverged": int(convergence.get("converged", 0)),
        "finalExpected": int(convergence.get("expected", 0)),
        "serverActiveSseAtHoldStart": int(report.get("serverActiveSseAtHoldStart", 0)),
        "serverPeakSseAtHoldStart": int(report.get("serverPeakSseAtHoldStart", 0)),
        "failureCodes": codes,
    }


def completed_stage_marker(stage_name: str, execution: dict[str, Any]) -> dict[str, str] | None:
    """Return only truthful completed/protected/skipped stage progress."""
    if execution.get("skipped") is True:
        outcome = "skipped"
    elif execution.get("earlyStopCauses"):
        outcome = "protected-early-stop"
    elif execution.get("exitCode") == 0 and execution.get("stalled") is not True:
        outcome = "passed"
    else:
        return None
    return {"name": stage_name, "outcome": outcome}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise CertificationError(f"{path} must contain an object")
    return value


def _read_linux_process(pid: int) -> tuple[float, int] | None:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines()
        ticks = int(stat[13]) + int(stat[14])
        rss_kib = next(
            int(line.split()[1]) for line in status if line.startswith("VmRSS:")
        )
        ticks_per_second = int(cast(Any, os).sysconf("SC_CLK_TCK"))
        return ticks / ticks_per_second, rss_kib * 1024
    except (IndexError, OSError, StopIteration, ValueError):
        # A child can become a zombie between poll() and the /proc reads. Linux
        # then omits VmRSS even though the status file still exists.
        return None


def _total_memory() -> int:
    try:
        line = next(
            item
            for item in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
            if item.startswith("MemTotal:")
        )
        return int(line.split()[1]) * 1024
    except (OSError, StopIteration, ValueError):
        return 1


def _run_harness(environment: dict[str, str], timeout_seconds: int) -> dict[str, Any]:
    process = subprocess.Popen(
        [sys.executable, "tests/load/classroom_sse.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    started = time.monotonic()
    previous = _read_linux_process(process.pid)
    previous_at = started
    max_cpu = 0.0
    max_memory = 0.0
    stalled = False
    while process.poll() is None:
        if time.monotonic() - started > timeout_seconds:
            stalled = True
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
            break
        time.sleep(1)
        current = _read_linux_process(process.pid)
        now = time.monotonic()
        if current is not None and previous is not None and now > previous_at:
            max_cpu = max(max_cpu, (current[0] - previous[0]) / (now - previous_at) * 100)
            max_memory = max(max_memory, current[1] / _total_memory() * 100)
        previous, previous_at = current, now
    stdout, stderr = process.communicate()
    report: dict[str, Any] = {}
    if stdout.strip():
        try:
            loaded = json.loads(stdout)
            if isinstance(loaded, dict):
                report = loaded
        except json.JSONDecodeError:
            pass
    errors = report.get("participantErrors", [])
    task_errors = report.get("taskErrors", [])
    dropped = (
        len(errors) + len(task_errors)
        if isinstance(errors, list) and isinstance(task_errors, list)
        else 1
    )
    return {
        "exitCode": process.returncode if process.returncode is not None else 1,
        "stalled": stalled,
        "report": report,
        "generator": {
            "cpuPctMax": round(min(100.0, max_cpu), 3),
            "memoryPctMax": round(min(100.0, max_memory), 3),
            "droppedIterations": dropped,
            "saturated": max_cpu >= 90 or max_memory >= 90,
        },
        # stderr is intentionally not returned or retained because it may contain URLs.
        "privateErrorPresent": bool(stderr.strip()),
    }


def _cleanup_synthetic_session(
    environment: dict[str, str],
    *,
    transport: httpx.BaseTransport | None = None,
    barrier_timeout_seconds: float = 28,
) -> bool:
    """Acknowledge completion; only shard zero resets after all six acknowledgements."""
    try:
        with httpx.Client(
            base_url=environment["PATHLAB_CLASSROOM_BASE_URL"],
            timeout=20,
            transport=transport,
        ) as client:
            login = client.post(
                "/api/v1/auth/session",
                json={
                    "username": environment["PATHLAB_CLASSROOM_ADMIN_USERNAME"],
                    "password": environment["PATHLAB_CLASSROOM_ADMIN_PASSWORD"],
                },
            )
            login.raise_for_status()
            headers = {
                "X-CSRF-Token": login.json()["csrfToken"],
                "X-PathLab-Synthetic-Run": environment["PATHLAB_CLASSROOM_RUN_ID"],
            }
            session_path = (
                f"/api/v1/admin/classroom/sessions/{environment['PATHLAB_CLASSROOM_SESSION_ID']}"
            )
            shard_index = int(environment["PATHLAB_CLASSROOM_SHARD_INDEX"])
            deadline = time.monotonic() + barrier_timeout_seconds
            while True:
                response = client.post(
                    f"{session_path}/synthetic-stage-ack",
                    headers=headers,
                    json={
                        "stageName": environment["PATHLAB_CLASSROOM_STAGE_NAME"],
                        "shardIndex": shard_index,
                    },
                )
                response.raise_for_status()
                if shard_index != 0:
                    return True
                if response.json().get("complete") is True:
                    reset = client.post(f"{session_path}/synthetic-reset", headers=headers)
                    return reset.status_code == 204
                if time.monotonic() >= deadline:
                    return False
                time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
        return False


def _load_stage_manifest(
    plan: dict[str, Any], environment: dict[str, str]
) -> dict[str, Any] | None:
    path = environment.get("PATHLAB_CLASSROOM_STAGE_MANIFEST", "")
    protected_remote = environment.get("PATHLAB_CLASSROOM_PROTECTED_REMOTE", "").lower() == "true"
    if not path:
        if protected_remote:
            raise CertificationError(
                "protected remote certification requires per-stage synthetic sessions"
            )
        return None
    manifest = _load(Path(path))
    # Validate the complete manifest, not only the first selected entry.
    first_stage = plan["stages"][0]["name"]
    stage_credentials(plan, first_stage, manifest)
    return manifest


def _strict_measurements(report: dict[str, Any], target: int) -> dict[str, Any]:
    journeys = report.get("journeys")
    server_metrics = report.get("serverMetrics")
    final_convergence = report.get("finalConvergence")
    required_pressure = {
        "queueMaxDepth",
        "queueCapacity",
        "eventLoopP99Ms",
        "poolWaitP95Ms",
        "poolTimeouts",
        "sqliteLockErrors",
    }
    if not isinstance(journeys, dict) or not isinstance(server_metrics, dict):
        raise CertificationError("strict stage measurements are missing")
    if not required_pressure.issubset(server_metrics):
        raise CertificationError("strict pressure measurements are missing")
    if not isinstance(final_convergence, dict):
        raise CertificationError("strict convergence measurements are missing")
    if (
        report.get("activeSseAtHoldStart") != target
        or report.get("serverActiveSseAtHoldStart", 0) < report.get("globalTargetUsers", 1)
        or report.get("serverPeakSseAtHoldStart", 0) < report.get("globalTargetUsers", 1)
    ):
        raise CertificationError("strict active SSE target was not sustained")
    reconnect_expected = max(1, target // 10)
    reconnect_rate = report.get("reconnectSuccessRate")
    return {
        "journeys": journeys,
        "realtime": {
            "converged": final_convergence["converged"],
            "expected": final_convergence["expected"],
            "reconnectsSucceeded": reconnect_expected if reconnect_rate == 1 else 0,
            "reconnectsExpected": reconnect_expected,
            "lostCriticalEvents": report.get("lostDiscreteEvents", 1),
            "unexpectedDisconnects": report.get("unexpectedSseDisconnects", 1),
            "queueOverflows": report.get("queueOverflows", 1),
        },
        "pressure": {name: server_metrics[name] for name in required_pressure},
    }


def shard_result_from_reports(
    plan: dict[str, Any], shard_index: int, stage_reports: list[dict[str, Any]]
) -> dict[str, object]:
    stages = plan.get("stages")
    if not isinstance(stages, list) or len(stage_reports) != len(stages):
        raise CertificationError("shard requires every planned stage report")
    normalized = []
    sustained_measurements: dict[str, Any] | None = None
    headroom_measurements: dict[str, Any] | None = None
    for position, (stage, execution) in enumerate(zip(stages, stage_reports, strict=True)):
        target = stage["shardTargets"][shard_index]
        report = execution.get("report")
        if not isinstance(report, dict):
            raise CertificationError(f"stage {position} did not emit an aggregate report")
        convergence = report.get("finalConvergence")
        early_stop = execution.get("earlyStopCauses")
        skipped = execution.get("skipped") is True
        if skipped:
            outcome = "skipped"
            abort_causes = ["escalation-blocked"]
            achieved = 0
        elif isinstance(early_stop, list) and early_stop:
            outcome = "protected-early-stop"
            abort_causes = [str(item) for item in early_stop]
            achieved = int(report.get("participants", 0))
        elif target == 0:
            outcome = "passed"
            abort_causes = []
            achieved = 0
        else:
            if execution.get("exitCode") != 0:
                raise CertificationError(f"stage {position} harness failed")
            if not isinstance(convergence, dict) or convergence.get("converged") != target:
                raise CertificationError(f"stage {position} did not converge")
            if report.get("participants") != target:
                raise CertificationError(f"stage {position} achieved-user count is invalid")
            if report.get("participantErrors") or report.get("taskErrors"):
                raise CertificationError(f"stage {position} reported client errors")
            if stage["name"] == "recovery-1200" and not (
                0 <= report.get("recoveryConvergenceSeconds", 999) <= 30
                and report.get("recoveryReadyEpochMs", 0) > 0
                and report.get("recoveryLocalConvergence")
                == {"converged": target, "expected": target}
            ):
                raise CertificationError(
                    "recovery stage did not prove all-client convergence within 30 seconds"
                )
            achieved = target
            outcome = "passed"
            abort_causes = []
            if stage["name"] == "sustained-1200":
                sustained_measurements = _strict_measurements(report, target)
            elif stage["name"] == "headroom-1500":
                headroom_measurements = _strict_measurements(report, target)
        normalized.append(
            {
                "name": stage["name"],
                "targetUsers": target,
                "achievedUsers": achieved,
                "admissionStartedEpochMs": execution["admissionStartedEpochMs"],
                "holdStartedEpochMs": execution["holdStartedEpochMs"],
                "holdEndedEpochMs": execution["holdEndedEpochMs"],
                "completed": outcome == "passed" and execution.get("exitCode") == 0,
                "stalled": execution.get("stalled") is True,
                "outcome": outcome,
                "abortCauses": abort_causes,
                "cleanupSucceeded": execution.get("cleanupSucceeded") is True,
                "generator": execution["generator"],
            }
        )
    if sustained_measurements is None or headroom_measurements is None:
        raise CertificationError("strict stage measurements were not produced")
    return {
        "schemaVersion": 1,
        "runId": plan["runId"],
        "workflowSha": plan["workflowSha"],
        "planDigest": plan["planDigest"],
        "shardId": f"linux-{shard_index + 1}",
        "shardIndex": shard_index,
        "stages": normalized,
        "sustainedMeasurements": sustained_measurements,
        "headroomMeasurements": headroom_measurements,
        "privacy": {
            "aggregateOnly": True,
            "credentialsMasked": True,
            "syntheticFixturesOnly": True,
        },
    }


def run(
    plan: dict[str, Any], shard_index: int, *, output_path: Path | None = None
) -> dict[str, object]:
    validate_plan(plan)
    if not 0 <= shard_index < 6:
        raise CertificationError("shard index must be zero through five")
    reports: list[dict[str, Any]] = []
    environment = os.environ.copy()
    completed_prefix: list[dict[str, Any]] = []
    failure_summary: dict[str, object] | None = None
    if output_path is not None:
        atomic_write_json(
            output_path,
            partial_shard_result(plan, shard_index, completed_prefix, abort_cause="in-progress"),
        )
    try:
        manifest = _load_stage_manifest(plan, environment)
        heavy_escalation_blocked = False
        for stage in plan["stages"]:
            admission_epoch_ms = int(stage["admissionStartEpochMs"])
            remaining = (admission_epoch_ms - int(time.time() * 1_000)) / 1_000
            if remaining > 0:
                time.sleep(remaining)
            actual_admission_start = int(time.time() * 1_000)
            target = int(stage["shardTargets"][shard_index])
            is_breakpoint = str(stage["name"]).startswith("breakpoint-")
            if heavy_escalation_blocked and is_breakpoint:
                execution = {
                    "exitCode": 1,
                    "stalled": False,
                    "skipped": True,
                    "report": {"participants": 0},
                    "generator": {
                        "cpuPctMax": 0.0,
                        "memoryPctMax": 0.0,
                        "droppedIterations": 0,
                        "saturated": False,
                    },
                    "admissionStartedEpochMs": actual_admission_start,
                    "holdStartedEpochMs": int(stage["holdStartEpochMs"]),
                    "holdEndedEpochMs": int(stage["holdStartEpochMs"]),
                    "cleanupSucceeded": True,
                }
            elif target == 0:
                hold_start = int(stage["holdStartEpochMs"])
                remaining = (hold_start - int(time.time() * 1_000)) / 1_000
                if remaining > 0:
                    time.sleep(remaining)
                actual_hold_start = int(time.time() * 1_000)
                time.sleep(int(stage["durationSeconds"]))
                execution = {
                    "exitCode": 0,
                    "stalled": False,
                    "report": {
                        "participants": 0,
                        "finalConvergence": {"converged": 0, "expected": 0},
                        "participantErrors": [],
                        "taskErrors": [],
                    },
                    "generator": {
                        "cpuPctMax": 0.0,
                        "memoryPctMax": 0.0,
                        "droppedIterations": 0,
                        "saturated": False,
                    },
                    "admissionStartedEpochMs": actual_admission_start,
                    "holdStartedEpochMs": actual_hold_start,
                    "holdEndedEpochMs": int(time.time() * 1_000),
                    "cleanupSucceeded": True,
                }
            else:
                stage_environment = environment.copy()
                if manifest is not None:
                    credentials = stage_credentials(plan, stage["name"], manifest)
                    stage_environment.update(
                        {
                            "PATHLAB_CLASSROOM_SESSION_ID": credentials["sessionId"],
                            "PATHLAB_CLASSROOM_JOIN_CODE": credentials["joinCode"],
                            "PATHLAB_CLASSROOM_SLIDE_ID": credentials["slideId"],
                            "PATHLAB_CLASSROOM_RUN_ID": str(plan["runId"]),
                            "PATHLAB_CLASSROOM_PLAN_DIGEST": str(plan["planDigest"]),
                            "PATHLAB_CLASSROOM_SAFETY_NONCE": credentials["safetyNonce"],
                            "PATHLAB_CLASSROOM_STAGE_NAME": str(stage["name"]),
                            "PATHLAB_CLASSROOM_SHARD_INDEX": str(shard_index),
                        }
                    )
                stage_environment.update(
                    {
                        "PATHLAB_CLASSROOM_PARTICIPANTS": str(target),
                        "PATHLAB_CLASSROOM_GLOBAL_TARGET": str(stage["targetUsers"]),
                        "PATHLAB_CLASSROOM_DURATION_SECONDS": str(stage["durationSeconds"]),
                        "PATHLAB_CLASSROOM_HOLD_START_EPOCH_MS": str(stage["holdStartEpochMs"]),
                        "PATHLAB_CLASSROOM_PUBLISHER": "true" if shard_index == 0 else "false",
                        "PATHLAB_CLASSROOM_EXPECT_RESTART": (
                            "true" if stage["name"] == "recovery-1200" else "false"
                        ),
                        "PATHLAB_CLASSROOM_HEAVY_STAGE": "true" if is_breakpoint else "false",
                    }
                )
                admission_seconds = (
                    int(stage["holdStartEpochMs"] - stage["admissionStartEpochMs"]) // 1_000
                )
                timeout_seconds = int(stage["durationSeconds"]) + admission_seconds + 120
                execution = _run_harness(stage_environment, timeout_seconds)
                raw_report = execution.get("report", {})
                report = raw_report if isinstance(raw_report, dict) else {}
                execution["admissionStartedEpochMs"] = report.get(
                    "admissionStartedEpochMs", actual_admission_start
                )
                execution["holdStartedEpochMs"] = report.get("holdStartedEpochMs", 0)
                execution["holdEndedEpochMs"] = report.get("holdEndedEpochMs", 0)
                early_causes = report.get("earlyStopCauses")
                protected_stop = (
                    isinstance(early_causes, list) and bool(early_causes) and is_breakpoint
                )
                # Every shard explicitly acknowledges client-local convergence.
                # Shard zero may reset only after the server has observed all six.
                execution["cleanupSucceeded"] = _cleanup_synthetic_session(stage_environment)
                if protected_stop:
                    execution["earlyStopCauses"] = early_causes
                    heavy_escalation_blocked = True
            reports.append(execution)
            marker = completed_stage_marker(stage["name"], execution)
            if marker is not None:
                completed_prefix.append(marker)
            if output_path is not None:
                atomic_write_json(
                    output_path,
                    partial_shard_result(
                        plan, shard_index, completed_prefix, abort_cause="in-progress"
                    ),
                )
            remaining = (int(stage["transitionEndEpochMs"]) - int(time.time() * 1_000)) / 1_000
            if remaining > 0:
                time.sleep(remaining)
            ordinary_failure = (
                execution["exitCode"] != 0
                and not execution.get("earlyStopCauses")
                and not execution.get("skipped")
            )
            if ordinary_failure:
                failure_summary = safe_harness_failure_summary(stage, execution, shard_index)
                raise CertificationError(f"stage {stage['name']} harness failed")
        return shard_result_from_reports(plan, shard_index, reports)
    except (KeyboardInterrupt, SystemExit, ShardCancelled):
        result = partial_shard_result(plan, shard_index, completed_prefix, abort_cause="cancelled")
    except Exception as error:
        abort_cause = (
            f"{failure_summary['stage']}-harness-failed"
            if failure_summary is not None
            else type(error).__name__
        )
        result = partial_shard_result(
            plan,
            shard_index,
            completed_prefix,
            abort_cause=abort_cause,
            failure_summary=failure_summary,
        )
    if output_path is not None:
        atomic_write_json(output_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one protected Classroom load shard")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    signal.signal(signal.SIGINT, cancellation_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, cancellation_handler)
    result = run(_load(args.plan), args.shard_index, output_path=args.output)
    atomic_write_json(args.output, result)
    if result.get("status") == "aborted":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
