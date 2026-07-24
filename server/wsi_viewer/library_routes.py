# ruff: noqa: B008

import hashlib
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import case, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .domain import InvalidTransition, SlideState, transition
from .library import (
    LibraryConflict,
    apply_sort_and_cursor,
    build_items_statement,
    collection_json,
    cursor_for_slide,
    folder_json,
    folder_subtree_ids,
    normalize_name,
    saved_view_json,
    slide_json,
    utcnow,
    validate_folder_parent,
    validate_saved_view,
)
from .models import (
    Collection,
    CollectionSlide,
    Folder,
    Job,
    LibraryShare,
    PublicationGrant,
    SavedView,
    ShareSlide,
    Slide,
)
from .publication import delete_all_slide_grants
from .sharing import (
    ShareConflict,
    activate_share,
    active_public_share,
    preview_share,
    public_manifest,
    revoke_share,
    rotate_share,
    share_json,
)
from .storage import StorageLayout


class FolderCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=120)
    parent_id: str | None = Field(default=None, alias="parentId")
    description: str = Field(default="", max_length=2000)


class FolderUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=120)
    parent_id: str | None = Field(default=None, alias="parentId")
    description: str | None = Field(default=None, max_length=2000)
    sort_order: int | None = Field(default=None, alias="sortOrder", ge=0)


class CollectionRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)


class CollectionUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = Field(default=None, alias="sortOrder", ge=0)


class SlideIdsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    slide_ids: list[str] = Field(alias="slideIds", min_length=1, max_length=50)


class BatchMoveRequest(SlideIdsRequest):
    folder_id: str | None = Field(default=None, alias="folderId")


class BatchMetadataRequest(SlideIdsRequest):
    model_config = ConfigDict(populate_by_name=True)

    display_name: str | None = Field(default=None, alias="displayName", max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    case_id: str | None = Field(default=None, alias="caseId", max_length=120)
    organ_site: str | None = Field(default=None, alias="organSite", max_length=120)
    stain: str | None = Field(default=None, max_length=80)
    diagnosis: str | None = Field(default=None, max_length=300)
    course: str | None = Field(default=None, max_length=160)
    tags: list[str] | None = Field(default=None, max_length=50)
    teaching_note: str | None = Field(default=None, alias="teachingNote", max_length=8000)
    admin_notes: str | None = Field(default=None, alias="adminNotes", max_length=16000)


class SavedViewRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    definition: dict[str, Any]
    sort: str = "updated_desc"


class SavedViewUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    definition: dict[str, Any] | None = None
    sort: str | None = None


class ShareCreateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    target_type: str = Field(alias="targetType", pattern="^(folder|collection)$")
    target_id: str = Field(alias="targetId")
    include_descendants: bool = Field(default=False, alias="includeDescendants")
    auto_include_new: bool = Field(default=False, alias="autoIncludeNew")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    slide_ids: list[str] | None = Field(default=None, alias="slideIds", min_length=1, max_length=50)
    deidentified_confirmed: bool = Field(default=False, alias="deidentifiedConfirmed")


def _conflict(error: LibraryConflict) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND if error.code.endswith("_NOT_FOUND") else status.HTTP_409_CONFLICT
    )
    return HTTPException(status_code=status_code, detail={"code": error.code})


def _folder_counts(
    database: OrmSession, folders: list[Folder]
) -> tuple[dict[str, int], dict[str, int]]:
    if not folders:
        return {}, {}
    folder_ids = [folder.id for folder in folders]
    item_counts = {
        str(folder_id): int(count)
        for folder_id, count in database.execute(
            select(Slide.folder_id, func.count(Slide.id))
            .where(
                Slide.folder_id.in_(folder_ids),
                Slide.trashed_at.is_(None),
            )
            .group_by(Slide.folder_id)
        )
        if folder_id is not None
    }
    child_counts = {
        str(parent_id): int(count)
        for parent_id, count in database.execute(
            select(Folder.parent_id, func.count(Folder.id))
            .where(
                Folder.parent_id.in_(folder_ids),
                Folder.trashed_at.is_(None),
            )
            .group_by(Folder.parent_id)
        )
        if parent_id is not None
    }
    return item_counts, child_counts


def _get_slide(database: OrmSession, slide_id: str) -> Slide:
    slide = database.get(Slide, slide_id)
    if slide is None:
        raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
    return slide


def _get_collection(database: OrmSession, collection_id: str) -> Collection:
    collection = database.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail={"code": "COLLECTION_NOT_FOUND"})
    return collection


