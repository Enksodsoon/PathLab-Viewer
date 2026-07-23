from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .domain import SlideState
from .library import (
    LibraryError,
    admin_slide_json,
    clean_label,
    clean_tags,
    clean_text,
    create_folder,
    delete_folder,
    folder_json,
    library_payload,
    move_folder,
)
from .models import AuditEvent, Folder, FolderShare, PublicationGrant, Session, Slide
from .publication import (
    FOLDER,
    active_folder_share,
    ensure_grant,
    remove_folder_grants,
    remove_grant,
)
from .storage import PublicationError, StorageLayout


class FolderCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    name: str
    parent_id: str | None = Field(default=None, alias="parentId")
    description: str = ""
    sort_order: int = Field(default=0, alias="sortOrder", ge=0, le=2_147_483_647)


class FolderPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    name: str | None = None
    parent_id: str | None = Field(default=None, alias="parentId")
    description: str | None = None
    sort_order: int | None = Field(
        default=None, alias="sortOrder", ge=0, le=2_147_483_647
    )


class SlidePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    display_name: str | None = Field(default=None, alias="displayName")
    description: str | None = None
    stain: str | None = None
    organ_site: str | None = Field(default=None, alias="organSite")
    tags: list[str] | None = None
    teaching_note: str | None = Field(default=None, alias="teachingNote")
    admin_notes: str | None = Field(default=None, alias="adminNotes")
    folder_id: str | None = Field(default=None, alias="folderId")
    sort_order: int | None = Field(
        default=None, alias="sortOrder", ge=0, le=2_147_483_647
    )


