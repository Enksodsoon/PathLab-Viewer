from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta, timezone

import httpx
import pytest
from build_capacity_decision import (
    build_decision,
    host_evidence_passes,
    presenter_fanout_passes,
    strict_stage_passes,
)
from build_distributed_evidence import build as build_distributed_evidence
from build_failure_decision import build as build_failure_decision
from build_failure_evidence import build as build_failure_evidence
from classroom_sse import (
    LocalStateSnapshot,
    Participant,
    Recorder,
    discrete_event_names,
    journey_measurements,
    lost_critical_events,
    media_paths_for_participant,
    publisher_enabled,
    record_sse_disconnect,
    recovery_local_state_convergence,
    remote_target_allowed,
    stage_credentials,
)
from distributed_certification import (
    ADMISSION_SECONDS,
    TRANSITION_SECONDS,
    CertificationError,
    build_plan,
    early_stop_causes,
    merge_shards,
)
from distributed_shard import (
    ShardCancelled,
    _cleanup_synthetic_session,
    atomic_write_json,
    cancellation_handler,
    completed_stage_marker,
    partial_shard_result,
    shard_result_from_reports,
)
from monitor_distributed_observer import timeline_causes

SHA = "a" * 40
ICT = timezone(timedelta(hours=7))


def test_critical_event_loss_is_measured_only_on_the_publisher_shard() -> None:
    participant = Participant(0, object(), "p-1", "csrf")  # type: ignore[arg-type]
    participant.events = {
        "control": 2,
        "pointer-removed": 1,
        "teaching-annotation-added": 1,
        "teaching-annotation-removed": 1,
    }

    assert lost_critical_events([participant], publisher=True) == 0
    participant.events["control"] = 1
    assert lost_critical_events([participant], publisher=True) == 1
    assert lost_critical_events([participant], publisher=False) == 0


def plan() -> dict[str, object]:
    return build_plan(
        run_id="123456",
        workflow_sha=SHA,
        browser_ci_run_id=987654,
        start_epoch_ms=int(datetime(2026, 8, 15, 2, 0, tzinfo=ICT).timestamp() * 1000),
        now_epoch_ms=int(datetime(2026, 8, 15, 1, 55, tzinfo=ICT).timestamp() * 1000),
    )


def healthy_host_samples(schedule: dict[str, object]) -> list[dict[str, object]]:
    stages = schedule["stages"]
    start_ms = schedule["startEpochMs"]
    end_ms = stages[-1]["transitionEndEpochMs"]
    samples = []
    for epoch_ms in range(start_ms, end_ms + 1, 10_000):
        samples.append(
            {
                "timestamp": datetime.fromtimestamp(epoch_ms / 1000, UTC)
                .isoformat()
                .replace("+00:00", "Z"),
                "releaseSha": schedule["workflowSha"],
                "ready": True,
                "cpuPct": 40,
                "memoryPct": 60,
                "swapUsedBytes": 0,
                "diskFreePct": 50,
                "networkRxBytesDelta": 10,
                "networkTxBytesDelta": 20,
                "diskReadBytesDelta": 10,
                "diskWriteBytesDelta": 10,
                "sockets": 100,
                "fileDescriptors": 200,
                "containerCpuPct": 30,
                "containerMemoryPct": 40,
                "servicesExact": True,
                "restartCount": 0,
                "classroomRestartCount": 0,
                "oomKilled": False,
            }
        )
    restart_epoch_ms = stages[-1]["holdStartEpochMs"] + 20_000
    for sample in samples:
        observed = datetime.fromisoformat(sample["timestamp"].replace("Z", "+00:00"))
        if observed.timestamp() * 1000 >= restart_epoch_ms:
            sample["restartCount"] = 1
            sample["classroomRestartCount"] = 1
    return samples


def healthy_fault() -> dict[str, object]:
    return {"classroomOnly": True, "generalApiResponsive": True}


