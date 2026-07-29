import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import case, func, select, text
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .domain import InvalidTransition, SlideState, transition
from .library import utcnow
from .models import (
    AuditEvent,
    Folder,
    Job,
    LibraryShare,
    PublicationGrant,
    ShareSlide,
    Slide,
)
from .publication import INDIVIDUAL, delivery_version
from .sharing import write_share_delivery_manifest
from .storage import (
    InsufficientStorage,
    PublicationError,
    StorageLayout,
    admission_required,
    measure_derivative,
    publish_derivative,
    publish_individual_derivative,
    unpublish_individual_derivative,
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


@dataclass(frozen=True)
class StorageCapacitySnapshot:
    used_bytes: int
    usable_bytes: int
    effective_capacity_bytes: int


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


def storage_capacity_snapshot(
    database: OrmSession,
    layout: StorageLayout,
) -> StorageCapacitySnapshot:
    used_bytes = _accounted_bytes(database)
    application_free = max(layout.cap_bytes - used_bytes, 0)
    physical_free = max(int(shutil.disk_usage(layout.root).free), 0)
    usable_bytes = min(application_free, physical_free)
    return StorageCapacitySnapshot(
        used_bytes=used_bytes,
        usable_bytes=usable_bytes,
        effective_capacity_bytes=used_bytes + usable_bytes,
    )


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
    folder_id: str | None = None,
) -> Slide:
    required = admission_required(source_bytes)
    _require_physical_space(layout.root, required)
    with factory() as database:
        _begin_immediate(database)
        _require_application_capacity(database, layout, required)
        if folder_id is not None:
            folder = database.get(Folder, folder_id)
            if folder is None or folder.trashed_at is not None:
                raise LookupError("Folder not found")
        slide = Slide(
            display_name=display_name,
            original_filename=original_filename,
            source_bytes=source_bytes,
            reserved_bytes=required,
            folder_id=folder_id,
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


def reserve_prepared_slide(
    factory: sessionmaker[OrmSession],
    layout: StorageLayout,
    *,
    display_name: str,
    original_filename: str,
    package_bytes: int,
    actor_user_id: str | None,
    folder_id: str | None = None,
) -> Slide:
    if package_bytes <= 0:
        raise ValueError("Prepared package length must be positive")
    required = package_bytes * 2 + 64 * 1024**2
    _require_physical_space(layout.root, required)
    with factory() as database:
        _begin_immediate(database)
        _require_application_capacity(database, layout, required)
        if folder_id is not None:
            folder = database.get(Folder, folder_id)
            if folder is None or folder.trashed_at is not None:
                raise LookupError("Folder not found")
        slide = Slide(
            display_name=display_name,
            original_filename=original_filename,
            source_bytes=package_bytes,
            reserved_bytes=required,
            folder_id=folder_id,
        )
        database.add(slide)
        database.flush()
        database.add(
            AuditEvent(
                actor_user_id=actor_user_id,
                action="prepared_slide.create",
                target_id=slide.id,
                detail={"bytes": package_bytes},
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
    public_deliveries: list[tuple[str, str]] = []
    individual_deliveries: list[tuple[str, str, str]] = []
    share_deliveries: list[tuple[LibraryShare, list[Slide]]] = []
    with factory() as database:
        _begin_immediate(database)
        database.execute(
            text(
                """
                UPDATE slides
                SET tags = :valid_tags
                WHERE tags = :legacy_tags
                """
            ),
            {"valid_tags": "[]", "legacy_tags": "'[]'"},
        )
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

        granted_slide_ids = set(
            database.scalars(select(PublicationGrant.slide_id).distinct()).all()
        )
        individual_slide_ids = set(
            database.scalars(
                select(PublicationGrant.slide_id).where(
                    PublicationGrant.source_type == INDIVIDUAL
                )
            ).all()
        )
        slides_by_id = {slide.id: slide for slide in slides}
        for slide_id in granted_slide_ids:
            granted_slide = slides_by_id.get(slide_id)
            if granted_slide is None:
                continue
            public_deliveries.append((granted_slide.id, granted_slide.public_id))
            if slide_id in individual_slide_ids:
                if granted_slide.published_at is None:
                    granted_slide.published_at = utcnow()
                individual_deliveries.append(
                    (
                        granted_slide.id,
                        granted_slide.public_id,
                        delivery_version(granted_slide),
                    )
                )

        active_shares = database.scalars(
            select(LibraryShare).where(
                LibraryShare.is_active.is_(True),
                LibraryShare.revoked_at.is_(None),
                LibraryShare.privacy_status == "passed",
            )
        ).all()
        now = utcnow()
        for share in active_shares:
            if share.expires_at is not None and share.expires_at <= now:
                continue
            share_slides = list(
                database.scalars(
                    select(Slide)
                    .join(ShareSlide, ShareSlide.slide_id == Slide.id)
                    .where(ShareSlide.share_id == share.id)
                    .order_by(ShareSlide.sort_order, Slide.id)
                )
            )
            share_deliveries.append((share, share_slides))
        database.commit()

        for slide_id, public_id in public_deliveries:
            target = layout.public_for(public_id)
            if os.path.lexists(target):
                measure_derivative(target)
            else:
                publish_derivative(layout, slide_id, public_id)

        expected_individual_ids = {
            public_id for _, public_id, _ in individual_deliveries
        }
        individual_root = layout.root / "delivery" / "individual"
        if individual_root.exists():
            for candidate in individual_root.iterdir():
                if candidate.name not in expected_individual_ids:
                    try:
                        layout.public_for(candidate.name)
                    except ValueError:
                        continue
                    unpublish_individual_derivative(layout, candidate.name)
        for slide_id, public_id, version in individual_deliveries:
            target = layout.individual_delivery_for(public_id, version)
            if os.path.lexists(target):
                measure_derivative(target)
                continue
            unpublish_individual_derivative(layout, public_id)
            publish_individual_derivative(layout, slide_id, public_id, version)

        expected_share_ids = {share.public_id for share, _ in share_deliveries}
        share_root = layout.root / "delivery" / "shares"
        if share_root.exists():
            for candidate in share_root.glob("*.json"):
                if candidate.stem not in expected_share_ids:
                    candidate.unlink(missing_ok=True)
        for share, share_slides in share_deliveries:
            write_share_delivery_manifest(layout, share, share_slides)
    return ReconciliationSummary(
        slide_count=len(slides),
        derivative_count=derivative_count,
        active_reservation_count=active_reservation_count,
    )
