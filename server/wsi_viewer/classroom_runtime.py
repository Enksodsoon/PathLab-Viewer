import importlib
import os
from pathlib import Path
from typing import Any, BinaryIO


class ClassroomSingletonLock:
    """Lifetime-held, nonblocking lock for the intentionally in-process hub."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._file: BinaryIO | None = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_file: BinaryIO | None = None
        try:
            lock_file = self.path.open("a+b")
            lock_file.seek(0)
            if lock_file.read(1) == b"":
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl: Any = importlib.import_module("fcntl")
                flock = fcntl.flock
                flock(
                    lock_file.fileno(),
                    int(fcntl.LOCK_EX) | int(fcntl.LOCK_NB),
                )
        except OSError:
            if lock_file is not None:
                lock_file.close()
            return False
        self._file = lock_file
        return True

    def release(self) -> None:
        if self._file is None:
            return
        self._file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl: Any = importlib.import_module("fcntl")
                flock = fcntl.flock
                flock(self._file.fileno(), int(fcntl.LOCK_UN))
        finally:
            self._file.close()
            self._file = None
