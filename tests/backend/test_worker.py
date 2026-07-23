import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from wsi_viewer import worker
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Job, Slide
from wsi_viewer.worker import (
    WorkerScheduler,
    expire_incomplete_uploads,
    recover_stale_jobs,
    run_worker_loop,
)


def scheduler_with(
    clock: Mock,
    recover: Mock,
    cleanup: Mock,
    process: Mock,
) -> WorkerScheduler:
    return WorkerScheduler(
        recover_stale=recover,
        cleanup_uploads=cleanup,
        process_job=process,
        monotonic=clock,
    )


def test_worker_maintenance_runs_at_startup_with_monotonic_clock() -> None:
    clock = Mock(return_value=100.0)
    recover = Mock()
    cleanup = Mock()
    process = Mock(return_value=False)

    delay = scheduler_with(clock, recover, cleanup, process).run_due()

    clock.assert_called_once_with()
    recover.assert_called_once_with()
    cleanup.assert_called_once_with()
    process.assert_called_once_with()
    assert delay == 2.0


def test_worker_maintenance_is_not_repeated_on_job_poll_cycles() -> None:
    clock = Mock(side_effect=[0.0, 2.0, 4.0])
    recover = Mock()
    cleanup = Mock()
    process = Mock(return_value=False)
    scheduler = scheduler_with(clock, recover, cleanup, process)

    scheduler.run_due()
    scheduler.run_due()
    scheduler.run_due()

    assert process.call_count == 3
    recover.assert_called_once_with()
    cleanup.assert_called_once_with()


def test_worker_maintenance_runs_again_after_each_interval() -> None:
    clock = Mock(side_effect=[0.0, 60.0, 1800.0])
    recover = Mock()
    cleanup = Mock()
    process = Mock(return_value=False)
    scheduler = scheduler_with(clock, recover, cleanup, process)

    scheduler.run_due()
    scheduler.run_due()
    scheduler.run_due()

    assert recover.call_count == 3
    assert cleanup.call_count == 2


def test_worker_processes_queued_jobs_without_an_extra_delay() -> None:
    clock = Mock(side_effect=[0.0, 0.0, 0.0])
    process = Mock(side_effect=[True, True, False])
    scheduler = scheduler_with(clock, Mock(), Mock(), process)

    assert scheduler.run_due() == 0.0
    assert scheduler.run_due() == 0.0
    assert scheduler.run_due() == 2.0
    assert process.call_count == 3


def test_shutdown_requested_during_maintenance_prevents_job_claim() -> None:
    shutdown = threading.Event()
    recover = Mock(side_effect=shutdown.set)
    process = Mock(return_value=True)
    scheduler = WorkerScheduler(
        recover_stale=recover,
        cleanup_uploads=Mock(),
        process_job=process,
        shutdown_requested=shutdown.is_set,
        monotonic=Mock(return_value=0.0),
    )

    scheduler.run_due()

    process.assert_not_called()


def test_shutdown_after_active_job_prevents_second_claim() -> None:
    shutdown = threading.Event()
    process = Mock(side_effect=lambda: shutdown.set() or True)
    scheduler = WorkerScheduler(
        recover_stale=Mock(),
        cleanup_uploads=Mock(),
        process_job=process,
        shutdown_requested=shutdown.is_set,
        monotonic=Mock(return_value=0.0),
    )

    run_worker_loop(scheduler, shutdown)

    process.assert_called_once_with()


def test_idle_worker_shutdown_is_prompt() -> None:
    shutdown = threading.Event()
    entered = threading.Event()

    class IdleScheduler:
        def run_due(self) -> float:
            entered.set()
            return 60.0

    thread = threading.Thread(target=run_worker_loop, args=(IdleScheduler(), shutdown))
    thread.start()
    assert entered.wait(timeout=1)

    started = time.monotonic()
    shutdown.set()
    thread.join(timeout=1)

    assert not thread.is_alive()
    assert time.monotonic() - started < 0.5


def test_stale_worker_job_is_requeued(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    factory = session_factory(settings)
    with factory() as database:
        slide = Slide(
            display_name="Test",
            original_filename="x.ome.tif",
            source_bytes=1,
            state=SlideState.VALIDATING,
        )
        database.add(slide)
        database.flush()
        database.add(
            Job(
                slide_id=slide.id,
                status="running",
                heartbeat_at=datetime.now(UTC) - timedelta(minutes=10),
            )
        )
        database.commit()
    assert recover_stale_jobs(factory, stale_after=timedelta(minutes=5)) == 1
    with factory() as database:
        job = database.query(Job).one()
        assert job.status == "queued"


def test_incomplete_tus_uploads_expire_after_24_hours(tmp_path: Path) -> None:
    info = tmp_path / "upload-1.info"
    data = tmp_path / "upload-1"
    info.write_text("{}", encoding="utf-8")
    data.write_bytes(b"partial")
    stale = (datetime.now(UTC) - timedelta(hours=25)).timestamp()
    import os

    os.utime(info, (stale, stale))
    assert expire_incomplete_uploads(tmp_path, older_than=timedelta(hours=24)) == 1
    assert not info.exists()
    assert not data.exists()


def test_worker_applies_libvips_limits_before_job_processing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}",
        data_root=tmp_path,
        libvips_concurrency=2,
        libvips_cache_max_mem_bytes=123456,
        libvips_cache_max_files=17,
        libvips_cache_max_operations=19,
    )
    events: list[str] = []

    class StopWorker(RuntimeError):
        pass

    class FakeScheduler:
        def __init__(self, **_kwargs: object) -> None:
            assert events == ["configured"]

        def run_due(self) -> float:
            raise StopWorker

    configure = Mock(side_effect=lambda **_kwargs: events.append("configured"))
    monkeypatch.setattr(worker, "Settings", Mock(return_value=settings))
    monkeypatch.setattr(worker, "configure_libvips", configure)
    monkeypatch.setattr(worker, "WorkerScheduler", FakeScheduler)
    monkeypatch.setattr(worker, "session_factory", Mock())

    with pytest.raises(StopWorker):
        worker.main()

    configure.assert_called_once_with(
        concurrency=2,
        cache_max_mem_bytes=123456,
        cache_max_files=17,
        cache_max_operations=19,
    )
