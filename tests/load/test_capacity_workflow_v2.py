from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from validate_sentinel_evidence import validate as validate_sentinel_evidence

WORKFLOW = Path(".github/workflows/capacity-certification.yml")


def workflow() -> dict[str, object]:
    loaded = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert isinstance(loaded, dict)
    return loaded


def test_capacity_workflow_is_manual_read_only_and_production_protected() -> None:
    loaded = workflow()

    assert set(loaded["on"]) == {"workflow_dispatch"}  # type: ignore[arg-type]
    assert loaded["permissions"] == {"contents": "read", "checks": "read"}
    assert loaded["concurrency"] == {
        "group": "production-control",
        "cancel-in-progress": "false",
    }
    confirmation = loaded["on"]["workflow_dispatch"]["inputs"]["confirmation"]  # type: ignore[index]
    assert "CERTIFY_PRODUCTION_MAX_STRESS" in confirmation["description"]
    window = loaded["on"]["workflow_dispatch"]["inputs"]["window_start_ict"]  # type: ignore[index]
    assert window["required"] == "true"
    assert "YYYY-MM-DDTHH:MM:00+07:00" in window["description"]


def test_capacity_workflow_uses_exactly_six_standard_linux_shards() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]
    shard = jobs["shard"]

    assert shard["runs-on"] == "ubuntu-24.04"
    assert "github.event.repository.visibility == 'public'" in WORKFLOW.read_text(encoding="utf-8")
    assert shard["strategy"]["max-parallel"] == "6"
    assert shard["strategy"]["matrix"]["shard-index"] == [
        "0",
        "1",
        "2",
        "3",
        "4",
        "5",
    ]
    assert shard["environment"]["name"] == "production"


def test_capacity_workflow_has_fail_closed_evidence_and_cleanup_jobs() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]

    assert set(jobs) == {
        "preflight",
        "arm",
        "shard",
        "sentinels",
        "fault-recovery",
        "decision",
        "aggregate",
        "cleanup",
        "postflight",
    }
    assert jobs["aggregate"]["needs"] == [
        "preflight",
        "shard",
        "sentinels",
        "fault-recovery",
        "cleanup",
        "postflight",
    ]
    assert jobs["cleanup"]["if"] == (
        "${{ always() && needs.preflight.result == 'success' }}"
    )
    assert jobs["cleanup"]["needs"] == [
        "preflight",
        "shard",
        "sentinels",
        "fault-recovery",
        "decision",
    ]
    assert jobs["decision"]["if"] == "${{ always() && needs.preflight.result == 'success' }}"
    assert jobs["postflight"]["if"] == "${{ always() && needs.cleanup.result != 'skipped' }}"
    assert jobs["postflight"]["needs"] == ["preflight", "decision", "cleanup"]


def test_capacity_cost_queries_use_monthly_utc_day_boundaries() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert serialized.count('usage_end="$(date -u +%Y-%m-%dT00:00:00Z)"') == 2
    assert "%Y-%m-%dT%H:%M:%SZ" not in serialized


def test_capacity_preflight_rejects_missing_accounting_baseline_before_oci_query() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    validation = serialized.index("Validate zero-cost accounting configuration")
    query = serialized.index("request-summarized-usages")
    assert validation < query
    assert '[[ "${PROJECTED_MONTHLY_RUNS}" =~ ^[1-9][0-9]*$ ]]' in serialized
    assert '[[ "${APPROVED_RESOURCE_COUNT}" =~ ^[1-9][0-9]*$ ]]' in serialized
    assert '[[ "${APPROVED_RESOURCE_DIGEST}" =~ ^[0-9a-f]{64}$ ]]' in serialized


def test_capacity_inventory_search_uses_supported_bounded_pagination() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert "oci search resource structured-search --limit 1000" in serialized
    assert "oci search resource structured-search --all" not in serialized


def test_capacity_accounting_evidence_is_uploaded_before_strict_gate() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]
    steps = jobs["preflight"]["steps"]
    upload_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("with", {}).get("name") == "capacity-accounting"
    )
    gate_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Enforce zero-cost accounting baseline"
    )

    assert upload_index < gate_index
    gate = steps[gate_index]["run"]
    assert ".monthToDateCost == 0 and .permanentResourcesAdded == false" in gate
    assert "observedResourceCount" in gate
    assert "observedInventoryDigest" in gate


