"""Actual repeated invocations, partial durable results and shared containment."""

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from wsi_viewer import alignment_warm as warm
from wsi_viewer import worker
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.alignment_processes import AlignmentContainmentLost


class _Output:
    def __init__(self):
        self.messages = []

    def put(self, value):
        self.messages.append(value)


@pytest.fixture(autouse=True)
def admitted_fixture_inputs(monkeypatch):
    monkeypatch.setattr(warm, "_input_digest", lambda side: "a" * 64)


def test_two_real_calls_same_pid_and_remaining_budget(tmp_path, monkeypatch):
    monkeypatch.setattr(warm.sys, "platform", "win32")
    clock = {"time": 100.0}
    monkeypatch.setattr(warm.time, "monotonic", lambda: clock["time"])
    calls = []

    def invocation(*args):
        calls.append(args[5])
        clock["time"] += 4
        args[7].put({"ok": True, "result": {"status": "approximate"}})

    monkeypatch.setattr(worker, "_alignment_invocation", invocation)
    output = _Output()
    warm._warm_child(
        "r",
        "m",
        (100, 100),
        (100, 100),
        "native-overview-v6",
        {
            "timeoutSeconds": 600,
            "_warmDeadlineMonotonic": 700,
            "_warmInputDigests": ["a" * 64, "a" * 64],
        },
        str(tmp_path),
        output,
    )
    assert [call["timeoutSeconds"] for call in calls] == [600, 600]
    receipts = [json.loads((tmp_path / f"invocation-{n}.json").read_bytes()) for n in (1, 2)]
    assert receipts[0]["childPid"] == receipts[1]["childPid"]
    assert receipts[1]["processTemperature"] == "warm-python-repeat"
    assert receipts[1]["retainedModelTemperature"] == "unverified"
    assert receipts[1]["requestedSettings"] == {"timeoutSeconds": 600}
    assert [receipt["grantedRemainingBudgetSeconds"] for receipt in receipts] == [600, 596]


def test_exhausted_shared_deadline_does_not_start_second_invocation(tmp_path, monkeypatch):
    monkeypatch.setattr(warm.sys, "platform", "win32")
    clock = {"time": 100.0}
    monkeypatch.setattr(warm.time, "monotonic", lambda: clock["time"])
    calls = []

    def invocation(*args):
        calls.append(True)
        clock["time"] = 701
        args[7].put({"ok": True, "result": {"status": "approximate"}})

    monkeypatch.setattr(worker, "_alignment_invocation", invocation)
    warm._warm_child(
        "r",
        "m",
        (100, 100),
        (100, 100),
        "native-overview-v6",
        {"_warmDeadlineMonotonic": 700, "_warmInputDigests": ["a" * 64, "a" * 64]},
        str(tmp_path),
        _Output(),
    )
    assert len(calls) == 1
    second = json.loads((tmp_path / "invocation-2.json").read_bytes())
    assert second["invocationExecuted"] is False
    assert second["grantedRemainingBudgetSeconds"] == 0


def test_first_atomic_result_survives_second_supervisor_failure(tmp_path, monkeypatch):
    def supervisor(*args, **kwargs):
        warm._atomic_receipt(
            tmp_path / "invocation-1.json",
            {"invocationOrdinal": 1, "result": {"ok": True, "result": {"status": "ready"}}},
        )
        raise AlignmentRejected("registration exceeded the pair timeout")

    monkeypatch.setattr(worker, "_run_alignment_bounded", supervisor)
    result = warm.run_warm_bounded(
        Path("r"),
        Path("m"),
        (100, 100),
        (100, 100),
        recipe="native-overview-v6",
        settings={},
        artifact_dir=tmp_path,
        input_digests=["a" * 64, "a" * 64],
    )
    assert result["invocations"][0]["result"]["ok"] is True
    assert result["invocations"][1]["result"]["type"] == "MissingInvocationReceipt"
    assert result["supervisorFailure"]["type"] == "AlignmentRejected"
    assert result["terminalContainmentVerified"] is True


def test_containment_loss_is_fatal_not_a_resumable_method_failure(tmp_path, monkeypatch):
    def fatal(*args, **kwargs):
        raise AlignmentContainmentLost("fixture containment failure", {})

    monkeypatch.setattr(worker, "_run_alignment_bounded", fatal)
    with pytest.raises(AlignmentContainmentLost):
        warm.run_warm_bounded(
            Path("r"),
            Path("m"),
            (100, 100),
            (100, 100),
            recipe="native-overview-v6",
            settings={},
            artifact_dir=tmp_path,
            input_digests=["a" * 64, "a" * 64],
        )


def _fixture_invocation(*args):
    if Path(args[6]).name == "invocation-2":
        time.sleep(30)
    args[7].put({"ok": True, "result": {"status": "approximate"}})


def _fixture_warm_child(*args):
    worker._alignment_invocation = _fixture_invocation
    warm._input_digest = lambda side: "a" * 64
    warm._warm_child(*args)


def test_actual_contained_timeout_preserves_first_result(tmp_path, monkeypatch):
    monkeypatch.setattr(warm, "_warm_child", _fixture_warm_child)
    result = warm.run_warm_bounded(
        Path("r"),
        Path("m"),
        (100, 100),
        (100, 100),
        recipe="native-overview-v6",
        settings={},
        artifact_dir=tmp_path,
        input_digests=["a" * 64, "a" * 64],
        timeout_seconds=5,
    )
    assert result["invocations"][0]["result"]["ok"] is True
    assert result["supervisorFailure"] is not None
    assert result["terminalContainmentVerified"] is True
    assert result["invocations"][1]["invocationExecuted"] is None
    assert result["invocations"][1]["invocationExecutionPhaseStarted"] is True


