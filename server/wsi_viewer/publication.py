from datetime import UTC, datetime, timedelta

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
from .time_support import as_utc

INDIVIDUAL = "individual"
SHARE = "share"


def delivery_version(slide: Slide, storage: StorageLayout | None = None) -> str:
    if slide.published_at is None:
        raise ValueError("Published slide has no publication timestamp")
    published = as_utc(slide.published_at)
    canonical = published.strftime("%Y%m%d%H%M%S%f")
    if storage is None:
        return canonical
    root = storage.individual_delivery_for(slide.public_id)
    if (root / canonical).is_dir():
        return canonical
    # Older code used the session's wall clock. Retain a legacy URL only with
    # both a plausible offset and the hardlink identity of the current public
    # descriptor. Copied/restored files and ambiguous histories need operator
    # reconciliation; do not guess a timestamp or rename historical assets.
    public_root = storage.public_for(slide.public_id)
    public_descriptor = public_root / "slide.dzi"
    candidates: list[str] = []
    try:
        if (root.is_symlink() or public_descriptor.is_symlink()
                or root.resolve() != root.parent.resolve() / root.name
                or public_root.resolve() != public_root.parent.resolve() / public_root.name):
            return canonical
        for candidate in root.iterdir():
            if (candidate.is_symlink() or not candidate.is_dir()
                    or candidate.resolve() != root.resolve() / candidate.name
                    or len(candidate.name) != 20 or not candidate.name.isascii()
                    or not candidate.name.isdigit()):
                continue
            try:
                wallclock = datetime.strptime(candidate.name, "%Y%m%d%H%M%S%f").replace(tzinfo=UTC)
            except ValueError:
                continue
            difference = abs(wallclock - published)
            descriptor = candidate / "slide.dzi"
            if (difference <= timedelta(hours=14)
                    and difference.total_seconds() % 60 == 0
                    and not descriptor.is_symlink()
                    and descriptor.samefile(public_descriptor)):
                candidates.append(candidate.name)
    except OSError:
        return canonical
    return candidates[0] if len(candidates) == 1 else canonical


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
    now = datetime.now(UTC)
    if slide.published_at is None:
        slide.published_at = now
    if grant_count == 0:
        if slide.render_mode == "ome_dynamic":
            paths = storage.for_slide(slide.id)
            if not paths.original.is_file() or not paths.ome_index.is_file():
                raise FileNotFoundError("Dynamic OME source is not ready")
        else:
            publish_derivative(storage, slide.id, slide.public_id)
    if source_type == INDIVIDUAL and slide.render_mode != "ome_dynamic":
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
    if source_type == INDIVIDUAL and slide.render_mode != "ome_dynamic":
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
        if slide.render_mode != "ome_dynamic":
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
    if slide.render_mode != "ome_dynamic":
        unpublish_individual_derivative(storage, slide.public_id)
        unpublish_derivative(storage, slide.public_id)
    slide.published_at = None
    if slide.state == SlideState.PUBLISHED:
        slide.state = SlideState.READY_PRIVATE