def test_capacity_workflow_retains_only_sanitized_aggregate_evidence() -> None:
    loaded = workflow()
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert "include-hidden-files" not in serialized
    assert "capacity-certification.json" in serialized
    assert "capacity-certification.md" in serialized
    assert "shard-${{ matrix.shard-index }}.json" in serialized
    assert "retention-days: 1" in serialized
    assert "joinCode" not in serialized
    assert "LOAD_TEST_ADMIN_PASSWORD" not in loaded["jobs"]["aggregate"].get("env", {})  # type: ignore[index]


def test_capacity_workflow_binds_exact_sha_current_browser_and_future_epoch() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert "git ls-remote origin refs/heads/main" in serialized
    assert '"browser"' in serialized or "browser" in serialized
    assert "CAPACITY_BROWSER_CI_RUN_ID" in serialized
    assert "--start-epoch-ms" in serialized
    assert "distributed_certification.py plan" in serialized
    assert "distributed_certification.py merge" in serialized
    assert "inputs.window_start_ict" in serialized
    assert "window_start_epoch_ms" in serialized
    assert "window-start=${window_start}" in serialized
    assert "window-end=${window_end}" in serialized
    assert "browser-matrix.json" in serialized
    assert "capacity-postflight.json" in serialized
    assert "OCI_ROLLBACK_RELEASE_SHA" in serialized
    assert "NOT CERTIFIED" in serialized
    assert "capacity_window.py" in serialized
    assert "capacity-decision.json.sig" in serialized
    sentinel_runner = Path("deploy/scripts/run-capacity-sentinels.sh").read_text(encoding="utf-8")
    assert "playwright.capacity-metrics.config.ts" in sentinel_runner
    assert "chromium firefox webkit" in serialized
    assert "arm-not-after=${arm_not_after}" in serialized
    assert "rollback-not-after=${rollback_not_after}" in serialized
    assert '.cleanupExecutionDeadlineEpoch' in serialized
    assert "steps.signed-decision.outputs.selected != '300'" in serialized
    assert "steps.signed-decision.outputs.selected == '300'" in serialized


def test_capacity_workflow_runs_the_complete_guarded_maximum_stress_scope() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")
    planner = Path("tests/load/distributed_certification.py").read_text(encoding="utf-8")

    for stage in (
        "smoke-2",
        "acceptance-100",
        "boundary-300",
        "boundary-600",
        "boundary-900",
        "sustained-1200",
        "headroom-1500",
        "breakpoint-1750",
        "breakpoint-2000",
        "recovery-1200",
    ):
        assert stage in planner
    assert "max-parallel: 6" in serialized
    assert "run-capacity-sentinels.sh" in serialized
    assert "run-capacity-fault-recovery.sh" in serialized


def test_capacity_workflow_bounds_each_final_phase_by_absolute_wall_clock() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert jobs["decision"]["timeout-minutes"] == "3"
    assert jobs["cleanup"]["timeout-minutes"] == "12"
    assert jobs["postflight"]["timeout-minutes"] == "5"
    assert jobs["aggregate"]["timeout-minutes"] == "3"
    for phase in ("arm", "decision", "cleanup", "postflight", "aggregate"):
        assert f"remaining --phase {phase}" in serialized
    assert "timeout --foreground" not in serialized
    assert serialized.count("timeout --signal=TERM") >= 5
    assert "--kill-after=250s" in serialized


def test_capacity_workflow_performs_no_bastion_or_host_action_before_arm_gate() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]
    preflight_runs = "\n".join(
        str(step.get("run", "")) for step in jobs["preflight"]["steps"]  # type: ignore[index]
    )
    arm_runs = "\n".join(
        str(step.get("run", "")) for step in jobs["arm"]["steps"]  # type: ignore[index]
    )

    assert "capacity-control-via-bastion.sh" not in preflight_runs
    assert "capacity-arm" not in preflight_runs
    gate_index = arm_runs.index("remaining --phase arm")
    assert gate_index < arm_runs.index("capacity-rollback-preflight")
    assert arm_runs.count("capacity-control-via-bastion.sh") == 1


