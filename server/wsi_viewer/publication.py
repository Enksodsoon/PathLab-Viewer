from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .domain import SlideState
from .models import FolderShare, PublicationGrant, Slide
from .storage import StorageLayout, publish_derivative, unpublish_derivative

INDIVIDUAL = "individual"
FOLDER = "folder"


def active_folder_share(database: Session, folder_id: str) -> FolderShare | None:
    now = datetime.now(UTC).replace(tzinfo=None)
    return database.scalar(
        select(FolderShare).where(
            FolderShare.folder_id == folder_id,
            FolderShare.is_active.is_(True),
            (FolderShare.expires_at.is_(None) | (FolderShare.expires_at > now)),
        )
    )


def grant_count(database: Session, slide_id: str) -> int:
    return int(
        database.scalar(
            select(func.count(PublicationGrant.id)).where(
                PublicationGrant.slide_id == slide_id
            )
        )
        or 0
    )


def ensure_grant(
    database: Session,
    layout: StorageLayout,
    slide: Slide,
    source_type: str,
    source_id: str,
) -> bool:
    existing = database.scalar(
        select(PublicationGrant.id).where(
            PublicationGrant.slide_id == slide.id,
            PublicationGrant.source_type == source_type,
            PublicationGrant.source_id == source_id,
        )
    )
    if existing is not None:
        return False
    first = grant_count(database, slide.id) == 0
    if first:
        if slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}:
            raise ValueError("DERIVATIVE_NOT_READY")
        if slide.state is not SlideState.PUBLISHED:
            publish_derivative(layout, slide.id, slide.public_id)
            slide.state = SlideState.PUBLISHED
            slide.published_at = datetime.now(UTC)
    database.add(
        PublicationGrant(
            slide_id=slide.id,
            source_type=source_type,
            source_id=source_id,
        )
    )
    database.flush()
    return True


def remove_grant(
    database: Session,
    layout: StorageLayout,
    slide: Slide,
    source_type: str,
    source_id: str,
) -> bool:
    grant = database.scalar(
        select(PublicationGrant).where(
            PublicationGrant.slide_id == slide.id,
            PublicationGrant.source_type == source_type,
            PublicationGrant.source_id == source_id,
        )
    )
    if grant is None:
        return False
    database.delete(grant)
    database.flush()
    if grant_count(database, slide.id) == 0:
        unpublish_derivative(layout, slide.public_id)
        if slide.state is SlideState.PUBLISHED:
            slide.state = SlideState.READY_PRIVATE
            slide.published_at = None
    return True


def remove_folder_grants(
    database: Session,
    layout: StorageLayout,
    folder_id: str,
) -> int:
    grants = database.scalars(
        select(PublicationGrant).where(
            PublicationGrant.source_type == FOLDER,
            PublicationGrant.source_id == folder_id,
        )
    ).all()
    removed = 0
    for grant in grants:
        slide = database.get(Slide, grant.slide_id)
        if slide is None:
            database.delete(grant)
            continue
        if remove_grant(database, layout, slide, FOLDER, folder_id):
            removed += 1
    return removed


def delete_all_slide_grants(database: Session, layout: StorageLayout, slide: Slide) -> None:
    unpublish_derivative(layout, slide.public_id)
    database.execute(
        delete(PublicationGrant).where(PublicationGrant.slide_id == slide.id)
    )
    slide.published_at = None
