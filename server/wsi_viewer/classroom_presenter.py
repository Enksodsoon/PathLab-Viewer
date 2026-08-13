import asyncio
import contextlib
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class PresenterSnapshot:
    session_id: str
    sequence: int
    slide_id: str
    viewport: dict[str, float]


class PresenterRuntime:
    """Latest presenter state with sparse, monotonic-clock persistence."""

    def __init__(
        self,
        persist: Callable[[Sequence[PresenterSnapshot]], None],
        *,
        reserve: Callable[[str, int], int] | None = None,
        interval_seconds: float = 2.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._persist = persist
        self._reserve = reserve or (lambda _session_id, sequence: sequence)
        self._interval = interval_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._states: dict[str, PresenterSnapshot] = {}
        self._dirty: set[str] = set()
        self._in_flight: set[str] = set()
        self._last_persisted_at: dict[str, float] = {}
        self._reserved_until: dict[str, int] = {}
        self._task: asyncio.Task[None] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake = asyncio.Event()
        self.persistence_writes = 0

    def start(self) -> None:
        if self._task is None:
            self._loop = asyncio.get_running_loop()
            self._task = asyncio.create_task(self._run())

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await self.flush(force=True)
        self._loop = None

    def update(
        self,
        session_id: str,
        persisted_sequence: int,
        persisted_reserved_sequence: int,
        persisted_slide_id: str | None,
        slide_id: str,
        viewport: dict[str, float],
    ) -> tuple[PresenterSnapshot, bool]:
        now = self._clock()
        with self._lock:
            previous = self._states.get(session_id)
            reserved_until = max(
                persisted_reserved_sequence,
                self._reserved_until.get(session_id, 0),
            )
            sequence = (
                previous.sequence + 1
                if previous is not None
                else max(persisted_sequence, persisted_reserved_sequence) + 1
            )
            if sequence > reserved_until:
                reserved_until = self._reserve(session_id, sequence + 1023)
                if reserved_until < sequence:
                    raise RuntimeError("Presenter sequence reservation did not advance")
                self._reserved_until[session_id] = reserved_until
            previous_slide_id = previous.slide_id if previous is not None else persisted_slide_id
            slide_changed = previous_slide_id is not None and previous_slide_id != slide_id
            snapshot = PresenterSnapshot(session_id, sequence, slide_id, viewport)
            self._states[session_id] = snapshot
            self._dirty.add(session_id)
            self._last_persisted_at.setdefault(session_id, now)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._wake.set)
        return snapshot, slide_changed

    def current(self, session_id: str) -> PresenterSnapshot | None:
        with self._lock:
            return self._states.get(session_id)

    def mark_persisted(self, session_id: str, sequence: int) -> None:
        with self._lock:
            self.persistence_writes += 1
            self._last_persisted_at[session_id] = self._clock()
            current = self._states.get(session_id)
            if current is None or current.sequence <= sequence:
                self._dirty.discard(session_id)

    def forget(self, session_id: str) -> None:
        with self._lock:
            self._states.pop(session_id, None)
            self._dirty.discard(session_id)
            self._in_flight.discard(session_id)
            self._last_persisted_at.pop(session_id, None)
            self._reserved_until.pop(session_id, None)

    async def flush(self, *, force: bool = False) -> None:
        now = self._clock()
        with self._lock:
            snapshots = [
                self._states[session_id]
                for session_id in tuple(self._dirty)
                if session_id not in self._in_flight
                and (
                    force
                    or now - self._last_persisted_at.get(session_id, now) >= self._interval
                )
            ]
            self._in_flight.update(item.session_id for item in snapshots)
        if not snapshots:
            return
        try:
            await asyncio.to_thread(self._persist, snapshots)
        except Exception:
            with self._lock:
                self._in_flight.difference_update(item.session_id for item in snapshots)
            raise
        with self._lock:
            completed_at = self._clock()
            self.persistence_writes += len(snapshots)
            for snapshot in snapshots:
                self._in_flight.discard(snapshot.session_id)
                self._last_persisted_at[snapshot.session_id] = completed_at
                current = self._states.get(snapshot.session_id)
                if current is None or current.sequence <= snapshot.sequence:
                    self._dirty.discard(snapshot.session_id)

    async def _run(self) -> None:
        while True:
            self._wake.clear()
            now = self._clock()
            with self._lock:
                due_at = [
                    self._last_persisted_at.get(session_id, now) + self._interval
                    for session_id in self._dirty
                    if session_id not in self._in_flight
                ]
            if not due_at:
                await self._wake.wait()
                continue
            delay = max(0.0, min(due_at) - now)
            if delay > 0:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=delay)
                    continue
                except TimeoutError:
                    pass
            try:
                await self.flush()
            except Exception:
                # Retain dirty state and retry on the next bounded interval.
                await asyncio.sleep(self._interval)