def test_legacy_rollback_waits_for_health_and_preserves_observed_result() -> None:
    rollback = Path("deploy/scripts/rollback-capacity-candidate.sh").read_text(encoding="utf-8")

    assert "for _ in $(seq 1 30)" in rollback
    assert "sleep_bounded" in rollback
    assert "serviceCount:5" in rollback
    assert "finalCapacity:$capacity" in rollback


def test_every_reconciliation_failure_precedes_finalize_and_triggers_fail_safe_rollback() -> None:
    cleanup = Path("deploy/scripts/cleanup-capacity-certification.sh").read_text(encoding="utf-8")
    trap_index = cleanup.index("trap write_result EXIT")
    finalize_index = cleanup.index('request="capacity-finalize')

    assert cleanup.index("fail_safe_recovery()") < trap_index
    assert '"capacity-abort run=${run_id} digest=${digest}"' in cleanup
    assert '"capacity-rollback candidate=${sha}' not in cleanup
    assert '"capacity-abort run=${run_id} digest=${digest}"' in cleanup
    for reconciliation_gate in (
        'login="$(curl',
        "/synthetic-reset",
        "/desktop-cleanup",
        "/share-cleanup",
        "/api/v2/admin/annotations/",
        "validate_sentinel_evidence.py",
        "oci bastion session list",
    ):
        assert trap_index < cleanup.index(reconciliation_gate) < finalize_index
    assert cleanup.index("cleanup_committed=true") > finalize_index
    assert '.phase == "aborted-restored" and .finalLimit == null' in cleanup
    assert '*\'"phase": "aborted-restored"\'*' not in cleanup


def test_cleanup_timeout_signals_the_entire_process_tree_before_recovery_reserve() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]
    cleanup_run = next(
        str(step["run"])
        for step in jobs["cleanup"]["steps"]  # type: ignore[index]
        if step.get("name") == "Restore capacity configuration and remove every synthetic fixture"
    )

    assert "timeout --signal=TERM --kill-after=250s" in cleanup_run
    assert "timeout --foreground --signal=TERM --kill-after=250s" not in cleanup_run


def test_aborted_restored_state_can_only_rollback_to_bound_300_release() -> None:
    host = Path("deploy/scripts/capacity-control-host.sh").read_text(encoding="utf-8")
    unit = Path("deploy/scripts/capacity-control-unit.sh").read_text(encoding="utf-8")
    rollback = Path("deploy/scripts/rollback-capacity-candidate.sh").read_text(encoding="utf-8")

    assert "capacity-rollback candidate=" not in host
    assert "capacity-rollback candidate=" not in Path(
        "deploy/scripts/cleanup-capacity-certification.sh"
    ).read_text(encoding="utf-8")
    assert 'if [[ "${FINAL_LIMIT}" == 300 ]]' in unit
    assert '"${current}" == "${ROLLBACK_SHA}" || -z "${current}"' in unit
    resumable_states = (
        '"${current}" == "${EXPECTED_CANDIDATE}" || "${current}" == "${ROLLBACK_SHA}"'
    )
    assert resumable_states in rollback


def test_missing_decision_aborts_rolls_back_and_reports_cleanup_failure() -> None:
    cleanup = Path("deploy/scripts/cleanup-capacity-certification.sh").read_text(encoding="utf-8")

    assert "decision_present=false" in cleanup
    assert "decision_valid=false" in cleanup
    assert "selected_capacity=300" in cleanup
    rollback_index = cleanup.index('if [[ "${selected_capacity}" == 300 ]]')
    missing_index = cleanup.index('if [[ "${decision_valid}" != true ]]')
    assert rollback_index < missing_index
    missing_branch = cleanup[missing_index : cleanup.index("cleanup_committed=true")]
    assert "candidate rolled back at the 300-seat floor" in missing_branch
    assert "exit 1" in missing_branch


def test_every_capacity_workflow_executable_exists() -> None:
    for path in (
        "deploy/scripts/run-capacity-fault-recovery.sh",
        "tests/load/build_distributed_evidence.py",
        "tests/load/validate_sentinel_evidence.py",
        "apps/web/e2e-live/capacity-sentinels.spec.ts",
    ):
        assert Path(path).is_file(), path


def test_sentinel_fixture_is_generated_sparse_and_not_supplied_by_secret() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert "generate_synthetic_ome.py" in serialized
    assert "secrets.CAPACITY_SYNTHETIC_330MB" not in serialized
    assert "330000000" in serialized


