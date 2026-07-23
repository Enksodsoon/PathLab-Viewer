import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from .domain import SlideState
from .models import Folder, FolderShare, PublicationGrant, Slide
from .publication import FOLDER, remove_folder_grants
from .storage import StorageLayout
from .storage_accounting import ACTIVE_STATES

MAX_FOLDER_DEPTH = 3


class LibraryError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def clean_label(value: str, *, maximum: int, code: str) -> str:
    cleaned = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
    if not cleaned or len(cleaned) > maximum:
        raise LibraryError(code)
    return cleaned


def clean_text(value: str, *, maximum: int, code: str) -> str:
    cleaned = unicodedata.normalize("NFC", value).strip()
    if len(cleaned) > maximum:
        raise LibraryError(code)
    return cleaned


def clean_tags(values: list[str]) -> list[str]:
    if len(values) > 20:
        raise LibraryError("INVALID_SLIDE_METADATA")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = clean_label(value, maximum=50, code="INVALID_SLIDE_METADATA")
        key = cleaned.casefold()
        if key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def folder_depth(database: Session, folder_id: str | None) -> int:
    depth = 0
    seen: set[str] = set()
    current_id = folder_id
    while current_id is not None:
        if current_id in seen:
            raise LibraryError("FOLDER_CYCLE")
        seen.add(current_id)
        current = database.get(Folder, current_id)
        if current is None:
            raise LibraryError("FOLDER_NOT_FOUND")
        depth += 1
        current_id = current.parent_id
        if depth > MAX_FOLDER_DEPTH:
            raise LibraryError("FOLDER_DEPTH_EXCEEDED")
    return depth


def _max_subtree_depth(database: Session, folder_id: str) -> int:
    folders = database.scalars(select(Folder)).all()
    children: dict[str | None, list[str]] = {}
    for folder in folders:
        children.setdefault(folder.parent_id, []).append(folder.id)

    def descend(current: str, seen: set[str]) -> int:
        if current in seen:
            raise LibraryError("FOLDER_CYCLE")
        next_seen = {*seen, current}
        nested = children.get(current, [])
        return 1 if not nested else 1 + max(descend(item, next_seen) for item in nested)

    return descend(folder_id, set())


def create_folder(
    database: Session,
    *,
    name: str,
    parent_id: str | None,
    description: str = "",
    sort_order: int = 0,
) -> Folder:
    if parent_id is not None and folder_depth(database, parent_id) >= MAX_FOLDER_DEPTH:
        raise LibraryError("FOLDER_DEPTH_EXCEEDED")
    cleaned = clean_label(name, maximum=120, code="INVALID_FOLDER_NAME")
    folder = Folder(
        parent_id=parent_id,
        name=cleaned,
        normalized_name=cleaned.casefold(),
        description=clean_text(
            description, maximum=2000, code="INVALID_FOLDER_DESCRIPTION"
        ),
        sort_order=sort_order,
    )
    database.add(folder)
    database.flush()
    return folder


def move_folder(database: Session, folder: Folder, parent_id: str | None) -> None:
    if parent_id == folder.id:
        raise LibraryError("FOLDER_CYCLE")
    current = parent_id
    while current is not None:
        if current == folder.id:
            raise LibraryError("FOLDER_CYCLE")
        parent = database.get(Folder, current)
        if parent is None:
            raise LibraryError("FOLDER_NOT_FOUND")
        current = parent.parent_id
    parent_depth = folder_depth(database, parent_id)
    if parent_depth + _max_subtree_depth(database, folder.id) > MAX_FOLDER_DEPTH:
        raise LibraryError("FOLDER_DEPTH_EXCEEDED")
    folder.parent_id = parent_id
    folder.updated_at = datetime.now(UTC)
    database.flush()


def delete_folder(
    database: Session,
    layout: StorageLayout,
    folder: Folder,
) -> None:
    children = database.scalars(
        select(Folder).where(Folder.parent_id == folder.id)
    ).all()
    destination_names = set(
        database.scalars(
            select(Folder.normalized_name).where(
                Folder.parent_id == folder.parent_id,
                Folder.id != folder.id,
            )
        ).all()
    )
    child_names = [child.normalized_name for child in children]
    if destination_names.intersection(child_names) or any(
        count > 1 for count in Counter(child_names).values()
    ):
        raise LibraryError("FOLDER_NAME_CONFLICT")
    remove_folder_grants(database, layout, folder.id)
    database.execute(
        update(Slide).where(Slide.folder_id == folder.id).values(folder_id=None)
    )
    for child in children:
        child.parent_id = folder.parent_id
    database.delete(folder)
    database.flush()


