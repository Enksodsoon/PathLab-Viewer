import os
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path

from .config import Settings


class HeartbeatWriter:
    def __init__(self, path: Path, *, interval_seconds: float) -> None:
        self._path = path
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="pathlab-worker-heartbeat",
            daemon=True,
        )

    def refresh(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_name(
            f".{self._path.name}.tmp-{os.getpid()}-{threading.get_ident()}"
        )
        temporary.write_text(repr(time.time()), encoding="ascii")
        for attempt in range(5):
            try:
                os.replace(temporary, self._path)
                return
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.01)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.refresh()
            self._stop.wait(self._interval_seconds)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join()
        with suppress(FileNotFoundError):
            self._path.unlink()


def check_heartbeat(
    path: Path,
    *,
    stale_after_seconds: float,
    now: float | None = None,
) -> bool:
    try:
        timestamp = float(path.read_text(encoding="ascii"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        return False
    current = time.time() if now is None else now
    age = current - timestamp
    return 0 <= age <= stale_after_seconds


def main() -> None:
    settings = Settings()
    if check_heartbeat(
        settings.worker_heartbeat_path,
        stale_after_seconds=settings.worker_heartbeat_stale_seconds,
    ):
        return
    print("Worker heartbeat unavailable", file=sys.stderr)
    raise SystemExit(1)
