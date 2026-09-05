import shutil
import subprocess
from pathlib import Path

import pytest
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
    assert 'delete_owned_bastion "${CAPACITY_RECOVERY_RUN_ID}"' in runner
    assert 'PATHLAB_CLASSROOM_PARTICIPANTS="${participants}"' in runner
    assert "participants=300" in runner
    assert "duration=600" in runner
    assert 'fault_start="$((deadline - 600))"' in runner
    assert 'fault_end="$((deadline - 300))"' in runner
    assert 'fault_start="$((now_epoch + 30))"' not in runner
    assert "PATHLAB_ANNOTATIONS_ENABLED" not in runner
    assert "OCI_ROLLBACK_RELEASE_SHA" not in runner


def test_controlled_abort_does_not_repeat_recovery_after_proved_restoration() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    abort_function = runner.split("abort_runtime() {", 1)[1].split("\n}", 1)[0]
    assert "capacity-abort run=${GITHUB_RUN_ID}" in abort_function
    assert "capacity-recover run=" not in abort_function
    assert "restored=true" in abort_function
    assert "armed=false" in abort_function
    assert 'if [[ "${CAPACITY_MODE}" == controlled-abort ]]; then' in runner
    assert "CAPACITY_ABORT_FAILED" in runner
    assert "CAPACITY_ABORT_INVALID" in runner


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
    assert "SECONDS + 600" in bastion
    assert '[[ "${state}" == DELETED ]]' in bastion
    assert 'delete_owned_bastion "${GITHUB_RUN_ID}"' in runner
    assert "sleep 5" in runner
    assert "sleep 5" in bastion
    assert 'install -d -m 0700 "${RUNTIME_DIR}"' not in Path(
        "deploy/scripts/with-capacity-override.sh"
    ).read_text(encoding="utf-8")
    assert "755:root:root" in Path("deploy/scripts/with-capacity-override.sh").read_text(
        encoding="utf-8"
    )


def run_isolated_shell(script: str) -> subprocess.CompletedProcess[str]:
    git_bash = Path("C:/Program Files/Git/bin/bash.exe")
    bash = str(git_bash) if git_bash.exists() else shutil.which("bash")
    if not bash:
        pytest.skip("Bash is required for isolated shell failure injection")
    return subprocess.run(
        [bash, "--noprofile", "--norc", "-c", script], capture_output=True, text=True, timeout=10
    )


def test_failed_fixture_reconciliation_never_proves_cleanup() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    function = (
        "reconcile_fixture() {"
        + runner.split("reconcile_fixture() {", 1)[1].split("\n}", 1)[0]
        + "\n}"
    )
    result = run_isolated_shell(
        """
set +e
cleanup_proved=true
python() { return 7; }
"""
        + function
        + """
reconcile_fixture || true
printf '%s' "$cleanup_proved"
"""
    )
    assert result.returncode == 0
    assert result.stdout == "false"


def test_cancelled_safe_verification_cannot_inherit_success_exit_status() -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    start = runner.index("finish() {")
    end = runner.index("\nstarted_at=", start)
    result = run_isolated_shell(
        """
set +e
primary_failure=NONE
restored=true
cleanup_proved=true
manifest_digest=''
GITHUB_RUN_ID=123456
fixture_dir=/unused
work_dir=/unused
reconcile_fixture() { return 0; }
recover_runtime() { return 0; }
delete_owned_bastion() { return 0; }
owned_bastion_count() { echo 0; }
write_status() { printf '%s:%s' "$1" "$primary_failure"; }
rm() { return 0; }
"""
        + runner[start:end]
        + "\nkill -TERM $$\n"
    )
    assert result.returncode != 0
    assert result.stdout == "FAILED_TERMINAL:SAFE_VERIFICATION_CANCELLED"


@pytest.mark.parametrize("json_accepted", [False, True])
def test_postflight_failure_revokes_earlier_restoration_proof(json_accepted: bool) -> None:
    runner = RUNNER.read_text(encoding="utf-8")
    start = runner.index("finish() {")
    end = runner.index("\ntrap finish EXIT", start)
    result = run_isolated_shell(
        """
set +e
primary_failure=NONE
restored=true
cleanup_proved=true
manifest_digest=known
GITHUB_RUN_ID=123456
GITHUB_SHA=known
fixture_dir=/unused
work_dir=/unused
reconcile_fixture() { return 0; }
recover_runtime() { return 0; }
delete_owned_bastion() { return 0; }
owned_bastion_count() { echo 0; }
bash() { echo '{"ready":true,"watchdogActive":true}'; return 1; }
jq() { return JSON_RESULT; }
write_status() { printf '%s:%s:%s' "$1" "$primary_failure" "$restored"; }
rm() { return 0; }
""".replace("JSON_RESULT", "0" if json_accepted else "1")
        + runner[start:end]
        + "\ntrue\nfinish\n"
    )
    assert result.returncode != 0
    assert result.stdout == "FAILED_TERMINAL:POSTFLIGHT_NOT_PROVED:false"


def test_exit_postflight_requires_watchdog_proof() -> None:
    finish = RUNNER.read_text().split("finish() {", 1)[1].split("\ntrap finish EXIT", 1)[0]
    assert ".watchdogExpected == true and .watchdogActive == true" in finish
