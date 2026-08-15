import asyncio
import json
import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal, cast

MAX_EVENT_BYTES = 4096
# Critical events remain discrete. Slow clients are closed instead of silently
# losing an event after this bounded queue fills; state endpoints repair the gap.
SUBSCRIBER_QUEUE_SIZE = 512
PARTICIPANT_RECONNECT_GRACE_SECONDS = 60.0
ROSTER_EVENT_INTERVAL_SECONDS = 1.0
EVENT_LOOP_SAMPLE_SECONDS = 0.05


@dataclass(eq=False)
class Subscriber:
    audience: Literal["teacher", "student"]
    participant_id: str | None = None
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
    )
    latest_presenter: dict[str, Any] | None = None
    latest_pointer: dict[str, Any] | None = None
    latest_roster: dict[str, Any] | None = None
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False
    registered: bool = False

    async def next_event(self) -> dict[str, Any] | None:
        while True:
            candidates: list[tuple[str, dict[str, Any]]] = []
            if not self.queue.empty():
                queued = cast(
                    deque[dict[str, Any]],
                    getattr(self.queue, "_queue"),  # noqa: B009
                )
                candidates.append(("queue", queued[0]))
            if self.latest_presenter is not None:
                candidates.append(("presenter", self.latest_presenter))
            if self.latest_pointer is not None:
                candidates.append(("pointer", self.latest_pointer))
            if self.latest_roster is not None:
                candidates.append(("roster", self.latest_roster))
            if candidates:
                source, event = min(candidates, key=lambda item: item[1]["eventSequence"])
                if source == "queue":
                    return self.queue.get_nowait()
                if source == "presenter":
                    self.latest_presenter = None
                elif source == "pointer":
                    self.latest_pointer = None
                else:
                    self.latest_roster = None
                return event
            if self.closed:
                return None
            self.wake.clear()
            if (
                not self.queue.empty()
                or self.latest_presenter is not None
                or self.latest_pointer is not None
                or self.latest_roster is not None
                or self.closed
            ):
                continue
            await self.wake.wait()


