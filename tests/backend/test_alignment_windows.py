"""Real bounded Windows process trees; no registration engine is imported or run."""

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

import pytest
from wsi_viewer import worker
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.alignment_processes import AlignmentContainmentLost

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Job Object contracts")


def _process_api():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    api.OpenProcess.restype = ctypes.c_void_p
    api.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    api.WaitForSingleObject.restype = ctypes.c_uint32
    api.TerminateProcess.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    api.TerminateProcess.restype = ctypes.c_int
    api.CloseHandle.argtypes = [ctypes.c_void_p]
    api.CloseHandle.restype = ctypes.c_int
    return api


def _tree_script(directory, allocation=0):
    directory = str(directory)
    grand = (
        "import os,time; from pathlib import Path; "
        f"Path({directory!r}+'/grand-ready').write_text(str(os.getpid())); time.sleep(120)"
    )
    return (
        "import os,json,subprocess,sys,time; from pathlib import Path; "
        f"p=subprocess.Popen([sys.executable,'-c',{grand!r}]); "
        f"Path({directory!r}+'/tree.json').write_text(json.dumps([os.getpid(),p.pid])); "
        f"allocation=bytearray({allocation}); time.sleep(120)"
    )


def _lightweight_tree_target(
    reference,
    moving,
    ref_size,
    mov_size,
    engine,
    settings,
    artifact,
    output,
    seed=None,
    startup_gate=None,
):
    if startup_gate is not None and not startup_gate.wait(20):
        return
    directory = Path(reference)
    subprocess.Popen([sys.executable, "-c", _tree_script(directory)])
    deadline = time.monotonic() + 10
    while not (directory / "grand-ready").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("test process tree did not start")
        time.sleep(0.02)
    while not (directory / "handles-ready").exists():
        if time.monotonic() > deadline:
            raise RuntimeError("parent did not capture process handles")
        time.sleep(0.02)
    if settings["mode"] == "normal":
        output.put({"ok": True, "result": {"status": "approximate"}})
        return
    if settings["mode"] == "root-exit":
        import os

        os._exit(0)
    time.sleep(120)


@pytest.mark.parametrize("mode", ["normal", "root-exit", "timeout", "cancel"])
def test_bounded_registration_cleans_child_and_grandchild_after_every_exit(
    tmp_path, monkeypatch, mode
):
    monkeypatch.setattr(worker, "_alignment_child", _lightweight_tree_target)
    api = _process_api()
    unrelated = subprocess.Popen([sys._base_executable, "-c", "import time; time.sleep(120)"])
    handles = []
    try:

        def heartbeat():
            if (tmp_path / "grand-ready").exists() and not handles:
                pids = json.loads((tmp_path / "tree.json").read_text())
                for pid in pids:
                    handle = api.OpenProcess(0x1000 | 0x100000 | 1, False, pid)
                    assert handle
                    handles.append(handle)
                (tmp_path / "handles-ready").touch()
            if mode == "cancel" and handles:
                raise AlignmentRejected("test cancellation")

        if mode == "normal":
            result = worker._run_alignment_bounded(
                tmp_path,
                tmp_path,
                (10, 10),
                (10, 10),
                engine_settings={"mode": mode},
                timeout_seconds=8,
                memory_bytes=2 * 1024**3,
                heartbeat=heartbeat,
            )
        else:
            with pytest.raises(AlignmentRejected) as rejected:
                worker._run_alignment_bounded(
                    tmp_path,
                    tmp_path,
                    (10, 10),
                    (10, 10),
                    engine_settings={"mode": mode},
                    timeout_seconds=8,
                    memory_bytes=2 * 1024**3,
                    heartbeat=heartbeat,
                )
        assert (tmp_path / "tree.json").exists()
        assert len(handles) == 2
        for handle in handles:
            assert api.WaitForSingleObject(handle, 1000) == 0, "enrolled descendant survived"
        assert unrelated.poll() is None
        if mode == "normal":
            assert result["processContainment"] == "windows-job-object"
            assert result["memoryMeasurementScope"] == "windows-job-sampled-working-set"
            assert result["peakCommittedMemoryBytes"] > 0
        else:
            assert rejected.value.resource_metrics["processContainment"] == "windows-job-object"
    finally:
        # Close only handles belonging to this fixture's recorded processes.
        for handle in handles:
            api.TerminateProcess(handle, 1)
            api.CloseHandle(handle)
        unrelated.terminate()
        unrelated.wait(timeout=5)


