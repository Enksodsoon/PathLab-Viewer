from __future__ import annotations

import json
from pathlib import Path

import pytest
from build_capacity_terminal_status import JOBS, build
from build_distributed_evidence import build as build_evidence
from build_failure_decision import build as build_failure_decision
from build_failure_evidence import build as build_failure_evidence
from distributed_certification import merge_shards
from test_distributed_certification import (
    bound_run_evidence,
    healthy_accounting,
    healthy_fixture_preparation,
    healthy_host_samples,
    healthy_postflight,
    healthy_shard,
    plan,
)


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path: Path) -> Path:
    schedule = plan()
    write(tmp_path / "capacity-plan.json", schedule)
    for index in range(6):
        write(tmp_path / f"shard-{index}.json", healthy_shard(index))
    identity = {key: schedule[key] for key in ("runId", "workflowSha", "planDigest")}
    write(
        tmp_path / "capacity-cleanup.json",
        {
            **identity,
            "succeeded": True,
            "fixturesRemoved": True,
            "configurationRestored": True,
            "bastionSessionsRemaining": 0,
        },
    )
    write(tmp_path / "capacity-postflight.json", healthy_postflight(schedule, capacity=300))
    sentinels, fault, cleanup = bound_run_evidence(schedule)
    write(
        tmp_path / "capacity-certification.json",
        build_evidence(
            schedule,
            merge_shards(schedule, [healthy_shard(index) for index in range(6)]),
            sentinels,
            fault,
            healthy_fixture_preparation(schedule),
            cleanup,
            healthy_host_samples(schedule),
            healthy_accounting(),
            healthy_postflight(schedule),
        ),
    )
    return tmp_path


def status(evidence: Path, **results: str) -> dict:
    schedule = plan()
    return build(
        evidence,
        {name: {"result": results.get(name, "success")} for name in JOBS},
        run_id=schedule["runId"],
        sha=schedule["workflowSha"],
        attempt=1,
        started_at=None,
        repository="example/viewer",
    )


def test_terminal_requires_bound_evidence_even_when_all_jobs_succeed(tmp_path: Path) -> None:
    result = status(tmp_path)
    assert result["state"] == "FAILED_TERMINAL"
    assert result["failureCategory"] == "HARNESS_FAILURE"
    assert result["restorationState"] == "UNPROVED"
    assert result["fixtureCount"] is None


def test_complete_terminal_retains_historical_v2_artifact(evidence: Path) -> None:
    result = status(evidence)
    assert result["state"] == "SUCCEEDED"
    assert result["restorationState"] == "RESTORED"
    assert result["failureCode"] is None
    assert result["resultManifest"] == "capacity-certification.json"
    assert result["startedAt"] is None


@pytest.mark.parametrize("mode", ["missing", "invalid", "duplicate", "wrong-run", "wrong-sha"])
def test_cleanup_evidence_cannot_be_invented_or_borrowed(evidence: Path, mode: str) -> None:
    path = evidence / "capacity-cleanup.json"
    value = json.loads(path.read_text())
    if mode == "missing":
        path.unlink()
    elif mode == "invalid":
        path.write_text("{")
    elif mode == "duplicate":
        (evidence / "duplicate").mkdir()
        write(evidence / "duplicate" / path.name, value)
    else:
        value["runId" if mode == "wrong-run" else "workflowSha"] = "unrelated"
        write(path, value)
    result = status(evidence)
    assert result["failureCategory"] == "HARNESS_FAILURE"
    assert result["fixtureCount"] is None
    assert result["runOwnedBastionCount"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("runId", "other"),
        ("expectedSha", "b" * 40),
        ("deployedSha", "b" * 40),
        ("planDigest", "b" * 64),
        ("finalCapacity", 1200),
        ("annotationsEnabled", True),
        ("watchdogActive", False),
        ("hostReady", False),
    ],
)
def test_restoration_requires_current_bound_safe_postflight(evidence: Path, field, value) -> None:
    path = evidence / "capacity-postflight.json"
    postflight = json.loads(path.read_text())
    postflight[field] = value
    write(path, postflight)
    result = status(evidence)
    assert result["restorationState"] == "UNPROVED"
    assert result["failureCategory"] == "HARNESS_FAILURE"


@pytest.mark.parametrize("conclusion", ["cancelled", "timed_out", "skipped"])
def test_interrupted_job_graph_cannot_succeed(evidence: Path, conclusion: str) -> None:
    result = status(evidence, shard=conclusion)
    assert result["state"] == "FAILED_TERMINAL"
    assert result["failureCategory"] == "HARNESS_FAILURE"


