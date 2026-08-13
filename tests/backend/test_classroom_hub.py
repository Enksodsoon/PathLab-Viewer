import asyncio

from wsi_viewer.classroom_hub import MAX_EVENT_BYTES, SUBSCRIBER_QUEUE_SIZE, ClassroomHub


def test_hub_discrete_queue_covers_bounded_reconnect_burst() -> None:
    assert SUBSCRIBER_QUEUE_SIZE >= 300


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

            question = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            control = await asyncio.wait_for(subscriber.next_event(), timeout=1)
            presenter = await asyncio.wait_for(subscriber.next_event(), timeout=1)

            assert question is not None and question["type"] == "question-removed"
            assert control is not None and control["type"] == "control"
            assert presenter is not None and presenter["presenterSequence"] == 3
            assert hub.presenter_events_coalesced == 2

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
