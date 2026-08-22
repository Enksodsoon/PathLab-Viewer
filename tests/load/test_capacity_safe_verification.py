from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/capacity-safe-verification.yml")
RUNNER = Path("deploy/scripts/run-capacity-safe-verification.sh")
HOST = Path("deploy/scripts/capacity-control-host.sh")
BASTION = Path("deploy/scripts/capacity-control-via-bastion.sh")
DISPATCHER = Path("deploy/scripts/deploy-release.sh")


def test_safe_verification_is_manual_serial_and_production_protected() -> None:
    loaded = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert set(loaded["on"]) == {"workflow_dispatch"}  # type: ignore[index]
    assert loaded["concurrency"] == {
        "group": "production-control",
        "cancel-in-progress": "false",
    }
    job = loaded["jobs"]["verify"]
    assert job["environment"]["name"] == "production"
    assert job["timeout-minutes"] == "65"
    options = loaded["on"]["workflow_dispatch"]["inputs"]["mode"]["options"]  # type: ignore[index]
    assert options == [
        "controlled-abort",
        "controller-termination",
        "delayed-cleanup",
        "full-300",
    ]


def test_runner_preserves_capacity_safety_and_exact_ownership_contracts() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    assert "lead_seconds >= 1200" in runner
    assert "lead_seconds <= 2400" in runner
    assert "capacity-runtime-preflight expected=${GITHUB_SHA}" in runner
    assert "capacity-postflight expected=${GITHUB_SHA}" in runner
    assert "capacity-abort run=${GITHUB_RUN_ID}" in runner
    assert "capacity-recover run=${GITHUB_RUN_ID} sha=${GITHUB_SHA}" in runner
    assert "capacity_fixtures.py reconcile" in runner
    assert "delete_owned_bastion \"${CAPACITY_RECOVERY_RUN_ID}\"" in runner
    assert "PATHLAB_CLASSROOM_PARTICIPANTS=\"${participants}\"" in runner
    assert "participants=300" in runner
    assert "duration=600" in runner
    assert 'fault_start="$((deadline - 600))"' in runner
    assert 'fault_end="$((deadline - 300))"' in runner
    assert 'fault_start="$((now_epoch + 30))"' not in runner
    assert "PATHLAB_ANNOTATIONS_ENABLED" not in runner
    assert "OCI_ROLLBACK_RELEASE_SHA" not in runner


def test_controller_termination_is_exact_run_bound_and_allowlisted() -> None:
    host = HOST.read_text(encoding="utf-8")
    bastion = BASTION.read_text(encoding="utf-8")
    dispatcher = DISPATCHER.read_text(encoding="utf-8")
    request = "capacity-terminate-controller"
    assert request in host
    assert '.runId == $run and .planDigest == $digest and .phase == "armed"' in host
    assert "--kill-whom=main --signal=KILL" in host
    assert request in bastion
    assert request in dispatcher


def test_terminal_artifact_is_compact_and_unconditional() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    assert "if: always()" in workflow
    assert "retention-days: 14" in workflow
    for field in (
        "jobId",
        "kind",
        "state",
        "releaseSha",
        "failureCode",
        "restorationState",
        "runOwnedBastionCount",
    ):
        assert field in runner


def test_bastion_deletion_and_identifier_redaction_are_bounded() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    runner = RUNNER.read_text(encoding="utf-8")
    bastion = BASTION.read_text(encoding="utf-8")
    assert "Mask production infrastructure identifiers" in workflow
    for name in ("CAPACITY_BASE_URL", "OCI_BASTION_ID", "OCI_INSTANCE_ID", "OCI_TARGET_PRIVATE_IP"):
        assert f'echo "::add-mask::${{{name}}}"' not in workflow
        assert name in workflow
    assert "seq 1 60" in runner
    assert "seq 1 60" in bastion
    assert "sleep 5" in runner
    assert "sleep 5" in bastion