def _has_active_share(
    database: OrmSession,
    *,
    target_type: str,
    target_id: str,
) -> bool:
    return (
        database.scalar(
            select(LibraryShare.id)
            .where(
                LibraryShare.target_type == target_type,
                LibraryShare.target_id == target_id,
                LibraryShare.is_active.is_(True),
                LibraryShare.revoked_at.is_(None),
            )
            .limit(1)
        )
        is not None
    )


def _unique_ids(slide_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(slide_ids))


def register_library_routes(
    app: FastAPI,
    *,
    factory: sessionmaker[OrmSession],
    storage: StorageLayout,
    database_dependency: Callable[[], Iterator[OrmSession]],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
) -> None:
    def navigation(
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        state_counts = database.execute(
            select(
                func.count(Slide.id).filter(Slide.trashed_at.is_(None)),
                func.count(Slide.id).filter(Slide.trashed_at.is_(None), Slide.folder_id.is_(None)),
                func.count(Slide.id).filter(
                    Slide.trashed_at.is_(None),
                    Slide.state.in_(
                        {
                            SlideState.UPLOADING,
                            SlideState.QUEUED,
                            SlideState.VALIDATING,
                            SlideState.CONVERTING,
                        }
                    ),
                ),
                func.count(Slide.id).filter(
                    Slide.trashed_at.is_(None), Slide.state == SlideState.FAILED
                ),
                func.count(Slide.id).filter(Slide.trashed_at.is_not(None)),
            )
        ).one()
        shared_count = int(
            database.scalar(
                select(func.count(func.distinct(PublicationGrant.slide_id)))
                .select_from(PublicationGrant)
                .join(Slide, Slide.id == PublicationGrant.slide_id)
                .where(Slide.trashed_at.is_(None))
            )
            or 0
        )
        roots = database.scalars(
            select(Folder)
            .where(Folder.parent_id.is_(None), Folder.trashed_at.is_(None))
            .order_by(Folder.sort_order, Folder.normalized_name)
        ).all()
        item_counts, child_counts = _folder_counts(database, list(roots))
        collections = database.execute(
            select(Collection, func.count(CollectionSlide.id))
            .outerjoin(
                CollectionSlide,
                CollectionSlide.collection_id == Collection.id,
            )
            .group_by(Collection.id)
            .order_by(Collection.sort_order, Collection.normalized_name)
        ).all()
        views = database.scalars(select(SavedView).order_by(SavedView.normalized_name)).all()
        return {
            "counts": {
                "all": int(state_counts[0]),
                "unfiled": int(state_counts[1]),
                "shared": shared_count,
                "processing": int(state_counts[2]),
                "failed": int(state_counts[3]),
                "trash": int(state_counts[4]),
            },
            "folders": [
                folder_json(
                    folder,
                    item_count=item_counts.get(folder.id, 0),
                    child_count=child_counts.get(folder.id, 0),
                )
                for folder in roots
            ],
            "collections": [
                collection_json(collection, int(count)) for collection, count in collections
            ],
            "savedViews": [saved_view_json(view) for view in views],
        }

    app.add_api_route(
        "/api/v2/admin/library/navigation",
        navigation,
        methods=["GET"],
    )

    def folder_children(
        folder_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        parent = database.get(Folder, folder_id)
        if parent is None or parent.trashed_at is not None:
            raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
        children = database.scalars(
            select(Folder)
            .where(Folder.parent_id == folder_id, Folder.trashed_at.is_(None))
            .order_by(Folder.sort_order, Folder.normalized_name)
        ).all()
        item_counts, child_counts = _folder_counts(database, list(children))
        return [
            folder_json(
                folder,
                item_count=item_counts.get(folder.id, 0),
                child_count=child_counts.get(folder.id, 0),
            )
            for folder in children
        ]

    app.add_api_route(
        "/api/v2/admin/folders/{folder_id}/children",
        folder_children,
        methods=["GET"],
    )

    def library_items(
        location: str = "all",
        q: str | None = Query(default=None, max_length=300),
        organ: str | None = Query(default=None, max_length=120),
        stain: str | None = Query(default=None, max_length=80),
        diagnosis: str | None = Query(default=None, max_length=300),
        course: str | None = Query(default=None, max_length=160),
        tags: list[str] | None = Query(default=None),
        state: str | None = Query(default=None, max_length=40),
        created_from: datetime | None = Query(default=None, alias="createdFrom"),
        created_to: datetime | None = Query(default=None, alias="createdTo"),
        updated_from: datetime | None = Query(default=None, alias="updatedFrom"),
        updated_to: datetime | None = Query(default=None, alias="updatedTo"),
        sort: str = Query(default="updated_desc", max_length=40),
        cursor: str | None = Query(default=None, max_length=1000),
        limit: int = Query(default=48, ge=1, le=100),
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        try:
            base = build_items_statement(
                database,
                location=location,
                query=q,
                organ=organ,
                stain=stain,
                diagnosis=diagnosis,
                course=course,
                tags=tags or (),
                state=state,
                created_from=created_from,
                created_to=created_to,
                updated_from=updated_from,
                updated_to=updated_to,
            )
            total = int(
                database.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
                or 0
            )
            statement = apply_sort_and_cursor(base, sort=sort, cursor=cursor).limit(limit + 1)
        except LibraryConflict as error:
            raise _conflict(error) from error
        slides = list(database.scalars(statement).all())
        has_more = len(slides) > limit
        page = slides[:limit]
        next_cursor = (
            cursor_for_slide(page[-1], sort) if has_more and page and sort != "manual" else None
        )
        return {
            "items": [slide_json(slide) for slide in page],
            "nextCursor": next_cursor,
            "total": total,
        }

    app.add_api_route(
        "/api/v2/admin/library/items",
        library_items,
        methods=["GET"],
    )

    def facets(
        location: str = "all",
        q: str | None = Query(default=None, max_length=300),
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        base = build_items_statement(
            database,
            location=location,
            query=q,
        ).with_only_columns(Slide.id)
        ids = base.subquery()

        def values(column: Any) -> list[dict[str, Any]]:
            rows = database.execute(
                select(column, func.count(Slide.id))
                .join(ids, ids.c.id == Slide.id)
                .where(column != "")
                .group_by(column)
                .order_by(func.count(Slide.id).desc(), column)
                .limit(100)
            )
            return [{"value": str(value), "count": int(count)} for value, count in rows]

        return {
            "organ": values(Slide.organ_site),
            "stain": values(Slide.stain),
            "diagnosis": values(Slide.diagnosis),
            "course": values(Slide.course),
        }

    app.add_api_route(
        "/api/v2/admin/library/facets",
        facets,
        methods=["GET"],
    )

    def slide_status(
        ids: str = Query(min_length=1, max_length=4000),
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide_ids = _unique_ids([item for item in ids.split(",") if item])
        if len(slide_ids) > 100:
            raise HTTPException(status_code=422, detail={"code": "TOO_MANY_SLIDES"})
        slides = database.scalars(select(Slide).where(Slide.id.in_(slide_ids))).all()
        by_id = {slide.id: slide for slide in slides}
        return {
            "items": [
                {
                    "id": slide_id,
                    "state": by_id[slide_id].state.value,
                    "errorCode": by_id[slide_id].error_code,
                }
                for slide_id in slide_ids
                if slide_id in by_id
            ]
        }

    app.add_api_route(
        "/api/v2/admin/slides/status",
        slide_status,
        methods=["GET"],
    )

    def get_slide_details(
        slide_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        return slide_json(_get_slide(database, slide_id), include_details=True)

    app.add_api_route(
        "/api/v2/admin/slides/{slide_id}",
        get_slide_details,
        methods=["GET"],
    )

    def create_folder(
        payload: FolderCreate,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        try:
            name, normalized = normalize_name(payload.name)
            validate_folder_parent(database, folder_id=None, parent_id=payload.parent_id)
            existing = database.scalar(
                select(Folder).where(
                    Folder.parent_id == payload.parent_id,
                    Folder.normalized_name == normalized,
                )
            )
            if existing is not None:
                raise LibraryConflict("FOLDER_NAME_CONFLICT")
            folder = Folder(
                name=name,
                normalized_name=normalized,
                parent_id=payload.parent_id,
                description=payload.description.strip(),
            )
            database.add(folder)
            database.commit()
            database.refresh(folder)
            return folder_json(folder)
        except LibraryConflict as error:
            database.rollback()
            raise _conflict(error) from error
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(status_code=409, detail={"code": "FOLDER_NAME_CONFLICT"}) from error

    app.add_api_route(
        "/api/v2/admin/folders",
        create_folder,
        methods=["POST"],
        status_code=201,
    )

    def update_folder(
        folder_id: str,
        payload: FolderUpdate,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        folder = database.get(Folder, folder_id)
        if folder is None or folder.trashed_at is not None:
            raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
        if (payload.name is not None or payload.description is not None) and _has_active_share(
            database,
            target_type="folder",
            target_id=folder.id,
        ):
            raise HTTPException(status_code=409, detail={"code": "SHARE_ACTIVE"})
        try:
            if "parent_id" in payload.model_fields_set:
                validate_folder_parent(database, folder_id=folder.id, parent_id=payload.parent_id)
                folder.parent_id = payload.parent_id
            if payload.name is not None:
                folder.name, folder.normalized_name = normalize_name(payload.name)
            if payload.description is not None:
                folder.description = payload.description.strip()
            if payload.sort_order is not None:
                folder.sort_order = payload.sort_order
            database.commit()
            database.refresh(folder)
            return folder_json(folder)
        except LibraryConflict as error:
            database.rollback()
            raise _conflict(error) from error
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(status_code=409, detail={"code": "FOLDER_NAME_CONFLICT"}) from error

    app.add_api_route(
        "/api/v2/admin/folders/{folder_id}",
        update_folder,
        methods=["PATCH"],
    )

    def trash_folder(
        folder_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        folder = database.get(Folder, folder_id)
        if folder is None or folder.trashed_at is not None:
            raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
        subtree = folder_subtree_ids(database, folder_id)
        now = utcnow()
        database.execute(
            update(Folder)
            .where(Folder.id.in_(subtree))
            .values(
                trashed_at=now,
                previous_parent_id=case(
                    (Folder.id == folder_id, Folder.parent_id),
                    else_=Folder.previous_parent_id,
                ),
            )
        )
        database.commit()
        return {"id": folder_id, "trashedAt": now.isoformat(), "folderIds": subtree}

    app.add_api_route(
        "/api/v2/admin/folders/{folder_id}/trash",
        trash_folder,
        methods=["POST"],
    )

    def restore_folder(
        folder_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        folder = database.get(Folder, folder_id)
        if folder is None or folder.trashed_at is None:
            raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
        subtree = folder_subtree_ids(database, folder_id)
        if folder.previous_parent_id:
            previous = database.get(Folder, folder.previous_parent_id)
            folder.parent_id = (
                folder.previous_parent_id
                if previous is not None and previous.trashed_at is None
                else None
            )
        database.execute(update(Folder).where(Folder.id.in_(subtree)).values(trashed_at=None))
        folder.previous_parent_id = None
        database.commit()
        return {"id": folder_id, "trashedAt": None, "folderIds": subtree}

    app.add_api_route(
        "/api/v2/admin/folders/{folder_id}/restore",
        restore_folder,
        methods=["POST"],
    )

    def permanently_delete_folder(
        folder_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        folder = database.get(Folder, folder_id)
        if folder is None or folder.trashed_at is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "TRASH_REQUIRED"},
            )
        subtree = folder_subtree_ids(database, folder_id)
        occupied = database.scalar(select(func.count(Slide.id)).where(Slide.folder_id.in_(subtree)))
        if occupied:
            raise HTTPException(
                status_code=409,
                detail={"code": "FOLDER_NOT_EMPTY"},
            )
        folders = database.scalars(select(Folder).where(Folder.id.in_(subtree))).all()
        by_id = {item.id: item for item in folders}

        def relative_depth(item: Folder) -> int:
            depth = 0
            parent_id = item.parent_id
            while parent_id in by_id:
                depth += 1
                parent_id = by_id[parent_id].parent_id
            return depth

        for item in sorted(folders, key=relative_depth, reverse=True):
            database.delete(item)
            database.flush()
        database.commit()
        return Response(status_code=204)

    app.add_api_route(
        "/api/v2/admin/folders/{folder_id}",
        permanently_delete_folder,
        methods=["DELETE"],
        status_code=204,
    )

    def create_collection(
        payload: CollectionRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        try:
            name, normalized = normalize_name(payload.name)
            collection = Collection(
                name=name,
                normalized_name=normalized,
                description=payload.description.strip(),
            )
            database.add(collection)
            database.commit()
            database.refresh(collection)
            return collection_json(collection)
        except (LibraryConflict, IntegrityError) as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "COLLECTION_NAME_CONFLICT"}
            ) from error

    app.add_api_route(
        "/api/v2/admin/collections",
        create_collection,
        methods=["POST"],
        status_code=201,
    )

    def update_collection(
        collection_id: str,
        payload: CollectionUpdate,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        collection = _get_collection(database, collection_id)
        if (payload.name is not None or payload.description is not None) and _has_active_share(
            database,
            target_type="collection",
            target_id=collection.id,
        ):
            raise HTTPException(status_code=409, detail={"code": "SHARE_ACTIVE"})
        try:
            if payload.name is not None:
                collection.name, collection.normalized_name = normalize_name(payload.name)
            if payload.description is not None:
                collection.description = payload.description.strip()
            if payload.sort_order is not None:
                collection.sort_order = payload.sort_order
            database.commit()
            database.refresh(collection)
            return collection_json(collection)
        except (LibraryConflict, IntegrityError) as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "COLLECTION_NAME_CONFLICT"}
            ) from error

    app.add_api_route(
        "/api/v2/admin/collections/{collection_id}",
        update_collection,
        methods=["PATCH"],
    )

    def delete_collection(
        collection_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        collection = _get_collection(database, collection_id)
        database.delete(collection)
        database.commit()
        return Response(status_code=204)

    app.add_api_route(
        "/api/v2/admin/collections/{collection_id}",
        delete_collection,
        methods=["DELETE"],
        status_code=204,
    )

    def add_collection_items(
        collection_id: str,
        payload: SlideIdsRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        _get_collection(database, collection_id)
        slide_ids = _unique_ids(payload.slide_ids)
        found = set(database.scalars(select(Slide.id).where(Slide.id.in_(slide_ids))).all())
        if found != set(slide_ids):
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        existing = {
            membership.slide_id: membership
            for membership in database.scalars(
                select(CollectionSlide)
                .where(CollectionSlide.collection_id == collection_id)
                .order_by(CollectionSlide.sort_order)
            ).all()
        }
        next_order = (
            max(
                (membership.sort_order for membership in existing.values()),
                default=-1,
            )
            + 1
        )
        for slide_id in slide_ids:
            if slide_id not in existing:
                membership = CollectionSlide(
                    collection_id=collection_id,
                    slide_id=slide_id,
                    sort_order=next_order,
                )
                database.add(membership)
                existing[slide_id] = membership
                next_order += 1
        database.commit()
        ordered = database.scalars(
            select(CollectionSlide.slide_id)
            .where(CollectionSlide.collection_id == collection_id)
            .order_by(CollectionSlide.sort_order, CollectionSlide.slide_id)
        ).all()
        return {"collectionId": collection_id, "slideIds": list(ordered)}

    app.add_api_route(
        "/api/v2/admin/collections/{collection_id}/items",
        add_collection_items,
        methods=["POST"],
    )

    def remove_collection_items(
        collection_id: str,
        payload: SlideIdsRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        _get_collection(database, collection_id)
        memberships = database.scalars(
            select(CollectionSlide).where(
                CollectionSlide.collection_id == collection_id,
                CollectionSlide.slide_id.in_(_unique_ids(payload.slide_ids)),
            )
        ).all()
        for membership in memberships:
            database.delete(membership)
        database.commit()
        return {
            "collectionId": collection_id,
            "removedSlideIds": [membership.slide_id for membership in memberships],
        }

    app.add_api_route(
        "/api/v2/admin/collections/{collection_id}/items",
        remove_collection_items,
        methods=["DELETE"],
    )

    def create_saved_view(
        payload: SavedViewRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        try:
            validate_saved_view(payload.definition, payload.sort)
            name, normalized = normalize_name(payload.name)
            view = SavedView(
                name=name,
                normalized_name=normalized,
                definition=payload.definition,
                sort=payload.sort,
            )
            database.add(view)
            database.commit()
            database.refresh(view)
            return saved_view_json(view)
        except LibraryConflict as error:
            database.rollback()
            status_code = 422 if error.code == "INVALID_SAVED_VIEW" else 409
            raise HTTPException(status_code=status_code, detail={"code": error.code}) from error
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "SAVED_VIEW_NAME_CONFLICT"}
            ) from error

    app.add_api_route(
        "/api/v2/admin/saved-views",
        create_saved_view,
        methods=["POST"],
        status_code=201,
    )

    def update_saved_view(
        view_id: str,
        payload: SavedViewUpdate,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        view = database.get(SavedView, view_id)
        if view is None:
            raise HTTPException(status_code=404, detail={"code": "SAVED_VIEW_NOT_FOUND"})
        definition = payload.definition or view.definition
        sort = payload.sort or view.sort
        try:
            validate_saved_view(definition, sort)
            if payload.name is not None:
                view.name, view.normalized_name = normalize_name(payload.name)
            view.definition = definition
            view.sort = sort
            database.commit()
            database.refresh(view)
            return saved_view_json(view)
        except LibraryConflict as error:
            database.rollback()
            raise HTTPException(status_code=422, detail={"code": error.code}) from error

    app.add_api_route(
        "/api/v2/admin/saved-views/{view_id}",
        update_saved_view,
        methods=["PATCH"],
    )

    def delete_saved_view(
        view_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        view = database.get(SavedView, view_id)
        if view is None:
            raise HTTPException(status_code=404, detail={"code": "SAVED_VIEW_NOT_FOUND"})
        database.delete(view)
        database.commit()
        return Response(status_code=204)

    app.add_api_route(
        "/api/v2/admin/saved-views/{view_id}",
        delete_saved_view,
        methods=["DELETE"],
        status_code=204,
    )

    def batch_move(
        payload: BatchMoveRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        if payload.folder_id is not None:
            folder = database.get(Folder, payload.folder_id)
            if folder is None or folder.trashed_at is not None:
                raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
        slide_ids = _unique_ids(payload.slide_ids)
        slides = database.scalars(
            select(Slide).where(Slide.id.in_(slide_ids), Slide.trashed_at.is_(None))
        ).all()
        if len(slides) != len(slide_ids):
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        for slide in slides:
            slide.folder_id = payload.folder_id
        database.commit()
        return {"items": [slide_json(slide) for slide in slides]}

    app.add_api_route(
        "/api/v2/admin/slides/batch-move",
        batch_move,
        methods=["POST"],
    )

    def batch_metadata(
        payload: BatchMetadataRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide_ids = _unique_ids(payload.slide_ids)
        slides = database.scalars(
            select(Slide).where(Slide.id.in_(slide_ids), Slide.trashed_at.is_(None))
        ).all()
        if len(slides) != len(slide_ids):
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        public_fields = {
            "display_name": payload.display_name,
            "description": payload.description,
            "case_id": payload.case_id,
            "organ_site": payload.organ_site,
            "stain": payload.stain,
            "diagnosis": payload.diagnosis,
            "course": payload.course,
            "tags": payload.tags,
            "teaching_note": payload.teaching_note,
        }
        public_changes = {
            field: value for field, value in public_fields.items() if value is not None
        }
        if public_changes:
            shared = database.scalar(
                select(PublicationGrant.id).where(PublicationGrant.slide_id.in_(slide_ids)).limit(1)
            )
            if shared is not None:
                raise HTTPException(status_code=409, detail={"code": "SLIDE_PUBLIC"})
        fields = {**public_fields, "admin_notes": payload.admin_notes}
        for slide in slides:
            for field, value in fields.items():
                if value is not None:
                    setattr(slide, field, value)
            if public_changes:
                slide.privacy_status = "pending"
                slide.privacy_scanned_at = None
        database.commit()
        return {"items": [slide_json(slide) for slide in slides]}

    app.add_api_route(
        "/api/v2/admin/slides/batch-metadata",
        batch_metadata,
        methods=["POST"],
    )

    def trash_slide(
        slide_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = _get_slide(database, slide_id)
        if slide.trashed_at is not None:
            return slide_json(slide)
        delete_all_slide_grants(database, storage, slide)
        slide.previous_folder_id = slide.folder_id
        slide.folder_id = None
        slide.trashed_at = utcnow()
        database.commit()
        return slide_json(slide)

    app.add_api_route(
        "/api/v2/admin/slides/{slide_id}/trash",
        trash_slide,
        methods=["POST"],
    )

    def restore_slide(
        slide_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = _get_slide(database, slide_id)
        if slide.trashed_at is None:
            return slide_json(slide)
        folder = (
            database.get(Folder, slide.previous_folder_id) if slide.previous_folder_id else None
        )
        slide.folder_id = folder.id if folder is not None and folder.trashed_at is None else None
        slide.previous_folder_id = None
        slide.trashed_at = None
        database.commit()
        return slide_json(slide)

    app.add_api_route(
        "/api/v2/admin/slides/{slide_id}/restore",
        restore_slide,
        methods=["POST"],
    )

    def permanently_delete_slide(
        slide_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        slide = _get_slide(database, slide_id)
        if slide.trashed_at is None:
            raise HTTPException(
                status_code=409,
                detail={"code": "TRASH_REQUIRED"},
            )
        try:
            slide.state = transition(slide.state, SlideState.DELETING)
        except InvalidTransition as error:
            raise HTTPException(status_code=409, detail={"code": "INVALID_STATE"}) from error
        database.add(Job(slide_id=slide.id, kind="delete"))
        database.commit()
        return slide_json(slide)

    app.add_api_route(
        "/api/v2/admin/slides/{slide_id}",
        permanently_delete_slide,
        methods=["DELETE"],
        status_code=202,
    )

    def thumbnail(
        slide_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> FileResponse:
        slide = _get_slide(database, slide_id)
        if not slide.thumbnail_filename:
            raise HTTPException(status_code=404, detail={"code": "THUMBNAIL_NOT_FOUND"})
        root = storage.for_slide(slide.id).private_derivative.resolve()
        target = (root / Path(slide.thumbnail_filename).name).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            raise HTTPException(status_code=404, detail={"code": "THUMBNAIL_NOT_FOUND"})
        stat_result = target.stat()
        etag = hashlib.sha256(
            f"{stat_result.st_mtime_ns}:{stat_result.st_size}".encode()
        ).hexdigest()
        return FileResponse(
            target,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, max-age=3600",
                "ETag": f'"{etag}"',
            },
        )

    app.add_api_route(
        "/api/v2/admin/slides/{slide_id}/thumbnail",
        thumbnail,
        methods=["GET"],
    )

    def _share_error(error: ShareConflict) -> HTTPException:
        if error.code == "SHARE_NOT_FOUND":
            return HTTPException(
                status_code=404,
                detail={"code": "SHARE_NOT_FOUND"},
            )
        if error.code == "SHARE_SLIDES_NOT_REVIEWED":
            return HTTPException(status_code=422, detail={"code": error.code})
        return HTTPException(status_code=409, detail={"code": error.code})

    def preview_library_share(
        target_type: str = Query(alias="targetType", pattern="^(folder|collection)$"),
        target_id: str = Query(alias="targetId"),
        include_descendants: bool = Query(default=False, alias="includeDescendants"),
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        try:
            return preview_share(
                database,
                target_type=target_type,
                target_id=target_id,
                include_descendants=include_descendants,
            )
        except ShareConflict as error:
            raise _share_error(error) from error

    app.add_api_route(
        "/api/v2/admin/shares/preview",
        preview_library_share,
        methods=["GET"],
    )

    def create_share(
        payload: ShareCreateRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        if not app.state.settings.multi_share_enabled:
            raise HTTPException(
                status_code=409,
                detail={"code": "PRIVACY_SCANNER_REQUIRED"},
            )
        if not payload.deidentified_confirmed:
            raise HTTPException(
                status_code=422,
                detail={"code": "DEIDENTIFICATION_CONFIRMATION_REQUIRED"},
            )
        expires_at = payload.expires_at
        if expires_at is not None:
            expires_at = expires_at.replace(tzinfo=None)
            if expires_at <= utcnow():
                raise HTTPException(
                    status_code=422,
                    detail={"code": "INVALID_SHARE_EXPIRATION"},
                )
        try:
            share = activate_share(
                database,
                storage,
                target_type=payload.target_type,
                target_id=payload.target_id,
                include_descendants=payload.include_descendants,
                auto_include_new=payload.auto_include_new,
                expires_at=expires_at,
                slide_ids=payload.slide_ids,
            )
        except ShareConflict as error:
            database.rollback()
            raise _share_error(error) from error
        return JSONResponse(
            content=share_json(database, share),
            status_code=201,
        )

    app.add_api_route(
        "/api/v2/admin/shares",
        create_share,
        methods=["POST"],
    )

    def list_shares(
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        shares = list(
            database.scalars(
                select(LibraryShare).order_by(LibraryShare.updated_at.desc(), LibraryShare.id)
            )
        )
        counts: dict[str, int] = {
            share_id: int(count)
            for share_id, count in database.execute(
                select(ShareSlide.share_id, func.count(ShareSlide.id)).group_by(ShareSlide.share_id)
            ).all()
        }
        return {
            "items": [
                share_json(database, share, included_count=counts.get(share.id, 0))
                for share in shares
            ]
        }

    app.add_api_route("/api/v2/admin/shares", list_shares, methods=["GET"])

    def rotate_library_share(
        share_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        share = database.get(LibraryShare, share_id)
        if share is None or not share.is_active:
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        rotate_share(share)
        database.commit()
        return share_json(database, share)

    app.add_api_route(
        "/api/v2/admin/shares/{share_id}/rotate",
        rotate_library_share,
        methods=["POST"],
    )

    def revoke_library_share(
        share_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        share = database.get(LibraryShare, share_id)
        if share is None or not share.is_active:
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        revoke_share(database, storage, share)
        database.commit()
        return Response(status_code=204)

    app.add_api_route(
        "/api/v2/admin/shares/{share_id}",
        revoke_library_share,
        methods=["DELETE"],
    )

    def get_public_share(
        public_id: str,
        target_type: str,
        database: OrmSession,
    ) -> dict[str, Any]:
        try:
            share = active_public_share(
                database,
                target_type=target_type,
                public_id=public_id,
            )
            return public_manifest(database, share)
        except ShareConflict as error:
            raise _share_error(error) from error

    def public_folder_share(
        public_id: str,
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        return get_public_share(public_id, "folder", database)

    def public_collection_share(
        public_id: str,
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        return get_public_share(public_id, "collection", database)

    app.add_api_route(
        "/api/v2/public/folders/{public_id}",
        public_folder_share,
        methods=["GET"],
    )
    app.add_api_route(
        "/api/v2/public/collections/{public_id}",
        public_collection_share,
        methods=["GET"],
    )

    def public_share_thumbnail(
        public_id: str,
        position: int,
        target_type: str,
        database: OrmSession,
    ) -> FileResponse:
        if position < 0:
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        try:
            share = active_public_share(
                database,
                target_type=target_type,
                public_id=public_id,
            )
        except ShareConflict as error:
            raise _share_error(error) from error
        slide = database.scalar(
            select(Slide)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .where(ShareSlide.share_id == share.id)
            .order_by(ShareSlide.sort_order, Slide.id)
            .offset(position)
            .limit(1)
        )
        if slide is None or not slide.thumbnail_filename:
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        target = storage.public_for(slide.public_id) / Path(slide.thumbnail_filename).name
        if not target.is_file():
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        return FileResponse(
            target,
            media_type="image/jpeg",
            headers={"Cache-Control": "private, no-store"},
        )

    def public_share_tile(
        public_id: str,
        position: int,
        tile_path: str,
        target_type: str,
        database: OrmSession,
    ) -> FileResponse:
        if position < 0:
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        try:
            share = active_public_share(
                database,
                target_type=target_type,
                public_id=public_id,
            )
        except ShareConflict as error:
            raise _share_error(error) from error
        slide = database.scalar(
            select(Slide)
            .join(ShareSlide, ShareSlide.slide_id == Slide.id)
            .where(ShareSlide.share_id == share.id)
            .order_by(ShareSlide.sort_order, Slide.id)
            .offset(position)
            .limit(1)
        )
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SHARE_NOT_FOUND"})
        try:
            target = storage.public_tile(slide.public_id, tile_path)
        except (FileNotFoundError, ValueError):
            raise HTTPException(
                status_code=404, detail={"code": "SHARE_NOT_FOUND"}
            ) from None
        media_type = "application/xml" if target.suffix.lower() == ".dzi" else "image/jpeg"
        return FileResponse(
            target,
            media_type=media_type,
            headers={"Cache-Control": "private, no-store"},
        )

    def public_folder_thumbnail(
        public_id: str,
        position: int,
        database: OrmSession = Depends(database_dependency),
    ) -> FileResponse:
        return public_share_thumbnail(public_id, position, "folder", database)

    def public_collection_thumbnail(
        public_id: str,
        position: int,
        database: OrmSession = Depends(database_dependency),
    ) -> FileResponse:
        return public_share_thumbnail(public_id, position, "collection", database)

    def public_folder_tile(
        public_id: str,
        position: int,
        tile_path: str,
        database: OrmSession = Depends(database_dependency),
    ) -> FileResponse:
        return public_share_tile(public_id, position, tile_path, "folder", database)

    def public_collection_tile(
        public_id: str,
        position: int,
        tile_path: str,
        database: OrmSession = Depends(database_dependency),
    ) -> FileResponse:
        return public_share_tile(public_id, position, tile_path, "collection", database)

    app.add_api_route(
        "/api/v2/public/folders/{public_id}/slides/{position}/thumbnail",
        public_folder_thumbnail,
        methods=["GET"],
    )
    app.add_api_route(
        "/api/v2/public/collections/{public_id}/slides/{position}/thumbnail",
        public_collection_thumbnail,
        methods=["GET"],
    )
    app.add_api_route(
        "/api/v2/public/folders/{public_id}/slides/{position}/tiles/{tile_path:path}",
        public_folder_tile,
        methods=["GET"],
    )
    app.add_api_route(
        "/api/v2/public/collections/{public_id}/slides/{position}/tiles/{tile_path:path}",
        public_collection_tile,
        methods=["GET"],
    )
