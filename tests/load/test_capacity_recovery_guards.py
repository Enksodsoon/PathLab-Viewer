"""Execute controller recovery against isolated files and mutation spies only."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
HOST = ROOT / "deploy/scripts/capacity-control-host.sh"
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")
SHA = "a" * 40
DIGEST = "b" * 64


def shell(value: Path | str) -> str:
    return shlex.quote(value.as_posix() if isinstance(value, Path) else value)


def fixture(tmp_path: Path):
    state = tmp_path / "run"
    live = tmp_path / "live"
    state.mkdir()
    (live / "deploy/scripts").mkdir(parents=True)
    (live / ".pathlab-release").write_text(SHA)
    (live / ".pathlab-runtime-safety.json").write_text(json.dumps({"manifestDigest": DIGEST}))
    controller = state / "pathlab-capacity-run-1-controller"
    controller.mkdir()
    (controller / "capacity-control-host.sh").write_text("preserve until validated")
    control = state / "pathlab-capacity-run-1-control.json"
    control.write_text(json.dumps({"runId": "run-1", "workflowSha": SHA, "phase": "armed"}))
    (state / "pathlab-capacity-controller").write_text(controller.as_posix() + "\n")
    (state / "pathlab-capacity-active.json").write_text(json.dumps({"runId": "run-1"}))
    trace = tmp_path / "trace"
    # Called synchronously by recover while its lock is held. It must not
    # acquire that lock again or recovery would wait on its own child.
    (live / "deploy/scripts/restore-capacity-runtime.sh").write_text(
        f"printf 'restore\\n' >> {shell(trace)}\nprintf '{{\"ready\":true}}\\n'\n"
    )
    source = HOST.read_text(encoding="utf-8")
    source = source.replace('LIVE_DIR="/opt/pathlab-viewer"', f"LIVE_DIR={shell(live)}")
    source = source.replace('STATE_DIR="/run"', f"STATE_DIR={shell(state)}")
    helpers = f"""
