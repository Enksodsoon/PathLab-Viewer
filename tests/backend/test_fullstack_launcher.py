import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from scripts.run_fullstack_tests import (
    ManagedProcess,
    ProcessManager,
    WindowsJob,
    isolated_environment,
    reserve_ports,
)


def test_fullstack_discards_inherited_production_configuration(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("PATHLAB_DATABASE_URL", "postgresql://production.invalid/private")
    monkeypatch.setenv("PATHLAB_SECURE_COOKIES", "true")
    monkeypatch.setenv("PATHLAB_IDENTITY_GOVERNANCE_ENABLED", "true")
    monkeypatch.setenv("LOAD_TEST_ADMIN_PASSWORD", "must-not-travel")
    monkeypatch.setenv("CAPACITY_BASE_URL", "https://production.invalid")
    env = isolated_environment(tmp_path)
    assert env["PATHLAB_DATABASE_URL"] == f"sqlite:///{(tmp_path / 'database.sqlite3').as_posix()}"
    assert env["PATHLAB_ENVIRONMENT"] == "test"
    assert env["PATHLAB_SECURE_COOKIES"] == "false"
    assert "PATHLAB_IDENTITY_GOVERNANCE_ENABLED" not in env
    assert "LOAD_TEST_ADMIN_PASSWORD" not in env
    assert "CAPACITY_BASE_URL" not in env
    assert isolated_environment(tmp_path)["PATHLAB_SECRET_KEY"] != env["PATHLAB_SECRET_KEY"]


def test_fullstack_selects_distinct_loopback_ports() -> None:
    ports = reserve_ports(4)
    assert len(set(ports)) == 4
    assert all(1024 <= port <= 65535 for port in ports)


def _wait_for_pid(marker: Path) -> int:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if marker.exists() and marker.read_text():
            return int(marker.read_text())
        time.sleep(0.02)
    raise AssertionError("Owned helper did not report readiness")


def _alive(pid: int) -> bool:
    if os.name == "nt":
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x100000, False, pid)
        if not handle:
            return False
        try:
            return kernel.WaitForSingleObject(handle, 0) == 258
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def _tree_command(
    marker: Path, *, wait_parent: bool = False, ignore_term: bool = False
) -> list[str]:
    child = (
        "import os, pathlib, signal, sys, time; "
        + ("signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_term else "")
        + "pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(60)"
    )
    # The actual command exits while its child remains; the manager's wrapper
    # then exits too. Its child must remain owned by the job/process group.
    parent = (
        "import json, subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', sys.argv[1], sys.argv[2]]); "
        + ("time.sleep(60)" if wait_parent else "")
    )
    return [sys.executable, "-c", parent, child, str(marker)]


def test_cleanup_owns_child_after_wrapper_exit_and_removes_temporary_directory(tmp_path):
    with tempfile.TemporaryDirectory(dir=tmp_path) as temporary:
        directory = Path(temporary)
        marker = directory / "child.pid"
        manager = ProcessManager(directory, isolated_environment(directory))
        try:
            owned = manager.start("service", _tree_command(marker))
            assert owned.wait(10) == 0
            child_pid = _wait_for_pid(marker)
            assert _alive(child_pid)
            if owned.job is not None:
                # Windows venv executables may add a redirector process as well.
                assert owned.job.active_processes() >= 1
        finally:
            manager.close()
        assert not _alive(child_pid)
        assert all(log.closed for log in manager.logs.values())
    assert not directory.exists()


@pytest.mark.parametrize("name", ["build", "browser"])
def test_timed_out_command_terminates_actual_child_tree(tmp_path, name):
    marker = tmp_path / "child.pid"
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            manager.run(name, _tree_command(marker, wait_parent=True), timeout=3)
        child_pid = _wait_for_pid(marker)
        assert not _alive(child_pid)
        assert manager.processes[0].closed
    finally:
        manager.close()


@pytest.mark.parametrize("name", ["build", "browser"])
def test_cancelled_command_terminates_actual_child_tree(tmp_path, monkeypatch, name):
    marker = tmp_path / "child.pid"
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    child_pid = None

    def cancel_after_child_started(self, timeout):
        nonlocal child_pid
        child_pid = _wait_for_pid(marker)
        raise KeyboardInterrupt

    monkeypatch.setattr(ManagedProcess, "wait", cancel_after_child_started)
    try:
        with pytest.raises(KeyboardInterrupt):
            manager.run(name, _tree_command(marker, wait_parent=True), timeout=30)
        assert child_pid is not None and not _alive(child_pid)
    finally:
        manager.close()
    assert all(log.closed for log in manager.logs.values())


def test_cleanup_continues_after_one_stop_failure_and_closes_all_logs(tmp_path, monkeypatch):
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    one = manager.start("one", _tree_command(tmp_path / "one.pid", wait_parent=True))
    two = manager.start("two", _tree_command(tmp_path / "two.pid", wait_parent=True))
    one_pid = _wait_for_pid(tmp_path / "one.pid")
    two_pid = _wait_for_pid(tmp_path / "two.pid")
    original_stop = two.stop

    def stop_then_report_failure():
        original_stop()
        raise OSError("Injected cleanup reporting failure")

    monkeypatch.setattr(two, "stop", stop_then_report_failure)
    with pytest.raises(RuntimeError, match="cleanup failed: two: OSError"):
        manager.close()
    assert not _alive(one_pid) and not _alive(two_pid)
    assert one.closed
    assert all(log.closed for log in manager.logs.values())


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object barrier")
def test_windows_job_assignment_precedes_command_release(tmp_path, monkeypatch):
    marker = tmp_path / "command-started"
    original_assign = WindowsJob.assign
    checked = False

    def inspect_barrier(self, process):
        nonlocal checked
        time.sleep(0.15)
        assert not marker.exists()
        original_assign(self, process)
        assert self.active_processes() == 1
        checked = True

    monkeypatch.setattr(WindowsJob, "assign", inspect_barrier)
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    try:
        manager.run(
            "barrier",
            [
                sys.executable,
                "-c",
                "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('started')",
                str(marker),
            ],
            timeout=10,
        )
        assert checked and marker.read_text() == "started"
    finally:
        manager.close()


@pytest.mark.skipif(os.name != "nt", reason="Windows Job Object assignment failure")
def test_failed_windows_job_assignment_never_runs_command(tmp_path, monkeypatch):
    marker = tmp_path / "must-not-exist"

    def reject_assignment(self, process):
        raise OSError("Injected job assignment failure")

    monkeypatch.setattr(WindowsJob, "assign", reject_assignment)
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    try:
        with pytest.raises(OSError, match="assignment failure"):
            manager.start(
                "blocked",
                [
                    sys.executable,
                    "-c",
                    "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()",
                    str(marker),
                ],
            )
    finally:
        manager.close()
    assert not marker.exists()


@pytest.mark.skipif(os.name == "nt", reason="POSIX process group escalation")
def test_posix_cleanup_kills_term_resistant_child_after_leader_exit(tmp_path):
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    marker = tmp_path / "child.pid"
    try:
        owned = manager.start("resistant", _tree_command(marker, ignore_term=True))
        assert owned.wait(10) == 0
        child_pid = _wait_for_pid(marker)
    finally:
        manager.close()
    assert not _alive(child_pid)


def test_tracked_command_stdin_and_failure_logs_keep_credentials_redacted(tmp_path, capsys):
    env = isolated_environment(tmp_path)
    manager = ProcessManager(tmp_path, env)
    try:
        manager.run(
            "fixture",
            [
                sys.executable,
                "-c",
                "import os,sys; print(os.environ['PATHLAB_SECRET_KEY']); print(sys.stdin.read())",
            ],
            timeout=10,
            input_text=env["PATHLAB_E2E_PASSWORD"],
        )
        manager.dump_logs()
        output = capsys.readouterr().err
        assert env["PATHLAB_SECRET_KEY"] not in output
        assert env["PATHLAB_E2E_PASSWORD"] not in output
        assert output.count("[redacted]") == 2
    finally:
        manager.close()
