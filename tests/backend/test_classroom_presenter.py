import asyncio

from wsi_viewer.classroom_presenter import PresenterRuntime, PresenterSnapshot


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_presenter_persistence_is_sparse_and_keeps_latest_state() -> None:
    async def scenario() -> None:
        clock = Clock()
        persisted: list[PresenterSnapshot] = []
        runtime = PresenterRuntime(
            lambda snapshots: persisted.extend(snapshots),
            interval_seconds=2,
            clock=clock,
        )

        for sequence in range(4):
            runtime.update(
                "session",
                0,
                0,
                "slide-1",
                "slide-1",
                {"x": sequence / 10, "y": 0.5, "zoom": 2},
            )
            await runtime.flush()
            clock.now += 0.5

        assert persisted == []
        await runtime.flush()
        assert len(persisted) == 1
        assert persisted[0].sequence == 4
        assert persisted[0].viewport["x"] == 0.3

        for sequence in range(4, 8):
            runtime.update(
                "session",
                0,
                0,
                "slide-1",
                "slide-1",
                {"x": sequence / 10, "y": 0.5, "zoom": 2},
            )
            await runtime.flush()
            clock.now += 0.5

        assert len(persisted) == 1
        await runtime.flush()
        assert len(persisted) == 2
        assert persisted[-1].sequence == 8
        assert persisted[-1].viewport["x"] == 0.7

    asyncio.run(scenario())


def test_presenter_shutdown_flushes_latest_dirty_state() -> None:
    async def scenario() -> None:
        persisted: list[PresenterSnapshot] = []
        runtime = PresenterRuntime(lambda snapshots: persisted.extend(snapshots))
        runtime.update(
            "session", 10, 10, "slide-1", "slide-1", {"x": 0.8, "y": 0.2, "zoom": 5}
        )
        await runtime.close()
        assert len(persisted) == 1
        assert persisted[0].sequence == 11

    asyncio.run(scenario())


def test_reserved_sequence_prevents_reuse_after_abrupt_restart() -> None:
    reservations: list[int] = []

    def reserve(_session_id: str, sequence: int) -> int:
        reservations.append(sequence)
        return sequence

    first = PresenterRuntime(lambda _snapshots: None, reserve=reserve)
    emitted, _ = first.update(
        "session", 0, 0, "slide-1", "slide-1", {"x": 0.4, "y": 0.5, "zoom": 2}
    )
    assert emitted.sequence == 1
    assert reservations == [1024]

    restarted = PresenterRuntime(lambda _snapshots: None, reserve=reserve)
    after_restart, _ = restarted.update(
        "session",
        0,
        reservations[-1],
        "slide-1",
        "slide-1",
        {"x": 0.6, "y": 0.5, "zoom": 2},
    )
    assert after_restart.sequence == 1025
    assert reservations[-1] == 2048
