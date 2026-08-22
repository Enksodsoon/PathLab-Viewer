from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session as OrmSession

from .models import ClassroomSession, Job, RuntimeGuard

CLASSROOM_GUARD_ID = "classroom-protection"
CLASSROOM_COOLDOWN = timedelta(seconds=120)

IDLE = "idle"
DRAINING = "draining_for_classroom"
LIVE = "classroom_live"
COOLDOWN = "classroom_cooldown"
PROTECTED_MODES = {DRAINING, LIVE, COOLDOWN}

BLOCKABLE_JOB_STATES = {"queued", "retry_wait"}
ACTIVE_JOB_STATES = {"running", "checkpointing"}
BLOCKED_RESOURCE_CLASSES = {"background", "isolated"}


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@dataclass(frozen=True)
class ProtectionSnapshot:
    mode: str
    classroom_session_id: str | None
    cooldown_until: datetime | None
    running_jobs: int = 0

    @property
    def blocks_background_work(self) -> bool:
        return self.mode in PROTECTED_MODES


def _guard(database: OrmSession) -> RuntimeGuard:
    guard = database.get(RuntimeGuard, CLASSROOM_GUARD_ID)
    if guard is None:
        guard = RuntimeGuard(id=CLASSROOM_GUARD_ID, mode=IDLE)
        database.add(guard)
        database.flush()
    # A no-op update serializes worker admission and Classroom transitions on
    # both PostgreSQL and SQLite without retaining a lock outside this transaction.
    database.execute(
        update(RuntimeGuard)
        .where(RuntimeGuard.id == CLASSROOM_GUARD_ID)
        .values(version=RuntimeGuard.version + 1, updated_at=utc_now())
    )
    database.refresh(guard)
    return guard


def _active_classroom_statement(now: datetime) -> Select[tuple[ClassroomSession]]:
    return select(ClassroomSession).where(
        ClassroomSession.status == "active",
        ClassroomSession.phase == "live",
        ClassroomSession.expires_at > now,
    )


def _block_waiting_jobs(database: OrmSession) -> None:
    database.execute(
        update(Job)
        .where(
            Job.status.in_(BLOCKABLE_JOB_STATES),
            Job.resource_class.in_(BLOCKED_RESOURCE_CLASSES),
        )
        .values(status="blocked_classroom", updated_at=utc_now())
    )


def _resume_waiting_jobs(database: OrmSession) -> None:
    now = utc_now()
    database.execute(
        update(Job)
        .where(Job.status == "blocked_classroom")
        .values(status="queued", cancellation_requested_at=None, updated_at=now)
    )


def _reconcile(database: OrmSession, guard: RuntimeGuard, now: datetime) -> RuntimeGuard:
    active = database.scalar(_active_classroom_statement(now))
    if active is not None:
        guard.mode = LIVE
        guard.classroom_session_id = active.id
        guard.cooldown_until = None
        _block_waiting_jobs(database)
        return guard
    if guard.mode == LIVE:
        guard.mode = COOLDOWN
        guard.classroom_session_id = None
        guard.cooldown_until = now + CLASSROOM_COOLDOWN
    if (
        guard.mode == COOLDOWN
        and guard.cooldown_until is not None
        and guard.cooldown_until <= now
    ):
        guard.mode = IDLE
        guard.cooldown_until = None
        _resume_waiting_jobs(database)
    return guard


def protection_snapshot(database: OrmSession, *, now: datetime | None = None) -> ProtectionSnapshot:
    current = now or utc_now()
    guard = _reconcile(database, _guard(database), current)
    running = len(
        list(
            database.scalars(
                select(Job.id).where(
                    Job.status.in_(ACTIVE_JOB_STATES),
                    Job.resource_class.in_(BLOCKED_RESOURCE_CLASSES),
                )
            )
        )
    )
    return ProtectionSnapshot(
        mode=guard.mode,
        classroom_session_id=guard.classroom_session_id,
        cooldown_until=guard.cooldown_until,
        running_jobs=running,
    )


def request_classroom_protection(
    database: OrmSession,
    *,
    classroom_session_id: str | None,
    now: datetime | None = None,
) -> ProtectionSnapshot:
    current = now or utc_now()
    guard = _reconcile(database, _guard(database), current)
    active_jobs = list(
        database.scalars(
            select(Job).where(
                Job.status.in_(ACTIVE_JOB_STATES),
                Job.resource_class.in_(BLOCKED_RESOURCE_CLASSES),
            )
        )
    )
    _block_waiting_jobs(database)
    if active_jobs:
        guard.mode = DRAINING
        guard.classroom_session_id = classroom_session_id
        guard.cooldown_until = None
        for job in active_jobs:
            job.cancellation_requested_at = current
        return ProtectionSnapshot(
            mode=guard.mode,
            classroom_session_id=guard.classroom_session_id,
            cooldown_until=None,
            running_jobs=len(active_jobs),
        )
    guard.mode = LIVE
    guard.classroom_session_id = classroom_session_id
    guard.cooldown_until = None
    return ProtectionSnapshot(
        mode=guard.mode,
        classroom_session_id=guard.classroom_session_id,
        cooldown_until=None,
    )


def read_protection_snapshot(
    database: OrmSession, *, now: datetime | None = None
) -> ProtectionSnapshot:
    """Read admission state without creating write traffic for each upload chunk."""
    current = now or utc_now()
    active = database.scalar(_active_classroom_statement(current))
    if active is not None:
        return ProtectionSnapshot(
            mode=LIVE,
            classroom_session_id=active.id,
            cooldown_until=None,
        )
    guard = database.get(RuntimeGuard, CLASSROOM_GUARD_ID)
    if guard is None:
        return ProtectionSnapshot(mode=DRAINING, classroom_session_id=None, cooldown_until=None)
    mode = guard.mode
    cooldown_until = guard.cooldown_until
    if mode == COOLDOWN and cooldown_until is not None and cooldown_until <= current:
        mode = IDLE
        cooldown_until = None
    return ProtectionSnapshot(
        mode=mode,
        classroom_session_id=guard.classroom_session_id,
        cooldown_until=cooldown_until,
    )


def bind_classroom_session(database: OrmSession, session_id: str) -> None:
    guard = _guard(database)
    guard.mode = LIVE
    guard.classroom_session_id = session_id
    guard.cooldown_until = None
    _block_waiting_jobs(database)


def begin_classroom_cooldown(
    database: OrmSession, *, now: datetime | None = None
) -> ProtectionSnapshot:
    current = now or utc_now()
    guard = _guard(database)
    guard.mode = COOLDOWN
    guard.classroom_session_id = None
    guard.cooldown_until = current + CLASSROOM_COOLDOWN
    _block_waiting_jobs(database)
    return ProtectionSnapshot(
        mode=guard.mode,
        classroom_session_id=None,
        cooldown_until=guard.cooldown_until,
    )