def bound_run_evidence(
    schedule: dict[str, object],
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    stages = schedule["stages"]
    binding = {
        "schemaVersion": 1,
        "runId": schedule["runId"],
        "workflowSha": schedule["workflowSha"],
        "planDigest": schedule["planDigest"],
    }
    sentinels = {
        **binding,
        "startedAt": datetime.fromtimestamp(stages[5]["startEpochMs"] / 1000, UTC).isoformat(),
        "completedAt": datetime.fromtimestamp(stages[5]["holdEndEpochMs"] / 1000, UTC).isoformat(),
        "fixtureBytes": 330_000_000,
        "adminResponsive": True,
        "conversionSucceeded": True,
        "degradedViewerRecovered": True,
        "functionalSentinels": {
            "uploadConversion": True,
            "annotations": True,
            "libraryShare": True,
            "dynamicViewer": True,
            "desktop": True,
        },
        "frontend": {
            "clsMax": 0.1,
            "lcpMsMax": 2500,
            "consoleErrors": 0,
            "networkErrors": 0,
            "blankCanvases": 0,
            "mobilePassed": True,
            "projects": {
                project: {
                    "cls": 0.1,
                    "lcpMs": 2500,
                    "consoleErrors": 0,
                    "networkErrors": 0,
                    "blankCanvases": 0,
                    "studentInteractionsPassed": True,
                    "teacherInteractionsPassed": True,
                }
                for project in ("chromium", "firefox", "webkit", "mobile-chromium")
            },
        },
        "crossBrowser": {
            "approved": True,
            "projects": ["chromium", "firefox", "webkit", "mobile-chromium"],
            "ciRunId": schedule["browserCiRunId"],
        },
        "cleanupSucceeded": True,
        "aggregateOnly": True,
        "syntheticOnly": True,
    }
    fault = {
        **binding,
        "startedAt": datetime.fromtimestamp(
            (stages[-1]["holdStartEpochMs"] + 15_000) / 1000, UTC
        ).isoformat(),
        "completedAt": datetime.fromtimestamp(
            (stages[-1]["holdStartEpochMs"] + 60_000) / 1000, UTC
        ).isoformat(),
        "classroomOnly": True,
        "generalApiResponsive": True,
        "readinessRecoverySeconds": 60,
        "convergenceSeconds": 20,
        "privacy": {
            "aggregateOnly": True,
            "credentialsMasked": True,
            "syntheticFixturesOnly": True,
        },
    }
    cleanup_start = datetime.fromtimestamp(stages[-1]["transitionEndEpochMs"] / 1000, ICT)
    cleanup = {
        **binding,
        "startedAt": cleanup_start.isoformat(),
        "completedAt": (cleanup_start + timedelta(seconds=30)).isoformat(),
        "attempted": True,
        "succeeded": True,
        "configurationRestored": True,
        "fixturesRemoved": True,
        "bastionSessionsRemaining": 0,
    }
    return sentinels, fault, cleanup


def healthy_accounting() -> dict[str, object]:
    return {
        "currency": "SGD",
        "monthToDateCost": 0,
        "projectedMonthlyEgressBytes": 1_000_000,
        "projectedMonthlyRuns": 1,
        "permanentResourcesAdded": False,
        "computeOcpus": 2,
        "memoryGb": 12,
        "storageGb": 200,
        "observedResourceCount": 7,
        "approvedResourceCount": 7,
        "observedInventoryDigest": "c" * 64,
        "approvedInventoryDigest": "c" * 64,
    }


def healthy_postflight(schedule: dict[str, object], *, capacity: int = 1500) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "runId": schedule["runId"],
        "workflowSha": schedule["workflowSha"],
        "planDigest": schedule["planDigest"],
        "observedAt": "2026-08-14T04:55:00+07:00",
        "expectedSha": schedule["workflowSha"],
        "deployedSha": schedule["workflowSha"],
        "releaseExact": True,
        "servicesExact": True,
        "serviceCount": 6,
        "hostReady": True,
        "endpointsHealthy": True,
        "watchdogExpected": True,
        "watchdogActive": True,
        "finalCapacity": capacity,
        "monthToDateCost": 0,
        "currency": "SGD",
        "aggregateOnly": True,
    }


def test_strict_shard_failure_produces_bound_300_not_certified_evidence() -> None:
    schedule = plan()
    sentinels, _, _ = bound_run_evidence(schedule)
    decision = build_failure_decision(schedule, sentinels, nonce="n" * 32)
    postflight = healthy_postflight(schedule, capacity=300)
    postflight["expectedSha"] = "d" * 40
    postflight["deployedSha"] = "d" * 40
    postflight["serviceCount"] = 5
    postflight["watchdogExpected"] = False
    postflight["watchdogActive"] = False
    report = build_failure_evidence(schedule, decision, postflight)

    assert report["certified"] is False
    assert report["certifiedTier"] is None
    assert report["selectedCapacity"] == 300
    assert report["postflight"]["releaseExact"] is True


def test_missing_sentinel_still_produces_truthful_signed_300_decision_input() -> None:
    schedule = plan()
    certification = build_failure_decision(schedule, None, nonce="n" * 32)["certification"]

    assert certification["selectedCapacity"] == 300
    assert certification["verdict"] == "NOT CERTIFIED"
    assert certification["fixtureCleanupSucceeded"] is False
    assert all(value is False for value in certification["functionalSentinels"].values())
    assert certification["stageResults"]["certification-1200"]["status"] == "failed"
    assert all(
        certification["stageResults"][name]["status"] == "skipped"
        for name in ("smoke-2", "smoke-100", "boundary-300", "boundary-600", "boundary-900")
    )


def test_host_evidence_is_required_continuous_exact_release_and_below_limits() -> None:
    schedule = plan()
    samples = healthy_host_samples(schedule)
    fault = bound_run_evidence(schedule)[1]
    assert host_evidence_passes(schedule, samples, fault)
    assert not host_evidence_passes(schedule, [], fault)
    assert not host_evidence_passes(schedule, samples[:-2], fault)
    samples[3]["releaseSha"] = "b" * 40
    assert not host_evidence_passes(schedule, samples, fault)


@pytest.mark.parametrize(
    ("field", "value"),
    [("memoryPct", 85), ("oomKilled", True), ("swapUsedBytes", 1)],
)
def test_host_evidence_rejects_resource_safety_breach(field: str, value: object) -> None:
    schedule = plan()
    fault = bound_run_evidence(schedule)[1]
    samples = healthy_host_samples(schedule)
    samples[4][field] = value
    assert not host_evidence_passes(schedule, samples, fault)


def test_host_evidence_rejects_sustained_cpu_and_pre_fault_restart() -> None:
    schedule = plan()
    fault = bound_run_evidence(schedule)[1]
    samples = healthy_host_samples(schedule)
    for item in samples[3:6]:
        item["cpuPct"] = 80
    assert not host_evidence_passes(schedule, samples, fault)