class BulkMove(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    slide_ids: list[str] = Field(alias="slideIds", min_length=1, max_length=50)
    folder_id: str | None = Field(default=None, alias="folderId")


def _error(error: LibraryError) -> HTTPException:
    status_code = 404 if error.code.endswith("NOT_FOUND") else 409
    return HTTPException(status_code=status_code, detail={"code": error.code})


def _folder_or_404(database: OrmSession, folder_id: str) -> Folder:
    folder = database.get(Folder, folder_id)
    if folder is None:
        raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
    return folder


def _slide_or_404(database: OrmSession, slide_id: str) -> Slide:
    slide = database.get(Slide, slide_id)
    if slide is None:
        raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
    return slide


def _grant_summary(database: OrmSession, slide: Slide) -> dict[str, Any]:
    grants = database.scalars(
        select(PublicationGrant).where(PublicationGrant.slide_id == slide.id)
    ).all()
    return admin_slide_json(
        slide,
        individual=any(grant.source_type == "individual" for grant in grants),
        folder_grant_count=sum(grant.source_type == FOLDER for grant in grants),
    )


def _share_json(share: FolderShare) -> dict[str, Any]:
    return {
        "publicId": share.public_id,
        "isActive": share.is_active,
        "createdAt": share.created_at.isoformat(),
    }


def _reconcile_move(
    database: OrmSession,
    storage: StorageLayout,
    slide: Slide,
    folder_id: str | None,
) -> None:
    old_folder = slide.folder_id
    if old_folder == folder_id:
        return
    if old_folder is not None:
        remove_grant(database, storage, slide, FOLDER, old_folder)
    slide.folder_id = folder_id
    if (
        folder_id is not None
        and active_folder_share(database, folder_id) is not None
        and slide.state in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
    ):
        ensure_grant(database, storage, slide, FOLDER, folder_id)


def register_library_routes(
    app: FastAPI,
    *,
    factory: sessionmaker[OrmSession],
    storage: StorageLayout,
    database_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
) -> None:
    Database = Annotated[OrmSession, Depends(database_dependency)]
    AdminSession = Annotated[Session, Depends(admin_dependency)]
    CsrfSession = Annotated[Session, Depends(csrf_dependency)]

    @app.get("/api/v1/admin/library")
    def get_library(_: AdminSession, database: Database) -> dict[str, Any]:
        return library_payload(database, storage.cap_bytes)

    @app.post("/api/v1/admin/folders", status_code=status.HTTP_201_CREATED)
    def add_folder(
        payload: FolderCreate,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, Any]:
        try:
            folder = create_folder(
                database,
                name=payload.name,
                parent_id=payload.parent_id,
                description=payload.description,
                sort_order=payload.sort_order,
            )
            database.add(
                AuditEvent(
                    actor_user_id=authenticated.user_id,
                    action="folder.create",
                    target_id=folder.id,
                )
            )
            database.commit()
            return folder_json(folder)
        except LibraryError as error:
            database.rollback()
            raise _error(error) from error
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "FOLDER_NAME_CONFLICT"}
            ) from error

    @app.patch("/api/v1/admin/folders/{folder_id}")
    def patch_folder(
        folder_id: str,
        payload: FolderPatch,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, Any]:
        folder = _folder_or_404(database, folder_id)
        fields = payload.model_fields_set
        try:
            if "name" in fields and payload.name is not None:
                folder.name = clean_label(
                    payload.name, maximum=120, code="INVALID_FOLDER_NAME"
                )
                folder.normalized_name = folder.name.casefold()
            if "description" in fields and payload.description is not None:
                folder.description = clean_text(
                    payload.description,
                    maximum=2000,
                    code="INVALID_FOLDER_DESCRIPTION",
                )
            if "sort_order" in fields and payload.sort_order is not None:
                folder.sort_order = payload.sort_order
            if "parent_id" in fields:
                move_folder(database, folder, payload.parent_id)
            folder.updated_at = datetime.now(UTC)
            database.add(
                AuditEvent(
                    actor_user_id=authenticated.user_id,
                    action="folder.update",
                    target_id=folder.id,
                )
            )
            database.commit()
            return folder_json(folder, active_folder_share(database, folder.id))
        except LibraryError as error:
            database.rollback()
            raise _error(error) from error
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "FOLDER_NAME_CONFLICT"}
            ) from error

    @app.delete(
        "/api/v1/admin/folders/{folder_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_folder(
        folder_id: str,
        authenticated: CsrfSession,
        database: Database,
    ) -> None:
        folder = _folder_or_404(database, folder_id)
        try:
            delete_folder(database, storage, folder)
            database.add(
                AuditEvent(
                    actor_user_id=authenticated.user_id,
                    action="folder.delete",
                    target_id=folder_id,
                )
            )
            database.commit()
        except LibraryError as error:
            database.rollback()
            raise _error(error) from error

    @app.patch("/api/v1/admin/slides/{slide_id}")
    def patch_slide(
        slide_id: str,
        payload: SlidePatch,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, Any]:
        slide = _slide_or_404(database, slide_id)
        fields = payload.model_fields_set
        try:
            if "display_name" in fields and payload.display_name is not None:
                slide.display_name = clean_label(
                    payload.display_name,
                    maximum=200,
                    code="INVALID_SLIDE_METADATA",
                )
            for field, maximum in (
                ("description", 4000),
                ("teaching_note", 4000),
                ("admin_notes", 4000),
            ):
                value = getattr(payload, field)
                if field in fields and value is not None:
                    setattr(
                        slide,
                        field,
                        clean_text(
                            value, maximum=maximum, code="INVALID_SLIDE_METADATA"
                        ),
                    )
            for field, maximum in (("stain", 80), ("organ_site", 120)):
                value = getattr(payload, field)
                if field in fields and value is not None:
                    setattr(
                        slide,
                        field,
                        (
                            clean_label(
                                value,
                                maximum=maximum,
                                code="INVALID_SLIDE_METADATA",
                            )
                            if value.strip()
                            else ""
                        ),
                    )
            if "tags" in fields and payload.tags is not None:
                slide.tags = clean_tags(payload.tags)
            if "sort_order" in fields and payload.sort_order is not None:
                slide.sort_order = payload.sort_order
            if "folder_id" in fields:
                if payload.folder_id is not None:
                    _folder_or_404(database, payload.folder_id)
                _reconcile_move(database, storage, slide, payload.folder_id)
            database.add(
                AuditEvent(
                    actor_user_id=authenticated.user_id,
                    action="slide.metadata",
                    target_id=slide.id,
                )
            )
            database.commit()
            return _grant_summary(database, slide)
        except LibraryError as error:
            database.rollback()
            raise _error(error) from error
        except (PublicationError, ValueError) as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "PUBLICATION_FAILED"}
            ) from error

    @app.post("/api/v1/admin/slides/bulk-move")
    def bulk_move(
        payload: BulkMove,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, int]:
        slide_ids = list(dict.fromkeys(payload.slide_ids))
        if payload.folder_id is not None:
            _folder_or_404(database, payload.folder_id)
        slides = database.scalars(select(Slide).where(Slide.id.in_(slide_ids))).all()
        if len(slides) != len(slide_ids):
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        try:
            for slide in slides:
                _reconcile_move(database, storage, slide, payload.folder_id)
            database.add(
                AuditEvent(
                    actor_user_id=authenticated.user_id,
                    action="slide.bulk_move",
                    detail={"count": len(slides)},
                )
            )
            database.commit()
            return {"moved": len(slides)}
        except (PublicationError, ValueError) as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "PUBLICATION_FAILED"}
            ) from error

    @app.post("/api/v1/admin/folders/{folder_id}/share")
    def share_folder(
        folder_id: str,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, Any]:
        _folder_or_404(database, folder_id)
        share = active_folder_share(database, folder_id)
        if share is None:
            share = FolderShare(folder_id=folder_id)
            database.add(share)
            database.flush()
        slides = database.scalars(
            select(Slide).where(
                Slide.folder_id == folder_id,
                Slide.state.in_([SlideState.READY_PRIVATE, SlideState.PUBLISHED]),
            )
        ).all()
        try:
            for slide in slides:
                ensure_grant(database, storage, slide, FOLDER, folder_id)
            database.add(
                AuditEvent(
                    actor_user_id=authenticated.user_id,
                    action="folder.share",
                    target_id=folder_id,
                    detail={"slideCount": len(slides)},
                )
            )
            database.commit()
        except (PublicationError, ValueError) as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "PUBLICATION_FAILED"}
            ) from error
        return _share_json(share)

    @app.delete(
        "/api/v1/admin/folders/{folder_id}/share",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def revoke_folder_share(
        folder_id: str,
        authenticated: CsrfSession,
        database: Database,
    ) -> None:
        _folder_or_404(database, folder_id)
        share = database.scalar(
            select(FolderShare).where(
                FolderShare.folder_id == folder_id,
                FolderShare.is_active.is_(True),
            )
        )
        if share is not None:
            share.is_active = False
            share.revoked_at = datetime.now(UTC)
        remove_folder_grants(database, storage, folder_id)
        database.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="folder.revoke",
                target_id=folder_id,
            )
        )
        database.commit()

    @app.post("/api/v1/admin/folders/{folder_id}/share/rotate")
    def rotate_folder_share(
        folder_id: str,
        authenticated: CsrfSession,
        database: Database,
    ) -> dict[str, Any]:
        _folder_or_404(database, folder_id)
        old = active_folder_share(database, folder_id)
        if old is None:
            raise HTTPException(
                status_code=409, detail={"code": "FOLDER_SHARE_NOT_ACTIVE"}
            )
        old.is_active = False
        old.revoked_at = datetime.now(UTC)
        database.flush()
        share = FolderShare(folder_id=folder_id)
        database.add(share)
        database.add(
            AuditEvent(
                actor_user_id=authenticated.user_id,
                action="folder.rotate",
                target_id=folder_id,
            )
        )
        database.commit()
        return _share_json(share)

    @app.get("/api/v1/public/folders/{folder_public_id}")
    def public_folder(folder_public_id: str, database: Database) -> dict[str, Any]:
        now = datetime.now(UTC).replace(tzinfo=None)
        share = database.scalar(
            select(FolderShare).where(
                FolderShare.public_id == folder_public_id,
                FolderShare.is_active.is_(True),
                (
                    FolderShare.expires_at.is_(None)
                    | (FolderShare.expires_at > now)
                ),
            )
        )
        if share is None:
            raise HTTPException(
                status_code=404, detail={"code": "FOLDER_NOT_FOUND"}
            )
        folder = database.get(Folder, share.folder_id)
        if folder is None:
            raise HTTPException(
                status_code=404, detail={"code": "FOLDER_NOT_FOUND"}
            )
        slides = database.scalars(
            select(Slide)
            .join(PublicationGrant, PublicationGrant.slide_id == Slide.id)
            .where(
                PublicationGrant.source_type == FOLDER,
                PublicationGrant.source_id == folder.id,
                Slide.folder_id == folder.id,
                Slide.state == SlideState.PUBLISHED,
            )
            .order_by(Slide.sort_order, Slide.display_name, Slide.created_at)
        ).all()
        return {
            "folderPublicId": share.public_id,
            "name": folder.name,
            "description": folder.description,
            "shareStatus": "active",
            "slides": [
                {
                    "publicId": slide.public_id,
                    "displayName": slide.display_name,
                    "description": slide.description,
                    "stain": slide.stain,
                    "organSite": slide.organ_site,
                    "tags": slide.tags,
                    "teachingNote": slide.teaching_note,
                    "metadata": slide.slide_metadata,
                    "tileSource": f"/tiles/{slide.public_id}/slide.dzi",
                    "sortOrder": slide.sort_order,
                }
                for slide in slides
            ],
        }
