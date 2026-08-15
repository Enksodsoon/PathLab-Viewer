import asyncio
import threading
import time
from collections.abc import Callable

import pytest
from wsi_viewer.classroom_hub import MAX_EVENT_BYTES, SUBSCRIBER_QUEUE_SIZE, ClassroomHub


class _PausingPopDict(dict[tuple[str, str], float | int]):
    def __init__(self, values: dict[tuple[str, str], float | int]) -> None:
        super().__init__(values)
        self.popped = threading.Event()
        self.release = threading.Event()

    def pop(self, key: tuple[str, str], default: object = None) -> float | int | object:
        value = super().pop(key, default)
        self.popped.set()
        assert self.release.wait(timeout=2)
        return value


def _assert_presence_read_waits_for_atomic_transition(
    hub: ClassroomHub,
    transition: Callable[[], object],
    pausing_map: _PausingPopDict,
) -> None:
    transition_thread = threading.Thread(target=transition)
    transition_thread.start()
    assert pausing_map.popped.wait(timeout=1)

    observer_entered = threading.Event()
    observer_done = threading.Event()
    observed: list[str] = []

    def observe() -> None:
        observer_entered.set()
        observed.append(hub.participant_presence("session", "participant"))
        observer_done.set()

    observer_thread = threading.Thread(target=observe)
    observer_thread.start()
    assert observer_entered.wait(timeout=1)
    read_was_blocked = not observer_done.wait(timeout=0.1)
    pausing_map.release.set()
    transition_thread.join(timeout=1)
    observer_thread.join(timeout=1)
    assert not transition_thread.is_alive()
    assert not observer_thread.is_alive()
    assert read_was_blocked
    assert observed == ["connected"] or observed == ["reconnecting"]


def test_presence_read_cannot_observe_partial_connect_transition() -> None:
    hub = ClassroomHub()
    hub.participant_activity("session", "participant")
    pausing_map = _PausingPopDict(dict(hub._participant_disconnected_at))
    hub._participant_disconnected_at = pausing_map  # type: ignore[assignment]

    _assert_presence_read_waits_for_atomic_transition(
        hub,
        lambda: hub.participant_connected("session", "participant"),
        pausing_map,
    )


def test_presence_read_cannot_observe_partial_disconnect_transition() -> None:
    hub = ClassroomHub()
    hub.participant_connected("session", "participant")
    pausing_map = _PausingPopDict(dict(hub._participant_connections))
    hub._participant_connections = pausing_map  # type: ignore[assignment]

    _assert_presence_read_waits_for_atomic_transition(
        hub,
        lambda: hub.participant_disconnected("session", "participant"),
        pausing_map,
    )


def test_hub_discrete_queue_covers_bounded_reconnect_burst() -> None:
    assert SUBSCRIBER_QUEUE_SIZE == 512


def test_hub_replaces_stale_participant_stream() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with (
            hub.subscribe("session", "student", participant_id="participant") as stale,
            hub.subscribe("session", "student", participant_id="participant") as current,
        ):
            assert await asyncio.wait_for(stale.next_event(), timeout=1) is None
            assert stale.closed is True
            assert current.closed is False
            assert hub.current_connections == 1

    asyncio.run(scenario())


def test_hub_terminates_session_streams_after_terminal_event_without_recreating_presence() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        assert hub.participant_connected("session", "participant") is True
        async with hub.subscribe(
            "session", "student", participant_id="participant"
        ) as subscriber:
            hub.terminate_session("session", state_version=9)
            terminal = await asyncio.wait_for(subscriber.next_event(), timeout=1)

            assert terminal is not None and terminal["type"] == "session-ended"
            assert terminal["stateVersion"] == 9
            assert await asyncio.wait_for(subscriber.next_event(), timeout=1) is None
            assert hub.current_connections == 0
            assert hub.participant_disconnected("session", "participant") is False
            assert hub.roster_version("session") == 0
            assert hub.metrics()["activeParticipants"] == 0

    asyncio.run(scenario())


def test_hub_coalesces_teacher_only_roster_changes() -> None:
    async def scenario() -> None:
        hub = ClassroomHub(roster_interval_seconds=0.02)
        hub.start()
        async with (
            hub.subscribe("session", "teacher") as teacher,
            hub.subscribe("session", "student") as student,
        ):
            assert hub.mark_roster_changed("session") == 1
            first = await asyncio.wait_for(teacher.next_event(), timeout=1)
            assert first is not None
            assert first["type"] == "roster-changed"
            assert first["rosterVersion"] == 1

            assert hub.mark_roster_changed("session") == 2
            assert hub.mark_roster_changed("session") == 3
            second = await asyncio.wait_for(teacher.next_event(), timeout=1)
            assert second is not None
            assert second["type"] == "roster-changed"
            assert second["rosterVersion"] == 3

            with pytest.raises(TimeoutError):
                await asyncio.wait_for(teacher.next_event(), timeout=0.04)
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(student.next_event(), timeout=0.04)

    asyncio.run(scenario())


