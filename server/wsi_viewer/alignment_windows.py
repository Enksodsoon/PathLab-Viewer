"""Windows registration containment using kernel Job Object membership."""

from __future__ import annotations

import ctypes
import time
from typing import Any, cast

from .alignment_processes import AlignmentContainmentLost

DWORD = ctypes.c_uint32
BOOL = ctypes.c_int32
HANDLE = ctypes.c_void_p
SIZE_T = ctypes.c_size_t
MAX_JOB_PROCESSES = 128


class BasicLimits(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", DWORD),
        ("MinimumWorkingSetSize", SIZE_T),
        ("MaximumWorkingSetSize", SIZE_T),
        ("ActiveProcessLimit", DWORD),
        ("Affinity", SIZE_T),
        ("PriorityClass", DWORD),
        ("SchedulingClass", DWORD),
    ]


class IoCounters(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_uint64)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", BasicLimits),
        ("IoInfo", IoCounters),
        ("ProcessMemoryLimit", SIZE_T),
        ("JobMemoryLimit", SIZE_T),
        ("PeakProcessMemoryUsed", SIZE_T),
        ("PeakJobMemoryUsed", SIZE_T),
    ]


class ProcessIds(ctypes.Structure):
    _fields_ = [
        ("NumberOfAssignedProcesses", DWORD),
        ("NumberOfProcessIdsInList", DWORD),
        ("ProcessIdList", SIZE_T * MAX_JOB_PROCESSES),
    ]


class MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", DWORD), ("PageFaultCount", DWORD)] + [
        (name, SIZE_T)
        for name in (
            "PeakWorkingSetSize",
            "WorkingSetSize",
            "QuotaPeakPagedPoolUsage",
            "QuotaPagedPoolUsage",
            "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage",
            "PagefileUsage",
            "PeakPagefileUsage",
            "PrivateUsage",
        )
    ]


