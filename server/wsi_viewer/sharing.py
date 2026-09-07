import json
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import Select, and_, or_, select, update
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import object_session

from .domain import SlideState
from .library import folder_subtree_ids, utcnow
from .models import (
    AuditEvent,
    Collection,
    CollectionSlide,
    Folder,
    LibraryShare,
    PublicationGrant,
    ShareSlide,
    Slide,
)
from .publication import SHARE, ensure_grant, remove_grant
from .storage import StorageLayout, publish_derivative, unpublish_derivative
from .time_support import as_utc, utc_now


class ShareConflict(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def lock_share_target(database: OrmSession, target_type: str, target_id: str) -> None:
    """Serialize against the target row, including on SQLite (no row-lock fiction).

    As with organization mutations, an UPDATE obtains SQLite's writer lock and
    PostgreSQL's row lock until commit/rollback. Re-read eligibility afterward.
    """
    model = Folder if target_type == "folder" else Collection
    database.execute(
        update(model).where(model.id == target_id).values(id=model.id, updated_at=model.updated_at)
    )


def shared_slide_statement(
    public_id: str,
    target_type: str,
) -> Select[tuple[Slide]]:
    return (
        select(Slide)
        .join(ShareSlide, ShareSlide.slide_id == Slide.id)
        .join(LibraryShare, LibraryShare.id == ShareSlide.share_id)
        .join(
            PublicationGrant,
            and_(
                PublicationGrant.slide_id == Slide.id,
                PublicationGrant.source_type == SHARE,
                PublicationGrant.source_id == LibraryShare.id,
            ),
        )
        .where(
            LibraryShare.public_id == public_id,
            LibraryShare.target_type == target_type,
            LibraryShare.is_active.is_(True),
            LibraryShare.revoked_at.is_(None),
            LibraryShare.privacy_status == "passed",
            or_(LibraryShare.expires_at.is_(None), LibraryShare.expires_at > utc_now()),
            Slide.state == SlideState.PUBLISHED,
            Slide.privacy_status == "passed",
            Slide.trashed_at.is_(None),
        )
    )


def active_folder_subtree_ids(database: OrmSession, root_id: str) -> list[str]:
    # Only sharing filters organizational trash; generic trash/restore traversal
    # must still visit every descendant.
    folders = list(
        database.scalars(
            select(Folder).where(
                Folder.id.in_(folder_subtree_ids(database, root_id)),
                Folder.trashed_at.is_(None),
            )
        )
    )
    children: dict[str | None, list[str]] = {}
    for folder in folders:
        children.setdefault(folder.parent_id, []).append(folder.id)
    result = [root_id]
    for folder_id in result:
        result.extend(children.get(folder_id, []))
    return result


def _share_delivery_path(storage: StorageLayout, public_id: str) -> Path:
    validated = storage.public_for(public_id).name
    return storage.root / "delivery" / "shares" / f"{validated}.json"


def _read_share_delivery_manifest(
    storage: StorageLayout,
    public_id: str,
    target_type: str,
) -> dict[str, Any]:
    try:
        raw = json.loads(_share_delivery_path(storage, public_id).read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("targetType") != target_type:
            raise ValueError
        slots = raw["slides"]
        if not isinstance(slots, list):
            raise ValueError
        seen: set[str] = set()
        for item in slots:
            if item is None:
                continue
            if not isinstance(item, str) or item in seen:
                raise ValueError
            storage.public_for(item)
            seen.add(item)
        return raw
    except (OSError, KeyError, TypeError, ValueError):
        raise ShareConflict("SHARE_NOT_FOUND") from None


def write_share_delivery_manifest(
    storage: StorageLayout,
    share: LibraryShare,
    slides: list[Slide],
) -> None:
    target = _share_delivery_path(storage, share.public_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    database = object_session(share)
    if database is None:
        raise ValueError("Share delivery requires persisted membership positions")
    members = list(
        database.execute(
            select(ShareSlide.sort_order, Slide.public_id)
            .join(Slide, Slide.id == ShareSlide.slide_id)
            .join(
                PublicationGrant,
                and_(
                    PublicationGrant.slide_id == Slide.id,
                    PublicationGrant.source_type == SHARE,
                    PublicationGrant.source_id == ShareSlide.share_id,
                ),
            )
            .where(
                ShareSlide.share_id == share.id,
                Slide.id.in_([slide.id for slide in slides]),
                Slide.trashed_at.is_(None),
                Slide.state == SlideState.PUBLISHED,
            )
        )
    )
    # The existing manifest owns every issued URL position, including legacy
    # manifests that compacted members. Preserve that mapping without changing
    # DB order; new public IDs start with the persisted membership order.
    if target.exists():
        previous = _read_share_delivery_manifest(storage, share.public_id, share.target_type)[
            "slides"
        ]
        eligible = {slide_public_id for _, slide_public_id in members}
        slots: list[str | None] = [item if item in eligible else None for item in previous]
        known = set(previous)
        slots.extend(
            slide_public_id
            for _, slide_public_id in sorted(members)
            if slide_public_id not in known
        )
    else:
        slots = [None] * (max((order for order, _ in members), default=-1) + 1)
        for order, slide_public_id in members:
            slots[order] = slide_public_id
    payload = {
        "targetType": share.target_type,
        "expiresAt": share.expires_at.isoformat() if share.expires_at else None,
        "slides": slots,
    }
    try:
        staging.write_text(
            json.dumps(payload, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(staging, target)
    finally:
        staging.unlink(missing_ok=True)


def remove_share_delivery_manifest(storage: StorageLayout, public_id: str) -> None:
    _share_delivery_path(storage, public_id).unlink(missing_ok=True)


def retire_share_delivery_manifest(storage: StorageLayout, public_id: str) -> None:
    """Cleanup after commit; stale files confer no grant and startup retries."""
    try:
        remove_share_delivery_manifest(storage, public_id)
    except OSError:
        logging.getLogger(__name__).warning("Share manifest cleanup deferred: %s", public_id)


def share_delivery_public_id(
    storage: StorageLayout,
    *,
    public_id: str,
    target_type: str,
    position: int,
) -> str:
    if position < 0:
        raise ShareConflict("SHARE_NOT_FOUND")
    try:
        raw = _read_share_delivery_manifest(storage, public_id, target_type)
        expires_at = raw.get("expiresAt")
        if expires_at is not None and as_utc(datetime.fromisoformat(expires_at)) <= utcnow():
            raise ValueError
        slides = raw["slides"]
        selected = slides[position]
        if not isinstance(selected, str):
            raise ValueError
        return storage.public_for(selected).name
    except (FileNotFoundError, IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise ShareConflict("SHARE_NOT_FOUND") from None


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
            active_folder_subtree_ids(database, folder.id) if include_descendants else [folder.id]
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


def relative_folder_path(
    database: OrmSession,
    *,
    root_id: str,
    folder_id: str | None,
) -> list[str]:
    if folder_id is None or folder_id == root_id:
        return []
    path: list[str] = []
    current_id: str | None = folder_id
    seen: set[str] = set()
    while current_id is not None and current_id != root_id:
        if current_id in seen:
            raise ShareConflict("SHARE_TARGET_NOT_FOUND")
        seen.add(current_id)
        current = database.get(Folder, current_id)
        if current is None or current.trashed_at is not None:
            raise ShareConflict("SHARE_TARGET_NOT_FOUND")
        path.append(current.name)
        current_id = current.parent_id
    if current_id != root_id:
        raise ShareConflict("SHARE_TARGET_NOT_FOUND")
    path.reverse()
    return path


def shared_folder_paths(
    database: OrmSession,
    *,
    root_id: str,
    include_descendants: bool,
) -> list[list[str]]:
    if not include_descendants:
        return []
    folder_ids = active_folder_subtree_ids(database, root_id)
    paths = [
        relative_folder_path(database, root_id=root_id, folder_id=folder_id)
        for folder_id in folder_ids
        if folder_id != root_id
    ]
    return sorted(
        paths,
        key=lambda path: (len(path), tuple(part.casefold() for part in path)),
    )


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
        {
            "id": slide.id,
            "displayName": slide.display_name,
            "privacyReviewRequired": slide.privacy_status != "passed",
            "folderPath": (
                relative_folder_path(
                    database,
                    root_id=target_id,
                    folder_id=slide.folder_id,
                )
                if target_type == "folder"
                else []
            ),
        }
        for slide in slides
        if slide.state in ready_states
    ]
    excluded = [
        {
            "id": slide.id,
            "displayName": slide.display_name,
            "reason": "SLIDE_NOT_READY",
            "folderPath": (
                relative_folder_path(
                    database,
                    root_id=target_id,
                    folder_id=slide.folder_id,
                )
                if target_type == "folder"
                else []
            ),
        }
        for slide in slides
        if slide.state not in ready_states
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
            database.scalars(select(ShareSlide.id).where(ShareSlide.share_id == share.id)).all()
        )
    state = "revoked" if not share.is_active else "active"
    if share.expires_at is not None and as_utc(share.expires_at) <= utc_now():
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
    synthetic_run_id: str | None = None,
) -> LibraryShare:
    lock_share_target(database, target_type, target_id)
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
    existing = list(
        database.scalars(
            select(LibraryShare).where(
                LibraryShare.target_type == target_type,
                LibraryShare.target_id == target_id,
                LibraryShare.is_active.is_(True),
            )
        )
    )
    if any(
        item.revoked_at is None and (item.expires_at is None or as_utc(item.expires_at) > utc_now())
        for item in existing
    ):
        raise ShareConflict("SHARE_ALREADY_ACTIVE")
    share = LibraryShare(
        target_type=target_type,
        target_id=target_id,
        include_descendants=include_descendants,
        auto_include_new=auto_include_new,
        folder_paths=(
            shared_folder_paths(
                database,
                root_id=target_id,
                include_descendants=include_descendants,
            )
            if target_type == "folder"
            else []
        ),
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
    unpublished_ids = [
        slide.public_id
        for slide in slides.values()
        if not database.scalar(
            select(PublicationGrant.id).where(PublicationGrant.slide_id == slide.id).limit(1)
        )
    ]
    previous_deliveries = list(
        database.execute(
            select(Slide.id, Slide.public_id)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .where(
                ShareSlide.share_id.in_([item.id for item in existing]),
                Slide.render_mode == "static_dzi",
                Slide.state == SlideState.PUBLISHED,
            )
        )
    )
    new_public_id = share.public_id
    try:
        for order, slide_id in enumerate(selected_ids):
            slide = slides[slide_id]
            database.add(
                ShareSlide(
                    share_id=share.id,
                    slide_id=slide.id,
                    folder_path=(
                        relative_folder_path(
                            database,
                            root_id=target_id,
                            folder_id=slide.folder_id,
                        )
                        if target_type == "folder"
                        else []
                    ),
                    sort_order=order,
                )
            )
            ensure_grant(database, storage, slide, SHARE, share.id)
        if synthetic_run_id is not None:
            database.add(
                AuditEvent(
                    action="capacity.sentinel.share",
                    target_id=share.id,
                    detail={"runId": synthetic_run_id},
                )
            )
        write_share_delivery_manifest(
            storage, share, [slides[slide_id] for slide_id in selected_ids]
        )
        for expired in existing:
            revoke_share(database, storage, expired)
        database.commit()
    except Exception:
        try:
            # Compensate while still holding the target lock, so a retry cannot
            # publish between rollback and cleanup of this attempt's aliases.
            retire_share_delivery_manifest(storage, new_public_id)
            for public_id in unpublished_ids:
                unpublish_derivative(storage, public_id)
            for slide_id, public_id in previous_deliveries:
                if not storage.public_for(public_id).exists():
                    publish_derivative(storage, slide_id, public_id)
        finally:
            database.rollback()
        raise
    for expired in existing:
        retire_share_delivery_manifest(storage, expired.public_id)
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
        or (share.expires_at is not None and as_utc(share.expires_at) <= utc_now())
    ):
        raise ShareConflict("SHARE_NOT_FOUND")
    return share


def public_manifest(
    database: OrmSession,
    share: LibraryShare,
    storage: StorageLayout,
) -> dict[str, Any]:
    target = (
        database.get(Folder, share.target_id)
        if share.target_type == "folder"
        else database.get(Collection, share.target_id)
    )
    if target is None:
        raise ShareConflict("SHARE_TARGET_NOT_FOUND")
    name, description = target.name, target.description
    rows = list(
        database.execute(
            select(Slide, ShareSlide)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .join(
                PublicationGrant,
                and_(
                    PublicationGrant.slide_id == Slide.id,
                    PublicationGrant.source_type == SHARE,
                    PublicationGrant.source_id == ShareSlide.share_id,
                ),
            )
            .where(
                ShareSlide.share_id == share.id,
                Slide.trashed_at.is_(None),
                Slide.state == SlideState.PUBLISHED,
                Slide.privacy_status == "passed",
            )
            .order_by(ShareSlide.sort_order, Slide.id)
        ).all()
    )
    persisted = _read_share_delivery_manifest(storage, share.public_id, share.target_type)
    positions = {
        value: position
        for position, value in enumerate(persisted["slides"])
        if isinstance(value, str)
    }
    route = "folders" if share.target_type == "folder" else "collections"
    return {
        "publicId": share.public_id,
        "targetType": share.target_type,
        "name": name,
        "description": description,
        "expiresAt": share.expires_at.isoformat() if share.expires_at else None,
        "folders": share.folder_paths or [],
        "slides": [
            {
                "position": positions[slide.public_id],
                "folderPath": membership.folder_path or [],
                "displayName": slide.display_name,
                "organSite": slide.organ_site,
                "stain": slide.stain,
                "diagnosis": slide.diagnosis,
                "tags": slide.tags,
                "teachingNote": slide.teaching_note,
                "thumbnailUrl": (
                    f"/api/v2/public/{route}/{share.public_id}/slides/{positions[slide.public_id]}/thumbnail"
                ),
                "tileSource": (
                    f"/api/v2/public/{route}/{share.public_id}/slides/{positions[slide.public_id]}/tiles/slide.dzi"
                ),
                "scale": (slide.slide_metadata or {}).get("physicalSizeX"),
            }
            for slide, membership in rows
            if slide.public_id in positions
        ],
    }


def rotate_share(share: LibraryShare) -> None:
    share.public_id = secrets.token_urlsafe(32)
    share.updated_at = datetime.now(UTC)


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


def detach_slide_from_shares(
    database: OrmSession,
    storage: StorageLayout,
    slide: Slide,
) -> list[tuple[LibraryShare, list[Slide]]]:
    memberships = list(
        database.execute(
            select(ShareSlide, LibraryShare)
            .join(LibraryShare, LibraryShare.id == ShareSlide.share_id)
            .where(ShareSlide.slide_id == slide.id)
        ).all()
    )
    active_shares = {
        share.id: share for _, share in memberships if share.is_active and share.revoked_at is None
    }
    for membership, share in memberships:
        remove_grant(database, storage, slide, SHARE, share.id)
        database.delete(membership)
    database.flush()
    return [
        (
            share,
            list(
                database.scalars(
                    select(Slide)
                    .join(ShareSlide, ShareSlide.slide_id == Slide.id)
                    .where(ShareSlide.share_id == share.id)
                    .order_by(ShareSlide.sort_order, Slide.id)
                )
            ),
        )
        for share in active_shares.values()
    ]
