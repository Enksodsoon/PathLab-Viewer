import base64
import json
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, String, and_, func, literal, or_, select, text
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .models import (
    Collection,
    CollectionSlide,
    Folder,
    PublicationGrant,
    SavedView,
    Slide,
)

MAX_FOLDER_DEPTH = 8
PROCESSING_STATES = {
    SlideState.UPLOADING,
    SlideState.QUEUED,
    SlideState.VALIDATING,
    SlideState.CONVERTING,
}
SORTS = {
    "updated_desc",
    "updated_asc",
    "created_desc",
    "created_asc",
    "name_asc",
    "name_desc",
    "manual",
}
FILTER_FIELDS = {
    "q",
    "organ",
    "stain",
    "diagnosis",
    "course",
    "tags",
    "state",
    "createdFrom",
    "createdTo",
    "updatedFrom",
    "updatedTo",
}


class LibraryConflict(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_name(value: str) -> tuple[str, str]:
    display = " ".join(unicodedata.normalize("NFKC", value).split())
    if not display:
        raise LibraryConflict("NAME_REQUIRED")
    return display, display.casefold()


def folder_depth(database: OrmSession, parent_id: str | None) -> int:
    depth = 1
    seen: set[str] = set()
    current_id = parent_id
    while current_id is not None:
        if current_id in seen:
            raise LibraryConflict("FOLDER_CYCLE")
        seen.add(current_id)
        parent = database.get(Folder, current_id)
        if parent is None or parent.trashed_at is not None:
            raise LibraryConflict("FOLDER_NOT_FOUND")
        depth += 1
        current_id = parent.parent_id
    return depth


def validate_folder_parent(
    database: OrmSession,
    *,
    folder_id: str | None,
    parent_id: str | None,
) -> None:
    if folder_id is not None and folder_id == parent_id:
        raise LibraryConflict("FOLDER_CYCLE")
    current_id = parent_id
    while current_id is not None:
        if current_id == folder_id:
            raise LibraryConflict("FOLDER_CYCLE")
        current = database.get(Folder, current_id)
        current_id = current.parent_id if current is not None else None
    depth = folder_depth(database, parent_id)
    subtree_height = 1
    if folder_id is not None:
        seed = select(
            Folder.id,
            literal(1).label("level"),
        ).where(Folder.id == folder_id).cte(name="folder_height", recursive=True)
        tree = seed.union_all(
            select(Folder.id, (seed.c.level + 1).label("level")).join(
                seed, Folder.parent_id == seed.c.id
            )
        )
        subtree_height = int(database.scalar(select(func.max(tree.c.level))) or 1)
    if depth + subtree_height - 1 > MAX_FOLDER_DEPTH:
        raise LibraryConflict("FOLDER_DEPTH_EXCEEDED")


def folder_subtree_ids(database: OrmSession, folder_id: str) -> list[str]:
    seed = select(Folder.id).where(Folder.id == folder_id).cte(
        name="folder_tree",
        recursive=True,
    )
    tree = seed.union_all(select(Folder.id).join(seed, Folder.parent_id == seed.c.id))
    return list(database.scalars(select(tree.c.id)))


def validate_saved_view(definition: dict[str, Any], sort: str) -> None:
    if set(definition) != {"version", "filters"} or definition.get("version") != 1:
        raise LibraryConflict("INVALID_SAVED_VIEW")
    filters = definition.get("filters")
    if not isinstance(filters, dict) or not set(filters) <= FILTER_FIELDS:
        raise LibraryConflict("INVALID_SAVED_VIEW")
    for value in filters.values():
        if not isinstance(value, (str, list)):
            raise LibraryConflict("INVALID_SAVED_VIEW")
        if isinstance(value, list) and (
            len(value) > 50 or any(not isinstance(item, str) for item in value)
        ):
            raise LibraryConflict("INVALID_SAVED_VIEW")
    if sort not in SORTS - {"manual"}:
        raise LibraryConflict("INVALID_SAVED_VIEW")


def _search_ids(database: OrmSession, query: str) -> list[str] | None:
    has_fts = database.scalar(
        text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'slide_search' LIMIT 1"
        )
    )
    if not has_fts:
        return None
    terms = [term.replace('"', '""') for term in query.split() if term]
    if not terms:
        return None
    expression = " AND ".join(f'"{term}"*' for term in terms)
    rows = database.execute(
        text(
            "SELECT slides.id FROM slide_search "
            "JOIN slides ON slides.rowid = slide_search.rowid "
            "WHERE slide_search MATCH :query LIMIT 5000"
        ),
        {"query": expression},
    )
    return [str(row[0]) for row in rows]