def test_host_evidence_allows_only_the_sampling_bound_first_post_fault_readiness_sample() -> None:
    schedule = plan()
    fault = bound_run_evidence(schedule)[1]
    samples = healthy_host_samples(schedule)
    fault_end = datetime.fromisoformat(str(fault["completedAt"]).replace("Z", "+00:00"))
    post_fault = [
        item
        for item in samples
        if datetime.fromisoformat(str(item["timestamp"]).replace("Z", "+00:00")) > fault_end
    ]
    post_fault[0]["ready"] = False
    post_fault[0]["servicesExact"] = False
    assert host_evidence_passes(schedule, samples, fault)
    post_fault[1]["ready"] = False
    assert not host_evidence_passes(schedule, samples, fault)


def test_host_evidence_requires_exact_classroom_restart_at_the_first_bound_sample() -> None:
    schedule = plan()
    fault = bound_run_evidence(schedule)[1]
    samples = healthy_host_samples(schedule)
    change = next(item for item in samples if item["restartCount"] == 1)
    change["classroomRestartCount"] = 0
    assert not host_evidence_passes(schedule, samples, fault)


def test_host_evidence_allows_only_stage_bound_protected_heavy_cpu_stop() -> None:
    schedule = plan()
    samples = healthy_host_samples(schedule)
    fault = bound_run_evidence(schedule)[1]
    merged = merge_shards(schedule, [healthy_shard(index) for index in range(6)])
    stage = merged["stages"][7]
    stage["outcome"] = "protected-early-stop"
    stage["abortCauses"] = ["cpu-sustained"]
    window = schedule["stages"][7]
    candidates = [
        sample
        for sample in samples
        if window["holdStartEpochMs"]
        <= datetime.fromisoformat(sample["timestamp"].replace("Z", "+00:00")).timestamp() * 1000
        <= window["holdEndEpochMs"]
    ]
    for sample in candidates[:3]:
        sample["cpuPct"] = 80

    assert host_evidence_passes(schedule, samples, fault, merged["stages"])
    stage["abortCauses"] = []
    assert not host_evidence_passes(schedule, samples, fault, merged["stages"])
    samples = healthy_host_samples(schedule)
    samples[4]["restartCount"] = 1
    assert not host_evidence_passes(schedule, samples, fault)


def test_live_observer_rejects_missing_late_and_out_of_order_samples() -> None:
    start = 1_000_000
    assert timeline_causes(start - 10_000, None, start) == []
    assert timeline_causes(start + 20_000, None, start) == ["observer-coverage"]
    assert timeline_causes(start + 20_001, start, start) == ["observer-gap"]
    assert timeline_causes(start, start, start) == ["observer-order"]


def healthy_shard(index: int) -> dict[str, object]:
    source = plan()
    stages = []
    for stage in source["stages"]:  # type: ignore[index]
        target = stage["shardTargets"][index]
        stages.append(
            {
                "name": stage["name"],
                "targetUsers": target,
                "achievedUsers": target,
                "admissionStartedEpochMs": stage["admissionStartEpochMs"],
                "holdStartedEpochMs": stage["holdStartEpochMs"],
                "holdEndedEpochMs": stage["holdEndEpochMs"],
                "completed": True,
                "stalled": False,
                "outcome": "passed",
                "abortCauses": [],
                "cleanupSucceeded": True,
                "generator": {
                    "cpuPctMax": 40.0,
                    "memoryPctMax": 35.0,
                    "droppedIterations": 0,
                    "saturated": False,
                },
            }
        )
    result: dict[str, object] = {
        "schemaVersion": 1,
        "runId": "123456",
        "workflowSha": SHA,
        "planDigest": source["planDigest"],
        "shardId": f"linux-{index + 1}",
        "shardIndex": index,
        "stages": stages,
        "sustainedMeasurements": {
            "journeys": {
                name: {
                    "requests": 10,
                    "failures": 0,
                    "failureRate": 0,
                    "latencyMs": {"p50": 1, "p95": 2, "p99": 3},
                }
                for name in (
                    "presenterSse",
                    "classroomControl",
                    "generalApi",
                    "staticTile",
                    "poster",
                    "question",
                )
            },
            "realtime": {
                "converged": 200,
                "expected": 200,
                "reconnectsSucceeded": 20,
                "reconnectsExpected": 20,
                "lostCriticalEvents": 0,
                "unexpectedDisconnects": 0,
                "queueOverflows": 0,
            },
            "pressure": {
                "queueMaxDepth": 1,
                "queueCapacity": 512,
                "eventLoopP99Ms": 1,
                "poolWaitP95Ms": 1,
                "poolTimeouts": 0,
                "sqliteLockErrors": 0,
            },
        },
        "privacy": {
            "aggregateOnly": True,
            "credentialsMasked": True,
            "syntheticFixturesOnly": True,
        },
    }
    result["headroomMeasurements"] = deepcopy(result["sustainedMeasurements"])
    for key in ("sustainedMeasurements", "headroomMeasurements"):
        presenter = result[key]["journeys"]["presenterSse"]
        presenter["fanout"] = {
            "sentEpochMs": {"1": 1_000} if index == 0 else {},
            "receivedEpochMs": {"1": 1_100 + index},
        }
    return result


