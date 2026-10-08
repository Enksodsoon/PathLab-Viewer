import ctypes
import json
import os
import subprocess
import sys
import tempfile
import time
from http.client import BadStatusLine
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from scripts.run_fullstack_tests import (
    ManagedProcess,
    ProcessManager,
    WindowsJob,
    isolated_environment,
    reserve_ports,
    wait_ready,
)


def test_readiness_recovers_from_partial_http_response(monkeypatch):
    calls = 0

    class ReadyResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    def probe(url, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise BadStatusLine("partial loopback startup response")
        return ReadyResponse()

    monkeypatch.setattr("scripts.run_fullstack_tests.urlopen", probe)
    monkeypatch.setattr("scripts.run_fullstack_tests.time.sleep", lambda _: None)
    wait_ready("http://127.0.0.1:12345/readyz", SimpleNamespace(poll=lambda: None))
    assert calls == 2


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
    assert env["PATHLAB_ALIGNMENT_ENABLED"] == "true"
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


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector containment")
def test_delayed_windows_assignment_contains_real_wrapper_and_command(tmp_path, monkeypatch):
    """Keep handles while alive; cleanup never reopens recorded PIDs after exit."""
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.IsProcessInJob.argtypes = [
        wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL),
    ]
    kernel.IsProcessInJob.restype = wintypes.BOOL
    kernel.GetSystemTimeAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = wintypes.BOOL

    def ticks(value):
        return (value.dwHighDateTime << 32) | value.dwLowDateTime

    before = wintypes.FILETIME()
    kernel.GetSystemTimeAsFileTime(ctypes.byref(before))
    original_assign = WindowsJob.assign

    def delayed_assign(self, process):
        # Let the venv redirector launch its base interpreter before admission.
        time.sleep(0.5)
        original_assign(self, process)

    monkeypatch.setattr(WindowsJob, "assign", delayed_assign)
    marker = tmp_path / "owned-handshake.json"
    nonce = uuid4().hex
    base = getattr(sys, "_base_executable", sys.executable)
    command = (
        "import json,os,pathlib,sys,time; "
        "p=pathlib.Path(sys.argv[1]); q=p.with_suffix('.pending'); q.write_text(json.dumps("
        "{'nonce':sys.argv[2],'child':os.getpid(),'wrapper':os.getppid()})); "
        "q.replace(p); time.sleep(60)"
    )
    unrelated = subprocess.Popen([base, "-c", "import time; time.sleep(60)"])
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    handles = []
    try:
        owned = manager.start("delayed-barrier", [base, "-c", command, str(marker), nonce])
        deadline = time.monotonic() + 10
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        handshake = json.loads(marker.read_text())
        assert handshake["nonce"] == nonce
        assert owned.job is not None
        membership = []
        for name in ("child", "wrapper"):
            handle = kernel.OpenProcess(0x100401, False, handshake[name])
            assert handle, ctypes.WinError(ctypes.get_last_error())
            handles.append(handle)
            created, exited, system, user = [wintypes.FILETIME() for _ in range(4)]
            assert kernel.GetProcessTimes(
                handle, ctypes.byref(created), ctypes.byref(exited),
                ctypes.byref(system), ctypes.byref(user),
            )
            assert ticks(created) >= ticks(before)
            assert kernel.WaitForSingleObject(handle, 0) == 258
            member = wintypes.BOOL()
            assert kernel.IsProcessInJob(handle, owned.job.handle, ctypes.byref(member))
            membership.append(bool(member.value))
        (tmp_path / "delayed-assignment-proof.json").write_text(json.dumps({
            "testRuntimeIsVenv": sys.executable != base,
            "commandAndWrapperInOwnedJob": membership,
            "unrelatedStillAlive": unrelated.poll() is None,
        }))
        assert membership == [True, True]
        manager.close()
        assert all(kernel.WaitForSingleObject(handle, 0) == 0 for handle in handles)
        assert unrelated.poll() is None
    finally:
        try:
            manager.close()
        finally:
            for handle in handles:
                try:
                    if kernel.WaitForSingleObject(handle, 0) == 258:
                        assert kernel.TerminateProcess(handle, 1)
                    assert kernel.WaitForSingleObject(handle, 5000) == 0
                finally:
                    kernel.CloseHandle(handle)
            if unrelated.poll() is None:
                unrelated.terminate()
            unrelated.wait(timeout=5)


@pytest.mark.skipif(os.name != "nt", reason="Windows direct venv bootstrap identity")
def test_windows_direct_bootstrap_preserves_wrapper_and_command_venv_context(tmp_path, monkeypatch):
    from importlib.metadata import version

    from scripts import run_fullstack_tests as launcher

    monkeypatch.setattr(
        launcher, "COMMAND_WRAPPER", launcher.COMMAND_WRAPPER.replace(
            "payload = json.loads(sys.stdin.buffer.readline())",
            "payload = json.loads(sys.stdin.buffer.readline())\n"
            "print(json.dumps({'kind':'wrapper','executable':sys.executable,"
            "'prefix':sys.prefix}),flush=True)",
        ),
    )
    manager = ProcessManager(tmp_path, isolated_environment(tmp_path))
    try:
        manager.run(
            "venv-context", [
                sys.executable, "-c",
                "import json,sys; from importlib.metadata import version; "
                "print(json.dumps({'kind':'command','executable':sys.executable,"
                "'prefix':sys.prefix,'dependencyVersion':version('fastapi')}))",
            ], timeout=10,
        )
    finally:
        manager.close()
    records = [
        json.loads(line) for line in (tmp_path / "venv-context.log").read_text().splitlines()
    ]
    assert [record["kind"] for record in records] == ["wrapper", "command"]
    assert all(Path(record["executable"]) == Path(sys.executable) for record in records)
    assert all(Path(record["prefix"]) == Path(sys.prefix) for record in records)
    assert records[1]["dependencyVersion"] == version("fastapi")


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