def test_presence_transitions_advance_the_atomic_roster_snapshot() -> None:
    hub = ClassroomHub()

    assert hub.participant_connected("session", "participant") is True
    connected, connected_version = hub.participant_roster_snapshot(
        "session", ["participant"]
    )
    assert connected == {"participant": "connected"}
    assert connected_version == 1

    assert hub.participant_disconnected("session", "participant") is True
    disconnected, disconnected_version = hub.participant_roster_snapshot(
        "session", ["participant"]
    )
    assert disconnected == {"participant": "reconnecting"}
    assert disconnected_version == 2


def test_reconnect_grace_expiry_advances_roster_version_and_notifies_teacher() -> None:
    async def scenario() -> None:
        hub = ClassroomHub(
            reconnect_grace_seconds=0.02,
            roster_interval_seconds=0.005,
        )
        hub.start()
        async with hub.subscribe("session", "teacher") as teacher:
            assert hub.participant_connected("session", "participant") is True
            connected_event = await asyncio.wait_for(teacher.next_event(), timeout=1)
            assert connected_event is not None and connected_event["rosterVersion"] == 1

            await asyncio.sleep(0.006)
            assert hub.participant_disconnected("session", "participant") is True
            reconnecting_event = await asyncio.wait_for(teacher.next_event(), timeout=1)
            assert reconnecting_event is not None
            assert reconnecting_event["rosterVersion"] == 2
            reconnecting, version = hub.participant_roster_snapshot(
                "session", ["participant"]
            )
            assert reconnecting == {"participant": "reconnecting"}
            assert version == 2

            expired_event = await asyncio.wait_for(teacher.next_event(), timeout=1)
            assert expired_event is not None and expired_event["rosterVersion"] == 3
            disconnected, expired_version = hub.participant_roster_snapshot(
                "session", ["participant"]
            )
            assert disconnected == {"participant": "disconnected"}
            assert expired_version == 3
            reserved, active_count = hub.reserve_stale_participants(
                "session", {"participant": True}
            )
            assert reserved == set()
            assert active_count == 1
            reserved, active_count = hub.reserve_stale_participants(
                "session", {"participant": False}
            )
            assert reserved == {"participant"}
            assert active_count == 0
        hub.close()

    asyncio.run(scenario())


def test_stale_timer_callbacks_cannot_cancel_newer_reconnect_grace() -> None:
    async def scenario() -> None:
        hub = ClassroomHub(reconnect_grace_seconds=0.02)
        hub.start()
        key = ("session", "participant")
        current = time.monotonic() - 1
        stale = current - 1
        hub._participant_disconnected_at[key] = current
        hub._install_presence_expiry(key, current)

        hub._install_presence_expiry(key, stale)
        hub._expire_participant_presence(key, stale)
        await asyncio.sleep(0.001)

        assert hub.participant_presence(*key) == "disconnected"
        assert hub.roster_version("session") == 1
        hub.close()

    asyncio.run(scenario())


def test_hub_keeps_critical_discrete_events_through_queue_capacity() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session", "teacher") as subscriber:
            for sequence in range(SUBSCRIBER_QUEUE_SIZE):
                hub._publish(
                    "session",
                    "control",
                    {"controlEpoch": sequence},
                    True,
                    "teacher",
                )

            assert subscriber.closed is False
            assert subscriber.queue.qsize() == SUBSCRIBER_QUEUE_SIZE
            observed = [subscriber.queue.get_nowait()["controlEpoch"] for _ in range(512)]
            assert observed == list(range(512))

    asyncio.run(scenario())


def test_hub_disconnects_instead_of_silently_dropping_critical_overflow() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session", "teacher") as subscriber:
            for sequence in range(SUBSCRIBER_QUEUE_SIZE + 1):
                hub._publish(
                    "session",
                    "control",
                    {"controlEpoch": sequence},
                    True,
                    "teacher",
                )

            assert subscriber.closed is True
            assert hub.current_connections == 0
            assert hub.queue_overflows == 1
            assert hub.slow_subscribers_disconnected == 1
            assert await subscriber.next_event() is None

    asyncio.run(scenario())


