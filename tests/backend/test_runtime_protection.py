from datetime import timedelta
from pathlib import Path

from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ClassroomSession, Job, RuntimeGuard, Slide
from wsi_viewer.runtime_protection import (
    ASSESSMENT_COOLDOWN,
    ASSESSMENT_DRAINING,
    ASSESSMENT_LIVE,
    COOLDOWN,
    DRAINING,
    IDLE,
    LIVE,
    begin_assessment_cooldown,
    begin_classroom_cooldown,
    protection_snapshot,
    request_assessment_protection,
    request_classroom_protection,
    utc_now,
)
from wsi_viewer.storage import StorageLayout
from wsi_viewer.worker import background_work_is_allowed, process_next


def _factory(tmp_path: Path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    return settings, session_factory(settings)


def _job(database, *, status: str = "queued") -> Job:
    slide = Slide(
        display_name="Protected work",
        original_filename="protected.ome.tif",
        source_bytes=1,
        state=SlideState.QUEUED,
    )
    database.add(slide)
    database.flush()
    job = Job(slide_id=slide.id, status=status)
    database.add(job)
    database.flush()
    return job


def test_protection_blocks_waiting_jobs_and_requests_running_cancellation(
    tmp_path: Path,
) -> None:
    _, factory = _factory(tmp_path)
    with factory() as database:
        queued = _job(database)
        running = _job(database, status="running")
        database.commit()
        queued_id = queued.id
        running_id = running.id

    with factory() as database:
        snapshot = request_classroom_protection(database, classroom_session_id="pending-classroom")
        database.commit()
        assert snapshot.mode == DRAINING
        assert snapshot.running_jobs == 1

    with factory() as database:
        assert database.get(Job, queued_id).status == "blocked_classroom"
        running = database.get(Job, running_id)
        assert running is not None
        assert running.cancellation_requested_at is not None


def test_cooldown_resumes_blocked_jobs_exactly_once(tmp_path: Path) -> None:
    _, factory = _factory(tmp_path)
    now = utc_now()
    with factory() as database:
        job = _job(database)
        request_classroom_protection(database, classroom_session_id="classroom-1", now=now)
        begin_classroom_cooldown(database, now=now)
        database.commit()
        job_id = job.id

    with factory() as database:
        snapshot = protection_snapshot(database, now=now + timedelta(seconds=60))
        database.commit()
        assert snapshot.mode == COOLDOWN
        assert database.get(Job, job_id).status == "blocked_classroom"

    with factory() as database:
        snapshot = protection_snapshot(database, now=now + timedelta(seconds=121))
        database.commit()
        assert snapshot.mode == IDLE
        assert database.get(Job, job_id).status == "queued"

    with factory() as database:
        snapshot = protection_snapshot(database, now=now + timedelta(seconds=122))
        database.commit()
        assert snapshot.mode == IDLE
        assert database.get(Job, job_id).status == "queued"


def test_worker_admission_fails_closed_while_guard_is_live(tmp_path: Path) -> None:
    settings, factory = _factory(tmp_path)
    with factory() as database:
        job = _job(database)
        now = utc_now()
        classroom = ClassroomSession(
            id="classroom-1",
            join_code_hash="a" * 64,
            phase="live",
            status="active",
            started_at=now,
            live_expires_at=now + timedelta(hours=1),
            expires_at=now + timedelta(hours=1),
        )
        database.add(classroom)
        database.flush()
        request_classroom_protection(database, classroom_session_id="classroom-1", now=now)
        database.commit()
        job_id = job.id

    assert not background_work_is_allowed(factory, enabled=True)
    assert not process_next(
        factory,
        layout=StorageLayout(settings.data_root),
        protection_enabled=True,
    )
    with factory() as database:
        assert database.get(RuntimeGuard, "classroom-protection").mode == LIVE
        assert database.get(Job, job_id).status == "blocked_classroom"


def test_disabled_protection_keeps_legacy_worker_admission(tmp_path: Path) -> None:
    _, factory = _factory(tmp_path)
    assert background_work_is_allowed(factory, enabled=False)


def test_assessment_and_classroom_share_one_protected_runtime(tmp_path: Path) -> None:
    settings, factory = _factory(tmp_path)
    now = utc_now()
    with factory() as database:
        queued = _job(database)
        running = _job(database, status="running")
        protection = request_assessment_protection(
            database,
            assessment_administration_id="assessment-1",
            now=now,
        )
        database.commit()
        queued_id = queued.id
        running_id = running.id
        assert protection.mode == ASSESSMENT_DRAINING
        assert protection.running_jobs == 1

    with factory() as database:
        running = database.get(Job, running_id)
        assert database.get(Job, queued_id).status == "blocked_classroom"
        assert running is not None and running.cancellation_requested_at is not None
        running.status = "cancelled"
        protection = request_assessment_protection(
            database,
            assessment_administration_id="assessment-1",
            now=now + timedelta(seconds=1),
        )
        assert protection.mode == ASSESSMENT_LIVE
        classroom = request_classroom_protection(
            database,
            classroom_session_id="classroom-1",
            now=now + timedelta(seconds=1),
        )
        assert classroom.conflicting_runtime is True
        database.commit()

    assert not process_next(
        factory,
        layout=StorageLayout(settings.data_root),
        protection_enabled=True,
    )
    with factory() as database:
        cooldown = begin_assessment_cooldown(database, now=now + timedelta(seconds=2))
        database.commit()
        assert cooldown.mode == ASSESSMENT_COOLDOWN
    with factory() as database:
        snapshot = protection_snapshot(database, now=now + timedelta(seconds=123))
        database.commit()
        assert snapshot.mode == IDLE
        assert database.get(Job, queued_id).status == "queued"
