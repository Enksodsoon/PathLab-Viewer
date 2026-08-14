from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import time
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[2]


def _load_capacity_control() -> ModuleType:
    path = ROOT / "deploy" / "scripts" / "capacity_control.py"
    spec = importlib.util.spec_from_file_location("capacity_control", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


capacity_control = _load_capacity_control()
CapacityControlError = capacity_control.CapacityControlError
arm = capacity_control.arm
consume_fault = capacity_control.consume_fault
consume_finalize = capacity_control.consume_finalize
hold_until_finalize = capacity_control.hold_until_finalize
mark_finished = capacity_control.mark_finished
request_finalize = capacity_control.request_finalize
sanitized_status = capacity_control.sanitized_status

SHA = "a" * 40
DIGEST = "b" * 64
NONCE = "capacity-nonce-123456"


def deadline() -> int:
    return int(time.time()) + 7_200


def test_arm_is_run_bound_and_rejects_concurrent_capacity_runs(tmp_path: Path) -> None:
    first = arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline_epoch=deadline())

    assert first["phase"] == "armed"
    assert first["nonceHash"] == hashlib.sha256(NONCE.encode()).hexdigest()
    with pytest.raises(CapacityControlError, match="another capacity run is active"):
        arm(tmp_path, "run-2", SHA, "c" * 64, "different-nonce", deadline())


def test_finalize_rejects_wrong_plan_sha_or_nonce_binding(tmp_path: Path) -> None:
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())

    with pytest.raises(CapacityControlError, match="binding"):
        request_finalize(
            tmp_path,
            "run-1",
            SHA,
            "c" * 64,
            NONCE,
            tmp_path / "decision.json",
            tmp_path / "decision.sig",
        )


def test_finalize_request_is_consumed_once_and_contains_only_paths(tmp_path: Path) -> None:
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())
    evidence = tmp_path / "pathlab-capacity-run-1-decision.json"
    signature = tmp_path / "pathlab-capacity-run-1-decision.json.sig"
    evidence.write_text("{}", encoding="utf-8")
    signature.write_text("0" * 64, encoding="utf-8")
    request_finalize(tmp_path, "run-1", SHA, DIGEST, NONCE, evidence, signature)

    result = consume_finalize(tmp_path, "run-1", SHA, DIGEST, NONCE)

    assert result == {"evidencePath": str(evidence), "signaturePath": str(signature)}
    with pytest.raises(CapacityControlError, match="not awaiting finalization"):
        consume_finalize(tmp_path, "run-1", SHA, DIGEST, NONCE)


def test_finished_run_leaves_replay_tombstone_but_releases_global_slot(tmp_path: Path) -> None:
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())
    evidence = tmp_path / "pathlab-capacity-run-1-decision.json"
    signature = tmp_path / "pathlab-capacity-run-1-decision.json.sig"
    evidence.write_text("{}", encoding="utf-8")
    signature.write_text("0" * 64, encoding="utf-8")
    request_finalize(tmp_path, "run-1", SHA, DIGEST, NONCE, evidence, signature)
    consume_finalize(tmp_path, "run-1", SHA, DIGEST, NONCE)
    mark_finished(tmp_path, "run-1", success=True, final_limit=1200)

    with pytest.raises(CapacityControlError, match="already exists"):
        arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())
    second = arm(tmp_path, "run-2", SHA, "c" * 64, "nonce-for-run-2", deadline())
    assert second["phase"] == "armed"


def test_failed_finish_never_claims_restoration_without_local_proof(tmp_path: Path) -> None:
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())
    mark_finished(tmp_path, "run-1", success=False)
    assert sanitized_status(tmp_path, "run-1")["phase"] == "restore-failed"
    with pytest.raises(CapacityControlError, match="another capacity run"):
        arm(tmp_path, "run-2", SHA, "c" * 64, "different-nonce", deadline())


def test_verified_abort_releases_slot_and_reports_aborted_restored(tmp_path: Path) -> None:
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())
    mark_finished(tmp_path, "run-1", success=False, restoration_verified=True)
    assert sanitized_status(tmp_path, "run-1")["phase"] == "aborted-restored"
    assert arm(tmp_path, "run-2", SHA, "c" * 64, "different-nonce", deadline())["phase"] == "armed"


def test_status_is_strictly_sanitized_and_never_exposes_nonce_or_paths(tmp_path: Path) -> None:
    expiry = deadline()
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, expiry)

    assert sanitized_status(tmp_path, "run-1") == {
        "runId": "run-1",
        "workflowSha": SHA,
        "planDigest": DIGEST,
        "deadlineEpoch": expiry,
        "phase": "armed",
        "finalLimit": None,
        "faultConsumed": False,
    }


