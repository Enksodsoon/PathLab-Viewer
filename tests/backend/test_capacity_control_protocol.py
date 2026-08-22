from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import time
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parents[2]
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")


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
SIGUSR1 = getattr(signal, "SIGUSR1", signal.SIGTERM)


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
    finalizing = json.loads((tmp_path / "pathlab-capacity-run-1-control.json").read_text())
    assert finalizing["evidenceDigest"] == hashlib.sha256(evidence.read_bytes()).hexdigest()
    assert finalizing["decisionSignature"] == "0" * 64

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
        "runtimeManifestDigest": "0" * 64,
        "restoreNotAfter": expiry + 300,
        "phase": "armed",
        "finalLimit": None,
        "faultConsumed": False,
    }


def test_arm_persists_immutable_runtime_manifest_and_restore_deadline(tmp_path: Path) -> None:
    expiry = deadline()
    restore_deadline = expiry + 270
    state = arm(
        tmp_path,
        "run-1",
        SHA,
        DIGEST,
        NONCE,
        expiry,
        runtime_manifest_digest="d" * 64,
        restore_not_after=restore_deadline,
    )

    assert state["runtimeManifestDigest"] == "d" * 64
    assert state["restoreNotAfter"] == restore_deadline
    persisted = json.loads((tmp_path / "pathlab-capacity-run-1-control.json").read_text())
    assert persisted["runtimeManifestDigest"] == "d" * 64
    assert persisted["restoreNotAfter"] == restore_deadline


