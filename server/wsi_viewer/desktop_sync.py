import base64
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from .models import DesktopSyncEvent, Folder, Slide

SCHEMA = "desktop-sync/v1"


def revision_for(value: datetime) -> int:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return int(aware.timestamp() * 1_000_000)


def encode_library_cursor(slide: Slide) -> str:
    payload = json.dumps(
        [slide.updated_at.isoformat(), slide.id], separators=(",", ":")
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_library_cursor(value: str) -> tuple[datetime, str]:
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not isinstance(decoded, list) or len(decoded) != 2:
            raise ValueError
        return datetime.fromisoformat(str(decoded[0])), str(decoded[1])
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("DESKTOP_SYNC_CURSOR_INVALID") from error


def remote_slide_json(slide: Slide) -> dict[str, Any]:
    metadata_revision = revision_for(slide.updated_at)
    return {
        "id": slide.id,
        "displayName": slide.display_name,
        "description": slide.description,
        "folderId": slide.folder_id,
        "caseId": slide.case_id,
        "organSite": slide.organ_site,
        "stain": slide.stain,
        "diagnosis": slide.diagnosis,
        "course": slide.course,
        "tags": slide.tags,
        "teachingNote": slide.teaching_note,
        "adminNotes": slide.admin_notes,
        "state": slide.state.value,
        "renderMode": slide.render_mode,
        "imageRevision": revision_for(slide.created_at),
        "annotationRevision": slide.annotation_version,
        "metadataRevision": metadata_revision,
        "folderRevision": metadata_revision,
        "contentBytes": slide.source_bytes if slide.render_mode == "ome_dynamic" else 0,
        "contentSha256": slide.sha256 if slide.render_mode == "ome_dynamic" else None,
        "thumbnailUrl": f"/api/v1/desktop/slides/{slide.id}/preview/thumbnail.jpg",
        "tileSourceUrl": f"/api/v1/desktop/slides/{slide.id}/preview/slide.dzi",
        "updatedAt": slide.updated_at.isoformat(),
    }


def remote_folder_json(folder: Folder) -> dict[str, Any]:
    return {
        "id": folder.id,
        "parentId": folder.parent_id,
        "name": folder.name,
        "description": folder.description,
        "revision": revision_for(folder.updated_at),
        "updatedAt": folder.updated_at.isoformat(),
    }


def change_json(event: DesktopSyncEvent) -> dict[str, Any]:
    return {
        "sequence": event.sequence,
        "entityType": event.entity_type,
        "entityId": event.entity_id,
        "operation": event.operation,
        "revision": event.revision,
        "createdAt": event.created_at.isoformat(),
    }


def record_sync_event(
    database: OrmSession,
    entity_type: str,
    entity_id: str,
    operation: str,
    revision: int,
) -> None:
    database.add(
        DesktopSyncEvent(
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            revision=revision,
        )
    )