def healthy_execution_reports(index: int) -> list[dict[str, object]]:
    schedule = plan()
    measurement = healthy_shard(index)["sustainedMeasurements"]
    reports = []
    for stage in schedule["stages"]:
        target = stage["shardTargets"][index]
        reports.append(
            {
                "exitCode": 0,
                "stalled": False,
                "admissionStartedEpochMs": stage["admissionStartEpochMs"],
                "holdStartedEpochMs": stage["holdStartEpochMs"],
                "holdEndedEpochMs": stage["holdEndEpochMs"],
                "cleanupSucceeded": True,
                "report": {
                    "participants": target,
                    "activeSseAtHoldStart": target,
                    "serverActiveSseAtHoldStart": stage["targetUsers"],
                    "serverPeakSseAtHoldStart": stage["targetUsers"],
                    "globalTargetUsers": stage["targetUsers"],
                    "recoveryReadyEpochMs": stage["holdStartEpochMs"],
                    "recoveryConvergenceSeconds": 20,
                    "recoveryLocalConvergence": {"converged": target, "expected": target},
                    "finalConvergence": {"converged": target, "expected": target},
                    "participantErrors": [],
                    "taskErrors": [],
                    "journeys": deepcopy(measurement["journeys"]),
                    "serverMetrics": deepcopy(measurement["pressure"]),
                    "reconnectSuccessRate": 1,
                    "lostDiscreteEvents": 0,
                    "unexpectedSseDisconnects": 0,
                    "queueOverflows": 0,
                },
                "generator": {
                    "cpuPctMax": 40.0,
                    "memoryPctMax": 35.0,
                    "droppedIterations": 0,
                    "saturated": False,
                },
            }
        )
    return reports


def test_plan_uses_exact_stages_and_balances_every_target_across_six_shards() -> None:
    result = plan()

    observed = [
        (item["name"], item["targetUsers"], item["durationSeconds"])
        for item in result["stages"]  # type: ignore[index]
    ]
    assert observed == [
        ("smoke-2", 2, 30),
        ("acceptance-100", 100, 600),
        ("boundary-300", 300, 600),
        ("boundary-600", 600, 600),
        ("boundary-900", 900, 600),
        ("sustained-1200", 1200, 3600),
        ("headroom-1500", 1500, 600),
        ("breakpoint-1750", 1750, 300),
        ("breakpoint-2000", 2000, 300),
        ("recovery-1200", 1200, 600),
    ]
    for stage in result["stages"]:  # type: ignore[index]
        assert len(stage["shardTargets"]) == 6
        assert sum(stage["shardTargets"]) == stage["targetUsers"]
        assert max(stage["shardTargets"]) - min(stage["shardTargets"]) <= 1


def test_plan_reserves_admission_full_hold_and_cleanup_transition_for_every_stage() -> None:
    stages = plan()["stages"]

    for index, stage in enumerate(stages):
        assert (
            stage["holdStartEpochMs"] - stage["admissionStartEpochMs"] == ADMISSION_SECONDS * 1000
        )
        assert (
            stage["holdEndEpochMs"] - stage["holdStartEpochMs"] == stage["durationSeconds"] * 1000
        )
        assert stage["transitionEndEpochMs"] - stage["holdEndEpochMs"] == TRANSITION_SECONDS * 1000
        if index:
            assert stage["admissionStartEpochMs"] == stages[index - 1]["transitionEndEpochMs"]


def test_remote_stage_credentials_require_one_resettable_synthetic_classroom() -> None:
    schedule = plan()
    manifest = {
        stage["name"]: {
            "sessionId": "capacity-session",
            "joinCode": "CAPACITY-JOIN",
            "slideId": "capacity-slide",
            "safetyNonce": f"stage-nonce-{stage['name']}-{'n' * 32}",
        }
        for stage in schedule["stages"]
    }

    selected = stage_credentials(schedule, "boundary-300", manifest)

    assert selected == manifest["boundary-300"]
    manifest["boundary-600"]["sessionId"] = "different-session"
    with pytest.raises(ValueError, match="one dedicated"):
        stage_credentials(schedule, "boundary-300", manifest)
    manifest["boundary-600"]["sessionId"] = "capacity-session"
    manifest["boundary-600"]["safetyNonce"] = manifest["boundary-300"]["safetyNonce"]
    with pytest.raises(ValueError, match="unique safety nonce"):
        stage_credentials(schedule, "boundary-300", manifest)


def test_publisher_cleanup_authenticates_and_resets_the_synthetic_session() -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/v1/auth/session":
            return httpx.Response(200, json={"csrfToken": "csrf"})
        assert request.headers["X-CSRF-Token"] == "csrf"
        if request.url.path.endswith("/synthetic-stage-ack"):
            return httpx.Response(200, json={"acknowledgedShards": 6, "complete": True})
        return httpx.Response(204)

    result = _cleanup_synthetic_session(
        {
            "PATHLAB_CLASSROOM_BASE_URL": "https://viewer.example.test",
            "PATHLAB_CLASSROOM_ADMIN_USERNAME": "synthetic-admin",
            "PATHLAB_CLASSROOM_ADMIN_PASSWORD": "masked",
            "PATHLAB_CLASSROOM_SESSION_ID": "disposable-stage-session",
            "PATHLAB_CLASSROOM_RUN_ID": "123456",
            "PATHLAB_CLASSROOM_STAGE_NAME": "boundary-300",
            "PATHLAB_CLASSROOM_SHARD_INDEX": "0",
        },
        transport=httpx.MockTransport(handler),
    )

    assert result
    assert requests == [
        ("POST", "/api/v1/auth/session"),
        (
            "POST",
            "/api/v1/admin/classroom/sessions/disposable-stage-session/synthetic-stage-ack",
        ),
        (
            "POST",
            "/api/v1/admin/classroom/sessions/disposable-stage-session/synthetic-reset",
        ),
    ]