def test_arm_persists_and_enforces_the_explicit_three_hour_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = 1_800_000_000
    monkeypatch.setattr(capacity_control.time, "time", lambda: now)
    state = arm(
        tmp_path,
        "run-window",
        SHA,
        DIGEST,
        NONCE,
        now + 9_900,
        runtime_manifest_digest="d" * 64,
        restore_not_after=now + 10_170,
        window_start_epoch=now,
        window_end_epoch=now + 10_800,
    )

    assert state["windowStartEpoch"] == now
    assert state["windowEndEpoch"] == now + 10_800

    with pytest.raises(CapacityControlError, match="exactly three hours"):
        arm(
            tmp_path / "other",
            "run-invalid-window",
            SHA,
            DIGEST,
            NONCE,
            now + 9_900,
            runtime_manifest_digest="d" * 64,
            restore_not_after=now + 10_170,
            window_start_epoch=now,
            window_end_epoch=now + 10_799,
        )


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
        "ACK_PATTERN",
    ):
        line = next(line for line in script.splitlines() if line.startswith(f"{name}="))
        assert "^capacity-" in line
        assert "$" in line
    assert "ConnectTimeout=10" in script
    assert "ConnectionAttempts=1" in script
    assert "ServerAliveCountMax=2" in script
    assert "create-port-forwarding" in script
    assert "create-managed-ssh" not in script
    assert "HostKeyAlias=pathlab-target" in script
    assert "OCI_TARGET_KEY_FILE" in script
    assert "OCI_TARGET_KNOWN_HOSTS_FILE" in script
    assert "HOST_KEY_REJECTED" in script
    assert "AUTH_REJECTED|ENDPOINT_NOT_READY|LOCAL_PORT_COLLISION" in script
    assert "ENDPOINT_NOT_READY" in script
    assert "for attempt in 1 2 3" in script


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_bastion_client_reuses_one_session_for_preflight_then_arm(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    command_log = tmp_path / "oci.log"
    ssh_log = tmp_path / "ssh.log"
    known_hosts = tmp_path / "known-hosts"
    known_hosts.write_text("pinned\n", encoding="utf-8")
    target_key = tmp_path / "target-key"
    target_key.write_text("test-key\n", encoding="utf-8")
    target_known_hosts = tmp_path / "target-known-hosts"
    target_known_hosts.write_text("target-pinned\n", encoding="utf-8")

    fake_oci = fake_bin / "oci"
    fake_oci.write_text(
        "#!/usr/bin/env bash\n"
        'printf \'%s\\n\' "$*" >> "$OCI_LOG"\n'
        'if [[ "$*" == *"create-port-forwarding"* ]]; then '
        'rm -f "$OCI_DELETE_MARKER"; echo "ocid1.bastionsession.test"; '
        'elif [[ "$*" == *"session delete"* ]]; then touch "$OCI_DELETE_MARKER"; '
        'elif [[ "$*" == *"lifecycle-state"* ]]; then '
        'if [[ -f "$OCI_DELETE_MARKER" ]]; then echo DELETED; else echo ACTIVE; fi; '
        'elif [[ "$*" == *"ssh-metadata"* ]]; then '
        'echo "ssh -i <privateKey> -N -L <localPort>:10.0.0.1:22 -p 22 test@example.com"; fi\n',
        encoding="utf-8",
    )
    fake_keygen = fake_bin / "ssh-keygen"
    fake_keygen.write_text(
        "#!/usr/bin/env bash\n"
        'while [[ "$#" -gt 0 ]]; do\n'
        '  [[ "$1" == -f ]] && { shift; touch "$1" "$1.pub"; exit; }\n'
        "  shift\n"
        "done\n",
        encoding="utf-8",
    )
    fake_ssh = fake_bin / "ssh"
    fake_ssh.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ " $* " == *" -N "* ]]; then '
        'printf \'tunnel\\n\' >> "$TUNNEL_LOG"; '
        'if [[ -n "${FAIL_EVERY_TUNNEL:-}" ]]; then '
        'echo "$FAIL_EVERY_TUNNEL" >&2; exit 255; fi; '
        'if [[ "${FAIL_FIRST_TUNNEL:-}" == true && '
        '! -f "$TUNNEL_RETRY_MARKER" ]]; then '
        'touch "$TUNNEL_RETRY_MARKER"; '
        'echo "${FIRST_TUNNEL_ERROR:-Connection refused}" >&2; exit 255; fi; '
        "trap 'exit 0' TERM INT; while true; do sleep 1; done; fi\n"
        'request="${!#}"\nprintf \'%s\\n\' "$request" >> "$SSH_LOG"\n'
        'if [[ "$request" == capacity-runtime-preflight* ]]; then '
        'if [[ "${INVALID_PREFLIGHT:-}" == true ]]; then echo \'{"directoryReady":false}\'; '
        f"else echo '{{\"releaseSha\":\"{'a' * 40}\",\"releaseExact\":true,"
        f"\"runtimeManifestDigest\":\"{'d' * 64}\",\"servicesExact\":true,"
        '"ready":true,"classroomEnabled":true,"finalCapacity":300,'
        '"annotationsEnabled":false}\'; fi; '
        'elif [[ "$request" == capacity-abort* ]]; then '
        f"echo '{{\"runId\":\"run-1\",\"planDigest\":\"{'b' * 64}\","
        '"phase":"aborted-restored","finalLimit":null,"releaseExact":true,'
        '"servicesExact":true,"ready":true,"classroomEnabled":true,'
        '"finalCapacity":300,"annotationsEnabled":false}\'; '
        'elif [[ "${FAIL_ARM:-}" == true ]]; then exit 9; else echo \'{"phase":"armed"}\'; fi\n',
        encoding="utf-8",
    )
    fake_jq = fake_bin / "jq"
    fake_jq.write_text(
        "#!/usr/bin/env bash\n"
        "value=\"$(cat)\"\n"
        'if [[ "$1" == -c ]]; then printf \'%s\\n\' "$value"; '
        'elif [[ "$*" == *runtimeManifestDigest* ]]; then '
        '[[ "$value" == *\'"releaseExact":true\'* && "$value" == *\'"servicesExact":true\'* ]]; '
        'elif [[ "$*" == *finalLimit* ]]; then '
        '[[ "$value" == *\'"phase":"aborted-restored"\'* && '
        '"$value" == *\'"finalLimit":null\'* && "$value" == *\'"runId":"run-1"\'* && '
        '"$value" == *\'"releaseExact":true\'* && "$value" == *\'"finalCapacity":300\'* ]]; '
        'elif [[ "$*" == *releaseExact* ]]; then '
        '[[ "$value" == *\'"servicesExact":true\'* && "$value" == *\'"finalCapacity":300\'* ]]; '
        "else exit 1; fi\n",
        encoding="utf-8",
    )
    for executable in (fake_oci, fake_keygen, fake_ssh, fake_jq):
        executable.chmod(0o755)

    preflight = f"capacity-runtime-preflight expected={'a' * 40} manifest={'d' * 64}"
    arm_request = (
        f"capacity-arm {'a' * 40} run=run-1 digest={'b' * 64} "
        f"manifest={'d' * 64} arm-not-after=1800000000 window-start=1799999760 "
        "window-end=1800010560 deadline=1800008000 "
        "restore-not-after=1800009000 fault-start=1800001000 "
        f"fault-end=1800002000 evidence=YQ signature={'c' * 64} nonce={'n' * 32}"
    )
    env = os.environ.copy()
    resolved_fake_bin = fake_bin.resolve().as_posix()
    bash_bin = (
        f"/{resolved_fake_bin[0].lower()}{resolved_fake_bin[2:]}"
        if os.name == "nt"
        else resolved_fake_bin
    )
    env.update(
        {
            "PATH": f"{bash_bin}:{env['PATH']}",
            "PATHLAB_CAPACITY_OCI_COMMAND": f"{bash_bin}/oci",
            "PATHLAB_CAPACITY_SSH_KEYGEN_COMMAND": f"{bash_bin}/ssh-keygen",
            "PATHLAB_CAPACITY_SSH_COMMAND": f"{bash_bin}/ssh",
            "PATHLAB_CAPACITY_JQ_COMMAND": f"{bash_bin}/jq",
            "OCI_LOG": str(command_log),
            "OCI_DELETE_MARKER": str(tmp_path / "oci-delete-marker"),
            "SSH_LOG": str(ssh_log),
            "TUNNEL_LOG": str(tmp_path / "tunnel.log"),
            "TUNNEL_RETRY_MARKER": str(tmp_path / "tunnel-retry-marker"),
            "OCI_BASTION_ID": "ocid1.bastion.test",
            "OCI_INSTANCE_ID": "ocid1.instance.test",
            "OCI_TARGET_PRIVATE_IP": "10.0.0.1",
            "OCI_KNOWN_HOSTS_FILE": str(known_hosts),
            "OCI_TARGET_KEY_FILE": str(target_key),
            "OCI_TARGET_KNOWN_HOSTS_FILE": str(target_known_hosts),
            "GITHUB_RUN_ID": "123",
        }
    )

    rejected_override = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", preflight, arm_request],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert rejected_override.returncode != 0
    assert not command_log.exists()
    env["PATHLAB_CAPACITY_TEST_MODE"] = "true"
    env["FAIL_FIRST_TUNNEL"] = "true"

    completed = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", preflight, arm_request],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode == 0, completed.stderr
    assert command_log.read_text(encoding="utf-8").count("create-port-forwarding") == 1
    assert ssh_log.read_text(encoding="utf-8").splitlines() == [preflight, arm_request]
    assert (tmp_path / "tunnel-retry-marker").exists()
    assert (tmp_path / "tunnel.log").read_text(encoding="utf-8").splitlines() == [
        "tunnel",
        "tunnel",
    ]

    command_log.unlink()
    ssh_log.unlink()
    (tmp_path / "tunnel.log").unlink()
    (tmp_path / "tunnel-retry-marker").unlink()
    env["FIRST_TUNNEL_ERROR"] = "Permission denied (publickey)."
    transient_bastion_auth = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", preflight, arm_request],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert transient_bastion_auth.returncode == 0, transient_bastion_auth.stderr
    assert command_log.read_text(encoding="utf-8").count("create-port-forwarding") == 1
    assert ssh_log.read_text(encoding="utf-8").splitlines() == [preflight, arm_request]
    assert (tmp_path / "tunnel.log").read_text(encoding="utf-8").splitlines() == [
        "tunnel",
        "tunnel",
    ]
    env.pop("FIRST_TUNNEL_ERROR")

    command_log.unlink()
    ssh_log.unlink()
    (tmp_path / "tunnel.log").unlink()
    (tmp_path / "tunnel-retry-marker").unlink()
    env["FAIL_EVERY_TUNNEL"] = "Host key verification failed."
    rejected_host_key = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", preflight, arm_request],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert rejected_host_key.returncode != 0
    assert "HOST_KEY_REJECTED" in rejected_host_key.stderr
    assert command_log.read_text(encoding="utf-8").count("create-port-forwarding") == 1
    assert (tmp_path / "tunnel.log").read_text(encoding="utf-8").splitlines() == ["tunnel"]
    env.pop("FAIL_EVERY_TUNNEL")

    command_log.unlink()
    if ssh_log.exists():
        ssh_log.unlink()
    (tmp_path / "tunnel.log").unlink()
    env["INVALID_PREFLIGHT"] = "true"
    invalid_preflight = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", preflight, arm_request],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert invalid_preflight.returncode != 0
    assert ssh_log.read_text(encoding="utf-8").splitlines() == [preflight]
    env.pop("INVALID_PREFLIGHT")

    command_log.unlink()
    ssh_log.unlink()
    env["FAIL_ARM"] = "true"
    failed = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", preflight, arm_request],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert failed.returncode != 0
    failed_oci = command_log.read_text(encoding="utf-8")
    assert failed_oci.count("create-port-forwarding") == 1
    assert failed_oci.count("session delete") == 1
    assert failed_oci.rfind("lifecycle-state") > failed_oci.rfind("session delete")
    assert "n" * 32 not in failed.stdout + failed.stderr

    command_log.unlink()
    ssh_log.unlink()
    env.pop("FAIL_ARM")
    abort = f"capacity-abort run=run-1 digest={'b' * 64}"
    recovery = subprocess.run(
        [str(BASH), "deploy/scripts/capacity-control-via-bastion.sh", abort],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert recovery.returncode == 0, recovery.stderr
    assert command_log.read_text(encoding="utf-8").count("create-port-forwarding") == 1
    assert ssh_log.read_text(encoding="utf-8").splitlines() == [abort]


def test_host_unit_owns_same_release_restoration_before_the_hard_deadline() -> None:
    host = Path("deploy/scripts/capacity-control-host.sh").read_text(encoding="utf-8")
    unit = Path("deploy/scripts/capacity-control-unit.sh").read_text(encoding="utf-8")
    restore = Path("deploy/scripts/restore-capacity-runtime.sh").read_text(encoding="utf-8")
    override = Path("deploy/scripts/with-capacity-override.sh").read_text(encoding="utf-8")
    control = Path("deploy/scripts/capacity_control.py").read_text(encoding="utf-8")

    assert "manifest=([0-9a-f]{64})" in host
    assert "restore-not-after=([0-9]{10})" in host
    assert '"${MANIFEST_DIGEST}" "${RESTORE_NOT_AFTER}"' in host
    assert '--property="TimeoutStopSec=${RESTORE_GRACE_SECONDS}"' in host
    assert "restore_safe_runtime" in unit
    assert "systemctl kill --kill-whom=main --signal=USR1" in host
    assert 'kill -TERM -- "-${CHILD_PID}"' in unit
    assert "setsid bash" in unit
    assert "PATHLAB_CAPACITY_RESTORE_NOT_AFTER" in unit
    assert "runtimeManifestDigest" in control and "restoreNotAfter" in control
    assert "-control.json" in host
    assert '.runtimeManifestDigest, (.restoreNotAfter | tostring)' in host
    assert "pathlab-capacity-controller" in host
    assert "prior-dispatcher" in host and "controller-cleanup" in host
    assert "RESTORE_NOT_AFTER" in override
    assert 'timeout --signal=TERM --kill-after=5s "${remaining}s"' in override
    assert "trap finish_failed EXIT" in unit
    assert unit.index("restore_safe_runtime()") < unit.index("trap finish_failed EXIT")
    assert "timeout --signal=TERM --kill-after=10s" in unit
    assert "EXPECTED_SHA" in restore
    assert "runtime_safety_manifest.py" in restore
    assert '"PATHLAB_CLASSROOM_MAX_PARTICIPANTS": "300"' in restore
    assert "rollback" not in restore.lower()


def test_stable_capacity_dispatcher_is_installed_atomically_and_always_restored() -> None:
    deploy = Path("deploy/scripts/deploy-release.sh").read_text(encoding="utf-8")
    host = Path("deploy/scripts/capacity-control-host.sh").read_text(encoding="utf-8")

    assert "^/run/pathlab-capacity-[a-z0-9-]{1,64}-controller$" in deploy
    assert deploy.index("/run/pathlab-capacity-controller") < deploy.index(
        'exec bash "${LIVE_DIR}/deploy/scripts/capacity-control-host.sh"'
    )
    backup = '"${STABLE_DISPATCHER}" "${CONTROLLER_DIR}/prior-dispatcher"'
    install = '"${LIVE_DIR}/deploy/scripts/deploy-release.sh"'
    assert backup in host and install in host
    assert host.index(backup) < host.index(install)
    assert "CONTROLLER_INSTALLED=true" in host
    assert 'install -o root -g root -m 755 "${CONTROLLER_DIR}/prior-dispatcher"' in host
    assert "reconcile-abort.sh" in host
    assert 'rm -f -- "${CONTROLLER_POINTER}"' in host
    assert "atomic_install" in host
    assert "os.fsync" in host
    assert "--timer-property=AccuracySec=1s" in host
    assert host.index("controller-cleanup.timer") < host.index('mv -f -- "${pointer_tmp}"')


def test_finalize_abort_and_ack_replay_from_retained_host_results() -> None:
    host = Path("deploy/scripts/capacity-control-host.sh").read_text(encoding="utf-8")
    unit = Path("deploy/scripts/capacity-control-unit.sh").read_text(encoding="utf-8")
    cleanup = Path("deploy/scripts/cleanup-capacity-certification.sh").read_text(encoding="utf-8")
    restore = Path("deploy/scripts/restore-capacity-runtime.sh").read_text(encoding="utf-8")

    assert host.count('FINAL_RESULT="${STATE_DIR}/pathlab-capacity-${RUN_ID}-final.json"') >= 2
    assert 'state.get("evidenceDigest")' in host
    assert 'state.get("decisionSignature")' in host
    assert "abort-reconcile.service" in host and "reconcile-abort.sh" in host
    assert "capacity-ack" in host and "controllerAcknowledged:true" in host
    assert "write_final_result" in unit and "FINAL_EVIDENCE" in unit
    assert host.count("windowStartEpoch,windowEndEpoch,phase,finalLimit,faultConsumed") >= 3
    assert '"capacity-ack run=${run_id} digest=${digest}"' in cleanup
    assert '.pathlab-release' in restore and '"${EXPECTED_SHA}"' in restore
    assert '.pathlab-runtime-safety.json' in restore
    assert 'stop api classroom' in restore
    assert '(.phase == "restored" and .finalLimit == 300)' in host


@pytest.mark.skipif(
    os.name == "nt" or BASH is None or shutil.which("setsid") is None,
    reason="POSIX process-group signals are required",
)
@pytest.mark.parametrize(
    ("interrupt", "restore_expected"),
    ((SIGUSR1, True), (signal.SIGTERM, True)),
)
def test_capacity_unit_waits_for_child_same_release_restoration(
    tmp_path: Path, interrupt: int, restore_expected: bool
) -> None:
    live = tmp_path / "live"
    deploy = live / "deploy" / "scripts"
    state = tmp_path / "run"
    deploy.mkdir(parents=True)
    state.mkdir()
    controller = state / "pathlab-capacity-run-1-controller"
    controller.mkdir()
    stable_dispatcher = tmp_path / "stable-dispatcher"
    (controller / "prior-dispatcher").write_text("prior", encoding="utf-8")
    (live / ".pathlab-release").write_text(SHA, encoding="utf-8")
    nonce_file = state / "pathlab-capacity-run-1-nonce"
    preflight = state / "preflight.json"
    signature_file = state / "preflight.json.sig"
    nonce_file.write_text(NONCE, encoding="utf-8")
    preflight.write_text("{}", encoding="utf-8")
    signature_file.write_text("c" * 64, encoding="utf-8")
    now = int(time.time())
    (state / "pathlab-capacity-run-1-control.json").write_text(
        json.dumps(
            {
                "runId": "run-1",
                "workflowSha": SHA,
                "planDigest": DIGEST,
                "deadlineEpoch": now + 30,
                "runtimeManifestDigest": "d" * 64,
                "restoreNotAfter": now + 60,
                "windowStartEpoch": now,
                "windowEndEpoch": now + 10_800,
                "phase": "armed",
                "finalLimit": None,
                "faultConsumed": False,
            }
        ),
        encoding="utf-8",
    )
    (deploy / "with-capacity-override.sh").write_text(
        """#!/usr/bin/env bash
set -Eeuo pipefail
printf started > "${PATHLAB_LIVE_DIR}/started"
restore() {
  printf '{"configurationRestored":true,"finalLimit":300,"servicesReady":true}\n' \
    > "${PATHLAB_CAPACITY_RESTORE_EVIDENCE}"
  printf stopped > "${PATHLAB_LIVE_DIR}/stopped"
  exit 143
}
trap restore TERM INT
while :; do sleep 1; done
""",
        encoding="utf-8",
    )
    (deploy / "capacity_control.py").write_text(
        """import os, pathlib, sys
log = pathlib.Path(os.environ['PATHLAB_LIVE_DIR'], 'control.log')
log.open('a').write(' '.join(sys.argv[1:]) + '\\n')
""",
        encoding="utf-8",
    )
    (deploy / "restore-capacity-runtime.sh").write_text(
        '#!/usr/bin/env bash\nprintf \'{"configurationRestored":true,"servicesReady":true}\'\n'
        'printf restored > "${PATHLAB_LIVE_DIR}/restored"\n',
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATHLAB_LIVE_DIR": str(live),
            "PATHLAB_CAPACITY_RUNTIME_DIR": str(state),
            "PATHLAB_CAPACITY_TEST_MODE": "true",
            "PATHLAB_CAPACITY_STABLE_DISPATCHER": str(stable_dispatcher),
        }
    )
    process = subprocess.Popen(
        [
            str(BASH),
            "deploy/scripts/capacity-control-unit.sh",
            "run-1",
            SHA,
            DIGEST,
            str(nonce_file),
            str(preflight),
            str(signature_file),
            "d" * 64,
            str(now + 60),
            str(controller),
        ],
        env=env,
    )
    try:
        for _ in range(100):
            if (live / "started").exists():
                break
            time.sleep(0.05)
        assert (live / "started").exists()
        os.kill(process.pid, interrupt)
        assert process.wait(timeout=10) == 143
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    assert (live / "stopped").read_text(encoding="utf-8") == "stopped"
    assert (live / "restored").exists() is restore_expected
    control_log = (live / "control.log").read_text(encoding="utf-8")
    assert "finish --run-id run-1 --restoration-verified" in control_log


@pytest.mark.skipif(BASH is None, reason="bash is unavailable")
def test_host_rejects_expired_arm_before_reading_or_mutating_live_release() -> None:
    request = (
        f"capacity-arm {'a' * 40} run=run-1 digest={'b' * 64} "
        f"manifest={'d' * 64} arm-not-after=1000000000 window-start=1000000000 "
        "window-end=1000010800 deadline=2000000000 "
        "restore-not-after=2000000300 fault-start=1900000000 "
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
