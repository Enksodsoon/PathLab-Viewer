"""Isolated executable deployment rejection tests; no runtime or network actions."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SOURCE = ROOT / "deploy/scripts/deploy-release.sh"
BASH = str(Path("C:/Program Files/Git/bin/bash.exe")) if os.name == "nt" else shutil.which("bash")


def quote(value):
    return shlex.quote(str(value).replace("\\", "/"))


def fixture(tmp_path):
    state = tmp_path / "run"
    state.mkdir()
    trace = tmp_path / "trace"
    script = tmp_path / "deploy.sh"
    source = SOURCE.read_text(encoding="utf-8")
    source = source.replace(
        '[[ "${EUID}" -eq 0 ]] || fail "this script must run as root"', ": # isolated test"
    )
    source = source.replace("/run/", state.as_posix() + "/")
    source = source.replace(
        "/var/lock/pathlab-viewer-deploy.lock", (state / "deploy.lock").as_posix()
    )
    helpers = f"""
flock() {{
 printf 'lock %s\\n' "$*" >> {quote(trace)}
 [[ "${{LOCK_BUSY:-}}" != "${{@: -1}}" ]] || return 1
 if [[ -n "${{REAL_FLOCK:-}}" ]]; then "${{REAL_FLOCK}}" "$@"; fi
}}
python3() {{
 if [[ "$2" == {quote(state / "pathlab-capacity-controller.lock")} ]]; then
  if [[ "${{REAL_METADATA:-false}}" == true ]]; then {quote(sys.executable)} "$@";
  else cat >/dev/null; [[ "${{LOCK_INVALID:-false}}" != true ]]; fi
 else {quote(sys.executable)} "$@"; fi
}}
timeout() {{ shift 3; "$@"; }}
systemctl() {{
 printf '%s\\n' "$1" >> {quote(trace)}
 [[ "${{SYSTEMCTL_FAIL:-}}" != "$1" ]] || return 1
 if [[ "$1" == list-units ]]; then printf '%s' "${{UNITS:-}}";
 else printf '%s' "${{JOBS:-}}"; fi
}}
mktemp() {{ printf 'STAGING\\n' >> {quote(trace)}; return 1; }}
git() {{ printf 'FORBIDDEN_GIT\\n' >> {quote(trace)}; return 1; }}
docker() {{ printf 'FORBIDDEN_COMPOSE\\n' >> {quote(trace)}; return 1; }}
mv() {{ printf 'FORBIDDEN_SWAP\\n' >> {quote(trace)}; return 1; }}
"""
    source = source.replace(
        '[[ "${REQUEST}" =~ ^deploy', helpers + '\n[[ "${REQUEST}" =~ ^deploy', 1
    )
    script.write_text(source, encoding="utf-8", newline="\n")
    return state, trace, script


def execute(script, **env):
    request = f"deploy {'a' * 40} evidence=e30 signature={'b' * 64} nonce=nonce-123456"
    return subprocess.run(
        [BASH, str(script), request],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, **env},
    )


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("entry", ["pathlab-capacity-controller", "pathlab-capacity-active.json"])
@pytest.mark.parametrize("kind", ["file", "directory"])
def test_any_capacity_binding_blocks_before_clone_compose_or_staging(tmp_path, entry, kind):
    state, trace, script = fixture(tmp_path)
    target = state / entry
    if kind == "file":
        target.write_text("even malformed or retired")
    else:
        target.mkdir()
    result = execute(script)
    assert result.returncode != 0
    assert "requires explicit" in result.stderr
    assert trace.read_text().splitlines() == ["lock -n 9", "lock --exclusive --nonblock 8"]
    assert target.exists()


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize(
    "units",
    [
        "pathlab-capacity-run.service loaded active running description",
        "pathlab-capacity-run.timer loaded active waiting description",
        "pathlab-capacity-run.service loaded activating start description",
        "pathlab-capacity-run.service loaded deactivating stop description",
        "pathlab-capacity-run.service error inactive dead description",
        "unexpected inventory",
    ],
)
def test_running_transitional_or_ambiguous_units_block_all_staging(tmp_path, units):
    _, trace, script = fixture(tmp_path)
    result = execute(script, UNITS=units)
    assert result.returncode != 0
    assert "inactivity is unproved" in result.stderr
    assert "STAGING" not in trace.read_text()
    assert "FORBIDDEN" not in trace.read_text()


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("failure", ["list-units", "list-jobs"])
def test_unavailable_inventory_blocks_deployment(tmp_path, failure):
    _, trace, script = fixture(tmp_path)
    result = execute(script, SYSTEMCTL_FAIL=failure)
    assert result.returncode != 0
    assert "inventory is unavailable" in result.stderr
    assert "STAGING" not in trace.read_text()


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("jobs", ["42 pathlab-capacity-run.service start waiting", "unparseable"])
def test_pending_capacity_or_unknown_jobs_block_deployment(tmp_path, jobs):
    _, trace, script = fixture(tmp_path)
    result = execute(script, JOBS=jobs)
    assert result.returncode != 0
    assert "inactivity is unproved" in result.stderr
    assert "STAGING" not in trace.read_text()


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("descriptor", ["9", "8"])
def test_lock_contention_is_nonblocking_and_precedes_inventory(tmp_path, descriptor):
    _, trace, script = fixture(tmp_path)
    result = execute(script, LOCK_BUSY=descriptor)
    assert result.returncode != 0
    assert "list-units" not in trace.read_text()
    assert "STAGING" not in trace.read_text()


@pytest.mark.skipif(not BASH, reason="bash unavailable")
def test_proved_inactive_units_and_unrelated_jobs_allow_next_deploy_step(tmp_path):
    _, trace, script = fixture(tmp_path)
    result = execute(
        script,
        UNITS="pathlab-capacity-old.service loaded inactive dead retired",
        JOBS="3 unrelated.service start running",
    )
    assert result.returncode != 0  # The isolated staging spy deliberately stops here.
    assert trace.read_text().splitlines() == [
        "lock -n 9",
        "lock --exclusive --nonblock 8",
        "list-units",
        "list-jobs",
        "STAGING",
    ]


@pytest.mark.skipif(os.name == "nt", reason="requires Linux descriptor metadata")
def test_real_metadata_rejects_writable_capacity_lock(tmp_path):
    state, trace, script = fixture(tmp_path)
    lock = state / "pathlab-capacity-controller.lock"
    lock.touch()
    lock.chmod(0o666)
    result = execute(script, REAL_METADATA="true")
    assert result.returncode != 0
    assert "lock ownership is invalid" in result.stderr
    assert trace.read_text().splitlines() == ["lock -n 9"]


def test_deploy_guard_is_after_dispatch_and_held_through_rollback():
    source = SOURCE.read_text(encoding="utf-8")
    call = source.index("\nexclude_capacity_for_deployment\n")
    assert source.index('if [[ "${REQUEST}" == capacity-recover') < call
    assert call < source.index('DEPLOY_EVIDENCE="$(mktemp')
    assert call < source.index('REMOTE_MAIN_SHA="$(git ls-remote')
    assert "flock --exclusive --nonblock 8" in source
    assert "exec 8>&-" not in source
    assert "flock -u" not in source


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("jobs", ["", "No jobs running."])
def test_both_explicit_empty_job_inventory_forms_allow_staging(tmp_path, jobs):
    _, trace, script = fixture(tmp_path)
    result = execute(script, JOBS=jobs)
    assert result.returncode != 0
    assert trace.read_text().splitlines()[-1] == "STAGING"


@pytest.mark.skipif(not BASH, reason="bash unavailable")
def test_untrusted_lock_metadata_blocks_before_inventory(tmp_path):
    _, trace, script = fixture(tmp_path)
    result = execute(script, LOCK_INVALID="true")
    assert result.returncode != 0
    assert "lock ownership is invalid" in result.stderr
    assert trace.read_text().splitlines() == ["lock -n 9"]


@pytest.mark.skipif(os.name == "nt" or not shutil.which("flock"), reason="requires Linux flock")
@pytest.mark.parametrize("lock_name", ["deploy.lock", "pathlab-capacity-controller.lock"])
def test_real_competing_lock_blocks_without_waiting_or_staging(tmp_path, lock_name):
    import fcntl

    state, trace, script = fixture(tmp_path)
    with (state / lock_name).open("w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = execute(script, REAL_FLOCK=shutil.which("flock"))
        assert result.returncode != 0
        assert "list-units" not in trace.read_text()
        assert "STAGING" not in trace.read_text()


@pytest.mark.skipif(not BASH, reason="bash unavailable")
@pytest.mark.parametrize("entry", ["pathlab-capacity-controller", "pathlab-capacity-active.json"])
def test_dangling_binding_symlink_blocks_deployment(tmp_path, entry):
    state, trace, script = fixture(tmp_path)
    try:
        (state / entry).symlink_to(state / "missing")
    except OSError:
        pytest.skip("symlink creation unavailable")
    result = execute(script)
    assert result.returncode != 0
    assert "requires explicit" in result.stderr
    assert "STAGING" not in trace.read_text()