class WindowsAlignmentJob:
    def __init__(self, process_id: int, memory_bytes: int):
        if process_id <= 0 or memory_bytes <= 0 or memory_bytes > ctypes.c_size_t(-1).value:
            raise OSError("invalid process containment memory ceiling")
        # Windows-only entry points are absent from Linux ctypes type stubs.
        self.kernel: Any = cast(Any, ctypes).WinDLL("kernel32", use_last_error=True)
        self.psapi: Any = cast(Any, ctypes).WinDLL("psapi", use_last_error=True)
        definitions = {
            "CreateJobObjectW": ([HANDLE, ctypes.c_wchar_p], HANDLE),
            "SetInformationJobObject": ([HANDLE, ctypes.c_int, HANDLE, DWORD], BOOL),
            "QueryInformationJobObject": ([HANDLE, ctypes.c_int, HANDLE, DWORD, HANDLE], BOOL),
            "AssignProcessToJobObject": ([HANDLE, HANDLE], BOOL),
            "TerminateJobObject": ([HANDLE, DWORD], BOOL),
            "OpenProcess": ([DWORD, BOOL, DWORD], HANDLE),
            "CloseHandle": ([HANDLE], BOOL),
            "IsProcessInJob": ([HANDLE, HANDLE, HANDLE], BOOL),
            "GetExitCodeProcess": ([HANDLE, HANDLE], BOOL),
        }
        for name, (arguments, result) in definitions.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result
        self.psapi.GetProcessMemoryInfo.argtypes = [HANDLE, HANDLE, DWORD]
        self.psapi.GetProcessMemoryInfo.restype = BOOL
        self.handle: Any = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise cast(Any, ctypes).WinError(cast(Any, ctypes).get_last_error())
        self.memory_bytes = memory_bytes
        self.peak_working_set = 0
        self.peak_committed = 0
        self.peak_process_count = 0
        self.peak_private_commit = 0
        self.current_private_commit = 0
        try:
            limits = ExtendedLimits()
            # No breakaway permissions: every ordinary descendant stays in this job.
            limits.BasicLimitInformation.LimitFlags = 0x2000 | 0x200 | 0x8
            limits.BasicLimitInformation.ActiveProcessLimit = MAX_JOB_PROCESSES
            limits.JobMemoryLimit = memory_bytes
            self._check(
                self.kernel.SetInformationJobObject(
                    self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
                )
            )
            process = self.kernel.OpenProcess(0x100 | 0x1, False, process_id)
            self._check(process)
            try:
                self._check(self.kernel.AssignProcessToJobObject(self.handle, process))
            finally:
                self.kernel.CloseHandle(process)
            if process_id not in self.process_ids():
                raise OSError("assigned registration process is missing from Job Object")
            self.measure()
            if self.peak_committed > memory_bytes:
                raise OSError("existing registration commitment exceeds the memory ceiling")
        except BaseException:
            try:
                self.close()
            except BaseException as cleanup_error:
                raise AlignmentContainmentLost(
                    "Windows admission cleanup could not prove all descendants terminal: "
                    f"{cleanup_error}",
                    self.metrics(),
                ) from cleanup_error
            raise

    @staticmethod
    def _check(success: Any) -> None:
        if not success:
            raise cast(Any, ctypes).WinError(cast(Any, ctypes).get_last_error())

    def process_ids(self) -> set[int]:
        ids = ProcessIds()
        self._check(
            self.kernel.QueryInformationJobObject(
                self.handle, 3, ctypes.byref(ids), ctypes.sizeof(ids), None
            )
        )
        assigned, count = ids.NumberOfAssignedProcesses, ids.NumberOfProcessIdsInList
        if assigned > MAX_JOB_PROCESSES or count > MAX_JOB_PROCESSES or assigned != count:
            raise OSError("Job Object PID accounting exceeded its bounded admission")
        return {int(ids.ProcessIdList[index]) for index in range(count)}

    def _process_memory(self, pid: int) -> tuple[int, int]:
        process = self.kernel.OpenProcess(0x1000 | 0x10, False, pid)
        if not process:
            if pid not in self.process_ids():
                return 0, 0  # A member exited between the two kernel snapshots.
            self._check(process)
        try:
            belongs = BOOL()
            self._check(self.kernel.IsProcessInJob(process, self.handle, ctypes.byref(belongs)))
            code = DWORD()
            self._check(self.kernel.GetExitCodeProcess(process, ctypes.byref(code)))
            if code.value != 259:
                return 0, 0
            if not belongs.value:
                raise OSError("PID changed Job Object membership during accounting")
            counters = MemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            self._check(
                self.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
            )
            return int(counters.WorkingSetSize), int(counters.PrivateUsage)
        finally:
            self.kernel.CloseHandle(process)

    def measure(self) -> dict[str, Any]:
        limits = ExtendedLimits()
        self._check(
            self.kernel.QueryInformationJobObject(
                self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits), None
            )
        )
        if limits.JobMemoryLimit != self.memory_bytes or (
            limits.BasicLimitInformation.LimitFlags & (0x2000 | 0x200 | 0x8)
        ) != (0x2000 | 0x200 | 0x8):
            raise OSError("Job Object memory ceiling is not active")
        pids = self.process_ids()
        measurements = [self._process_memory(pid) for pid in pids]
        working_set = sum(working for working, _ in measurements)
        self.current_private_commit = sum(private for _, private in measurements)
        self.peak_private_commit = max(self.peak_private_commit, self.current_private_commit)
        self.peak_working_set = max(self.peak_working_set, working_set)
        self.peak_committed = max(self.peak_committed, int(limits.PeakJobMemoryUsed))
        self.peak_process_count = max(self.peak_process_count, len(pids))
        return self.metrics()

    def metrics(self) -> dict[str, Any]:
        return {
            "processContainment": "windows-job-object",
            "memoryMeasurementScope": "windows-job-sampled-working-set",
            "peakMemoryBytes": self.peak_working_set,
            "peakCommittedMemoryBytes": self.peak_committed,
            "kernelReportedPeakJobMemoryBytes": self.peak_committed,
            "committedMemoryMeasurementScope": "windows-job-kernel-reported-high-water",
            "currentPrivateCommittedMemoryBytes": self.current_private_commit,
            "sampledPeakPrivateCommittedMemoryBytes": self.peak_private_commit,
            "committedMemoryLimitBytes": self.memory_bytes,
            "peakContainedProcesses": self.peak_process_count,
        }

    def close(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, None
            try:
                self._check(self.kernel.TerminateJobObject(handle, 1))
                # Termination is asynchronous; prove the job empty before reuse.
                deadline = time.monotonic() + 5
                while True:
                    ids = ProcessIds()
                    self._check(
                        self.kernel.QueryInformationJobObject(
                            handle, 3, ctypes.byref(ids), ctypes.sizeof(ids), None
                        )
                    )
                    if ids.NumberOfAssignedProcesses == 0 and ids.NumberOfProcessIdsInList == 0:
                        break
                    if time.monotonic() >= deadline:
                        raise OSError(
                            "contained descendants did not terminate before cleanup deadline"
                        )
                    time.sleep(0.02)
            finally:
                self._check(self.kernel.CloseHandle(handle))
