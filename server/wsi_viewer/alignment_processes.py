"""Linux registration session accounting and PID-safe descendant cleanup."""

import os
import signal
import time
from contextlib import suppress
from pathlib import Path
from typing import Any, cast


class AlignmentContainmentLost(SystemExit):
    """Stop the supervisor when terminal descendant state cannot be proved."""

    def __init__(self, message: str, resource_metrics: dict[str, Any]):
        super().__init__(message)
        self.resource_metrics = resource_metrics


def _identity(pid: int) -> tuple[str, int, int, int]:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return fields[0], int(fields[2]), int(fields[3]), int(fields[19])


class LinuxAlignmentGroup:
    def __init__(self, pid: int, timeout_seconds: float):
        self.pid = pid
        self.start_time = _identity(pid)[3]
        self.closed = False
        deadline = time.monotonic() + timeout_seconds
        # The target creates its session before waiting at the startup barrier.
        while True:
            state, group, session, started = _identity(pid)
            if started != self.start_time or state == "Z":
                raise OSError("registration root exited before session admission")
            if group == pid and session == pid:
                break
            if time.monotonic() >= deadline:
                raise OSError("registration session admission exceeded its deadline")
            time.sleep(0.01)
        if not hasattr(os, "pidfd_open") or not hasattr(signal, "pidfd_send_signal"):
            raise OSError("registration containment requires Linux PID file descriptors")

    def members(self) -> dict[int, int]:
        members = {}
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal():
                continue
            pid = int(entry.name)
            try:
                state, group, session, started = _identity(pid)
            except FileNotFoundError:
                continue
            if pid == self.pid and started != self.start_time:
                raise OSError("registration session leader identity changed")
            if state != "Z" and session == self.pid and started >= self.start_time:
                members[pid] = started
        return members

    def _signal(self, number: int) -> None:
        for pid, started in self.members().items():
            try:
                descriptor = cast(Any, os).pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                try:
                    _, group, session, current = _identity(pid)
                except FileNotFoundError:
                    continue
                if current != started or session != self.pid:
                    raise OSError("registration member identity changed before termination")
                with suppress(ProcessLookupError):
                    cast(Any, signal).pidfd_send_signal(descriptor, number)
            finally:
                os.close(descriptor)

    def close(self) -> None:
        if self.closed:
            return
        self._signal(signal.SIGTERM)
        grace = time.monotonic() + 0.2
        deadline = time.monotonic() + 5
        while self.members():
            if time.monotonic() >= grace:
                # Re-enumerate the owned session, including new descendants,
                # even when its root already exited or ignored TERM.
                self._signal(cast(Any, signal).SIGKILL)
            if time.monotonic() >= deadline:
                raise OSError("registration session descendants did not terminate")
            time.sleep(0.02)
        self.closed = True
