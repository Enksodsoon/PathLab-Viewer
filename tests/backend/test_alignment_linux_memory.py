"""Enforcement must distinguish unreadable live RSS from confirmed exit races."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from wsi_viewer import alignment_processes


def _group(monkeypatch, outcome, identity=("S", 42, 42, 100)):
    group = alignment_processes.LinuxAlignmentGroup.__new__(
        alignment_processes.LinuxAlignmentGroup
    )
    group.pid, group.start_time, group.closed = 42, 100, False
    monkeypatch.setattr(group, "members", lambda: {42: 100})

    def read(path, *args, **kwargs):
        assert path.as_posix() == "/proc/42/statm"
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def current(pid):
        assert pid == 42
        if isinstance(identity, Exception):
            raise identity
        return identity

    monkeypatch.setattr(Path, "read_text", read)
    monkeypatch.setattr(alignment_processes, "_identity", current)
    monkeypatch.setattr(alignment_processes.os, "sysconf", lambda _: 4096, raising=False)
    return group


@pytest.mark.parametrize(
    "outcome", [PermissionError("denied"), FileNotFoundError("missing"), "bad", "10 -2"]
)
def test_live_owned_unreadable_rss_rejects(monkeypatch, outcome):
    group = _group(monkeypatch, outcome)
    with pytest.raises(OSError, match="RSS unavailable"):
        group.resident_bytes()


@pytest.mark.parametrize(
    "identity",
    [FileNotFoundError("exited"), ("Z", 42, 42, 100), ("S", 42, 42, 101), ("S", 42, 43, 100)],
)
@pytest.mark.parametrize("outcome", [FileNotFoundError("exit race"), "10 2"])
def test_confirmed_exit_or_different_identity_is_not_charged(monkeypatch, outcome, identity):
    assert _group(monkeypatch, outcome, identity).resident_bytes() == 0


def test_live_owned_rss_uses_resident_pages(monkeypatch):
    assert _group(monkeypatch, "999 2 999").resident_bytes() == 8192


def test_unknown_identity_does_not_silently_allow_missing_rss(monkeypatch):
    group = _group(monkeypatch, PermissionError("statm"), PermissionError("identity"))
    with pytest.raises(PermissionError, match="identity"):
        group.resident_bytes()


def test_optional_telemetry_remains_best_effort_while_enforcement_rejects(monkeypatch):
    from wsi_viewer import worker

    group = _group(monkeypatch, PermissionError("live statm unreadable"))
    monkeypatch.setattr(worker.sys, "platform", "linux")
    assert worker._process_rss_bytes(42) == 0
    with pytest.raises(OSError, match="RSS unavailable"):
        group.resident_bytes()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_supervisor_rejects_live_telemetry_loss_but_allows_next_child_after_cleanup(
    monkeypatch, tmp_path, cleanup_fails
):
    # The worker contract is exercised on every host; actual PID cleanup is
    # separately exercised by the Linux-only child fixture and stdlib smoke.
    from wsi_viewer import worker
    from wsi_viewer.alignment import AlignmentRejected
    from wsi_viewer.alignment_processes import AlignmentContainmentLost

    events = []
    fail = [True]

    class Process:
        pid = 42

        def start(self):
            events.append("start")

        def join(self, timeout):
            pass

        def is_alive(self):
            return False

    class Output:
        def get(self, timeout):
            return {"ok": True, "result": {"status": "approximate"}}

        def close(self):
            events.append("queue-close")

    class Group:
        def __init__(self, *args):
            pass

        def members(self):
            return {42: 100}

        def resident_bytes(self):
            if fail[0]:
                raise OSError("live registration member RSS unavailable")
            return 8192

        def close(self):
            events.append("cleanup-attempt" if cleanup_fails else "proved-empty")
            if cleanup_fails:
                raise OSError("descendants not terminal")

    context = SimpleNamespace(
        Event=lambda: SimpleNamespace(set=lambda: events.append("release")),
        Queue=lambda **kwargs: Output(),
        Process=lambda **kwargs: Process(),
    )
    monkeypatch.setattr(worker.sys, "platform", "linux")
    monkeypatch.setattr(worker.multiprocessing, "get_context", lambda _: context)
    monkeypatch.setattr(worker, "_LinuxAlignmentGroup", Group)
    monkeypatch.setattr(worker, "_process_rss_bytes", lambda _: 0)
    options = dict(timeout_seconds=10, memory_bytes=2 * 1024**3)
    expected = AlignmentContainmentLost if cleanup_fails else AlignmentRejected
    with pytest.raises(expected):
        worker._run_alignment_bounded(tmp_path, tmp_path, (10, 10), (10, 10), **options)
    if cleanup_fails:
        assert events == ["start", "release", "cleanup-attempt", "queue-close"]
        return
    assert events == ["start", "release", "proved-empty", "queue-close"]
    fail[0] = False
    result = worker._run_alignment_bounded(tmp_path, tmp_path, (10, 10), (10, 10), **options)
    assert result["status"] == "approximate" and result["peakMemoryBytes"] == 8192
    assert events.count("start") == events.count("proved-empty") == 2
