import json
import os
import secrets
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .library import folder_subtree_ids, utcnow
from .models import (
    AuditEvent,
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


def _share_delivery_path(storage: StorageLayout, public_id: str) -> Path:
    validated = storage.public_for(public_id).name
    return storage.root / "delivery" / "shares" / f"{validated}.json"


def write_share_delivery_manifest(
    storage: StorageLayout,
    share: LibraryShare,
    slides: list[Slide],
) -> None:
    target = _share_delivery_path(storage, share.public_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    payload = {
        "targetType": share.target_type,
        "expiresAt": share.expires_at.isoformat() if share.expires_at else None,
        "slides": [slide.public_id for slide in slides],
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
        raw = json.loads(_share_delivery_path(storage, public_id).read_text(encoding="utf-8"))
        if raw.get("targetType") != target_type:
            raise ValueError
        expires_at = raw.get("expiresAt")
        if expires_at is not None and datetime.fromisoformat(expires_at) <= utcnow():
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
        folder_ids = folder_subtree_ids(database, folder.id) if include_descendants else [folder.id]
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
    folder_ids = folder_subtree_ids(database, root_id)
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
    synthetic_run_id: str | None = None,
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
    database.commit()
    write_share_delivery_manifest(
        storage,
        share,
        [slides[slide_id] for slide_id in selected_ids],
    )
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
    rows = list(
        database.execute(
            select(Slide, ShareSlide)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .where(ShareSlide.share_id == share.id)
            .order_by(ShareSlide.sort_order, Slide.id)
        ).all()
    )
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
                "position": position,
                "folderPath": membership.folder_path or [],
                "displayName": slide.display_name,
                "organSite": slide.organ_site,
                "stain": slide.stain,
                "diagnosis": slide.diagnosis,
                "tags": slide.tags,
                "teachingNote": slide.teaching_note,
                "thumbnailUrl": (
                    f"/api/v2/public/{route}/{share.public_id}/slides/{position}/thumbnail"
                ),
                "tileSource": (
                    f"/api/v2/public/{route}/{share.public_id}/slides/{position}/tiles/slide.dzi"
                ),
                "scale": (slide.slide_metadata or {}).get("physicalSizeX"),
            }
            for position, (slide, membership) in enumerate(rows)
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
    for share in active_shares.values():
        remove_share_delivery_manifest(storage, share.public_id)
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