@pytest.mark.parametrize(
    "codes,category",
    [
        (["report-missing", "http-status-error"], "HARNESS_FAILURE"),
        (["harness-stalled"], "HARNESS_FAILURE"),
        (["unrecognized-error"], "HARNESS_FAILURE"),
        (["tile-errors"], "WORKLOAD_FAILURE"),
    ],
)
def test_shard_failures_distinguish_measurement_loss_from_workload(
    evidence: Path,
    codes: list[str],
    category: str,
) -> None:
    shard = healthy_shard(0)
    shard.update(status="aborted", failureSummary={"failureCodes": codes, "cleanupSucceeded": True})
    write(evidence / "shard-0.json", shard)
    result = status(evidence, shard="failure")
    assert result["failureCategory"] == category
    assert result["state"] == "FAILED_TERMINAL"


def test_missing_shard_is_harness_failure_and_paths_are_not_exposed(evidence: Path) -> None:
    (evidence / "shard-2.json").unlink()
    result = status(evidence, shard="failure")
    assert result["failureCategory"] == "HARNESS_FAILURE"
    assert str(evidence) not in json.dumps(result)


@pytest.mark.parametrize("sentinel_missing", [False, True])
def test_historical_compact_v2_fallback_is_unproved_evidence(
    evidence: Path,
    sentinel_missing: bool,
) -> None:
    schedule = plan()
    sentinels, _, _ = bound_run_evidence(schedule)
    write(
        evidence / "capacity-certification.json",
        build_failure_evidence(
            schedule,
            build_failure_decision(
                schedule, None if sentinel_missing else sentinels, nonce="n" * 32
            ),
            healthy_fixture_preparation(schedule),
            healthy_postflight(schedule),
        ),
    )
    result = status(evidence)
    assert result["failureCategory"] == "HARNESS_FAILURE"
    assert result["workloadFailureCodes"] == []
    assert "QUALIFICATION_EVIDENCE_UNPROVED" in result["harnessFailureCodes"]
    assert result["resultManifest"] == "capacity-certification.json"
    assert result["restorationState"] == "RESTORED"


@pytest.mark.parametrize("damage", ["null", "missing-stage", "cleanup-failed", "measurements"])
def test_completed_shards_require_strict_planned_evidence(evidence: Path, damage: str) -> None:
    shard = healthy_shard(0)
    if damage == "null":
        shard["stages"] = [None]
    elif damage == "missing-stage":
        shard["stages"].pop()
    elif damage == "cleanup-failed":
        shard["stages"][0]["cleanupSucceeded"] = False
    else:
        shard["sustainedMeasurements"] = None
    write(evidence / "shard-0.json", shard)
    result = status(evidence)
    assert result["state"] == "FAILED_TERMINAL"
    assert result["failureCategory"] == "HARNESS_FAILURE"
    assert "COMPLETED_SHARD_EVIDENCE_INVALID" in result["harnessFailureCodes"]
    assert result["restorationState"] == "RESTORED"


@pytest.mark.parametrize("measured", [False, True])
def test_full_v2_negative_classification_requires_observed_workload_failure(
    evidence: Path,
    measured: bool,
) -> None:
    path = evidence / "capacity-certification.json"
    manifest = json.loads(path.read_text())
    manifest["certified"] = False
    manifest["certifiedTier"] = None
    if measured:
        manifest["metrics"]["tileP95Ms"] = 500
        manifest["checks"]["tileLatency"] = False
    else:
        manifest["browserCi"]["conclusion"] = "failure"
        manifest["checks"]["browserCi"] = False
    write(path, manifest)
    result = status(evidence)
    assert result["resultManifest"] == "capacity-certification.json"
    if measured:
        assert result["failureCategory"] == "WORKLOAD_FAILURE"
        assert result["workloadFailureCodes"] == ["MEASURED_TILELATENCY_FAILED"]
    else:
        assert result["failureCategory"] == "HARNESS_FAILURE"
        assert result["workloadFailureCodes"] == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("succeeded", False),
        ("fixturesRemoved", False),
        ("configurationRestored", False),
        ("bastionSessionsRemaining", 1),
        ("bastionSessionsRemaining", False),
    ],
)
def test_cleanup_success_flag_does_not_override_missing_proof(evidence: Path, field, value) -> None:
    path = evidence / "capacity-cleanup.json"
    cleanup = json.loads(path.read_text())
    cleanup[field] = value
    write(path, cleanup)
    assert status(evidence)["failureCategory"] == "HARNESS_FAILURE"