def test_plan_is_retained_before_arm_and_stage_reset_requires_six_ack_barrier() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    assert serialized.index("name: capacity-plan") < serialized.index("capacity-arm")
    assert "CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON" in serialized
    assert "PATHLAB_CLASSROOM_STAGE_MANIFEST" in serialized
    assert "if: always()" in serialized
    assert "if-no-files-found: error" in serialized
    shard = Path("tests/load/distributed_shard.py").read_text(encoding="utf-8")
    assert "synthetic-stage-ack" in shard
    assert 'response.json().get("complete") is True' in shard
    assert "PATHLAB_CLASSROOM_SHARD_INDEX" in shard


def test_private_capacity_inputs_are_validated_before_arm() -> None:
    serialized = WORKFLOW.read_text(encoding="utf-8")

    validation = serialized.index("Validate protected capacity fixtures")
    arm = serialized.index("  arm:")
    assert validation < arm
    for name in (
        "CAPACITY_MEDIA_MANIFEST_JSON",
        "CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON",
        "CAPACITY_ANNOTATION_SLIDE_ID",
        "CAPACITY_ANNOTATION_ITEM_ID",
        "CAPACITY_SHARE_TARGET_ID",
        "CAPACITY_DYNAMIC_PUBLIC_ID",
    ):
        assert name in serialized[validation:arm]
    assert "every planned stage requires one protected credential entry" in serialized
    assert "media manifest is incomplete" in serialized


def test_cleanup_installs_abort_trap_before_fixture_validation() -> None:
    cleanup = Path("deploy/scripts/cleanup-capacity-certification.sh").read_text(
        encoding="utf-8"
    )

    trap_index = cleanup.index("trap write_result EXIT")
    assert trap_index < cleanup.index(
        ': "${CAPACITY_CLASSROOM_STAGE_MANIFEST_JSON:?'
    )
    assert trap_index < cleanup.index(': "${DEPLOY_EVIDENCE_KEY:?')
    assert trap_index < cleanup.index(': "${CAPACITY_BASE_URL:?')
    assert trap_index < cleanup.index(': "${LOAD_TEST_ADMIN_USERNAME:?')
    assert trap_index < cleanup.index(': "${CAPACITY_ANNOTATION_SLIDE_ID:?')
    assert trap_index < cleanup.index(': "${CAPACITY_ANNOTATION_ITEM_ID:?')


def test_fault_job_can_wait_for_the_late_recovery_stage() -> None:
    jobs = workflow()["jobs"]  # type: ignore[index]
    assert int(jobs["fault-recovery"]["timeout-minutes"]) >= 170
    assert "holdStartEpochMs" in Path("deploy/scripts/run-capacity-fault-recovery.sh").read_text(
        encoding="utf-8"
    )
    assert "holdStartEpochMs" in Path("deploy/scripts/run-capacity-sentinels.sh").read_text(
        encoding="utf-8"
    )
    assert "observe-via-bastion.sh 9340" in Path(
        "deploy/scripts/run-capacity-observer.sh"
    ).read_text(encoding="utf-8")


def test_sentinel_evidence_is_exact_run_bound_and_cleanup_fail_closed() -> None:
    value = {
        "schemaVersion": 1,
        "runId": "123456",
        "workflowSha": "a" * 40,
        "planDigest": "b" * 64,
        "startedAt": "2026-08-14T02:00:00+07:00",
        "completedAt": "2026-08-14T02:30:00+07:00",
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
            "ciRunId": 42,
        },
        "cleanupSucceeded": True,
        "aggregateOnly": True,
        "syntheticOnly": True,
    }
    assert validate_sentinel_evidence(value, require_cleanup=True) == value
    for field, invalid in (
        ("planDigest", "bad"),
        ("fixtureBytes", 329_999_999),
        ("cleanupSucceeded", False),
    ):
        changed = deepcopy(value)
        changed[field] = invalid
        with pytest.raises(ValueError):
            validate_sentinel_evidence(changed, require_cleanup=True)

    changed = deepcopy(value)
    changed["frontend"]["lcpMsMax"] = 2500.001
    with pytest.raises(ValueError):
        validate_sentinel_evidence(changed, require_cleanup=True)
