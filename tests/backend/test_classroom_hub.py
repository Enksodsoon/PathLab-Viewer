import asyncio

from wsi_viewer.classroom_hub import MAX_EVENT_BYTES, ClassroomHub


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