def test_hub_assigns_sequences_and_removes_subscriber() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session") as subscriber:
            hub.publish("session", "participant-joined", {"stateVersion": 2}, critical=True)
            event = await asyncio.wait_for(subscriber.queue.get(), timeout=1)
            assert event is not None
            assert event["eventSequence"] == 1
            assert event["hubEpoch"] == hub.hub_epoch
            assert event["_encoded"].startswith('{"type":"participant-joined"')
            assert '"_encoded"' not in event["_encoded"]
            assert hub.current_connections == 1
        assert hub.current_connections == 0

    asyncio.run(scenario())


def test_hub_rejects_oversized_events() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session"):
            try:
                hub._publish(
                    "session",
                    "question-added",
                    {"text": "x" * MAX_EVENT_BYTES},
                    True,
                )
            except ValueError as error:
                assert "4 KiB" in str(error)
            else:
                raise AssertionError("oversized event was accepted")

    asyncio.run(scenario())


def test_hub_does_not_disclose_teacher_only_events_to_students() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with (
            hub.subscribe("session", "teacher") as teacher,
            hub.subscribe("session", "student") as student,
        ):
            hub._publish(
                "session",
                "question-added",
                {"text": "private question"},
                True,
                "teacher",
            )
            event = await asyncio.wait_for(teacher.queue.get(), timeout=1)
            assert event is not None and event["type"] == "question-added"
            assert student.queue.empty()

    asyncio.run(scenario())


def test_hub_coalesces_presenter_state_without_coalescing_discrete_events() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session") as subscriber:
            for sequence in range(1, 4):
                hub._publish(
                    "session",
                    "presenter",
                    {"presenterSequence": sequence},
                    False,
                    "all",
                )
            hub._publish("session", "question-removed", {"questionId": "q1"}, True, "all")
            hub._publish("session", "control", {"controlEpoch": 2}, True, "all")

            presenter = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            question = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            control = await asyncio.wait_for(subscriber.next_event(), timeout=1)

            assert presenter is not None and presenter["presenterSequence"] == 3
            assert question is not None and question["type"] == "question-removed"
            assert control is not None and control["type"] == "control"
            assert hub.presenter_events_coalesced == 2

    asyncio.run(scenario())


def test_pointer_removal_cannot_be_followed_by_stale_pointer() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session") as subscriber:
            hub._publish("session", "pointer", {"x": 0.2}, False, "all")
            hub._publish("session", "pointer-removed", {}, True, "all")

            pointer = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            removed = await asyncio.wait_for(subscriber.next_event(), timeout=1)

            assert pointer is not None and pointer["type"] == "pointer"
            assert removed is not None and removed["type"] == "pointer-removed"

    asyncio.run(scenario())


def test_hub_preserves_sequence_order_between_pointer_and_presenter() -> None:
    async def scenario() -> None:
        hub = ClassroomHub()
        hub.start()
        async with hub.subscribe("session") as subscriber:
            hub._publish("session", "pointer", {"x": 0.2}, False, "all")
            hub._publish("session", "presenter", {"presenterSequence": 2}, False, "all")

            pointer = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            presenter = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            assert pointer is not None and pointer["type"] == "pointer"
            assert presenter is not None and presenter["type"] == "presenter"

    asyncio.run(scenario())


def test_hub_bounds_transient_pin_and_control_request_per_participant() -> None:
    hub = ClassroomHub()
    hub.set_pin("session", "participant", {"participantId": "participant", "x": 0.1})
    hub.set_pin("session", "participant", {"participantId": "participant", "x": 0.2})
    assert hub.active_pins("session") == [{"participantId": "participant", "x": 0.2}]
    assert hub.request_control("session", "participant") is True
    assert hub.request_control("session", "participant") is False
    assert list(hub.control_requests("session")) == ["participant"]
    hub.clear_participant("session", "participant")
    assert hub.active_pins("session") == []
    assert hub.control_requests("session") == {}


def test_hub_bounds_transient_teaching_tools_and_clears_them_with_session() -> None:
    hub = ClassroomHub()
    hub.set_teacher_pointer("session", {"style": "green-arrow", "x": 0.2, "y": 0.3})
    for index in range(45):
        hub.add_teaching_annotation(
            "session",
            {"id": f"mark-{index}", "points": [{"x": 0.2, "y": 0.3}]},
        )

    assert hub.teacher_pointer("session") == {"style": "green-arrow", "x": 0.2, "y": 0.3}
    assert len(hub.teaching_annotations("session")) == 40
    assert hub.teaching_annotations("session")[0]["id"] == "mark-5"
    assert hub.remove_teaching_annotation("session", "mark-44") is True

    hub.clear_session("session")
    assert hub.teacher_pointer("session") is None
    assert hub.teaching_annotations("session") == []
