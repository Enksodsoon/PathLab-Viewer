import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .domain import InvalidTransition, SlideState, transition
from .models import AuditEvent, Job, Slide
from .storage import (
    InsufficientStorage,
    PublicationError,
    StorageLayout,
    admission_required,
    measure_derivative,
)

ACTIVE_STATES = (
    SlideState.UPLOADING,
    SlideState.QUEUED,
    SlideState.VALIDATING,
    SlideState.CONVERTING,
)


@dataclass(frozen=True)
class ReconciliationSummary:
    slide_count: int
    derivative_count: int
    active_reservation_count: int


def _begin_immediate(database: OrmSession) -> None:
    database.connection().exec_driver_sql("BEGIN IMMEDIATE")


def _accounted_bytes(database: OrmSession, *, exclude_slide_id: str | None = None) -> int:
    contribution = case(
        (Slide.state.in_(ACTIVE_STATES), Slide.reserved_bytes),
        else_=Slide.source_bytes + Slide.derivative_bytes,
    )
    statement = select(func.coalesce(func.sum(contribution), 0))
    if exclude_slide_id is not None:
        statement = statement.where(Slide.id != exclude_slide_id)
    return int(database.scalar(statement) or 0)


def _require_physical_space(root: Path, required: int) -> None:
    if shutil.disk_usage(root).free < required:
        raise InsufficientStorage("Insufficient physical storage")


def _require_application_capacity(
    database: OrmSession,
    layout: StorageLayout,
    required: int,
    *,
    exclude_slide_id: str | None = None,
) -> None:
    if _accounted_bytes(database, exclude_slide_id=exclude_slide_id) + required > layout.cap_bytes:
        raise InsufficientStorage("Upload would exceed the application storage cap")


def reserve_new_slide(
    factory: sessionmaker[OrmSession],
    layout: StorageLayout,
    *,
    display_name: str,
    original_filename: str,
    source_bytes: int,
    actor_user_id: str | None,
) -> Slide:
    required = admission_required(source_bytes)
    _require_physical_space(layout.root, required)
    with factory() as database:
        _begin_immediate(database)
        _require_application_capacity(database, layout, required)
        slide = Slide(
            display_name=display_name,
            original_filename=original_filename,
            source_bytes=source_bytes,
            reserved_bytes=required,
        )
        database.add(slide)
        database.flush()
        database.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action="slide.create",
                target_id=slide.id,
                detail={"bytes": source_bytes},
            )
        )
        database.commit()
        return slide


def reserve_retry(
    factory: sessionmaker[OrmSession],
    layout: StorageLayout,
    *,
    slide_id: str,
    actor_user_id: str | None,
) -> Slide:
    with factory() as database:
        _begin_immediate(database)
        slide = database.get(Slide, slide_id)
        if slide is None:
            raise LookupError("Slide not found")
        if slide.state is not SlideState.FAILED:
            raise InvalidTransition("Slide is not failed")
        required = admission_required(slide.source_bytes)
        _require_physical_space(layout.root, required)
        _require_application_capacity(
            database,
            layout,
            required,
            exclude_slide_id=slide.id,
        )
        slide.state = transition(slide.state, SlideState.QUEUED)
        slide.reserved_bytes = required
        slide.error_code = None
        slide.error_message = None
        database.add(Job(slide_id=slide.id))
        database.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action="slide.queued",
                target_id=slide.id,
            )
        )
        database.commit()
        return slide


def reconcile_storage(
    factory: sessionmaker[OrmSession],
    layout: StorageLayout,
) -> ReconciliationSummary:
    derivative_count = 0
    active_reservation_count = 0
    with factory() as database:
        _begin_immediate(database)
        slides = database.scalars(select(Slide).order_by(Slide.id)).all()
        for slide in slides:
            derivative = layout.for_slide(slide.id).private_derivative
            if os.path.lexists(derivative):
                measurement = measure_derivative(derivative)
                slide.derivative_bytes = measurement.derivative_bytes
                slide.derivative_file_count = measurement.file_count
                derivative_count += 1
            else:
                if slide.state in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}:
                    raise PublicationError("MISSING_CANONICAL_DERIVATIVE")
                slide.derivative_bytes = 0
                slide.derivative_file_count = 0
            if slide.state in ACTIVE_STATES:
                slide.reserved_bytes = admission_required(slide.source_bytes)
                active_reservation_count += 1
            else:
                slide.reserved_bytes = 0
        database.commit()
    return ReconciliationSummary(
        slide_count=len(slides),
        derivative_count=derivative_count,
        active_reservation_count=active_reservation_count,
    )
