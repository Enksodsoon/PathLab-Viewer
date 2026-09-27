import asyncio
import sqlite3
from contextlib import suppress
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from wsi_viewer import study_routes
from wsi_viewer.models import Base
from wsi_viewer.study_routes import StudyPurger


def test_transient_database_lock_does_not_kill_purger_or_shutdown(
    tmp_path: Path, monkeypatch, caplog,
):
    path = tmp_path / "purger.sqlite"
    engine = create_engine(
        f"sqlite:///{path.as_posix()}", connect_args={"timeout": 0.02},
    )
    Base.metadata.create_all(engine)
    lock = sqlite3.connect(path)
    lock.execute("BEGIN EXCLUSIVE")
    native_purge = study_routes.purge_due_study_data
    native_wait = asyncio.wait_for
    successes = []
    requested_timeouts = []

    def observed_purge(database):
        result = native_purge(database)
        successes.append(result)
        return result

    async def accelerated_hourly_wait(awaitable, *, timeout):
        requested_timeouts.append(timeout)
        lock.rollback()
        return await native_wait(awaitable, timeout=0.01)

    monkeypatch.setattr(study_routes, "purge_due_study_data", observed_purge)
    monkeypatch.setattr(study_routes.asyncio, "wait_for", accelerated_hourly_wait)

    async def exercise():
        purger = StudyPurger(sessionmaker(engine))
        purger.start()
        try:
            for _ in range(100):
                if successes:
                    break
                await asyncio.sleep(0.01)
            assert purger.task is not None
            assert not purger.task.done(), "A transient SQLite lock killed retention cleanup"
            assert successes, "The next scheduled native SQLite purge never succeeded"
            assert requested_timeouts and set(requested_timeouts) == {3600}
            lock.rollback()
            await native_wait(purger.close(), timeout=1)
        finally:
            lock.rollback()
            if purger.task is not None:
                purger.stop_event.set()
                with suppress(Exception):
                    await native_wait(purger.task, timeout=1)

    try:
        asyncio.run(exercise())
        assert "Study retention cleanup failed: OperationalError" in caplog.text
        assert "SELECT" not in caplog.text
        assert "parameters" not in caplog.text
    finally:
        lock.close()
        engine.dispose()