def test_windows_assignment_failure_cannot_start_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "_alignment_child", _lightweight_tree_target)

    class RefusedJob:
        def __init__(self, *_):
            raise OSError("test job assignment refused")

    monkeypatch.setattr(worker, "_WindowsAlignmentJob", RefusedJob, raising=False)
    with pytest.raises(AlignmentRejected, match="containment"):
        worker._run_alignment_bounded(
            tmp_path,
            tmp_path,
            (10, 10),
            (10, 10),
            engine_settings={"mode": "normal"},
            timeout_seconds=8,
            memory_bytes=2 * 1024**3,
        )
    assert not (tmp_path / "tree.json").exists()


def test_windows_job_structures_use_explicit_pointer_width_and_active_memory_limits():
    from wsi_viewer.alignment_windows import BasicLimits, ExtendedLimits, ProcessIds

    assert ctypes.sizeof(ctypes.c_void_p) == 8  # Current x64/ARM64 ABI contract.
    assert ctypes.sizeof(BasicLimits) == 64
    assert ctypes.sizeof(ExtendedLimits) == 144
    assert ExtendedLimits.JobMemoryLimit.offset == 120
    assert ProcessIds.ProcessIdList.offset == 8


def test_windows_accounting_failure_stops_contained_tree(tmp_path, monkeypatch):
    real_job = worker._WindowsAlignmentJob
    api = _process_api()
    handles = []

    class BrokenAccounting(real_job):
        def measure(self):
            if (tmp_path / "grand-ready").exists():
                for pid in json.loads((tmp_path / "tree.json").read_text()):
                    handle = api.OpenProcess(0x100000 | 1, False, pid)
                    assert handle
                    handles.append(handle)
                raise OSError("test authoritative accounting failure")
            return super().measure()

    monkeypatch.setattr(worker, "_WindowsAlignmentJob", BrokenAccounting)
    monkeypatch.setattr(worker, "_alignment_child", _lightweight_tree_target)
    with pytest.raises(AlignmentRejected, match="accounting"):
        worker._run_alignment_bounded(
            tmp_path,
            tmp_path,
            (10, 10),
            (10, 10),
            engine_settings={"mode": "timeout"},
            timeout_seconds=8,
            memory_bytes=2 * 1024**3,
        )
    try:
        assert len(handles) == 2
        assert all(api.WaitForSingleObject(handle, 1000) == 0 for handle in handles)
    finally:
        for handle in handles:
            api.TerminateProcess(handle, 1)
            api.CloseHandle(handle)


def test_windows_aggregate_committed_limit_counts_both_descendants(tmp_path):
    from wsi_viewer.alignment_windows import ExtendedLimits

    directory = str(tmp_path)
    allocate = (
        "import os,time; from pathlib import Path\n"
        f"Path({directory!r}+'/ready-'+str(os.getpid())).touch()\n"
        f"while not Path({directory!r}+'/allocate').exists(): time.sleep(.01)\n"
        "try:\n allocation=bytearray(48*1024**2)\n"
        f"except MemoryError: Path({directory!r}+'/oom-'+str(os.getpid())).touch()\n"
        f"else: Path({directory!r}+'/success-'+str(os.getpid())).touch()\n"
        "time.sleep(120)\n"
    )
    child = (
        "import subprocess,sys; subprocess.Popen([sys.executable,'-c',"
        + repr(allocate)
        + "]);\n"
        + allocate
    )
    root = (
        "import subprocess,sys,time; from pathlib import Path\n"
        f"while not Path({directory!r}+'/start').exists(): time.sleep(.01)\n"
        "subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); time.sleep(120)"
    )
    # Bypass the venv launcher, as multiprocessing's Windows spawn does. Any
    # interpreter children must be created only after the root joins its job.
    process = subprocess.Popen(
        [sys._base_executable, "-c", root], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    api = _process_api()
    job = None
    handles = []
    try:
        job = worker._WindowsAlignmentJob(process.pid, 2 * 1024**3)
        (tmp_path / "start").touch()
        deadline = time.monotonic() + 8
        while len(list(tmp_path.glob("ready-*"))) < 2 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(list(tmp_path.glob("ready-*"))) == 2
        baseline = job.measure()["peakCommittedMemoryBytes"]
        pids = job.process_ids()
        assert len(pids) == 3
        for pid in pids:
            handle = api.OpenProcess(0x100000 | 1, False, pid)
            assert handle
            handles.append(handle)
        # Both descendants are resident and waiting. One allocation plus a
        # 16 MiB margin fits; two allocations cannot fit in the aggregate.
        limit = baseline + (48 + 16) * 1024**2
        limits = ExtendedLimits()
        job._check(
            job.kernel.QueryInformationJobObject(
                job.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits), None
            )
        )
        limits.JobMemoryLimit = limit
        job._check(
            job.kernel.SetInformationJobObject(
                job.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
            )
        )
        job.memory_bytes = limit
        (tmp_path / "allocate").touch()
        deadline = time.monotonic() + 8
        while (
            len(list(tmp_path.glob("success-*"))) + len(list(tmp_path.glob("oom-*"))) < 2
            and time.monotonic() < deadline
        ):
            time.sleep(0.02)
        assert len(list(tmp_path.glob("success-*"))) == 1
        assert len(list(tmp_path.glob("oom-*"))) == 1
        metrics = job.measure()
        assert baseline > 0
        assert baseline + 48 * 1024**2 <= limit < baseline + 96 * 1024**2
        assert metrics["kernelReportedPeakJobMemoryBytes"] >= baseline
        assert metrics["peakCommittedMemoryBytes"] == metrics["kernelReportedPeakJobMemoryBytes"]
        assert metrics["currentPrivateCommittedMemoryBytes"] <= limit
        assert metrics["sampledPeakPrivateCommittedMemoryBytes"] <= limit
        assert metrics["committedMemoryLimitBytes"] == limit
        assert metrics["peakContainedProcesses"] == 3
        print(
            json.dumps(
                {
                    "schema": "pathlab-windows-job-memory-smoke/1",
                    "baselineKernelReportedPeakJobMemoryBytes": baseline,
                    "successfulAllocations": 1,
                    "rejectedAllocations": 1,
                    "allocationBytesEach": 48 * 1024**2,
                    **metrics,
                }
            )
        )
        job.close()
        assert all(api.WaitForSingleObject(handle, 1000) == 0 for handle in handles)
    finally:
        if job is not None:
            job.close()
        for handle in handles:
            api.TerminateProcess(handle, 1)
            api.CloseHandle(handle)
        if process.poll() is None:
            process.terminate()
        process.wait(timeout=5)