def test_shard_zero_waits_for_delayed_sixth_ack_before_reset() -> None:
    requests: list[str] = []
    acknowledgements = iter((5, 5, 6))

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request.url.path)
        if request.url.path == "/api/v1/auth/session":
            return httpx.Response(200, json={"csrfToken": "csrf"})
        if request.url.path.endswith("/synthetic-stage-ack"):
            count = next(acknowledgements)
            return httpx.Response(200, json={"acknowledgedShards": count, "complete": count == 6})
        return httpx.Response(204)

    assert _cleanup_synthetic_session(
        {
            "PATHLAB_CLASSROOM_BASE_URL": "https://viewer.example.test",
            "PATHLAB_CLASSROOM_ADMIN_USERNAME": "synthetic-admin",
            "PATHLAB_CLASSROOM_ADMIN_PASSWORD": "masked",
            "PATHLAB_CLASSROOM_SESSION_ID": "dedicated-session",
            "PATHLAB_CLASSROOM_RUN_ID": "123456",
            "PATHLAB_CLASSROOM_STAGE_NAME": "sustained-1200",
            "PATHLAB_CLASSROOM_SHARD_INDEX": "0",
        },
        transport=httpx.MockTransport(handler),
        barrier_timeout_seconds=2,
    )
    assert requests[-1].endswith("/synthetic-reset")
    assert sum(path.endswith("/synthetic-stage-ack") for path in requests) == 3


def test_atomic_partial_artifact_retains_abort_cause(tmp_path) -> None:
    output = tmp_path / "shard.json"
    atomic_write_json(output, {"status": "aborted", "abortCause": "cancelled", "stages": []})

    assert output.read_text(encoding="utf-8").endswith("\n")
    assert __import__("json").loads(output.read_text(encoding="utf-8"))["abortCause"] == "cancelled"
    assert not list(tmp_path.glob("*.tmp"))


def test_partial_shard_result_is_run_bound_and_records_completed_prefix() -> None:
    result = partial_shard_result(
        plan(),
        2,
        [{"name": "smoke-2", "outcome": "passed"}],
        abort_cause="cancelled",
    )

    assert result["status"] == "aborted"
    assert result["abortCause"] == "cancelled"
    assert result["runId"] == "123456"
    assert result["shardIndex"] == 2
    assert result["completedStages"] == [{"name": "smoke-2", "outcome": "passed"}]


def test_process_signal_becomes_a_caught_cancellation_abort() -> None:
    with pytest.raises(ShardCancelled, match="signal 15"):
        cancellation_handler(15, None)


def test_failed_execution_is_not_recorded_in_completed_partial_prefix() -> None:
    assert completed_stage_marker("boundary-900", {"exitCode": 1}) is None
    assert completed_stage_marker(
        "breakpoint-1750", {"exitCode": 1, "earlyStopCauses": ["memory"]}
    ) == {"name": "breakpoint-1750", "outcome": "protected-early-stop"}


def test_merge_rejects_a_passed_stage_that_did_not_hold_the_full_duration() -> None:
    shards = [healthy_shard(index) for index in range(6)]
    shards[0]["stages"][5]["holdEndedEpochMs"] -= 1

    with pytest.raises(CertificationError, match="full planned hold"):
        merge_shards(plan(), shards)


def test_shard_result_carries_truthful_admission_hold_transition_and_cleanup() -> None:
    result = shard_result_from_reports(plan(), 0, healthy_execution_reports(0))

    sustained = result["stages"][5]
    assert sustained["admissionStartedEpochMs"] < sustained["holdStartedEpochMs"]
    assert sustained["holdEndedEpochMs"] - sustained["holdStartedEpochMs"] == 3_600_000
    assert sustained["cleanupSucceeded"] is True
    assert sustained["outcome"] == "passed"


def test_recovery_stage_rejects_any_client_local_convergence_over_thirty_seconds() -> None:
    reports = healthy_execution_reports(0)
    reports[-1]["report"]["recoveryConvergenceSeconds"] = 30.001
    with pytest.raises(CertificationError, match="all-client convergence"):
        shard_result_from_reports(plan(), 0, reports)


def test_recovery_convergence_requires_changed_canonical_local_state_not_connection_time() -> None:
    participant = Participant(0, object(), "p-1", "csrf")  # type: ignore[arg-type]
    participant.connected_epoch_ms = [1_000, 2_000]
    participant.local_state_snapshots = [
        LocalStateSnapshot("epoch-1", 10, 20, 1_500),
        LocalStateSnapshot("epoch-2", 11, 21, 31_000),
    ]
    assert recovery_local_state_convergence([participant], 2_000) == (1, 29)
    participant.local_state_snapshots[1] = LocalStateSnapshot("epoch-2", 11, 20, 3_000)
    assert recovery_local_state_convergence([participant], 2_000) == (0, 0)
    participant.local_state_snapshots[1] = LocalStateSnapshot("epoch-2", 11, 21, 32_001)
    assert recovery_local_state_convergence([participant], 2_000) == (0, 0)