def test_second_invocation_refuses_changed_input_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(warm.sys, "platform", "win32")
    count = {"reads": 0, "calls": 0}

    def inputs(side):
        count["reads"] += 1
        return "a" * 64 if count["reads"] <= 2 else "b" * 64

    def invocation(*args):
        count["calls"] += 1
        args[7].put({"ok": True, "result": {"status": "approximate"}})

    monkeypatch.setattr(warm, "_input_digest", inputs)
    monkeypatch.setattr(worker, "_alignment_invocation", invocation)
    warm._warm_child(
        "r",
        "m",
        (100, 100),
        (100, 100),
        "native-overview-v6",
        {
            "timeoutSeconds": 600,
            "_warmDeadlineMonotonic": time.monotonic() + 600,
            "_warmInputDigests": ["a" * 64, "a" * 64],
        },
        str(tmp_path),
        _Output(),
    )
    assert count["calls"] == 1
    second = json.loads((tmp_path / "invocation-2.json").read_bytes())
    assert second["invocationExecuted"] is False
    assert second["verifiedInputDigests"] == ["b" * 64, "b" * 64]


def test_parent_deadline_survives_artifact_admission_delay(tmp_path, monkeypatch):
    monkeypatch.setattr(warm.time, "monotonic", lambda: 150)
    captured = {}

    def supervisor(*args, **kwargs):
        captured.update(kwargs)
        raise AlignmentRejected("fixture deadline")

    monkeypatch.setattr(worker, "_run_alignment_bounded", supervisor)
    warm.run_warm_bounded(
        Path("r"),
        Path("m"),
        (100, 100),
        (100, 100),
        recipe="native-overview-v6",
        settings={},
        artifact_dir=tmp_path,
        input_digests=["a" * 64, "a" * 64],
        absolute_deadline=700,
    )
    assert captured["_absolute_deadline"] == 700
    assert captured["engine_settings"]["_warmDeadlineMonotonic"] == 700


def test_expired_absolute_deadline_never_spawns(monkeypatch):
    monkeypatch.setattr(worker.time, "monotonic", lambda: 700)
    monkeypatch.setattr(
        worker.multiprocessing,
        "get_context",
        lambda *args: pytest.fail("expired budget must not create a child"),
    )
    with pytest.raises(AlignmentRejected, match="before process startup"):
        worker._run_alignment_bounded(
            Path("r"),
            Path("m"),
            (100, 100),
            (100, 100),
            timeout_seconds=600,
            memory_bytes=7 * 1024**3,
            _absolute_deadline=700,
        )


def test_supervisor_includes_spawn_time_in_absolute_deadline(monkeypatch):
    clock = {"time": 100.0}
    state = {"alive": True}
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock["time"])
    monkeypatch.setattr(worker.sys, "platform", "win32")

    def start():
        clock["time"] += 4

    def receive(**kwargs):
        clock["time"] += 1
        raise worker.queue.Empty

    process = SimpleNamespace(
        pid=12345, start=start, is_alive=lambda: state["alive"], join=lambda *args: None
    )
    output = SimpleNamespace(get=receive, close=lambda: None)
    context = SimpleNamespace(
        Event=lambda: SimpleNamespace(set=lambda: None),
        Queue=lambda **kwargs: output,
        Process=lambda **kwargs: process,
    )
    monkeypatch.setattr(worker.multiprocessing, "get_context", lambda *args: context)
    job = SimpleNamespace(
        metrics=lambda: {"peakMemoryBytes": 0},
        measure=lambda: {"peakMemoryBytes": 0},
        close=lambda: None,
    )
    monkeypatch.setattr(worker, "_WindowsAlignmentJob", lambda *args: job)
    monkeypatch.setattr(worker, "_terminate_process_tree", lambda *args: state.update(alive=False))
    with pytest.raises(AlignmentRejected, match="pair timeout"):
        worker._run_alignment_bounded(
            Path("r"),
            Path("m"),
            (100, 100),
            (100, 100),
            timeout_seconds=5,
            memory_bytes=7 * 1024**3,
            _absolute_deadline=105,
        )
    assert clock["time"] == 105


def _blocked_fixture_input(side):
    time.sleep(30)
    return "a" * 64


def _fixture_blocked_admission_child(*args):
    warm._input_digest = _blocked_fixture_input
    worker._alignment_invocation = _fixture_invocation
    warm._warm_child(*args)


def test_actual_blocking_input_hash_is_contained_by_shared_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(warm, "_warm_child", _fixture_blocked_admission_child)
    result = warm.run_warm_bounded(
        Path("r"),
        Path("m"),
        (100, 100),
        (100, 100),
        recipe="native-overview-v6",
        settings={},
        artifact_dir=tmp_path,
        input_digests=["a" * 64, "a" * 64],
        timeout_seconds=5,
    )
    assert result["supervisorFailure"] is not None
    assert [call["invocationExecuted"] for call in result["invocations"]] == [False, False]
    assert result["terminalContainmentVerified"] is True