def _apply_text_search(
    database: OrmSession,
    statement: Select[tuple[Slide]],
    query: str | None,
) -> Select[tuple[Slide]]:
    if query is None or not query.strip():
        return statement
    found = _search_ids(database, query.strip())
    if found is not None:
        return statement.where(Slide.id.in_(found or [""]))
    escaped = query.strip().casefold()
    pattern = f"%{escaped}%"
    return statement.where(
        or_(
            func.lower(Slide.display_name).like(pattern),
            func.lower(Slide.original_filename).like(pattern),
            func.lower(Slide.case_id).like(pattern),
            func.lower(Slide.organ_site).like(pattern),
            func.lower(Slide.stain).like(pattern),
            func.lower(Slide.diagnosis).like(pattern),
            func.lower(Slide.course).like(pattern),
            func.lower(func.cast(Slide.tags, String)).like(pattern),
        )
    )


def _apply_filters(
    statement: Select[tuple[Slide]],
    *,
    organ: str | None = None,
    stain: str | None = None,
    diagnosis: str | None = None,
    course: str | None = None,
    tags: Iterable[str] = (),
    state: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
) -> Select[tuple[Slide]]:
    exact = (
        (Slide.organ_site, organ),
        (Slide.stain, stain),
        (Slide.diagnosis, diagnosis),
        (Slide.course, course),
    )
    for column, value in exact:
        if value:
            statement = statement.where(func.lower(column) == value.casefold())
    for tag in tags:
        statement = statement.where(
            func.lower(func.cast(Slide.tags, String)).like(
                f'%"{tag.casefold()}"%'
            )
        )
    if state:
        statement = statement.where(Slide.state == state)
    if created_from:
        statement = statement.where(Slide.created_at >= created_from)
    if created_to:
        statement = statement.where(Slide.created_at <= created_to)
    if updated_from:
        statement = statement.where(Slide.updated_at >= updated_from)
    if updated_to:
        statement = statement.where(Slide.updated_at <= updated_to)
    return statement


def build_items_statement(
    database: OrmSession,
    *,
    location: str,
    query: str | None,
    organ: str | None = None,
    stain: str | None = None,
    diagnosis: str | None = None,
    course: str | None = None,
    tags: Iterable[str] = (),
    state: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    updated_from: datetime | None = None,
    updated_to: datetime | None = None,
) -> Select[tuple[Slide]]:
    statement = select(Slide)
    if location == "trash":
        statement = statement.where(Slide.trashed_at.is_not(None))
    else:
        statement = statement.where(
            Slide.trashed_at.is_(None),
            or_(
                Slide.folder_id.is_(None),
                Slide.folder_id.not_in(
                    select(Folder.id).where(Folder.trashed_at.is_not(None))
                ),
            ),
        )
        if location == "unfiled":
            statement = statement.where(Slide.folder_id.is_(None))
        elif location == "shared":
            statement = statement.where(
                Slide.id.in_(select(PublicationGrant.slide_id).distinct())
            )
        elif location == "processing":
            statement = statement.where(Slide.state.in_(PROCESSING_STATES))
        elif location == "failed":
            statement = statement.where(Slide.state == SlideState.FAILED)
        elif location.startswith("folder:"):
            folder_id = location.split(":", 1)[1]
            folder = database.get(Folder, folder_id)
            if folder is None or folder.trashed_at is not None:
                return statement.where(text("0 = 1"))
            statement = statement.where(Slide.folder_id == folder_id)
        elif location.startswith("collection:"):
            collection_id = location.split(":", 1)[1]
            statement = statement.join(
                CollectionSlide,
                and_(
                    CollectionSlide.slide_id == Slide.id,
                    CollectionSlide.collection_id == collection_id,
                ),
            )
        elif location.startswith("saved:"):
            view_id = location.split(":", 1)[1]
            view = database.get(SavedView, view_id)
            if view is None:
                return statement.where(text("0 = 1"))
            saved_filters = view.definition.get("filters", {})
            query = str(saved_filters.get("q") or query or "") or None
            organ = _first(saved_filters.get("organ")) or organ
            stain = _first(saved_filters.get("stain")) or stain
            diagnosis = _first(saved_filters.get("diagnosis")) or diagnosis
            course = _first(saved_filters.get("course")) or course
        elif location != "all":
            return statement.where(text("0 = 1"))
    statement = _apply_text_search(database, statement, query)
    return _apply_filters(
        statement,
        organ=organ,
        stain=stain,
        diagnosis=diagnosis,
        course=course,
        tags=tags,
        state=state,
        created_from=created_from,
        created_to=created_to,
        updated_from=updated_from,
        updated_to=updated_to,
    )


