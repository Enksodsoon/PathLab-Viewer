"""Behavioral guards for release-bound capacity restoration containment."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[2]
RESTORE = ROOT / "deploy/scripts/restore-capacity-runtime.sh"
GIT_BASH = Path("C:/Program Files/Git/bin/bash.exe")
BASH = str(GIT_BASH) if GIT_BASH.exists() else shutil.which("bash")
SHA = "a" * 40
OTHER_SHA = "c" * 40


def signed_manifest(release_sha: str = SHA) -> tuple[dict[str, Any], str]:
    value: dict[str, Any] = {
        "schemaVersion": 1,
        "releaseSha": release_sha,
        "schemaRevision": "20260905_0025",
        "databaseEngine": "sqlite",
        "services": ["api", "caddy", "classroom", "tile-service", "tusd", "worker"],
        "composeConfigDigest": "d" * 64,
        "classroomEnabled": True,
        "safeCapacity": 300,
        "annotationsEnabled": False,
        "watchdogExpected": True,
        "createdAt": "2026-09-05T00:00:00+00:00",
    }
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    value["manifestDigest"] = digest
    return value, digest


MANIFEST, DIGEST = signed_manifest()


def shell(value: Path | str) -> str:
    return shlex.quote(value.as_posix() if isinstance(value, Path) else value)


def write_verifier(live: Path, behavior: str) -> None:
    validator = live / "deploy/scripts/runtime_safety_validator.py"
    shutil.copyfile(ROOT / "deploy/scripts/runtime_safety_manifest.py", validator)
    wrapper = live / "deploy/scripts/runtime_safety_manifest.py"
    wrapper.write_text(
        "import importlib.util\n"
        "import pathlib\n"
        "_validator = pathlib.Path(__file__).with_name('runtime_safety_validator.py')\n"
        "_spec = importlib.util.spec_from_file_location('fixture_validator', _validator)\n"
        "assert _spec is not None and _spec.loader is not None\n"
        "_module = importlib.util.module_from_spec(_spec)\n"
        "_spec.loader.exec_module(_module)\n"
        "load_manifest = _module.load_manifest\n"
        "if __name__ == '__main__':\n"
        f"{textwrap.indent(behavior, '    ')}\n",
        encoding="utf-8",
    )


def fixture(tmp_path: Path) -> tuple[Path, Path, Path, Path, Path]:
    live = tmp_path / "live"
    scripts = live / "deploy/scripts"
    scripts.mkdir(parents=True)
    (live / "deploy/.env").write_text(
        "PATHLAB_PRODUCTION_CLASSROOM_ENABLED=true\n"
        "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=2000\n"
        "PATHLAB_ANNOTATIONS_ENABLED=true\n",
        encoding="utf-8",
    )
    (live / ".pathlab-release").write_text(SHA + "\n", encoding="utf-8", newline="\n")
    manifest_path = live / ".pathlab-runtime-safety.json"
    manifest_path.write_text(json.dumps(MANIFEST) + "\n", encoding="utf-8")
    manifest_path.chmod(0o600)
    compose_trace = tmp_path / "compose.trace"
    (scripts / "compose-pathlab.sh").write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {shell(compose_trace)}\n",
        encoding="utf-8",
        newline="\n",
    )
    (scripts / "install-watchdog.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8", newline="\n"
    )
    write_verifier(
        live,
        "import sys\nprint('bounded verifier cause', file=sys.stderr)\nraise SystemExit(1)",
    )
    source = RESTORE.read_text(encoding="utf-8").replace("python3", shell(Path(sys.executable)))
    for production, reduced in {
        "COMMAND_KILL_SECONDS=5": "COMMAND_KILL_SECONDS=1",
        "CONTAINMENT_RESERVE_SECONDS=20": "CONTAINMENT_RESERVE_SECONDS=9",
        "CONTAINMENT_PROBE_SECONDS=5": "CONTAINMENT_PROBE_SECONDS=3",
        "CONTAINMENT_STOP_SECONDS=10": "CONTAINMENT_STOP_SECONDS=2",
        "CONTAINMENT_STOP_KILL_SECONDS=2": "CONTAINMENT_STOP_KILL_SECONDS=1",
        "CONTAINMENT_SLACK_SECONDS=2": "CONTAINMENT_SLACK_SECONDS=2",
    }.items():
        source = source.replace(production, reduced)
    if os.name != "posix":
        source = source.replace(
            "set -Eeuo pipefail", "set -Eeuo pipefail\nflock() { return 0; }", 1
        )
    script = tmp_path / "restore.sh"
    script.write_text(source, encoding="utf-8", newline="\n")
    return live, live / "deploy/.env", compose_trace, script, tmp_path / "deploy.lock"


def execute(
    live: Path,
    script: Path,
    lock_file: Path,
    *,
    expected_sha: str = SHA,
    manifest_digest: str = DIGEST,
    deadline_seconds: int = 15,
) -> subprocess.CompletedProcess[str]:
    assert BASH
    return subprocess.run(
        [
            BASH,
            str(script),
            expected_sha,
            manifest_digest,
            str(int(time.time()) + deadline_seconds),
        ],
        capture_output=True,
        text=True,
        timeout=deadline_seconds + 8,
        env={
            **os.environ,
            "PATHLAB_LIVE_DIR": live.as_posix(),
            "PATHLAB_DEPLOY_LOCK_FILE": lock_file.as_posix(),
            "PATHLAB_CAPACITY_TEST_MODE": "true",
        },
    )


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
@pytest.mark.parametrize(
    "damage",
    [
        "different-release",
        "embedded-release-newline",
        "missing-manifest",
        "malformed-manifest",
        "oversized-manifest",
        "wrong-schema",
        "invalid-manifest-fields",
        "wrong-manifest-release",
        "self-reported-digest",
    ],
)
def test_unowned_or_noncanonical_binding_fails_before_any_mutation(
    tmp_path: Path, damage: str
) -> None:
    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    before = env_file.read_bytes()
    manifest_digest = DIGEST
    manifest_path = live / ".pathlab-runtime-safety.json"
    if damage == "different-release":
        (live / ".pathlab-release").write_text(OTHER_SHA + "\n", encoding="utf-8", newline="\n")
    elif damage == "embedded-release-newline":
        (live / ".pathlab-release").write_text(SHA + "\nignored\n", encoding="utf-8", newline="\n")
    elif damage == "missing-manifest":
        manifest_path.unlink()
    elif damage == "malformed-manifest":
        manifest_path.write_text("{", encoding="utf-8")
    elif damage == "oversized-manifest":
        manifest_path.write_bytes(b"{" + b" " * 65536 + b"}")
    elif damage == "wrong-schema":
        value = dict(MANIFEST)
        value.pop("manifestDigest")
        value["schemaVersion"] = 2
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        manifest_digest = hashlib.sha256(canonical).hexdigest()
        value["manifestDigest"] = manifest_digest
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
    elif damage == "invalid-manifest-fields":
        value = dict(MANIFEST)
        value.pop("manifestDigest")
        value["services"] = ["api"]
        canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        manifest_digest = hashlib.sha256(canonical).hexdigest()
        value["manifestDigest"] = manifest_digest
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
    elif damage == "wrong-manifest-release":
        value, manifest_digest = signed_manifest(OTHER_SHA)
        manifest_path.write_text(json.dumps(value), encoding="utf-8")
    else:
        value = dict(MANIFEST)
        value["safeCapacity"] = 2000
        manifest_path.write_text(json.dumps(value), encoding="utf-8")

    result = execute(live, script, lock_file, manifest_digest=manifest_digest)

    assert result.returncode != 0
    assert env_file.read_bytes() == before
    assert not compose_trace.exists()
    assert "API and Classroom were stopped" not in result.stderr


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_manifest_symlink_fails_before_any_mutation(tmp_path: Path) -> None:
    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    before = env_file.read_bytes()
    manifest = live / ".pathlab-runtime-safety.json"
    target = live / "manifest-target.json"
    manifest.replace(target)
    try:
        manifest.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert env_file.read_bytes() == before
    assert not compose_trace.exists()


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_deployment_lock_symlink_fails_before_any_mutation(tmp_path: Path) -> None:
    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    before = env_file.read_bytes()
    target = tmp_path / "lock-target"
    target.touch()
    try:
        lock_file.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable")

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert "deployment lock is unavailable or unsafe" in result.stderr
    assert env_file.read_bytes() == before
    assert not compose_trace.exists()


@pytest.mark.skipif(BASH is None or os.name != "posix", reason="POSIX mode required")
def test_manifest_writable_mode_fails_before_any_mutation(tmp_path: Path) -> None:
    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    before = env_file.read_bytes()
    (live / ".pathlab-runtime-safety.json").chmod(0o666)

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert env_file.read_bytes() == before
    assert not compose_trace.exists()


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_failing_verifier_stdout_never_becomes_success(tmp_path: Path) -> None:
    live, _, compose_trace, script, lock_file = fixture(tmp_path)
    write_verifier(
        live,
        "print('FAILED_STDOUT')\nraise SystemExit(1)",
    )

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert "FAILED_STDOUT" not in result.stdout
    assert compose_trace.read_text(encoding="utf-8").splitlines()[-1] == ("stop api classroom")


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_owned_failure_is_contained_and_diagnostic_is_sanitized(tmp_path: Path) -> None:
    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    write_verifier(
        live,
        "import sys\n"
        "sys.stderr.buffer.write(b'\\x1b[31mbounded verifier cause\\r\\x00\\n')\n"
        "raise SystemExit(1)",
    )

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert compose_trace.read_text(encoding="utf-8").splitlines()[-1] == ("stop api classroom")
    restored = env_file.read_text(encoding="utf-8")
    assert "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300" in restored
    assert "PATHLAB_ANNOTATIONS_ENABLED=false" in restored
    assert "Last capacity runtime verification error:" in result.stderr
    assert "bounded verifier cause" in result.stderr
    assert "API and Classroom were stopped" in result.stderr
    assert all(character not in result.stderr for character in "\x1b\r\x00")
    assert len(result.stderr.encode()) < 4096


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_binding_change_after_mutation_does_not_stop_new_release(tmp_path: Path) -> None:
    live, _, compose_trace, script, lock_file = fixture(tmp_path)
    write_verifier(
        live,
        "import pathlib, sys\n"
        f"pathlib.Path({str(live / '.pathlab-release')!r}).write_bytes("
        f"({OTHER_SHA!r} + '\\n').encode())\n"
        "print('runtime selection changed', file=sys.stderr)\n"
        "raise SystemExit(1)",
    )

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    trace = compose_trace.read_text(encoding="utf-8").splitlines()
    assert "up -d" in trace
    assert "stop api classroom" not in trace
    assert "runtime binding changed before containment" in result.stderr


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_slow_verifier_leaves_time_for_containment(tmp_path: Path) -> None:
    live, _, compose_trace, script, lock_file = fixture(tmp_path)
    write_verifier(
        live,
        "import sys, time\ntime.sleep(30)\nprint('late failure', file=sys.stderr)\n"
        "raise SystemExit(1)",
    )

    result = execute(live, script, lock_file, deadline_seconds=15)

    assert result.returncode != 0
    assert compose_trace.read_text(encoding="utf-8").splitlines()[-1] == ("stop api classroom")
    assert "API and Classroom were stopped" in result.stderr


@pytest.mark.skipif(BASH is None, reason="bash unavailable")
def test_failed_containment_remains_nonzero_and_unproved(tmp_path: Path) -> None:
    live, _, compose_trace, script, lock_file = fixture(tmp_path)
    (live / "deploy/scripts/compose-pathlab.sh").write_text(
        f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" >> {shell(compose_trace)}\n"
        "[[ \"$*\" != 'stop api classroom' ]]\n",
        encoding="utf-8",
        newline="\n",
    )

    result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert "containment is unproved" in result.stderr


@pytest.mark.skipif(BASH is None or os.name != "posix", reason="POSIX flock semantics required")
def test_active_deployment_lock_fails_before_any_mutation(tmp_path: Path) -> None:
    import fcntl

    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    before = env_file.read_bytes()
    with lock_file.open("w") as held:
        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = execute(live, script, lock_file)

    assert result.returncode != 0
    assert "deployment or another restore is active" in result.stderr
    assert env_file.read_bytes() == before
    assert not compose_trace.exists()


@pytest.mark.skipif(BASH is None or os.name != "posix", reason="POSIX flock semantics required")
def test_competing_restore_fails_before_mutation(tmp_path: Path) -> None:
    live, env_file, compose_trace, script, lock_file = fixture(tmp_path)
    write_verifier(live, "import time\ntime.sleep(30)\nraise SystemExit(1)")
    command = [BASH, str(script), SHA, DIGEST, str(int(time.time()) + 15)]
    environment = {
        **os.environ,
        "PATHLAB_LIVE_DIR": live.as_posix(),
        "PATHLAB_DEPLOY_LOCK_FILE": lock_file.as_posix(),
        "PATHLAB_CAPACITY_TEST_MODE": "true",
    }
    first = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    try:
        for _ in range(40):
            if compose_trace.exists():
                break
            time.sleep(0.05)
        assert compose_trace.read_text(encoding="utf-8").splitlines() == ["up -d"]
        before_env = env_file.read_bytes()
        before_trace = compose_trace.read_bytes()

        second = execute(live, script, lock_file)

        assert second.returncode != 0
        assert "deployment or another restore is active" in second.stderr
        assert env_file.read_bytes() == before_env
        assert compose_trace.read_bytes() == before_trace
    finally:
        first_stdout, first_stderr = first.communicate(timeout=20)
    assert first.returncode != 0, (first_stdout, first_stderr)