def folder_json(folder: Folder, share: FolderShare | None = None) -> dict[str, Any]:
    return {
        "id": folder.id,
        "parentId": folder.parent_id,
        "name": folder.name,
        "description": folder.description,
        "sortOrder": folder.sort_order,
        "createdAt": folder.created_at.isoformat(),
        "updatedAt": folder.updated_at.isoformat(),
        "share": (
            {
                "publicId": share.public_id,
                "isActive": share.is_active,
                "createdAt": share.created_at.isoformat(),
            }
            if share is not None
            else None
        ),
    }


def admin_slide_json(
    slide: Slide,
    *,
    individual: bool,
    folder_grant_count: int,
) -> dict[str, Any]:
    return {
        "id": slide.id,
        "publicId": slide.public_id,
        "displayName": slide.display_name,
        "filename": slide.original_filename,
        "sourceBytes": slide.source_bytes,
        "reservedBytes": slide.reserved_bytes,
        "derivativeBytes": slide.derivative_bytes,
        "derivativeFileCount": slide.derivative_file_count,
        "state": slide.state.value,
        "errorCode": slide.error_code,
        "errorMessage": slide.error_message,
        "metadata": slide.slide_metadata,
        "createdAt": slide.created_at.isoformat(),
        "folderId": slide.folder_id,
        "description": slide.description,
        "stain": slide.stain,
        "organSite": slide.organ_site,
        "tags": slide.tags,
        "teachingNote": slide.teaching_note,
        "adminNotes": slide.admin_notes,
        "sortOrder": slide.sort_order,
        "publication": {
            "individual": individual,
            "folderGrantCount": folder_grant_count,
            "isPublic": slide.state is SlideState.PUBLISHED,
        },
    }


def library_payload(database: Session, cap_bytes: int) -> dict[str, Any]:
    folders = database.scalars(
        select(Folder).order_by(
            Folder.sort_order, Folder.normalized_name, Folder.created_at
        )
    ).all()
    shares = {
        share.folder_id: share
        for share in database.scalars(
            select(FolderShare).where(FolderShare.is_active.is_(True))
        ).all()
    }
    slides = database.scalars(
        select(Slide).order_by(Slide.sort_order, Slide.display_name, Slide.created_at)
    ).all()
    grants: dict[str, list[PublicationGrant]] = {}
    for grant in database.scalars(select(PublicationGrant)).all():
        grants.setdefault(grant.slide_id, []).append(grant)
    contribution = case(
        (Slide.state.in_(ACTIVE_STATES), Slide.reserved_bytes),
        else_=Slide.source_bytes + Slide.derivative_bytes,
    )
    totals = database.execute(
        select(
            func.coalesce(func.sum(Slide.source_bytes), 0),
            func.coalesce(func.sum(Slide.reserved_bytes), 0),
            func.coalesce(func.sum(Slide.derivative_bytes), 0),
            func.coalesce(func.sum(Slide.derivative_file_count), 0),
            func.coalesce(func.sum(contribution), 0),
        )
    ).one()
    return {
        "folders": [folder_json(item, shares.get(item.id)) for item in folders],
        "slides": [
            admin_slide_json(
                slide,
                individual=any(
                    grant.source_type == "individual" for grant in grants.get(slide.id, [])
                ),
                folder_grant_count=sum(
                    grant.source_type == FOLDER for grant in grants.get(slide.id, [])
                ),
            )
            for slide in slides
        ],
        "storage": {
            "sourceBytes": int(totals[0]),
            "reservedBytes": int(totals[1]),
            "derivativeBytes": int(totals[2]),
            "derivativeFileCount": int(totals[3]),
            "accountedBytes": int(totals[4]),
            "capBytes": cap_bytes,
            "availableBytes": max(0, cap_bytes - int(totals[4])),
        },
    }