python3() {{ {shell(Path(sys.executable))} "$@"; }}
flock() {{
  printf 'lock\\n' >> {shell(trace)}
  [[ "${{LOCK_BUSY:-false}}" != true ]] || return 1
  if [[ -n "${{REAL_FLOCK:-}}" ]]; then "${{REAL_FLOCK}}" "$@"; fi
}}
systemctl() {{
  if [[ "$1" == show ]]; then
    if [[ "$*" == *LoadState* ]]; then printf 'loaded\\n';
    elif [[ "${{STOP_STILL_ACTIVE:-false}}" == true ]]; then printf 'active\\n';
    else printf 'inactive\\n'; fi
    return 0
  fi
  printf 'systemctl\\n' >> {shell(trace)}
  [[ "${{STOP_FAIL:-false}}" != true ]] || return 1
  # Simulate a detached unit's synchronous stop handler completing recovery.
  bash {shell(live / "deploy/scripts/restore-capacity-runtime.sh")} >/dev/null
}}
timeout() {{ shift 3; "$@"; }}
jq() {{
  if [[ "$*" == *manifestDigest* ]]; then printf '{DIGEST}\\n'; else cat; fi
}}
"""
    source = source.replace(
        'fail() { echo "Capacity control failed: $*" >&2; exit 1; }',
        'fail() { echo "Capacity control failed: $*" >&2; exit 1; }' + helpers,
    )
    script = tmp_path / "controller.sh"
    script.write_text(source, encoding="utf-8", newline="\n")
    return state, controller, control, trace, script


def execute(script: Path, *, request: str | None = None, env: dict[str, str] | None = None):
    assert BASH
    return subprocess.run(
        [BASH, str(script), request or f"capacity-recover run=run-1 sha={SHA}"],
        capture_output=True,
        text=True,
        timeout=12,
        env={**os.environ, **(env or {})},
    )


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
@pytest.mark.parametrize(
    "damage",
    [
        "foreign-pointer",
        "foreign-active",
        "wrong-sha",
        "wrong-run",
        "missing-state",
        "malformed-active",
        "malformed-pointer",
    ],
)
def test_unproved_recovery_ownership_causes_zero_mutations(tmp_path, damage):
    state, controller, control, trace, script = fixture(tmp_path)
    if damage == "foreign-pointer":
        (state / "pathlab-capacity-controller").write_text(
            (state / "pathlab-capacity-other-controller").as_posix()
        )
    elif damage == "foreign-active":
        (state / "pathlab-capacity-active.json").write_text('{"runId":"other"}')
    elif damage == "wrong-sha":
        control.write_text(json.dumps({"runId": "run-1", "workflowSha": "c" * 40}))
    elif damage == "wrong-run":
        control.write_text(json.dumps({"runId": "other", "workflowSha": SHA}))
    elif damage == "missing-state":
        control.unlink()
    elif damage == "malformed-active":
        (state / "pathlab-capacity-active.json").write_text("null")
    else:
        (state / "pathlab-capacity-controller").write_text("/run/unrelated")
    original = {p.relative_to(state): p.read_bytes() for p in state.rglob("*") if p.is_file()}
    outcome = execute(script)
    assert outcome.returncode != 0
    assert "ownership" in outcome.stderr
    assert trace.read_text().splitlines() == ["lock"]
    assert controller.exists()
    assert {
        p.relative_to(state): p.read_bytes()
        for p in state.rglob("*")
        if p.is_file() and p.name != "pathlab-capacity-controller.lock"
    } == original


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_exact_run_recovery_stops_restores_and_releases_only_own_binding(tmp_path):
    state, controller, control, trace, script = fixture(tmp_path)
    other = state / "pathlab-capacity-other-controller"
    other.mkdir()
    (other / "preserved").write_text("other run")
    result = execute(script)
    assert result.returncode == 0, result.stderr
    assert trace.read_text().splitlines() == ["lock", "systemctl", "restore", "restore"]
    assert not controller.exists()
    assert not (state / "pathlab-capacity-controller").exists()
    assert not (state / "pathlab-capacity-active.json").exists()
    assert (other / "preserved").read_text() == "other run"
    assert json.loads(control.read_text())["phase"] == "aborted-restored"


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_busy_mutex_blocks_before_recovery_or_arm_changes(tmp_path):
    _, controller, _, trace, script = fixture(tmp_path)
    result = execute(script, env={"LOCK_BUSY": "true"})
    assert result.returncode != 0
    assert "mutation is in progress" in result.stderr
    assert trace.read_text().splitlines() == ["lock"]
    assert controller.exists()


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_arm_preserves_preexisting_retired_pointer_before_any_install(tmp_path):
    state, controller, _, trace, script = fixture(tmp_path)
    (state / "pathlab-capacity-active.json").unlink()
    request = (
        f"capacity-arm {SHA} run=run-2 digest={DIGEST} manifest={DIGEST} "
        "arm-not-after=1800000000 window-start=1800000000 window-end=1800010800 "
        "deadline=1800009900 restore-not-after=1800010200 "
        f"fault-start=1800009800 fault-end=1800009890 evidence=e30 signature={DIGEST} "
        "nonce=nonce-123456"
    )
    result = execute(script, request=request)
    assert result.returncode != 0
    assert "requires retirement before arm" in result.stderr
    assert controller.exists()
    assert (state / "pathlab-capacity-controller").read_text().strip() == controller.as_posix()
    assert trace.read_text().splitlines() == ["lock"]


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
@pytest.mark.parametrize("damage", ["STOP_FAIL", "STOP_STILL_ACTIVE"])
def test_recovery_never_restores_or_deletes_binding_after_unproved_stop(tmp_path, damage):
    state, controller, control, trace, script = fixture(tmp_path)
    before = control.read_bytes()
    result = execute(script, env={damage: "true"})
    assert result.returncode != 0
    assert controller.exists()
    assert control.read_bytes() == before
    assert (state / "pathlab-capacity-controller").exists()
    assert (state / "pathlab-capacity-active.json").exists()
    # A successful stop may invoke its own restoration; the caller must not
    # continue with its separate restore or metadata deletion after this gate.
    expected = ["lock", "systemctl"] if damage == "STOP_FAIL" else ["lock", "systemctl", "restore"]
    assert trace.read_text().splitlines() == expected


@pytest.mark.skipif(os.name == "nt" or not shutil.which("flock"), reason="requires Linux flock")
def test_recovery_mutex_serializes_other_process_and_does_not_deadlock_stop(tmp_path):
    import fcntl

    state, controller, _, trace, script = fixture(tmp_path)
    lock = state / "pathlab-capacity-controller.lock"
    with lock.open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        denied = execute(script, env={"REAL_FLOCK": shutil.which("flock") or ""})
        assert denied.returncode != 0
        assert trace.read_text().splitlines() == ["lock"]
        assert controller.exists()
    trace.unlink()
    allowed = execute(script, env={"REAL_FLOCK": shutil.which("flock") or ""})
    assert allowed.returncode == 0, allowed.stderr
    assert trace.read_text().splitlines() == ["lock", "systemctl", "restore", "restore"]


def test_lock_writer_scope_preserves_stop_handler_and_retirement_ownership():
    source = HOST.read_text()
    arm = source.split('  EVIDENCE_B64="${BASH_REMATCH[12]}"', 1)[1]
    assert arm.index("lock_controller_mutation") < arm.index("runtime_status")
    retirement = source.split('cat > "${restore_script}" <<EOF', 1)[1].split("\nEOF", 1)[0]
    assert retirement.index("flock --exclusive --timeout") < retirement.index("pointer")
    assert retirement.index(".runId == \\$run") < retirement.index('temporary="')
    assert retirement.index('== "${CONTROLLER_DIR}"') < retirement.index('temporary="')
    # The unit stop handler must be able to complete while recover owns the lock.
    for name in ("capacity-control-unit.sh", "restore-capacity-runtime.sh"):
        assert "lock_controller_mutation" not in (ROOT / "deploy/scripts" / name).read_text()


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_failed_arm_before_pointer_publication_preserves_previous_run_pointer(tmp_path):
    source = HOST.read_text()
    body = source.split("  arm_failed() {", 1)[1].split("\n  }\n", 1)[0]
    controller = tmp_path / "new-controller"
    controller.mkdir()
    (controller / "prior-dispatcher").write_text("prior")
    pointer = tmp_path / "pointer"
    pointer.write_text("previous-run-controller")
    trace = tmp_path / "mutations"
    script = tmp_path / "failed-arm.sh"
    script.write_text(
        f"""#!/usr/bin/env bash