class ClassroomHub:
    """One-process bounded SSE fanout. Persistent state remains in SQLite."""

    def __init__(
        self,
        *,
        roster_interval_seconds: float = ROSTER_EVENT_INTERVAL_SECONDS,
        reconnect_grace_seconds: float = PARTICIPANT_RECONNECT_GRACE_SECONDS,
    ) -> None:
        self.hub_epoch = str(uuid.uuid4())
        self._roster_interval_seconds = roster_interval_seconds
        self._reconnect_grace_seconds = reconnect_grace_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[str, set[Subscriber]] = defaultdict(set)
        self._participant_subscribers: dict[tuple[str, str], Subscriber] = {}
        self._terminated_sessions: set[str] = set()
        self._event_sequences: dict[tuple[str, str], int] = defaultdict(int)
        self._participant_connections: dict[tuple[str, str], int] = defaultdict(int)
        self._participant_disconnected_at: dict[tuple[str, str], float] = {}
        self._participant_stale: set[tuple[str, str]] = set()
        self._presence_expiry_handles: dict[tuple[str, str], tuple[float, asyncio.TimerHandle]] = {}
        self._seen_participants: set[tuple[str, str]] = set()
        self._participant_retirements: set[tuple[str, str]] = set()
        self._retired_participants: set[tuple[str, str]] = set()
        self._presence_lock = threading.RLock()
        self._roster_lock = threading.Lock()
        self._roster_versions: dict[str, int] = defaultdict(int)
        self._roster_pending: dict[str, int] = {}
        self._roster_last_published_at: dict[str, float] = {}
        self._roster_handles: dict[str, asyncio.TimerHandle] = {}
        self._presenter_last_at: dict[str, float] = {}
        self._transient_lock = threading.Lock()
        self._active_pins: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        self._teacher_pointers: dict[str, dict[str, Any]] = {}
        self._teaching_annotations: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._control_requests: dict[str, dict[str, float]] = defaultdict(dict)
        self.current_connections = 0
        self.peak_connections = 0
        self.presenter_events_published = 0
        self.presenter_events_coalesced = 0
        self.slow_subscribers_disconnected = 0
        self.queue_overflows = 0
        self.reconnects = 0
        self.queue_max_depth = 0
        self._event_loop_lag_ms: deque[float] = deque(maxlen=2048)
        self._capacity_safety_stops: dict[str, tuple[str, str, str, set[str]]] = {}
        self._synthetic_stage_acks: dict[tuple[str, str, str], set[int]] = defaultdict(set)
        self._recovery_ready_epoch_ms: dict[str, int] = {}
        self._capacity_lock = threading.Lock()
        self._event_loop_sample_handle: asyncio.TimerHandle | None = None

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        expected = time.monotonic() + EVENT_LOOP_SAMPLE_SECONDS
        self._event_loop_sample_handle = self._loop.call_later(
            EVENT_LOOP_SAMPLE_SECONDS, self._sample_event_loop, expected
        )

    def _sample_event_loop(self, expected: float) -> None:
        loop = self._loop
        if loop is None:
            return
        now = time.monotonic()
        self._event_loop_lag_ms.append(max(0.0, (now - expected) * 1000))
        next_expected = now + EVENT_LOOP_SAMPLE_SECONDS
        self._event_loop_sample_handle = loop.call_later(
            EVENT_LOOP_SAMPLE_SECONDS, self._sample_event_loop, next_expected
        )

    def close(self) -> None:
        if self._event_loop_sample_handle is not None:
            self._event_loop_sample_handle.cancel()
            self._event_loop_sample_handle = None
        for session_id, subscribers in tuple(self._subscribers.items()):
            for subscriber in tuple(subscribers):
                self._retire_subscriber(session_id, subscriber)
        self._subscribers.clear()
        self._participant_subscribers.clear()
        self._terminated_sessions.clear()
        for handle in self._roster_handles.values():
            handle.cancel()
        self._roster_handles.clear()
        for _, handle in self._presence_expiry_handles.values():
            handle.cancel()
        self._presence_expiry_handles.clear()
        with self._roster_lock:
            self._roster_versions.clear()
            self._roster_pending.clear()
            self._roster_last_published_at.clear()
        with self._presence_lock:
            self._participant_connections.clear()
            self._participant_disconnected_at.clear()
            self._participant_stale.clear()
            self._seen_participants.clear()
            self._participant_retirements.clear()
            self._retired_participants.clear()
        self._presenter_last_at.clear()
        with self._transient_lock:
            self._active_pins.clear()
            self._teacher_pointers.clear()
            self._teaching_annotations.clear()
            self._control_requests.clear()
        self.current_connections = 0
        self._loop = None

    def publish(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        critical: bool,
        audience: Literal["all", "teacher"] = "all",
    ) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(
            self._publish, session_id, event_type, payload, critical, audience
        )

    def terminate_session(self, session_id: str, *, state_version: int) -> None:
        """Deliver the terminal event, retire streams, and clear in-memory state."""

        with self._presence_lock:
            self._terminated_sessions.add(session_id)
        loop = self._loop
        if loop is None:
            self.clear_session(session_id)
            return
        loop.call_soon_threadsafe(self._terminate_session, session_id, state_version)

    def _terminate_session(self, session_id: str, state_version: int) -> None:
        self._publish(
            session_id,
            "session-ended",
            {"stateVersion": state_version},
            True,
            "all",
        )
        for subscriber in tuple(self._subscribers.get(session_id, ())):
            self._retire_subscriber(session_id, subscriber, drain=False)
        self._subscribers.pop(session_id, None)
        self.clear_session(session_id)

    def _publish(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        critical: bool,
        audience: Literal["all", "teacher"] = "all",
    ) -> None:
        if event_type == "presenter":
            self.presenter_events_published += 1
        destinations = ("teacher", "student") if audience == "all" else ("teacher",)
        for destination in destinations:
            key = (session_id, destination)
            self._event_sequences[key] += 1
            event = {
                "type": event_type,
                "hubEpoch": self.hub_epoch,
                "eventSequence": self._event_sequences[key],
                **payload,
            }
            encoded = json.dumps(event, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
                raise ValueError("Classroom event exceeds 4 KiB")
            # The event object is shared read-only by every subscriber. Cache its
            # wire representation once instead of serializing it 300 times.
            event["_encoded"] = encoded
            for subscriber in tuple(self._subscribers.get(session_id, ())):
                if subscriber.audience != destination:
                    continue
                if event_type == "presenter":
                    if subscriber.latest_presenter is not None:
                        self.presenter_events_coalesced += 1
                    subscriber.latest_presenter = event
                    subscriber.wake.set()
                    continue
                if event_type == "pointer":
                    subscriber.latest_pointer = event
                    subscriber.wake.set()
                    continue
                if event_type == "roster-changed":
                    subscriber.latest_roster = event
                    subscriber.wake.set()
                    continue
                try:
                    subscriber.queue.put_nowait(event)
                    self.queue_max_depth = max(self.queue_max_depth, subscriber.queue.qsize())
                    subscriber.wake.set()
                except asyncio.QueueFull:
                    self.queue_overflows += 1
                    if critical:
                        self.slow_subscribers_disconnected += 1
                        self._retire_subscriber(session_id, subscriber)
                    # Presenter deltas are intentionally coalescible: the client
                    # resynchronizes through HTTP if it detects a sequence gap.

    @asynccontextmanager
    async def subscribe(
        self,
        session_id: str,
        audience: Literal["teacher", "student"] = "student",
        participant_id: str | None = None,
    ) -> AsyncIterator[Subscriber]:
        subscriber = Subscriber(audience=audience, participant_id=participant_id)
        with self._presence_lock:
            admitted = session_id not in self._terminated_sessions
            if admitted and participant_id is not None:
                admitted = self.participant_connected(session_id, participant_id) is not None
            if admitted:
                if participant_id is not None:
                    key = (session_id, participant_id)
                    stale = self._participant_subscribers.get(key)
                    if stale is not None:
                        self._retire_subscriber(session_id, stale)
                    self._participant_subscribers[key] = subscriber
                self._subscribers[session_id].add(subscriber)
                subscriber.registered = True
                self.current_connections += 1
                self.peak_connections = max(self.peak_connections, self.current_connections)
            else:
                subscriber.closed = True
        if not admitted:
            yield subscriber
            return
        try:
            yield subscriber
        finally:
            if participant_id is not None:
                key = (session_id, participant_id)
                if self._participant_subscribers.get(key) is subscriber:
                    self._participant_subscribers.pop(key, None)
            self._retire_subscriber(session_id, subscriber)
            if participant_id is not None:
                self.participant_disconnected(session_id, participant_id)

    def _retire_subscriber(
        self, session_id: str, subscriber: Subscriber, *, drain: bool = True
    ) -> None:
        if subscriber.participant_id is not None:
            key = (session_id, subscriber.participant_id)
            if self._participant_subscribers.get(key) is subscriber:
                self._participant_subscribers.pop(key, None)
        if subscriber.registered:
            self._subscribers[session_id].discard(subscriber)
            subscriber.registered = False
            self.current_connections = max(0, self.current_connections - 1)
        self._close_subscriber(subscriber, drain=drain)

    def subscription_is_current(self, session_id: str, subscriber: Subscriber) -> bool:
        """Atomically revalidate stream admission after asynchronous bootstrap work."""

        with self._presence_lock:
            if (
                session_id in self._terminated_sessions
                or not subscriber.registered
                or subscriber.closed
                or subscriber not in self._subscribers.get(session_id, ())
            ):
                return False
            participant_id = subscriber.participant_id
            return (
                participant_id is None
                or self._participant_subscribers.get((session_id, participant_id)) is subscriber
            )

    @staticmethod
    def _close_subscriber(subscriber: Subscriber, *, drain: bool = True) -> None:
        if drain:
            while not subscriber.queue.empty():
                subscriber.queue.get_nowait()
            subscriber.latest_presenter = None
            subscriber.latest_pointer = None
            subscriber.latest_roster = None
        subscriber.closed = True
        subscriber.wake.set()

    def mark_roster_changed(self, session_id: str) -> int:
        with self._roster_lock:
            version = self._roster_versions[session_id] + 1
            self._roster_versions[session_id] = version
            self._roster_pending[session_id] = version
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._schedule_roster_changed, session_id)
        return version

    def roster_version(self, session_id: str) -> int:
        with self._roster_lock:
            return self._roster_versions.get(session_id, 0)

    def _schedule_roster_changed(self, session_id: str) -> None:
        with self._roster_lock:
            pending = session_id in self._roster_pending
        if not pending:
            return
        existing = self._roster_handles.get(session_id)
        if existing is not None and not existing.cancelled():
            return
        now = time.monotonic()
        last_published = self._roster_last_published_at.get(session_id)
        if last_published is None or now - last_published >= self._roster_interval_seconds:
            self._emit_roster_changed(session_id)
            return
        loop = self._loop
        if loop is None:
            return
        delay = self._roster_interval_seconds - (now - last_published)
        self._roster_handles[session_id] = loop.call_later(
            delay, self._emit_roster_changed, session_id
        )

    def _emit_roster_changed(self, session_id: str) -> None:
        self._roster_handles.pop(session_id, None)
        with self._roster_lock:
            version = self._roster_pending.pop(session_id, None)
        if version is None:
            return
        self._roster_last_published_at[session_id] = time.monotonic()
        self._publish(
            session_id,
            "roster-changed",
            {"rosterVersion": version},
            False,
            "teacher",
        )

    def _cancel_roster_session(self, session_id: str) -> None:
        handle = self._roster_handles.pop(session_id, None)
        if handle is not None:
            handle.cancel()
        self._roster_last_published_at.pop(session_id, None)

    def metrics(self) -> dict[str, int | float | str | list[str]]:
        with self._presence_lock:
            active_participants = len(self._participant_connections)
        ordered_lag = sorted(self._event_loop_lag_ms)
        lag_index = max(0, min(len(ordered_lag) - 1, int(len(ordered_lag) * 0.99)))
        with self._capacity_lock:
            safety_stages = {
                stage for stage, _digest, _nonce, _causes in self._capacity_safety_stops.values()
            }
            safety_digests = {
                digest for _stage, digest, _nonce, _causes in self._capacity_safety_stops.values()
            }
            safety_nonce_digests = {
                nonce_digest
                for _stage, _digest, nonce_digest, _causes in self._capacity_safety_stops.values()
            }
            safety_causes = sorted(
                {
                    cause
                    for _stage, _digest, _nonce, causes in self._capacity_safety_stops.values()
                    for cause in causes
                }
            )
            recovery_ready = max(self._recovery_ready_epoch_ms.values(), default=0)
        return {
            "currentSseConnections": self.current_connections,
            "peakSseConnections": self.peak_connections,
            "presenterEventsPublished": self.presenter_events_published,
            "presenterEventsCoalesced": self.presenter_events_coalesced,
            "slowSubscribersDisconnected": self.slow_subscribers_disconnected,
            "queueOverflows": self.queue_overflows,
            "reconnects": self.reconnects,
            "activeParticipants": active_participants,
            "queueMaxDepth": self.queue_max_depth,
            "queueCapacity": SUBSCRIBER_QUEUE_SIZE,
            "eventLoopP99Ms": round(ordered_lag[lag_index], 3) if ordered_lag else 0.0,
            "capacitySafetyStopCauses": safety_causes,
            "capacitySafetyStopStage": next(iter(safety_stages)) if len(safety_stages) == 1 else "",
            "capacitySafetyStopPlanDigest": (
                next(iter(safety_digests)) if len(safety_digests) == 1 else ""
            ),
            "capacitySafetyStopNonceDigest": (
                next(iter(safety_nonce_digests)) if len(safety_nonce_digests) == 1 else ""
            ),
            "recoveryReadyEpochMs": recovery_ready,
        }

    def signal_capacity_safety_stop(
        self,
        session_id: str,
        stage_name: str,
        plan_digest: str,
        nonce_digest: str,
        causes: set[str],
    ) -> None:
        with self._capacity_lock:
            current_stage, current_digest, current_nonce, current_causes = (
                self._capacity_safety_stops.get(
                    session_id, (stage_name, plan_digest, nonce_digest, set())
                )
            )
            if (
                current_stage != stage_name
                or current_digest != plan_digest
                or current_nonce != nonce_digest
            ):
                current_causes = set()
            current_causes.update(causes)
            self._capacity_safety_stops[session_id] = (
                stage_name,
                plan_digest,
                nonce_digest,
                current_causes,
            )

    def acknowledge_synthetic_stage(
        self, session_id: str, run_id: str, stage_name: str, shard_index: int
    ) -> int:
        key = (session_id, run_id, stage_name)
        with self._capacity_lock:
            self._synthetic_stage_acks[key].add(shard_index)
            return len(self._synthetic_stage_acks[key])

    def mark_recovery_ready(self, session_id: str, epoch_ms: int) -> None:
        with self._capacity_lock:
            self._recovery_ready_epoch_ms[session_id] = epoch_ms

    def event_sequence(
        self,
        session_id: str,
        audience: Literal["teacher", "student"],
    ) -> int:
        return self._event_sequences.get((session_id, audience), 0)

    def restore_participants(self, session_id: str, participant_ids: list[str]) -> None:
        """Start a current-epoch reconnect grace for durable live membership."""

        disconnected_at = time.monotonic()
        restored: list[tuple[str, str]] = []
        with self._presence_lock:
            if session_id in self._terminated_sessions:
                return
            for participant_id in participant_ids:
                key = (session_id, participant_id)
                self._seen_participants.add(key)
                self._participant_stale.discard(key)
                self._participant_disconnected_at[key] = disconnected_at
                restored.append(key)
        for key in restored:
            self._schedule_presence_expiry(key, disconnected_at)

    def participant_connected(self, session_id: str, participant_id: str) -> bool | None:
        with self._presence_lock:
            key = (session_id, participant_id)
            if (
                session_id in self._terminated_sessions
                or key in self._participant_retirements
                or key in self._retired_participants
            ):
                return None
            if key in self._seen_participants and self._participant_connections.get(key, 0) == 0:
                self.reconnects += 1
            self._seen_participants.add(key)
            self._participant_stale.discard(key)
            disconnected_at = self._participant_disconnected_at.pop(key, None)
            if disconnected_at is not None:
                self._request_presence_expiry_cancel(key, disconnected_at)
            self._participant_connections[key] += 1
            first_connection = self._participant_connections[key] == 1
            if first_connection:
                self.mark_roster_changed(session_id)
            return first_connection

    def participant_disconnected(self, session_id: str, participant_id: str) -> bool:
        with self._presence_lock:
            key = (session_id, participant_id)
            count = self._participant_connections.get(key, 0)
            if count <= 0:
                return False
            if count == 1:
                self._participant_connections.pop(key, None)
                disconnected_at = time.monotonic()
                self._participant_stale.discard(key)
                self._participant_disconnected_at[key] = disconnected_at
                self._schedule_presence_expiry(key, disconnected_at)
                self.mark_roster_changed(session_id)
                return True
            self._participant_connections[key] = count - 1
            return False

    def participant_is_connected(self, session_id: str, participant_id: str) -> bool:
        with self._presence_lock:
            return self._participant_connections.get((session_id, participant_id), 0) > 0

    def participant_activity(self, session_id: str, participant_id: str) -> None:
        with self._presence_lock:
            key = (session_id, participant_id)
            if (
                session_id in self._terminated_sessions
                or key in self._participant_retirements
                or key in self._retired_participants
            ):
                return
            self._participant_stale.discard(key)
            if self._participant_connections.get(key, 0) == 0:
                disconnected_at = time.monotonic()
                self._participant_disconnected_at[key] = disconnected_at
                self._schedule_presence_expiry(key, disconnected_at)

    def _schedule_presence_expiry(self, key: tuple[str, str], disconnected_at: float) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._install_presence_expiry, key, disconnected_at)

    def _install_presence_expiry(self, key: tuple[str, str], disconnected_at: float) -> None:
        with self._presence_lock:
            if (
                key[0] in self._terminated_sessions
                or self._participant_connections.get(key, 0) > 0
                or self._participant_disconnected_at.get(key) != disconnected_at
            ):
                return
        existing = self._presence_expiry_handles.pop(key, None)
        if existing is not None:
            existing[1].cancel()
        loop = self._loop
        if loop is None:
            return
        remaining = max(
            0.0,
            disconnected_at + self._reconnect_grace_seconds - time.monotonic(),
        )
        handle = loop.call_later(remaining, self._expire_participant_presence, key, disconnected_at)
        self._presence_expiry_handles[key] = (disconnected_at, handle)

    def _request_presence_expiry_cancel(self, key: tuple[str, str], disconnected_at: float) -> None:
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._cancel_presence_expiry, key, disconnected_at)

    def _cancel_presence_expiry(self, key: tuple[str, str], disconnected_at: float) -> None:
        scheduled = self._presence_expiry_handles.get(key)
        if scheduled is None or scheduled[0] != disconnected_at:
            return
        self._presence_expiry_handles.pop(key, None)
        scheduled[1].cancel()

    def _expire_participant_presence(self, key: tuple[str, str], disconnected_at: float) -> None:
        scheduled = self._presence_expiry_handles.get(key)
        if scheduled is None or scheduled[0] != disconnected_at:
            return
        with self._presence_lock:
            if (
                key[0] in self._terminated_sessions
                or self._participant_connections.get(key, 0) > 0
                or self._participant_disconnected_at.get(key) != disconnected_at
                or key in self._participant_retirements
                or key in self._retired_participants
            ):
                self._presence_expiry_handles.pop(key, None)
                return
            remaining = disconnected_at + self._reconnect_grace_seconds - time.monotonic()
            if remaining > 0:
                loop = self._loop
                if loop is not None:
                    handle = loop.call_later(
                        remaining,
                        self._expire_participant_presence,
                        key,
                        disconnected_at,
                    )
                    self._presence_expiry_handles[key] = (disconnected_at, handle)
                return
            self._presence_expiry_handles.pop(key, None)
            self._participant_disconnected_at.pop(key, None)
            self._participant_stale.add(key)
            self.mark_roster_changed(key[0])

    def participant_presence(self, session_id: str, participant_id: str) -> str:
        with self._presence_lock:
            key = (session_id, participant_id)
            if key in self._participant_retirements or key in self._retired_participants:
                return "disconnected"
            if self._participant_connections.get(key, 0) > 0:
                return "connected"
            if key in self._participant_disconnected_at:
                return "reconnecting"
            return "disconnected"

    def participant_is_present(self, session_id: str, participant_id: str) -> bool:
        return self.participant_presence(session_id, participant_id) != "disconnected"

    def participant_presence_snapshot(
        self, session_id: str, participant_ids: list[str]
    ) -> dict[str, str]:
        snapshot, _ = self.participant_roster_snapshot(session_id, participant_ids)
        return snapshot

    def participant_roster_snapshot(
        self, session_id: str, participant_ids: list[str]
    ) -> tuple[dict[str, str], int]:
        with self._presence_lock, self._roster_lock:
            snapshot: dict[str, str] = {}
            for participant_id in participant_ids:
                key = (session_id, participant_id)
                if key in self._participant_retirements or key in self._retired_participants:
                    snapshot[participant_id] = "disconnected"
                elif self._participant_connections.get(key, 0) > 0:
                    snapshot[participant_id] = "connected"
                else:
                    snapshot[participant_id] = (
                        "reconnecting"
                        if key in self._participant_disconnected_at
                        else "disconnected"
                    )
            return snapshot, self._roster_versions.get(session_id, 0)

    def reserve_stale_participants(
        self, session_id: str, recent_by_participant_id: dict[str, bool]
    ) -> tuple[set[str], int]:
        """Linearize stale retirement and capacity accounting without database I/O."""

        with self._presence_lock:
            reserved_ids: set[str] = set()
            for participant_id, is_recent in recent_by_participant_id.items():
                key = (session_id, participant_id)
                if (
                    key in self._participant_stale
                    and not is_recent
                    and key not in self._participant_retirements
                    and key not in self._retired_participants
                ):
                    self._participant_retirements.add(key)
                    reserved_ids.add(participant_id)

            retired = self._participant_retirements | self._retired_participants
            active_count = sum(
                (session_id, participant_id) not in retired
                for participant_id in recent_by_participant_id
            )
            return reserved_ids, active_count

    def cancel_stale_reservations(self, session_id: str, participant_ids: set[str]) -> None:
        with self._presence_lock:
            for participant_id in participant_ids:
                self._participant_retirements.discard((session_id, participant_id))

    def complete_stale_reservations(self, session_id: str, participant_ids: set[str]) -> None:
        with self._presence_lock:
            for participant_id in participant_ids:
                key = (session_id, participant_id)
                self._participant_retirements.discard(key)
                self._retired_participants.add(key)
                self._participant_connections.pop(key, None)
                disconnected_at = self._participant_disconnected_at.pop(key, None)
                self._participant_stale.discard(key)
                self._seen_participants.discard(key)
                if disconnected_at is not None:
                    self._request_presence_expiry_cancel(key, disconnected_at)
        for participant_id in participant_ids:
            self.clear_pin(session_id, participant_id)
            self.cancel_control_request(session_id, participant_id)

    def allow_presenter(self, actor_id: str, *, interval_seconds: float = 0.04) -> bool:
        now = time.monotonic()
        previous = self._presenter_last_at.get(actor_id, 0.0)
        if now - previous < interval_seconds:
            return False
        self._presenter_last_at[actor_id] = now
        return True

    def set_pin(
        self,
        session_id: str,
        participant_id: str,
        pin: dict[str, Any],
    ) -> None:
        with self._transient_lock:
            self._active_pins[session_id][participant_id] = dict(pin)

    def clear_pin(self, session_id: str, participant_id: str) -> bool:
        with self._transient_lock:
            pins = self._active_pins.get(session_id)
            if not pins or participant_id not in pins:
                return False
            del pins[participant_id]
            if not pins:
                self._active_pins.pop(session_id, None)
            return True

    def clear_pin_if(
        self,
        session_id: str,
        participant_id: str,
        *,
        slide_id: str,
        x: float,
        y: float,
    ) -> bool:
        with self._transient_lock:
            pins = self._active_pins.get(session_id)
            pin = pins.get(participant_id) if pins else None
            if (
                pin is None
                or pin.get("slideId") != slide_id
                or pin.get("x") != x
                or pin.get("y") != y
            ):
                return False
            assert pins is not None
            del pins[participant_id]
            if not pins:
                self._active_pins.pop(session_id, None)
            return True

    def active_pins(self, session_id: str) -> list[dict[str, Any]]:
        with self._transient_lock:
            return [dict(pin) for pin in self._active_pins.get(session_id, {}).values()]

    def set_teacher_pointer(self, session_id: str, pointer: dict[str, Any]) -> None:
        with self._transient_lock:
            self._teacher_pointers[session_id] = dict(pointer)

    def teacher_pointer(self, session_id: str) -> dict[str, Any] | None:
        with self._transient_lock:
            pointer = self._teacher_pointers.get(session_id)
            return dict(pointer) if pointer else None

    def clear_teacher_pointer(self, session_id: str) -> bool:
        with self._transient_lock:
            return self._teacher_pointers.pop(session_id, None) is not None

    def add_teaching_annotation(
        self, session_id: str, annotation: dict[str, Any]
    ) -> list[dict[str, Any]]:
        with self._transient_lock:
            annotations = self._teaching_annotations[session_id]
            annotations[:] = [
                item for item in annotations if item.get("id") != annotation.get("id")
            ]
            annotations.append(dict(annotation))
            del annotations[:-40]
            return [dict(item) for item in annotations]

    def remove_teaching_annotation(self, session_id: str, annotation_id: str) -> bool:
        with self._transient_lock:
            annotations = self._teaching_annotations.get(session_id)
            if not annotations:
                return False
            remaining = [item for item in annotations if item.get("id") != annotation_id]
            if len(remaining) == len(annotations):
                return False
            if remaining:
                self._teaching_annotations[session_id] = remaining
            else:
                self._teaching_annotations.pop(session_id, None)
            return True

    def teaching_annotations(self, session_id: str) -> list[dict[str, Any]]:
        with self._transient_lock:
            return [dict(item) for item in self._teaching_annotations.get(session_id, [])]

    def clear_teaching_annotations(self, session_id: str) -> bool:
        with self._transient_lock:
            return self._teaching_annotations.pop(session_id, None) is not None

    def request_control(self, session_id: str, participant_id: str) -> bool:
        with self._transient_lock:
            requests = self._control_requests[session_id]
            if participant_id in requests:
                return False
            requests[participant_id] = time.time()
            return True

    def cancel_control_request(self, session_id: str, participant_id: str) -> bool:
        with self._transient_lock:
            requests = self._control_requests.get(session_id)
            if not requests or participant_id not in requests:
                return False
            del requests[participant_id]
            if not requests:
                self._control_requests.pop(session_id, None)
            return True

    def control_requests(self, session_id: str) -> dict[str, float]:
        with self._transient_lock:
            return dict(self._control_requests.get(session_id, {}))

    def clear_participant(self, session_id: str, participant_id: str) -> None:
        with self._presence_lock:
            key = (session_id, participant_id)
            self._participant_connections.pop(key, None)
            disconnected_at = self._participant_disconnected_at.pop(key, None)
            self._participant_stale.discard(key)
            self._seen_participants.discard(key)
            self._participant_retirements.discard(key)
            self._retired_participants.discard(key)
            if disconnected_at is not None:
                self._request_presence_expiry_cancel(key, disconnected_at)
        self.clear_pin(session_id, participant_id)
        self.cancel_control_request(session_id, participant_id)

    def clear_session(self, session_id: str) -> None:
        with self._roster_lock:
            self._roster_versions.pop(session_id, None)
            self._roster_pending.pop(session_id, None)
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._cancel_roster_session, session_id)
        with self._presence_lock:
            presence_keys = {
                key
                for key in (
                    self._seen_participants
                    | set(self._participant_connections)
                    | set(self._participant_disconnected_at)
                    | self._participant_stale
                    | self._participant_retirements
                    | self._retired_participants
                )
                if key[0] == session_id
            }
            for key in presence_keys:
                self._participant_connections.pop(key, None)
                disconnected_at = self._participant_disconnected_at.pop(key, None)
                self._participant_stale.discard(key)
                self._seen_participants.discard(key)
                self._participant_retirements.discard(key)
                self._retired_participants.discard(key)
                if disconnected_at is not None:
                    self._request_presence_expiry_cancel(key, disconnected_at)
        with self._transient_lock:
            self._active_pins.pop(session_id, None)
            self._control_requests.pop(session_id, None)
            self._teacher_pointers.pop(session_id, None)
            self._teaching_annotations.pop(session_id, None)

    def reset_session(self, session_id: str) -> None:
        """Close every stream and clear transient state without retiring the room."""
        for subscriber in tuple(self._subscribers.get(session_id, ())):
            self._retire_subscriber(session_id, subscriber)
        self._subscribers.pop(session_id, None)
        self.clear_session(session_id)
        with self._capacity_lock:
            self._capacity_safety_stops.pop(session_id, None)
            self._recovery_ready_epoch_ms.pop(session_id, None)
            for key in tuple(self._synthetic_stage_acks):
                if key[0] == session_id:
                    self._synthetic_stage_acks.pop(key, None)
