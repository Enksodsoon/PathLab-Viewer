import asyncio
import inspect
import threading
from pathlib import Path
from typing import Any, cast

from pytest import MonkeyPatch
from wsi_viewer.classroom_prewarm import (
    MAX_HOTSET_FILES,
    ClassroomPrewarmer,
    PrewarmSlide,
    hotset_paths,
    warm_hotset,
)
from wsi_viewer.classroom_routes import ClassroomRouteRuntime


def _slide(root: Path, *, width: int = 4096, height: int = 2048) -> PrewarmSlide:
    return PrewarmSlide(
        root=root,
        width=width,
        height=height,
        tile_size=512,
        tile_format="jpg",
        poster_filename="thumbnail.jpg",
    )


def test_hotset_is_current_next_and_has_a_fixed_file_bound(tmp_path: Path) -> None:
    first = _slide(tmp_path / "first")
    second = _slide(tmp_path / "second")
    ignored = _slide(tmp_path / "ignored")

    paths = hotset_paths((first, second, ignored))

    assert len(paths) <= MAX_HOTSET_FILES == 28
    assert first.root / "slide.dzi" in paths
    assert first.root / "thumbnail.jpg" in paths
    assert second.root / "slide.dzi" in paths
    assert not any(path.is_relative_to(ignored.root) for path in paths)
    assert {path.parent.name for path in paths if path.parent.parent.name == "slide_files"} == {
        "10",
        "11",
        "12",
    }


def test_hotset_derivation_never_enumerates_the_pyramid(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    def reject_enumeration(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("pyramid enumeration is forbidden")

    monkeypatch.setattr(Path, "iterdir", reject_enumeration)
    monkeypatch.setattr(Path, "glob", reject_enumeration)
    monkeypatch.setattr(Path, "rglob", reject_enumeration)

    assert hotset_paths((_slide(tmp_path / "slide"),))


def test_hotset_reads_are_byte_bounded_and_missing_files_are_best_effort(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.bin"
    second = tmp_path / "second.bin"
    first.write_bytes(b"a" * 20)
    second.write_bytes(b"b" * 20)

    result = warm_hotset(
        (first, tmp_path / "missing.bin", second),
        max_bytes_per_file=4,
        max_total_bytes=6,
    )

    assert result.bytes_read == 6
    assert result.files_read == 2
    assert result.files_missing == 1


def test_prewarm_replaces_pending_work_and_keeps_event_loop_responsive(
    tmp_path: Path,
) -> None:
    started = threading.Event()
    release = threading.Event()
    calls: list[tuple[Path, ...]] = []

    def blocked_reader(paths: tuple[Path, ...]) -> None:
        calls.append(paths)
        if len(calls) == 1:
            started.set()
            assert release.wait(timeout=2)

    async def scenario() -> None:
        runtime = ClassroomPrewarmer(reader=blocked_reader)
        runtime.start()
        runtime.request((_slide(tmp_path / "first"),))
        assert await asyncio.to_thread(started.wait, 1)

        runtime.request((_slide(tmp_path / "superseded"),))
        runtime.request((_slide(tmp_path / "latest"),))
        await asyncio.sleep(0)
        assert len(calls) == 1

        release.set()
        for _ in range(100):
            if len(calls) == 2:
                break
            await asyncio.sleep(0.01)
        await runtime.close()

    asyncio.run(scenario())

    assert len(calls) == 2
    assert calls[0][0].is_relative_to(tmp_path / "first")
    assert calls[1][0].is_relative_to(tmp_path / "latest")


def test_route_runtime_awaits_startup_restore_before_becoming_ready() -> None:
    assert inspect.iscoroutinefunction(ClassroomRouteRuntime.start)
    restore_started = threading.Event()
    release_restore = threading.Event()

    class FakePresenter:
        def start(self) -> None:
            return

        async def close(self) -> None:
            return

    class FakePrewarmer:
        started = False

        def start(self) -> None:
            self.started = True

        async def close(self) -> None:
            return

    prewarmer = FakePrewarmer()

    def restore() -> None:
        assert prewarmer.started
        restore_started.set()
        assert release_restore.wait(timeout=2)

    async def scenario() -> None:
        runtime = ClassroomRouteRuntime(
            cast(Any, FakePresenter()), cast(Any, prewarmer), restore
        )
        startup = asyncio.create_task(runtime.start())
        assert await asyncio.to_thread(restore_started.wait, 1)
        assert not startup.done()
        release_restore.set()
        await startup
        await runtime.close()

    asyncio.run(scenario())
