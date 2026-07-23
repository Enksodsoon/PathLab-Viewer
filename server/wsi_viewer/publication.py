from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .models import PublicationGrant, Slide
from .storage import StorageLayout, publish_derivative, unpublish_derivative

INDIVIDUAL = "individual"
SHARE = "share"


def ensure_grant(
    database: OrmSession,
    storage: StorageLayout,
    slide: Slide,
    source_type: str,
    source_id: str,
) -> PublicationGrant:
    existing = database.scalar(
        select(PublicationGrant).where(
            PublicationGrant.slide_id == slide.id,
            PublicationGrant.source_type == source_type,
            PublicationGrant.source_id == source_id,
        )
    )
    if existing is not None:
        return existing
    grant_count = int(
        database.scalar(
            select(func.count())
            .select_from(PublicationGrant)
            .where(PublicationGrant.slide_id == slide.id)
        )
        or 0
    )
    if grant_count == 0:
        publish_derivative(storage, slide.id, slide.public_id)
    grant = PublicationGrant(
        slide_id=slide.id,
        source_type=source_type,
        source_id=source_id,
    )
    database.add(grant)
    now = datetime.now(UTC).replace(tzinfo=None)
    slide.privacy_status = "passed"
    slide.privacy_scanned_at = now
    slide.state = SlideState.PUBLISHED
    slide.published_at = now
    return grant


def remove_grant(
    database: OrmSession,
    storage: StorageLayout,
    slide: Slide,
    source_type: str,
    source_id: str,
) -> None:
    grant = database.scalar(
        select(PublicationGrant).where(
            PublicationGrant.slide_id == slide.id,
            PublicationGrant.source_type == source_type,
            PublicationGrant.source_id == source_id,
        )
    )
    if grant is None:
        return
    database.delete(grant)
    database.flush()
    remaining = int(
        database.scalar(
            select(func.count())
            .select_from(PublicationGrant)
            .where(PublicationGrant.slide_id == slide.id)
        )
        or 0
    )
    if remaining == 0:
        unpublish_derivative(storage, slide.public_id)
        if slide.state is SlideState.PUBLISHED:
            slide.state = SlideState.READY_PRIVATE
        slide.published_at = None


def delete_all_slide_grants(
    database: OrmSession,
    storage: StorageLayout,
    slide: Slide,
) -> None:
    grants = database.scalars(
        select(PublicationGrant).where(PublicationGrant.slide_id == slide.id)
    ).all()
    for grant in grants:
        database.delete(grant)
    unpublish_derivative(storage, slide.public_id)
    slide.published_at = None