def _first(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value and isinstance(value[0], str):
        return value[0]
    return None


def encode_cursor(value: str, slide_id: str) -> str:
    raw = json.dumps({"v": value, "id": slide_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[str, str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        if not isinstance(payload["v"], str) or not isinstance(payload["id"], str):
            raise ValueError
        return payload["v"], payload["id"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise LibraryConflict("INVALID_CURSOR") from error


def apply_sort_and_cursor(
    statement: Select[tuple[Slide]],
    *,
    sort: str,
    cursor: str | None,
) -> Select[tuple[Slide]]:
    if sort not in SORTS:
        raise LibraryConflict("INVALID_SORT")
    if sort == "manual":
        return statement.order_by(CollectionSlide.sort_order.asc(), Slide.id.asc())

    column: Any
    if sort.startswith("updated"):
        column = Slide.updated_at
    elif sort.startswith("created"):
        column = Slide.created_at
    else:
        column = Slide.display_name
    descending = sort.endswith("_desc")

    if cursor:
        raw_value, slide_id = decode_cursor(cursor)
        value: Any = raw_value
        if column in {Slide.updated_at, Slide.created_at}:
            value = datetime.fromisoformat(raw_value)
        if descending:
            statement = statement.where(
                or_(column < value, and_(column == value, Slide.id < slide_id))
            )
        else:
            statement = statement.where(
                or_(column > value, and_(column == value, Slide.id > slide_id))
            )
    direction = column.desc() if descending else column.asc()
    id_direction = Slide.id.desc() if descending else Slide.id.asc()
    return statement.order_by(direction, id_direction)


def cursor_for_slide(slide: Slide, sort: str) -> str:
    if sort.startswith("updated"):
        value = slide.updated_at.isoformat()
    elif sort.startswith("created"):
        value = slide.created_at.isoformat()
    else:
        value = slide.display_name
    return encode_cursor(value, slide.id)


def slide_json(slide: Slide, *, include_details: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": slide.id,
        "publicId": slide.public_id,
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
        "sourceBytes": slide.source_bytes,
        "derivativeBytes": slide.derivative_bytes,
        "state": slide.state.value,
        "errorCode": slide.error_code,
        "createdAt": slide.created_at.isoformat(),
        "updatedAt": slide.updated_at.isoformat(),
        "trashedAt": slide.trashed_at.isoformat() if slide.trashed_at else None,
        "thumbnailUrl": (
            f"/api/v2/admin/slides/{slide.id}/thumbnail"
            if slide.thumbnail_filename
            else None
        ),
    }
    if include_details:
        result["filename"] = slide.original_filename
        result["adminNotes"] = slide.admin_notes
        result["metadata"] = slide.slide_metadata
    return result


def folder_json(
    folder: Folder,
    *,
    item_count: int = 0,
    child_count: int = 0,
) -> dict[str, Any]:
    return {
        "id": folder.id,
        "parentId": folder.parent_id,
        "name": folder.name,
        "description": folder.description,
        "sortOrder": folder.sort_order,
        "itemCount": item_count,
        "childCount": child_count,
        "hasChildren": child_count > 0,
        "trashedAt": folder.trashed_at.isoformat() if folder.trashed_at else None,
        "updatedAt": folder.updated_at.isoformat(),
    }


def collection_json(collection: Collection, item_count: int = 0) -> dict[str, Any]:
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "sortOrder": collection.sort_order,
        "itemCount": item_count,
        "updatedAt": collection.updated_at.isoformat(),
    }


def saved_view_json(view: SavedView) -> dict[str, Any]:
    return {
        "id": view.id,
        "name": view.name,
        "definition": view.definition,
        "sort": view.sort,
        "updatedAt": view.updated_at.isoformat(),
    }


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
