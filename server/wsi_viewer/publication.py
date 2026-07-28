from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .models import PublicationGrant, Slide
from .storage import (
    StorageLayout,
    publish_derivative,
    publish_individual_derivative,
    unpublish_derivative,
    unpublish_individual_derivative,
)

INDIVIDUAL = "individual"
SHARE = "share"


def delivery_version(slide: Slide) -> str:
    if slide.published_at is None:
        raise ValueError("Published slide has no publication timestamp")
    return slide.published_at.strftime("%Y%m%d%H%M%S%f")


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
    now = datetime.now(UTC).replace(tzinfo=None)
    if slide.published_at is None:
        slide.published_at = now
    if grant_count == 0:
        publish_derivative(storage, slide.id, slide.public_id)
    if source_type == INDIVIDUAL:
        publish_individual_derivative(
            storage,
            slide.id,
            slide.public_id,
            delivery_version(slide),
        )
    grant = PublicationGrant(
        slide_id=slide.id,
        source_type=source_type,
        source_id=source_id,
    )
    database.add(grant)
    slide.privacy_status = "passed"
    slide.privacy_scanned_at = now
    slide.state = SlideState.PUBLISHED
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
    if source_type == INDIVIDUAL:
        unpublish_individual_derivative(storage, slide.public_id)
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
        if slide.state == SlideState.PUBLISHED:
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
    unpublish_individual_derivative(storage, slide.public_id)
    unpublish_derivative(storage, slide.public_id)
    slide.published_at = None