set -u
CONTROLLER_STARTED=false
CONTROLLER_LAUNCH_ATTEMPTED=false
CONTROLLER_INSTALLED=true
CONTROLLER_POINTER_INSTALLED=false
ARMED=false
RUN_ID=run-1
CONTROLLER_DIR={shell(controller)}
CONTROLLER_POINTER={shell(pointer)}
STABLE_DISPATCHER=unused-dispatcher
PREFLIGHT=unused-preflight
PREFLIGHT_SIG=unused-signature
NONCE_FILE=unused-nonce
READY_FILE=unused-ready
systemctl() {{ :; }}
atomic_install() {{ printf 'dispatcher-replaced\\n' >> {shell(trace)}; }}
rm() {{ printf '%s\\n' "$*" >> {shell(trace)}; }}
arm_failed() {{{body}
}}
(exit 8)
arm_failed
""",
        encoding="utf-8",
        newline="\n",
    )
    result = execute(script)
    assert result.returncode == 8
    assert pointer.read_text() == "previous-run-controller"
    assert "dispatcher-replaced" not in trace.read_text()
    assert pointer.as_posix() not in trace.read_text()


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
@pytest.mark.parametrize(
    "stop_ok,unit_state,runtime_ok,proved",
    [
        (True, "inactive", True, True),
        (False, "inactive", True, False),
        (True, "active", True, False),
        (True, "inactive", False, False),
        (True, "unknown", True, False),
        (True, "query-failed", True, False),
    ],
)
def test_failed_arm_never_verifies_restoration_without_stopped_unit_and_runtime_proof(
    tmp_path, stop_ok, unit_state, runtime_ok, proved
):
    source = HOST.read_text()
    body = source.split("  arm_failed() {", 1)[1].split("\n  }\n", 1)[0]
    trace = tmp_path / "finish-arguments"
    script = tmp_path / "arm-failure.sh"
    script.write_text(
        f"""#!/usr/bin/env bash