def test_plan_requires_a_future_start_inside_the_protected_ict_window() -> None:
    with pytest.raises(CertificationError, match="future start epoch"):
        build_plan(
            run_id="123456",
            workflow_sha=SHA,
            browser_ci_run_id=1,
            start_epoch_ms=1,
            now_epoch_ms=2,
        )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing", "exactly six shard results"),
        ("late", "timing drift"),
        ("saturated", "generator saturated"),
        ("stalled", "stalled"),
        ("under-target", "missed achieved-user target"),
        ("dropped", "dropped iterations"),
    ],
)
def test_merge_rejects_unhealthy_or_incomplete_shards(mutation: str, message: str) -> None:
    schedule = plan()
    shards = [healthy_shard(index) for index in range(6)]
    if mutation == "missing":
        shards.pop()
    elif mutation == "late":
        shards[0]["stages"][5]["holdStartedEpochMs"] += 1001  # type: ignore[index]
    elif mutation == "saturated":
        shards[0]["stages"][5]["generator"]["saturated"] = True  # type: ignore[index]
    elif mutation == "stalled":
        shards[0]["stages"][5]["stalled"] = True  # type: ignore[index]
    elif mutation == "under-target":
        shards[0]["stages"][5]["achievedUsers"] -= 1  # type: ignore[index]
    elif mutation == "dropped":
        shards[0]["stages"][5]["generator"]["droppedIterations"] = 1  # type: ignore[index]

    with pytest.raises(CertificationError, match=message):
        merge_shards(schedule, shards)


def test_merge_returns_only_aggregate_shard_evidence() -> None:
    result = merge_shards(plan(), [healthy_shard(index) for index in range(6)])

    assert result["stages"][5]["achievedUsers"] == 1200
    assert len(result["stages"][5]["shards"]) == 6
    assert len(result["sustainedMeasurements"]) == 6
    assert len(result["headroomMeasurements"]) == 6
    assert "joinCode" not in repr(result)
    assert "password" not in repr(result).lower()


@pytest.mark.parametrize(
    ("measurement", "expected"),
    [
        ({"cpuPct": 80.0, "cpuDurationSeconds": 30}, ["cpu-sustained"]),
        ({"memoryPct": 85.0}, ["memory"]),
        ({"queueDepth": 384, "queueCapacity": 512}, ["queue-pressure"]),
        ({"eventLoopP99Ms": 250.001}, ["event-loop"]),
        ({"failureRate": 0.005}, ["failure-rate"]),
        ({"poolTimeouts": 1}, ["pool-timeout"]),
        ({"sqliteLockErrors": 1}, ["sqlite-lock"]),
        ({"latencyRatio": 2.01, "latencyBreachSeconds": 120}, ["latency"]),
    ],
)
def test_heavy_stage_early_stop_thresholds_are_exact_and_fail_closed(
    measurement: dict[str, float | int], expected: list[str]
) -> None:
    assert early_stop_causes(measurement) == expected


def test_heavy_stage_does_not_stop_below_every_threshold() -> None:
    assert (
        early_stop_causes(
            {
                "cpuPct": 79.999,
                "cpuDurationSeconds": 29,
                "memoryPct": 84.999,
                "queueDepth": 383,
                "queueCapacity": 512,
                "eventLoopP99Ms": 250,
                "failureRate": 0.00499,
                "poolTimeouts": 0,
                "sqliteLockErrors": 0,
                "latencyRatio": 2,
                "latencyBreachSeconds": 119,
            }
        )
        == []
    )


def test_merge_rejects_plan_digest_mismatch() -> None:
    shard = healthy_shard(0)
    shard["planDigest"] = "0" * 64
    shards = [shard, *[healthy_shard(index) for index in range(1, 6)]]

    with pytest.raises(CertificationError, match="plan digest"):
        merge_shards(plan(), shards)


def test_merge_rejects_a_plan_modified_after_its_digest_was_issued() -> None:
    schedule = plan()
    schedule["stages"][5]["durationSeconds"] = 3_599

    with pytest.raises(CertificationError, match="plan digest"):
        merge_shards(schedule, [healthy_shard(index) for index in range(6)])


def test_remote_harness_requires_https_and_all_protected_ci_guards() -> None:
    assert remote_target_allowed(
        "https://viewer.example.test",
        {
            "PATHLAB_CLASSROOM_PROTECTED_REMOTE": "true",
            "GITHUB_ACTIONS": "true",
            "PATHLAB_CLASSROOM_SYNTHETIC_ONLY": "true",
        },
    )
    assert not remote_target_allowed(
        "http://viewer.example.test",
        {
            "PATHLAB_CLASSROOM_PROTECTED_REMOTE": "true",
            "GITHUB_ACTIONS": "true",
            "PATHLAB_CLASSROOM_SYNTHETIC_ONLY": "true",
        },
    )
    assert not remote_target_allowed(
        "https://viewer.example.test",
        {"PATHLAB_CLASSROOM_PROTECTED_REMOTE": "true", "GITHUB_ACTIONS": "true"},
    )


def test_classroom_media_mix_is_eighty_percent_follow_and_twenty_percent_explore() -> None:
    manifest = {
        "descriptor": "/tiles/synthetic/slide.dzi",
        "poster": "/tiles/synthetic/poster.jpg",
        "commonTiles": ["/tiles/synthetic/common-1.jpg", "/tiles/synthetic/common-2.jpg"],
        "randomTiles": [
            "/tiles/synthetic/random-1.jpg",
            "/tiles/synthetic/random-2.jpg",
            "/tiles/synthetic/random-3.jpg",
        ],
    }

    paths = [media_paths_for_participant(manifest, sequence) for sequence in range(100)]

    assert all(item[:2] == [manifest["descriptor"], manifest["poster"]] for item in paths)
    assert sum(item[2] in manifest["commonTiles"] for item in paths) == 80
    assert sum(item[2] in manifest["randomTiles"] for item in paths) == 20
    assert all(1 <= len(item[2:]) <= 4 for item in paths)
    assert all(len(set(item[2:])) == len(item[2:]) for item in paths)