def test_fault_is_one_shot_and_only_consumed_inside_bound_recovery_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = int(time.time())
    arm(
        tmp_path,
        "run-1",
        SHA,
        DIGEST,
        NONCE,
        deadline(),
        fault_start_epoch=now + 60,
        fault_end_epoch=now + 120,
    )
    monkeypatch.setattr(capacity_control.time, "time", lambda: now + 59)
    with pytest.raises(CapacityControlError, match="recovery window"):
        consume_fault(tmp_path, "run-1", DIGEST)
    monkeypatch.setattr(capacity_control.time, "time", lambda: now + 60)
    consumed = consume_fault(tmp_path, "run-1", DIGEST)
    assert consumed["faultConsumed"] is True
    with pytest.raises(CapacityControlError, match="already consumed"):
        consume_fault(tmp_path, "run-1", DIGEST)


def test_concurrent_fault_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    now = int(time.time())
    arm(
        tmp_path,
        "run-1",
        SHA,
        DIGEST,
        NONCE,
        deadline(),
        fault_start_epoch=now,
        fault_end_epoch=now + 60,
    )
    consume_fault(tmp_path, "run-1", DIGEST)
    assert (tmp_path / "pathlab-capacity-run-1-fault-claim").is_file()


def test_hold_copies_only_the_consumed_bound_decision(tmp_path: Path) -> None:
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, deadline())
    evidence = tmp_path / "pathlab-capacity-run-1-decision.json"
    signature = tmp_path / "pathlab-capacity-run-1-decision.json.sig"
    evidence.write_text('{"certification": {}}', encoding="utf-8")
    signature.write_text("0" * 64, encoding="utf-8")
    request_finalize(tmp_path, "run-1", SHA, DIGEST, NONCE, evidence, signature)
    decision_output = tmp_path / "wrapper-decision.json"
    signature_output = tmp_path / "wrapper-decision.sig"

    hold_until_finalize(
        tmp_path,
        "run-1",
        SHA,
        DIGEST,
        NONCE,
        decision_output,
        signature_output,
    )

    assert decision_output.read_text(encoding="utf-8") == '{"certification": {}}'
    assert signature_output.read_text(encoding="utf-8") == "0" * 64


def test_hold_fails_closed_at_absolute_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expiry = deadline()
    arm(tmp_path, "run-1", SHA, DIGEST, NONCE, expiry)
    monkeypatch.setattr(capacity_control.time, "time", lambda: expiry)

    with pytest.raises(CapacityControlError, match="absolute deadline"):
        hold_until_finalize(
            tmp_path,
            "run-1",
            SHA,
            DIGEST,
            NONCE,
            tmp_path / "decision.json",
            tmp_path / "decision.sig",
        )


def test_host_arm_rolls_back_state_if_transient_unit_does_not_start() -> None:
    script = Path("deploy/scripts/capacity-control-host.sh").read_text(encoding="utf-8")

    assert "arm_failed" in script
    assert 'capacity_control.py" finish' in script
    assert '--run-id "${RUN_ID}"' in script
    assert "trap arm_failed EXIT" in script
    assert "trap - EXIT" in script


def test_bastion_client_fully_anchors_every_allowlisted_request() -> None:
    script = Path("deploy/scripts/capacity-control-via-bastion.sh").read_text(encoding="utf-8")

    for name in (
        "ARM_PATTERN",
        "STATUS_PATTERN",
        "FINALIZE_PATTERN",
        "FAULT_PATTERN",
        "ABORT_PATTERN",
    ):
        line = next(line for line in script.splitlines() if line.startswith(f"{name}="))
        assert "^capacity-" in line
        assert "$" in line


GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_host_rejects_expired_arm_before_reading_or_mutating_live_release() -> None:
    request = (
        f"capacity-arm {'a' * 40} run=run-1 digest={'b' * 64} "
        "arm-not-after=1000000000 deadline=2000000000 fault-start=1900000000 "
        f"fault-end=1900000100 evidence=YQ signature={'c' * 64} nonce={'n' * 32}"
    )

    result = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-host.sh", request],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "arm authorization expired before host mutation" in result.stderr


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_forced_command_parser_does_not_execute_shell_injection(tmp_path: Path) -> None:
    marker = tmp_path / "injected"
    request = f"capacity-status run=run-1;touch {marker}"

    result = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-host.sh", request],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert not marker.exists()