set -u
CONTROLLER_STARTED=false
CONTROLLER_LAUNCH_ATTEMPTED=true
CONTROLLER_INSTALLED=true
CONTROLLER_POINTER_INSTALLED=true
CONTROLLER_DIR=/nonexistent-owned-controller
CONTROLLER_POINTER=/nonexistent-owned-pointer
ARMED=true
UNIT=test-unit
RUN_ID=run-1
SHA={SHA}
MANIFEST_DIGEST={DIGEST}
LIVE_DIR=/unused
PREFLIGHT=/nonexistent-test-preflight
PREFLIGHT_SIG=/nonexistent-test-signature
NONCE_FILE=/nonexistent-test-nonce
READY_FILE=/nonexistent-test-ready
timeout() {{ shift 3; "$@"; }}
systemctl() {{
  if [[ "$1" == stop ]]; then return {0 if stop_ok else 1}; fi
  printf '{unit_state}\\n'
  return {1 if unit_state == "query-failed" else 0}
}}
runtime_status() {{ [[ "$1" == {SHA} && "$2" == {DIGEST} ]] && return {0 if runtime_ok else 1}; }}
python3() {{ printf '%s\\n' "$*" >> {shell(trace)}; }}
rm() {{ printf 'DELETE %s\\n' "$*" >> {shell(trace)}; }}
arm_failed() {{{body}
}}
(exit 7)
arm_failed
""",
        encoding="utf-8",
        newline="\n",
    )
    result = execute(script)
    assert result.returncode == 7
    assert ("--restoration-verified" in trace.read_text()) is proved
    if not proved:
        assert "DELETE" not in trace.read_text()


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
@pytest.mark.parametrize("damage", ["pointer", "active"])
@pytest.mark.parametrize("command", ["abort", "fault", "finalize", "terminate-controller", "ack"])
def test_all_mutating_run_requests_reject_foreign_owner_before_side_effects(
    tmp_path, damage, command
):
    state, controller, control, trace, script = fixture(tmp_path)
    if damage == "pointer":
        (state / "pathlab-capacity-controller").write_text("/run/pathlab-capacity-other-controller")
    else:
        (state / "pathlab-capacity-active.json").write_text('{"runId":"other"}')
    request = f"capacity-{command} run=run-1 digest={DIGEST}"
    if command == "finalize":
        request = (
            f"capacity-finalize {SHA} run=run-1 digest={DIGEST} evidence=e30 "
            f"signature={DIGEST} nonce=nonce-123456"
        )
    before = control.read_bytes()
    result = execute(script, request=request)
    assert result.returncode != 0
    assert "ownership" in result.stderr
    assert trace.read_text().splitlines() == ["lock"]
    assert controller.exists()
    assert control.read_bytes() == before


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_inherited_dispatcher_lock_rejects_invalid_descriptor_before_mutation(tmp_path):
    _, controller, _, trace, script = fixture(tmp_path)
    result = execute(script, env={"PATHLAB_CAPACITY_DISPATCH_LOCK_FD": "7"})
    assert result.returncode != 0
    assert "dispatcher lock is invalid" in result.stderr
    assert not trace.exists()
    assert controller.exists()