def test_windows_memory_ceiling_admission_is_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setattr(worker, "_alignment_child", _lightweight_tree_target)
    with pytest.raises(AlignmentRejected, match="memory ceiling"):
        worker._run_alignment_bounded(
            tmp_path,
            tmp_path,
            (10, 10),
            (10, 10),
            engine_settings={"mode": "normal"},
            timeout_seconds=8,
            memory_bytes=1,
        )
    assert not (tmp_path / "tree.json").exists()


def _tiny_target(
    reference,
    moving,
    ref_size,
    mov_size,
    engine,
    settings,
    artifact,
    output,
    seed=None,
    startup_gate=None,
):
    if startup_gate is not None and not startup_gate.wait(20):
        return
    marker = Path(reference) / "engine-starts"
    with marker.open("a") as stream:
        stream.write("started\n")
    output.put({"ok": True, "result": {"status": "approximate"}})


def test_unproved_job_cleanup_is_fatal_and_second_recipe_never_starts(tmp_path, monkeypatch):
    real_job = worker._WindowsAlignmentJob

    class UnprovedClose(real_job):
        def close(self):
            super().close()
            raise OSError("test terminal membership query failed")

    monkeypatch.setattr(worker, "_WindowsAlignmentJob", UnprovedClose)
    monkeypatch.setattr(worker, "_alignment_child", _tiny_target)
    with pytest.raises(AlignmentContainmentLost, match="could not prove"):
        for _ in range(2):
            try:
                worker._run_alignment_bounded(
                    tmp_path,
                    tmp_path,
                    (10, 10),
                    (10, 10),
                    timeout_seconds=8,
                    memory_bytes=2 * 1024**3,
                )
            except AlignmentRejected:
                continue  # Ordinary per-recipe rejection must not admit another engine.
    assert (tmp_path / "engine-starts").read_text().splitlines() == ["started"]


@pytest.mark.parametrize("cleanup_proved", [False, True])
def test_constructor_accounting_failure_preserves_fatal_cleanup_failure(
    tmp_path, monkeypatch, cleanup_proved
):
    real_job = worker._WindowsAlignmentJob

    class AdmissionAccountingFailure(real_job):
        def measure(self):
            raise OSError("test admission accounting failed after assignment")

        def close(self):
            super().close()
            if not cleanup_proved:
                raise OSError("test constructor cleanup cannot prove terminal state")

    monkeypatch.setattr(worker, "_WindowsAlignmentJob", AdmissionAccountingFailure)
    monkeypatch.setattr(worker, "_alignment_child", _tiny_target)
    expected = AlignmentRejected if cleanup_proved else AlignmentContainmentLost
    with pytest.raises(expected) as rejected:
        worker._run_alignment_bounded(
            tmp_path,
            tmp_path,
            (10, 10),
            (10, 10),
            timeout_seconds=8,
            memory_bytes=2 * 1024**3,
        )
    assert not (tmp_path / "engine-starts").exists()
    if not cleanup_proved:
        assert rejected.value.resource_metrics["processContainment"] == "windows-job-object"
