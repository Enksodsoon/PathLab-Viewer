import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .library import folder_subtree_ids, utcnow
from .models import (
    Collection,
    CollectionSlide,
    Folder,
    LibraryShare,
    ShareSlide,
    Slide,
)
from .publication import SHARE, ensure_grant, remove_grant
from .storage import StorageLayout


class ShareConflict(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def target_slides(
    database: OrmSession,
    *,
    target_type: str,
    target_id: str,
    include_descendants: bool,
) -> tuple[str, str, list[Slide]]:
    if target_type == "folder":
        folder = database.get(Folder, target_id)
        if folder is None or folder.trashed_at is not None:
            raise ShareConflict("SHARE_TARGET_NOT_FOUND")
        folder_ids = (
            folder_subtree_ids(database, folder.id)
            if include_descendants
            else [folder.id]
        )
        slides = list(
            database.scalars(
                select(Slide)
                .where(
                    Slide.folder_id.in_(folder_ids),
                    Slide.trashed_at.is_(None),
                )
                .order_by(Slide.sort_order, Slide.updated_at.desc(), Slide.id)
            )
        )
        return folder.name, folder.description, slides
    if target_type == "collection":
        collection = database.get(Collection, target_id)
        if collection is None:
            raise ShareConflict("SHARE_TARGET_NOT_FOUND")
        slides = list(
            database.scalars(
                select(Slide)
                .join(CollectionSlide, CollectionSlide.slide_id == Slide.id)
                .where(
                    CollectionSlide.collection_id == collection.id,
                    Slide.trashed_at.is_(None),
                )
                .order_by(CollectionSlide.sort_order, Slide.id)
            )
        )
        return collection.name, collection.description, slides
    raise ShareConflict("SHARE_TARGET_NOT_FOUND")


def preview_share(
    database: OrmSession,
    *,
    target_type: str,
    target_id: str,
    include_descendants: bool,
) -> dict[str, Any]:
    name, description, slides = target_slides(
        database,
        target_type=target_type,
        target_id=target_id,
        include_descendants=include_descendants,
    )
    ready_states = {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
    included = [
        {"id": slide.id, "displayName": slide.display_name}
        for slide in slides
        if slide.state in ready_states and slide.privacy_status == "passed"
    ]
    excluded = [
        {
            "id": slide.id,
            "displayName": slide.display_name,
            "reason": (
                "PRIVACY_REVIEW_REQUIRED"
                if slide.privacy_status != "passed"
                else "SLIDE_NOT_READY"
            ),
        }
        for slide in slides
        if slide.state not in ready_states or slide.privacy_status != "passed"
    ]
    return {
        "targetType": target_type,
        "targetId": target_id,
        "name": name,
        "description": description,
        "included": included,
        "excluded": excluded,
    }


def share_json(
    database: OrmSession,
    share: LibraryShare,
    *,
    included_count: int | None = None,
) -> dict[str, Any]:
    count = included_count
    if count is None:
        count = len(
            database.scalars(
                select(ShareSlide.id).where(ShareSlide.share_id == share.id)
            ).all()
        )
    state = "revoked" if not share.is_active else "active"
    if share.expires_at is not None and share.expires_at <= utcnow():
        state = "expired"
    return {
        "id": share.id,
        "publicId": share.public_id,
        "targetType": share.target_type,
        "targetId": share.target_id,
        "state": state,
        "includeDescendants": share.include_descendants,
        "autoIncludeNew": share.auto_include_new,
        "expiresAt": share.expires_at.isoformat() if share.expires_at else None,
        "includedCount": count,
        "updatedAt": share.updated_at.isoformat(),
    }


def activate_share(
    database: OrmSession,
    storage: StorageLayout,
    *,
    target_type: str,
    target_id: str,
    include_descendants: bool,
    auto_include_new: bool,
    expires_at: datetime | None,
    slide_ids: list[str] | None,
) -> LibraryShare:
    preview = preview_share(
        database,
        target_type=target_type,
        target_id=target_id,
        include_descendants=include_descendants,
    )
    eligible_ids = [str(item["id"]) for item in preview["included"]]
    selected_ids = list(dict.fromkeys(slide_ids or eligible_ids))
    if not selected_ids or not set(selected_ids) <= set(eligible_ids):
        raise ShareConflict("SHARE_SLIDES_NOT_REVIEWED")
    existing = database.scalar(
        select(LibraryShare).where(
            LibraryShare.target_type == target_type,
            LibraryShare.target_id == target_id,
            LibraryShare.is_active.is_(True),
        )
    )
    if existing is not None:
        raise ShareConflict("SHARE_ALREADY_ACTIVE")
    share = LibraryShare(
        target_type=target_type,
        target_id=target_id,
        include_descendants=include_descendants,
        auto_include_new=auto_include_new,
        privacy_status="passed",
        confirmed_at=utcnow(),
        expires_at=expires_at,
    )
    database.add(share)
    database.flush()
    slides = {
        slide.id: slide
        for slide in database.scalars(select(Slide).where(Slide.id.in_(selected_ids)))
    }
    for order, slide_id in enumerate(selected_ids):
        slide = slides[slide_id]
        database.add(
            ShareSlide(share_id=share.id, slide_id=slide.id, sort_order=order)
        )
        ensure_grant(database, storage, slide, SHARE, share.id)
    database.commit()
    return share


def active_public_share(
    database: OrmSession,
    *,
    target_type: str,
    public_id: str,
) -> LibraryShare:
    share = database.scalar(
        select(LibraryShare).where(
            LibraryShare.public_id == public_id,
            LibraryShare.target_type == target_type,
            LibraryShare.is_active.is_(True),
            LibraryShare.revoked_at.is_(None),
        )
    )
    if (
        share is None
        or share.privacy_status != "passed"
        or (share.expires_at is not None and share.expires_at <= utcnow())
    ):
        raise ShareConflict("SHARE_NOT_FOUND")
    return share


def public_manifest(database: OrmSession, share: LibraryShare) -> dict[str, Any]:
    name, description, _ = target_slides(
        database,
        target_type=share.target_type,
        target_id=share.target_id,
        include_descendants=share.include_descendants,
    )
    slides = list(
        database.scalars(
            select(Slide)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .where(ShareSlide.share_id == share.id)
            .order_by(ShareSlide.sort_order, Slide.id)
        )
    )
    route = "folders" if share.target_type == "folder" else "collections"
    return {
        "publicId": share.public_id,
        "targetType": share.target_type,
        "name": name,
        "description": description,
        "expiresAt": share.expires_at.isoformat() if share.expires_at else None,
        "slides": [
            {
                "position": position,
                "displayName": slide.display_name,
                "organSite": slide.organ_site,
                "stain": slide.stain,
                "diagnosis": slide.diagnosis,
                "tags": slide.tags,
                "teachingNote": slide.teaching_note,
                "thumbnailUrl": (
                    f"/api/v2/public/{route}/{share.public_id}/slides/"
                    f"{position}/thumbnail"
                ),
                "tileSource": f"/tiles/{slide.public_id}/slide.dzi",
                "scale": (slide.slide_metadata or {}).get("physicalSizeX"),
            }
            for position, slide in enumerate(slides)
        ],
    }


def rotate_share(share: LibraryShare) -> None:
    share.public_id = secrets.token_urlsafe(32)
    share.updated_at = datetime.now(UTC).replace(tzinfo=None)


def revoke_share(
    database: OrmSession,
    storage: StorageLayout,
    share: LibraryShare,
) -> None:
    slides = list(
        database.scalars(
            select(Slide)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .where(ShareSlide.share_id == share.id)
        )
    )
    for slide in slides:
        remove_grant(database, storage, slide, SHARE, share.id)
    share.is_active = False
    share.revoked_at = utcnow()
    share.updated_at = utcnow()