def test_protocol_sentinel_covers_every_classroom_discrete_feature() -> None:
    assert discrete_event_names() == (
        "question",
        "pin",
        "control-request",
        "control-grant-revoke",
        "pointer",
        "teaching-annotation",
    )


def test_only_shard_zero_publishes_teacher_mutations() -> None:
    assert publisher_enabled("true")
    assert not publisher_enabled("false")
    assert not publisher_enabled("")


def test_journey_measurements_keep_each_slo_path_separate() -> None:
    recorder = Recorder(
        presenter_latencies_ms=[100.0, 200.0],
        question_latencies_ms=[500.0],
        control_latencies_ms=[250.0],
        tile_latencies_ms=[300.0, 400.0],
        poster_latencies_ms=[900.0],
        general_latencies_ms=[100.0],
    )

    result = journey_measurements(recorder)

    assert result["presenterSse"]["latencyMs"]["p95"] == 200.0
    assert result["staticTile"]["requests"] == 2
    assert result["poster"]["latencyMs"]["p95"] == 900.0
    assert result["generalApi"]["latencyMs"]["p95"] == 100.0


def test_journey_measurements_count_presenter_http_failures_and_stream_disconnects() -> None:
    recorder = Recorder(
        presenter_latencies_ms=[100.0],
        presenter_http_errors=2,
        unexpected_sse_disconnects=3,
    )

    result = journey_measurements(recorder)

    assert result["presenterSse"]["requests"] == 3
    assert result["presenterSse"]["failures"] == 2
    assert recorder.unexpected_sse_disconnects == 3


def test_only_unexpected_reconnectable_sse_disconnects_are_counted() -> None:
    recorder = Recorder()

    record_sse_disconnect(recorder, expected=False, reconnect_possible=True)
    record_sse_disconnect(recorder, expected=True, reconnect_possible=True)
    record_sse_disconnect(recorder, expected=False, reconnect_possible=False)

    assert recorder.unexpected_sse_disconnects == 1


def test_shard_result_fails_closed_when_harness_did_not_converge() -> None:
    schedule = plan()
    reports = []
    for stage in schedule["stages"]:  # type: ignore[index]
        target = stage["shardTargets"][0]
        reports.append(
            {
                "admissionStartedEpochMs": stage["admissionStartEpochMs"],
                "holdStartedEpochMs": stage["holdStartEpochMs"],
                "holdEndedEpochMs": stage["holdEndEpochMs"],
                "cleanupSucceeded": True,
                "exitCode": 0,
                "stalled": False,
                "report": {
                    "participants": target,
                    "finalConvergence": {"converged": target, "expected": target},
                    "participantErrors": [],
                    "taskErrors": [],
                },
                "generator": {
                    "cpuPctMax": 50.0,
                    "memoryPctMax": 40.0,
                    "droppedIterations": 0,
                    "saturated": False,
                },
            }
        )
    reports[5]["report"]["finalConvergence"]["converged"] -= 1

    with pytest.raises(CertificationError, match="did not converge"):
        shard_result_from_reports(schedule, 0, reports)


def test_protected_heavy_early_stop_preserves_prior_strict_results_and_skips_escalation() -> None:
    schedule = plan()
    shards = [healthy_shard(index) for index in range(6)]
    for shard in shards:
        stopped = shard["stages"][7]
        stopped["achievedUsers"] = max(1, stopped["targetUsers"] - 1)
        stopped["completed"] = False
        stopped["outcome"] = "protected-early-stop"
        stopped["abortCauses"] = ["cpu-sustained"]
        skipped = shard["stages"][8]
        skipped["achievedUsers"] = 0
        skipped["completed"] = False
        skipped["outcome"] = "skipped"
        skipped["abortCauses"] = ["escalation-blocked"]

    merged = merge_shards(schedule, shards)

    assert merged["stages"][5]["outcome"] == "passed"
    assert merged["stages"][6]["outcome"] == "passed"
    assert merged["stages"][7]["outcome"] == "protected-early-stop"
    assert merged["stages"][8]["outcome"] == "skipped"
    assert merged["stages"][9]["outcome"] == "passed"


def test_queue_overflow_and_unexpected_disconnect_invalidate_strict_measurement() -> None:
    measurement = deepcopy(healthy_shard(0)["sustainedMeasurements"])
    measurement["realtime"]["unexpectedDisconnects"] = 1
    measurement["realtime"]["queueOverflows"] = 1

    with pytest.raises(CertificationError, match="realtime failures"):
        merge_shards(
            plan(),
            [
                {**healthy_shard(0), "sustainedMeasurements": measurement},
                *[healthy_shard(index) for index in range(1, 6)],
            ],
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("journeys", "presenterSse", "latencyMs", "p95"), 250.001),
        (("journeys", "staticTile", "latencyMs", "p95"), 500.0),
        (("journeys", "poster", "latencyMs", "p95"), 1500.0),
        (("journeys", "question", "failureRate"), 0.001),
        (("realtime", "lostCriticalEvents"), 1),
        (("pressure", "queueMaxDepth"), 384),
        (("pressure", "eventLoopP99Ms"), 250.001),
        (("pressure", "poolTimeouts"), 1),
        (("pressure", "sqliteLockErrors"), 1),
    ],
)
def test_strict_stage_decision_never_weakens_an_slo(
    path: tuple[str, ...], value: float | int
) -> None:
    measurement = deepcopy(healthy_shard(0)["sustainedMeasurements"])
    target = measurement
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value

    assert not strict_stage_passes([measurement])


