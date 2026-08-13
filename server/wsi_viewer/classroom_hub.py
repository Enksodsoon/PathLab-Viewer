import asyncio
import json
import threading
import time
import uuid
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Literal

MAX_EVENT_BYTES = 4096
# A teacher may receive one critical presence delta for every seat while a full
# class reconnects. asyncio.Queue uses a deque (it does not preallocate these
# slots), so this bound covers the 300-seat burst without adding idle memory.
SUBSCRIBER_QUEUE_SIZE = 384


@dataclass(eq=False)
class Subscriber:
    audience: Literal["teacher", "student"]
    queue: asyncio.Queue[dict[str, Any]] = field(
        default_factory=lambda: asyncio.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
    )
    latest_presenter: dict[str, Any] | None = None
    latest_pointer: dict[str, Any] | None = None
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    closed: bool = False

    async def next_event(self) -> dict[str, Any] | None:
        while True:
            if not self.queue.empty():
                return self.queue.get_nowait()
            if self.latest_presenter is not None and self.latest_pointer is not None:
                if self.latest_presenter["eventSequence"] <= self.latest_pointer["eventSequence"]:
                    event = self.latest_presenter
                    self.latest_presenter = None
                else:
                    event = self.latest_pointer
                    self.latest_pointer = None
                return event
            if self.latest_presenter is not None:
                event = self.latest_presenter
                self.latest_presenter = None
                return event
            if self.latest_pointer is not None:
                event = self.latest_pointer
                self.latest_pointer = None
                return event
            if self.closed:
                return None
            self.wake.clear()
            if (
                not self.queue.empty()
                or self.latest_presenter is not None
                or self.latest_pointer is not None
                or self.closed
            ):
                continue
            await self.wake.wait()


class ClassroomHub:
    """One-process bounded SSE fanout. Persistent state remains in SQLite."""

    def __init__(self) -> None:
        self.hub_epoch = str(uuid.uuid4())
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: dict[str, set[Subscriber]] = defaultdict(set)
        self._event_sequences: dict[tuple[str, str], int] = defaultdict(int)
        self._participant_connections: dict[tuple[str, str], int] = defaultdict(int)
        self._seen_participants: set[tuple[str, str]] = set()
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

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()

    def close(self) -> None:
        for subscribers in self._subscribers.values():
            for subscriber in subscribers:
                self._close_subscriber(subscriber)
        self._subscribers.clear()
        self._participant_connections.clear()
        self._seen_participants.clear()
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
                try:
                    subscriber.queue.put_nowait(event)
                    subscriber.wake.set()
                except asyncio.QueueFull:
                    self.queue_overflows += 1
                    if critical:
                        self.slow_subscribers_disconnected += 1
                        self._subscribers[session_id].discard(subscriber)
                        self._close_subscriber(subscriber)
                    # Presenter deltas are intentionally coalescible: the client
                    # resynchronizes through HTTP if it detects a sequence gap.

    @asynccontextmanager
    async def subscribe(
        self,
        session_id: str,
        audience: Literal["teacher", "student"] = "student",
    ) -> AsyncIterator[Subscriber]:
        subscriber = Subscriber(audience=audience)
        self._subscribers[session_id].add(subscriber)
        self.current_connections += 1
        self.peak_connections = max(self.peak_connections, self.current_connections)
        try:
            yield subscriber
        finally:
            if subscriber in self._subscribers.get(session_id, set()):
                self._subscribers[session_id].discard(subscriber)
            self.current_connections = max(0, self.current_connections - 1)

    @staticmethod
    def _close_subscriber(subscriber: Subscriber) -> None:
        while not subscriber.queue.empty():
            subscriber.queue.get_nowait()
        subscriber.latest_presenter = None
        subscriber.latest_pointer = None
        subscriber.closed = True
        subscriber.wake.set()

    def metrics(self) -> dict[str, int]:
        return {
            "currentSseConnections": self.current_connections,
            "peakSseConnections": self.peak_connections,
            "presenterEventsPublished": self.presenter_events_published,
            "presenterEventsCoalesced": self.presenter_events_coalesced,
            "slowSubscribersDisconnected": self.slow_subscribers_disconnected,
            "queueOverflows": self.queue_overflows,
            "reconnects": self.reconnects,
            "activeParticipants": len(self._participant_connections),
        }

    def event_sequence(
        self,
        session_id: str,
        audience: Literal["teacher", "student"],
    ) -> int:
        return self._event_sequences.get((session_id, audience), 0)

    def participant_connected(self, session_id: str, participant_id: str) -> bool:
        key = (session_id, participant_id)
        if key in self._seen_participants and self._participant_connections.get(key, 0) == 0:
            self.reconnects += 1
        self._seen_participants.add(key)
        self._participant_connections[key] += 1
        return self._participant_connections[key] == 1

    def participant_disconnected(self, session_id: str, participant_id: str) -> bool:
        key = (session_id, participant_id)
        count = self._participant_connections.get(key, 0)
        if count <= 1:
            self._participant_connections.pop(key, None)
            return True
        self._participant_connections[key] = count - 1
        return False

    def participant_is_connected(self, session_id: str, participant_id: str) -> bool:
        return self._participant_connections.get((session_id, participant_id), 0) > 0

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
        self.clear_pin(session_id, participant_id)
        self.cancel_control_request(session_id, participant_id)

    def clear_session(self, session_id: str) -> None:
        with self._transient_lock:
            self._active_pins.pop(session_id, None)
            self._control_requests.pop(session_id, None)
            self._teacher_pointers.pop(session_id, None)
            self._teaching_annotations.pop(session_id, None)