def test_strict_stage_accepts_measurements_below_every_limit() -> None:
    assert strict_stage_passes(
        [deepcopy(healthy_shard(index)["sustainedMeasurements"]) for index in range(6)]
    )


def test_strict_stage_allows_one_teacher_publisher_when_fanout_is_separately_proven() -> None:
    measurements = [deepcopy(healthy_shard(index)["sustainedMeasurements"]) for index in range(6)]
    for measurement in measurements[1:]:
        for name in ("classroomControl", "question"):
            measurement["journeys"][name] = {
                "requests": 0,
                "failures": 0,
                "failureRate": 0,
                "latencyMs": {"p50": 0, "p95": 0, "p99": 0},
            }

    assert strict_stage_passes(measurements)


def test_presenter_fanout_requires_one_publisher_and_receipt_on_every_shard() -> None:
    measurements = [deepcopy(healthy_shard(index)["sustainedMeasurements"]) for index in range(6)]
    assert presenter_fanout_passes(measurements)
    measurements[5]["journeys"]["presenterSse"]["fanout"]["receivedEpochMs"] = {}
    assert not presenter_fanout_passes(measurements)


def test_provisional_decision_cannot_raise_capacity_without_complete_host_evidence() -> None:
    schedule = plan()
    merged = merge_shards(schedule, [healthy_shard(index) for index in range(6)])
    sentinels, fault, _ = bound_run_evidence(schedule)

    for observer in ([], healthy_host_samples(schedule)[:-2]):
        decision = build_decision(
            schedule,
            merged,
            sentinels,
            fault,
            observer,
            healthy_accounting(),
            nonce="n" * 32,
        )["certification"]
        assert decision["strictStages"]["1200"]["passed"] is False
        assert decision["strictStages"]["1500"]["passed"] is False
        assert decision["allPreflightGatesPassed"] is False


def test_provisional_decision_rejects_invalid_per_browser_sentinel_evidence() -> None:
    schedule = plan()
    merged = merge_shards(schedule, [healthy_shard(index) for index in range(6)])
    sentinels, fault, _ = bound_run_evidence(schedule)
    sentinels["frontend"]["projects"]["firefox"]["lcpMs"] = 0

    with pytest.raises(ValueError, match="frontend metrics for firefox failed"):
        build_decision(
            schedule,
            merged,
            sentinels,
            fault,
            healthy_host_samples(schedule),
            healthy_accounting(),
            nonce="n" * 32,
        )


def test_final_builder_accepts_protected_heavy_stop_without_discarding_strict_tier() -> None:
    schedule = plan()
    shards = [healthy_shard(index) for index in range(6)]
    for shard in shards:
        stopped = shard["stages"][7]
        stopped.update(
            achievedUsers=max(1, stopped["targetUsers"] - 1),
            completed=False,
            outcome="protected-early-stop",
            abortCauses=["cpu-sustained"],
        )
        skipped = shard["stages"][8]
        skipped.update(
            achievedUsers=0,
            completed=False,
            outcome="skipped",
            abortCauses=["escalation-blocked"],
        )
    merged = merge_shards(schedule, shards)
    sentinels, fault, cleanup = bound_run_evidence(schedule)

    report = build_distributed_evidence(
        schedule,
        merged,
        sentinels,
        fault,
        cleanup,
        healthy_host_samples(schedule),
        healthy_accounting(),
        healthy_postflight(schedule),
    )

    assert report["certified"] is True
    assert report["certifiedTier"] == 1500
    assert report["stages"][7]["outcome"] == "protected-early-stop"
    assert report["stages"][8]["outcome"] == "skipped"


def test_final_builder_reports_1200_tier_when_headroom_strict_slo_fails() -> None:
    schedule = plan()
    merged = merge_shards(schedule, [healthy_shard(index) for index in range(6)])
    merged["headroomMeasurements"][0]["journeys"]["presenterSse"]["latencyMs"]["p95"] = 251
    sentinels, fault, cleanup = bound_run_evidence(schedule)

    report = build_distributed_evidence(
        schedule,
        merged,
        sentinels,
        fault,
        cleanup,
        healthy_host_samples(schedule),
        healthy_accounting(),
        healthy_postflight(schedule, capacity=1200),
    )

    assert report["certified"] is True
    assert report["certifiedTier"] == 1200


def test_final_builder_does_not_count_the_intentional_classroom_fault_as_unexpected_restart() -> (
    None
):
    schedule = plan()
    merged = merge_shards(schedule, [healthy_shard(index) for index in range(6)])
    sentinels, fault, cleanup = bound_run_evidence(schedule)
    observer = healthy_host_samples(schedule)
    fault_start = datetime.fromisoformat(fault["startedAt"])
    for sample in observer:
        observed = datetime.fromisoformat(sample["timestamp"].replace("Z", "+00:00"))
        if observed >= fault_start:
            sample["restartCount"] = 1

    report = build_distributed_evidence(
        schedule,
        merged,
        sentinels,
        fault,
        cleanup,
        observer,
        healthy_accounting(),
        healthy_postflight(schedule),
    )

    assert report["resources"]["containerRestarts"] == 0
    assert report["certified"] is True
    assert report["certifiedTier"] == 1500
