# ruff: noqa: B008
from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .alignment import _registration_triangles
from .alignment_engines import (
    ENGINE_HISALIGN,
    ENGINE_NATIVE,
    ENGINE_VALIS,
    SUPPORTED_ENGINES,
    engine_availability,
    settings_digest,
)
from .domain import SlideState
from .models import (
    ComparisonRegistrationCandidate,
    ComparisonRegistrationRevision,
    ComparisonSet,
    ComparisonSetMember,
    Job,
    LibraryShare,
    ShareSlide,
    Slide,
)
from .security import UploadGrant, issue_upload_token
from .sharing import ShareConflict, active_public_share
from .stack_service import (
    READY_STATES,
    cancel_stack_jobs,
    membership_rows,
    queue_ready_registrations,
    sync_membership_mirror,
)
from .storage import InsufficientStorage, StorageLayout
from .storage_accounting import reserve_new_slide


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=160)
    slide_ids: list[str] = Field(alias="slideIds", min_length=1, max_length=12)
    reference_slide_id: str = Field(alias="referenceSlideId", min_length=1, max_length=64)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, allow_inf_nan=False)
    version: int = Field(ge=1)
    reference_slide_id: str | None = Field(default=None, alias="referenceSlideId")
    preview_only: bool = Field(default=False, alias="previewOnly")
    moving_points: list[tuple[float, float]] = Field(
        alias="movingPoints", min_length=3, max_length=20
    )
    reference_points: list[tuple[float, float]] = Field(
        alias="referencePoints", min_length=3, max_length=20
    )


class ComparisonUpdateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: int = Field(ge=1)
    reference_slide_id: str | None = Field(default=None, alias="referenceSlideId")
    anchors: dict[str, str] | None = None


class StackMemberInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=64)
    anchor_slide_id: str | None = Field(default=None, alias="anchorSlideId", max_length=64)


class StackMembershipRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: int = Field(ge=1)
    add: list[StackMemberInput] = Field(default_factory=list, max_length=11)
    remove: list[str] = Field(default_factory=list, max_length=11)
    reference_slide_id: str | None = Field(default=None, alias="referenceSlideId", max_length=64)
    order: list[str] | None = Field(default=None, max_length=12)


class StackUploadRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    version: int = Field(ge=1)
    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    filename: str = Field(min_length=1, max_length=500)
    length: int = Field(gt=0)
    stain: str = Field(min_length=1, max_length=80)
    anchor_slide_id: str = Field(alias="anchorSlideId", min_length=1, max_length=64)
    folder_id: str | None = Field(default=None, alias="folderId", max_length=64)
    case_id: str = Field(default="", alias="caseId", max_length=120)
    organ_site: str = Field(default="", alias="organSite", max_length=120)


class BenchmarkRequest(BaseModel):
    version: int = Field(ge=1)
    engines: list[str] = Field(default_factory=lambda: list(SUPPORTED_ENGINES), min_length=1)
    rerun: bool = False


class PromoteCandidateRequest(BaseModel):
    version: int = Field(ge=1)


def _error(code: str, http_status: int = 422) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code})


def _utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _members(database: OrmSession, item: ComparisonSet) -> list[Slide]:
    rows = membership_rows(database, item)
    member_ids = [row.slide_id for row in rows]
    slides = {
        slide.id: slide for slide in database.scalars(select(Slide).where(Slide.id.in_(member_ids)))
    }
    if len(slides) != len(member_ids):
        raise _error("COMPARISON_SOURCE_CHANGED", 409)
    return [slides[slide_id] for slide_id in member_ids]


def _settled_registration_status(item: ComparisonSet) -> str:
    """Return the durable stack status when no registration job is active."""
    target_count = max(0, len(item.member_slide_ids) - 1)
    if target_count == 0:
        return "draft"
    registrations = {
        slide_id: registration
        for slide_id, registration in (item.registrations or {}).items()
        if slide_id in item.member_slide_ids and slide_id != item.reference_slide_id
    }
    if not registrations:
        return "draft"
    if len(registrations) == target_count and all(
        registration.get("status") == "ready" for registration in registrations.values()
    ):
        return "ready"
    return "partial"


def _serial_group(slide: Slide) -> str | None:
    text = f"{slide.display_name} {slide.original_filename}"
    match = re.search(r"(?<!\d)(\d+)\s*of\s*(\d+)(?!\d)", text, re.IGNORECASE)
    return f"{match.group(1)}of{match.group(2)}" if match else None


def _alignment_anchors(slides: list[Slide], primary_reference_id: str) -> dict[str, str]:
    he_by_group: dict[str, list[str]] = {}
    for slide in slides:
        group = _serial_group(slide)
        stain = (slide.stain or "").casefold().replace("&", "").replace(" ", "")
        if group and stain in {"he", "hande", "hematoxylinandeosin"}:
            he_by_group.setdefault(group, []).append(slide.id)
    anchors: dict[str, str] = {}
    for slide in slides:
        group = _serial_group(slide)
        candidates = he_by_group.get(group or "", [])
        is_secondary_reference = slide.id in candidates and slide.id != primary_reference_id
        anchors[slide.id] = (
            primary_reference_id
            if is_secondary_reference or len(candidates) != 1
            else candidates[0]
        )
    return anchors


def _json(
    item: ComparisonSet,
    slides: list[Slide],
    *,
    shared: dict[str, int] | None = None,
    database: OrmSession | None = None,
) -> dict[str, Any]:
    anchors = (item.alignment_config or {}).get("anchors", {})
    if database is not None:
        anchors = {
            row.slide_id: row.anchor_slide_id or item.reference_slide_id
            for row in membership_rows(database, item)
            if row.slide_id != item.reference_slide_id
        }
    members = []
    for slide in slides:
        position = shared.get(slide.id) if shared is not None else None
        revision = slide.sha256 or str(int(slide.updated_at.timestamp()))
        available = slide.trashed_at is None and slide.state in READY_STATES
        tile_source = None
        if available:
            tile_source = (
                f"/api/v2/public/collections/{{sharePublicId}}/slides/{position}/tiles/slide.dzi?v={revision}"
                if position is not None
                else f"/api/v1/admin/slides/{slide.id}/preview/slide.dzi?v={revision}"
            )
        availability_reason = None
        if slide.trashed_at is not None:
            availability_reason = "trashed"
        elif slide.state not in READY_STATES:
            availability_reason = slide.state.value
        members.append(
            {
                "slideId": slide.id,
                "displayName": slide.display_name,
                "stain": slide.stain,
                "metadata": slide.slide_metadata,
                "tileSource": tile_source,
                "thumbnailUrl": tile_source.replace("slide.dzi", "thumbnail.jpg")
                if tile_source
                else None,
                "registration": item.registrations.get(slide.id),
                "state": slide.state.value,
                "availabilityReason": availability_reason,
                "errorCode": slide.error_code,
                "anchorSlideId": None
                if slide.id == item.reference_slide_id
                else anchors.get(slide.id, item.reference_slide_id),
            }
        )
    return {
        "id": item.id,
        "name": item.name,
        "referenceSlideId": item.reference_slide_id,
        "status": item.status,
        "version": item.version,
        "alignmentConfig": item.alignment_config,
        "members": members,
    }


def register_alignment_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
    enabled: bool,
    factory: sessionmaker[OrmSession] | None = None,
    storage: StorageLayout | None = None,
    secret_key: str | None = None,
    tus_public_url: str = "/files/",
    max_upload_bytes: int = 5 * 1024**3,
    hisalign_enabled: bool = False,
    valis_enabled: bool = False,
) -> None:
    if not enabled:
        return

    def list_sets(
        _: Any = Depends(admin_dependency), database: OrmSession = Depends(database_dependency)
    ) -> list[dict[str, Any]]:
        return [
            _json(item, _members(database, item), database=database)
            for item in database.scalars(
                select(ComparisonSet).order_by(ComparisonSet.updated_at.desc())
            )
        ]

    def create_set(
        payload: ComparisonRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        ids = list(dict.fromkeys(payload.slide_ids))
        if payload.reference_slide_id not in ids:
            raise _error("REFERENCE_NOT_MEMBER")
        slides = list(database.scalars(select(Slide).where(Slide.id.in_(ids))))
        by_id = {slide.id: slide for slide in slides}
        if len(by_id) != len(ids) or any(
            by_id[item].trashed_at is not None
            or by_id[item].state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
            for item in ids
        ):
            raise _error("SLIDES_NOT_READY")
        item = ComparisonSet(
            name=payload.name.strip(),
            reference_slide_id=payload.reference_slide_id,
            member_slide_ids=ids,
            source_versions={item: by_id[item].sha256 for item in ids},
            registrations={},
            alignment_config={},
            status="draft",
        )
        database.add(item)
        database.flush()
        suggested_anchors = _alignment_anchors(
            [by_id[slide_id] for slide_id in ids], item.reference_slide_id
        )
        for position, slide_id in enumerate(ids):
            database.add(
                ComparisonSetMember(
                    comparison_set_id=item.id,
                    slide_id=slide_id,
                    anchor_slide_id=None
                    if slide_id == item.reference_slide_id
                    else suggested_anchors.get(slide_id, item.reference_slide_id),
                    position=position,
                )
            )
        database.flush()
        sync_membership_mirror(database, item)
        queue_ready_registrations(database, item)
        database.commit()
        return _json(item, [by_id[item] for item in ids], database=database)

    def get_set(
        set_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        return _json(item, _members(database, item), database=database)

    def queue_set(
        set_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        slides = _members(database, item)
        anchors = _alignment_anchors(slides, item.reference_slide_id)
        configured = (item.alignment_config or {}).get("anchors", {})
        anchors.update(
            {
                slide_id: anchor_id
                for slide_id, anchor_id in configured.items()
                if slide_id in item.member_slide_ids and anchor_id in item.member_slide_ids
            }
        )
        for row in membership_rows(database, item):
            if row.slide_id != item.reference_slide_id:
                row.anchor_slide_id = anchors.get(row.slide_id, item.reference_slide_id)
        sync_membership_mirror(database, item)
        queued = queue_ready_registrations(database, item)
        database.commit()
        return {"comparisonSetId": item.id, "queuedPairs": queued, "status": item.status}

    def update_set(
        set_id: str,
        payload: ComparisonUpdateRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        if item.version != payload.version:
            raise _error("COMPARISON_STALE_WRITE", 409)
        reference_id = payload.reference_slide_id or item.reference_slide_id
        if reference_id not in item.member_slide_ids:
            raise _error("REFERENCE_NOT_MEMBER")
        anchors = payload.anchors or (item.alignment_config or {}).get("anchors", {})
        if any(
            slide_id not in item.member_slide_ids or anchor_id not in item.member_slide_ids
            for slide_id, anchor_id in anchors.items()
        ):
            raise _error("ANCHOR_NOT_MEMBER")
        changed = reference_id != item.reference_slide_id or anchors != (
            item.alignment_config or {}
        ).get("anchors", {})
        item.reference_slide_id = reference_id
        item.alignment_config = {**(item.alignment_config or {}), "anchors": anchors}
        if changed:
            for row in membership_rows(database, item):
                row.anchor_slide_id = (
                    None
                    if row.slide_id == reference_id
                    else anchors.get(row.slide_id, reference_id)
                )
            item.version += 1
            item.registrations = {}
            item.status = "draft"
            cancel_stack_jobs(database, item.id)
            sync_membership_mirror(database, item)
        database.commit()
        return _json(item, _members(database, item), database=database)

    def update_members(
        set_id: str,
        payload: StackMembershipRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        if item.version != payload.version:
            raise _error("COMPARISON_STALE_WRITE", 409)
        rows = membership_rows(database, item)
        by_slide = {row.slide_id: row for row in rows}
        remove_ids = set(payload.remove)
        if len({entry.slide_id for entry in payload.add}) != len(payload.add):
            raise _error("STACK_MEMBER_DUPLICATE")
        next_reference = payload.reference_slide_id or item.reference_slide_id
        if item.reference_slide_id in remove_ids and next_reference == item.reference_slide_id:
            raise _error("REFERENCE_REPLACEMENT_REQUIRED")
        add_ids = [entry.slide_id for entry in payload.add if entry.slide_id not in by_slide]
        final_ids = [row.slide_id for row in rows if row.slide_id not in remove_ids] + add_ids
        if not final_ids or len(final_ids) > 12:
            raise _error("STACK_MEMBER_LIMIT")
        if next_reference not in final_ids:
            raise _error("REFERENCE_NOT_MEMBER")
        if payload.order is not None and (
            len(payload.order) != len(final_ids) or set(payload.order) != set(final_ids)
        ):
            raise _error("STACK_ORDER_INVALID")
        additions = {
            slide.id: slide
            for slide in database.scalars(select(Slide).where(Slide.id.in_(add_ids)))
        }
        if len(additions) != len(add_ids) or any(
            slide.trashed_at is not None or slide.state not in READY_STATES
            for slide in additions.values()
        ):
            raise _error("SLIDES_NOT_READY")
        anchors = {
            row.slide_id: row.anchor_slide_id or next_reference
            for row in rows
            if row.slide_id not in remove_ids
        }
        anchors.update(
            {entry.slide_id: entry.anchor_slide_id or next_reference for entry in payload.add}
        )
        if any(
            anchor_id not in final_ids
            for slide_id, anchor_id in anchors.items()
            if slide_id != next_reference
        ):
            raise _error("ANCHOR_NOT_MEMBER")
        for row in rows:
            if row.slide_id in remove_ids:
                database.delete(row)
        position = len(rows) - len(remove_ids)
        for entry in payload.add:
            if entry.slide_id in by_slide:
                by_slide[entry.slide_id].anchor_slide_id = entry.anchor_slide_id or next_reference
                continue
            database.add(
                ComparisonSetMember(
                    comparison_set_id=item.id,
                    slide_id=entry.slide_id,
                    anchor_slide_id=None
                    if entry.slide_id == next_reference
                    else entry.anchor_slide_id or next_reference,
                    position=position,
                )
            )
            position += 1
        database.flush()
        ordered_ids = payload.order or final_ids
        for row in membership_rows(database, item):
            row.anchor_slide_id = (
                None
                if row.slide_id == next_reference
                else anchors.get(row.slide_id, next_reference)
            )
            row.position = ordered_ids.index(row.slide_id)
        affected = remove_ids | {entry.slide_id for entry in payload.add}
        if next_reference != item.reference_slide_id:
            affected.update({item.reference_slide_id, next_reference})
        registrations = dict(item.registrations or {})
        for slide_id in list(registrations):
            if slide_id in affected or registrations[slide_id].get("anchorSlideId") in affected:
                registrations.pop(slide_id, None)
        item.registrations = registrations
        item.reference_slide_id = next_reference
        item.version += 1
        item.status = "draft"
        item.source_versions = {
            slide_id: digest
            for slide_id, digest in (item.source_versions or {}).items()
            if slide_id in final_ids
        }
        for slide_id, slide in additions.items():
            item.source_versions[slide_id] = slide.sha256
        cancel_stack_jobs(database, item.id)
        sync_membership_mirror(database, item)
        queue_ready_registrations(database, item)
        database.commit()
        return _json(item, _members(database, item), database=database)

    def reregister(
        set_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        cancel_stack_jobs(database, item.id)
        item.version += 1
        # Keep the last usable map active while a replacement is calculated.
        # The worker replaces it atomically only after the new result succeeds.
        item.status = "draft"
        queued = queue_ready_registrations(
            database,
            item,
            force=True,
            preserve_existing=True,
        )
        database.commit()
        return {
            "comparisonSetId": item.id,
            "queuedPairs": queued,
            "status": item.status,
        }

    def slide_stacks(
        slide_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        if database.get(Slide, slide_id) is None:
            raise _error("SLIDE_NOT_FOUND", 404)
        set_ids = list(
            database.scalars(
                select(ComparisonSetMember.comparison_set_id).where(
                    ComparisonSetMember.slide_id == slide_id
                )
            )
        )
        result = []
        for set_id in set_ids:
            item = database.get(ComparisonSet, set_id)
            if item is None:
                continue
            members = _members(database, item)
            result.append(
                {
                    "id": item.id,
                    "name": item.name,
                    "status": item.status,
                    "version": item.version,
                    "referenceSlideId": item.reference_slide_id,
                    "role": "reference" if item.reference_slide_id == slide_id else "member",
                    "memberCount": len(members),
                    "stains": [slide.stain for slide in members if slide.stain],
                }
            )
        return result

    def stack_suggestions(
        slide_id: str,
        q: str = Query(default="", max_length=200),
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        source = database.get(Slide, slide_id)
        if source is None:
            raise _error("SLIDE_NOT_FOUND", 404)
        query = q.strip().casefold()
        candidates = list(
            database.scalars(
                select(Slide)
                .where(
                    Slide.id != source.id,
                    Slide.trashed_at.is_(None),
                    Slide.state.in_(READY_STATES),
                )
                .limit(250)
            )
        )
        scored: list[tuple[int, Slide, list[str]]] = []
        for slide in candidates:
            haystack = " ".join(
                (slide.display_name, slide.case_id, slide.organ_site, slide.stain)
            ).casefold()
            if query and query not in haystack:
                continue
            reasons: list[str] = []
            score = 0
            if source.case_id and slide.case_id == source.case_id:
                score += 4
                reasons.append("Same case")
            if source.folder_id and slide.folder_id == source.folder_id:
                score += 2
                reasons.append("Same folder")
            if source.organ_site and slide.organ_site.casefold() == source.organ_site.casefold():
                score += 1
                reasons.append("Same organ")
            scored.append((score, slide, reasons or ["Library result"]))
        scored.sort(key=lambda value: (-value[0], value[1].display_name.casefold()))
        return [
            {
                "slideId": slide.id,
                "displayName": slide.display_name,
                "stain": slide.stain,
                "caseId": slide.case_id,
                "organSite": slide.organ_site,
                "folderId": slide.folder_id,
                "thumbnailUrl": f"/api/v1/admin/slides/{slide.id}/preview/thumbnail.jpg",
                "reasons": reasons,
            }
            for _, slide, reasons in scored[:50]
        ]

    def reserve_stack_upload(
        set_id: str,
        payload: StackUploadRequest,
        authenticated: Any = Depends(csrf_dependency),
    ) -> dict[str, Any]:
        if factory is None or storage is None or secret_key is None:
            raise _error("STACK_UPLOAD_UNAVAILABLE", 503)
        if payload.length > max_upload_bytes:
            raise _error("UPLOAD_TOO_LARGE", 413)
        if not payload.filename.casefold().endswith((".ome.tif", ".ome.tiff")):
            raise _error("OME_TIFF_REQUIRED")

        def attach(database: OrmSession, slide: Slide) -> None:
            item = database.get(ComparisonSet, set_id)
            if item is None:
                raise _error("COMPARISON_NOT_FOUND", 404)
            if item.version != payload.version:
                raise _error("COMPARISON_STALE_WRITE", 409)
            rows = membership_rows(database, item)
            member_ids = {row.slide_id for row in rows}
            if len(rows) >= 12:
                raise _error("STACK_MEMBER_LIMIT")
            if payload.anchor_slide_id not in member_ids:
                raise _error("ANCHOR_NOT_MEMBER")
            anchor = database.get(Slide, payload.anchor_slide_id)
            if anchor is None or anchor.trashed_at is not None or anchor.state not in READY_STATES:
                raise _error("ANCHOR_NOT_READY")
            slide.case_id = payload.case_id.strip()
            slide.organ_site = payload.organ_site.strip()
            slide.stain = payload.stain.strip()
            database.add(
                ComparisonSetMember(
                    comparison_set_id=item.id,
                    slide_id=slide.id,
                    anchor_slide_id=payload.anchor_slide_id,
                    position=len(rows),
                )
            )
            item.version += 1
            item.status = "draft"
            item.source_versions = {**(item.source_versions or {}), slide.id: None}
            cancel_stack_jobs(database, item.id)
            database.flush()
            sync_membership_mirror(database, item)

        try:
            slide = reserve_new_slide(
                factory,
                storage,
                display_name=payload.display_name.strip(),
                original_filename=Path(payload.filename).name,
                source_bytes=payload.length,
                actor_user_id=getattr(authenticated, "user_id", None),
                folder_id=payload.folder_id,
                after_flush=attach,
            )
        except InsufficientStorage as error:
            raise _error("INSUFFICIENT_STORAGE", 507) from error
        except LookupError as error:
            raise _error("FOLDER_NOT_FOUND", 404) from error
        token = issue_upload_token(
            UploadGrant(slide.id, payload.length), secret_key, ttl=timedelta(hours=1)
        )
        return {
            "slide": {
                "id": slide.id,
                "publicId": slide.public_id,
                "displayName": slide.display_name,
                "filename": slide.original_filename,
                "sourceBytes": slide.source_bytes,
                "state": slide.state.value,
                "errorCode": slide.error_code,
                "errorMessage": slide.error_message,
                "metadata": slide.slide_metadata,
                "createdAt": slide.created_at.isoformat(),
                "folderId": slide.folder_id,
            },
            "uploadUrl": tus_public_url,
            "uploadToken": token,
            "expiresIn": 3600,
            "comparisonSetId": set_id,
        }

    def revisions(
        set_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        if database.get(ComparisonSet, set_id) is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        return [
            {
                "id": revision.id,
                "slideId": revision.slide_id,
                "setVersion": revision.set_version,
                "sourceVersion": revision.source_version,
                "anchorSlideId": revision.anchor_slide_id,
                "algorithmVersion": revision.algorithm_version,
                "provenance": revision.provenance,
                "registration": revision.registration,
                "createdAt": revision.created_at.isoformat(),
            }
            for revision in database.scalars(
                select(ComparisonRegistrationRevision)
                .where(ComparisonRegistrationRevision.comparison_set_id == set_id)
                .order_by(ComparisonRegistrationRevision.created_at.desc())
            )
        ]

    def candidates(
        set_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        rows = database.scalars(
            select(ComparisonRegistrationCandidate)
            .where(ComparisonRegistrationCandidate.comparison_set_id == set_id)
            .order_by(ComparisonRegistrationCandidate.created_at.desc())
        )
        return {
            "comparisonSetId": set_id,
            "setVersion": item.version,
            "engineAvailability": engine_availability(),
            "candidates": [
                {
                    "id": row.id,
                    "slideId": row.slide_id,
                    "setVersion": row.set_version,
                    "anchorSlideId": row.anchor_slide_id,
                    "engine": row.engine,
                    "engineVersion": row.engine_version,
                    "settingsDigest": row.settings_digest,
                    "currentSettings": row.settings_digest == settings_digest(row.engine),
                    "status": row.status,
                    "validationState": row.validation_state,
                    "registration": row.registration,
                    "evidence": row.evidence,
                    "artifactSha256": row.artifact_sha256,
                    "failureReason": row.failure_reason,
                    "createdAt": row.created_at.isoformat(),
                }
                for row in rows
            ],
        }

    def benchmark(
        set_id: str,
        payload: BenchmarkRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        if item.version != payload.version:
            raise _error("COMPARISON_STALE_WRITE", 409)
        requested = list(dict.fromkeys(payload.engines))
        if any(engine not in SUPPORTED_ENGINES for engine in requested):
            raise _error("ALIGNMENT_ENGINE_UNSUPPORTED")
        enabled_engines = {ENGINE_NATIVE}
        if hisalign_enabled:
            enabled_engines.add(ENGINE_HISALIGN)
        if valis_enabled:
            enabled_engines.add(ENGINE_VALIS)
        if any(engine not in enabled_engines for engine in requested):
            raise _error("ALIGNMENT_ENGINE_DISABLED", 409)
        slides = _members(database, item)
        anchors = _alignment_anchors(slides, item.reference_slide_id)
        anchors.update((item.alignment_config or {}).get("anchors", {}))
        queued = 0
        for slide in slides:
            if slide.id == item.reference_slide_id:
                continue
            anchor_id = anchors.get(slide.id, item.reference_slide_id)
            anchor = next(member for member in slides if member.id == anchor_id)
            for engine in requested:
                digest = settings_digest(engine)
                existing_candidate = database.scalar(
                    select(ComparisonRegistrationCandidate.id).where(
                        ComparisonRegistrationCandidate.comparison_set_id == item.id,
                        ComparisonRegistrationCandidate.slide_id == slide.id,
                        ComparisonRegistrationCandidate.set_version == item.version,
                        ComparisonRegistrationCandidate.anchor_slide_id == anchor_id,
                        ComparisonRegistrationCandidate.engine == engine,
                        ComparisonRegistrationCandidate.source_version == slide.sha256,
                        ComparisonRegistrationCandidate.anchor_version == anchor.sha256,
                        ComparisonRegistrationCandidate.settings_digest == digest,
                    )
                )
                key = hashlib.sha256(
                    (
                        f"benchmark:{item.id}:{item.version}:{slide.id}:{anchor_id}:"
                        f"{engine}:{slide.sha256}:{anchor.sha256}:{digest}"
                    ).encode()
                ).hexdigest()
                existing_job = database.scalar(
                    select(Job.id).where(Job.idempotency_key_hash == key)
                )
                if not payload.rerun and (
                    existing_candidate is not None or existing_job is not None
                ):
                    continue
                if payload.rerun:
                    key = hashlib.sha256(f"{key}:{uuid.uuid4()}".encode()).hexdigest()
                database.add(
                    Job(
                        slide_id=slide.id,
                        kind="align_benchmark",
                        resource_class="isolated",
                        idempotency_key_hash=key,
                        checkpoint={
                            "comparisonSetId": item.id,
                            "memberId": slide.id,
                            "anchorSlideId": anchor_id,
                            "setVersion": item.version,
                            "engine": engine,
                            "progress": 0,
                            "stage": "queued",
                        },
                        resource_limits={
                            "cpuThreads": 2,
                            "memoryBytes": 7 * 1024**3,
                            "timeoutSeconds": 2700,
                        },
                    )
                )
                queued += 1
        config = dict(item.alignment_config or {})
        config["enginePolicy"] = "benchmark"
        config["benchmarkEngines"] = requested
        item.alignment_config = config
        database.commit()
        return {"comparisonSetId": item.id, "queuedCandidates": queued, "engines": requested}

    def promote_candidate(
        set_id: str,
        candidate_id: str,
        payload: PromoteCandidateRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        candidate = database.get(ComparisonRegistrationCandidate, candidate_id)
        if item is None or candidate is None or candidate.comparison_set_id != set_id:
            raise _error("ALIGNMENT_CANDIDATE_NOT_FOUND", 404)
        if item.version != payload.version or candidate.set_version != item.version:
            raise _error("COMPARISON_STALE_WRITE", 409)
        if candidate.status != "ready" or candidate.validation_state != "engineering_passed":
            raise _error("ALIGNMENT_CANDIDATE_NOT_PROMOTABLE", 409)
        source = database.get(Slide, candidate.slide_id)
        anchor = database.get(Slide, candidate.anchor_slide_id)
        if (
            source is None
            or anchor is None
            or source.sha256 != candidate.source_version
            or anchor.sha256 != candidate.anchor_version
            or item.source_versions.get(source.id) != source.sha256
            or item.source_versions.get(anchor.id) != anchor.sha256
        ):
            raise _error("ALIGNMENT_CANDIDATE_STALE", 409)
        if candidate.settings_digest != settings_digest(candidate.engine):
            raise _error("ALIGNMENT_CANDIDATE_SETTINGS_STALE", 409)
        registration = {
            **candidate.registration,
            "provenance": "automatic",
            "selectedCandidateId": candidate.id,
            "engine": candidate.engine,
            "engineVersion": candidate.engine_version,
            "sourceVersion": candidate.source_version,
            "anchorVersion": candidate.anchor_version,
        }
        registrations = dict(item.registrations)
        registrations[candidate.slide_id] = registration
        item.registrations = registrations
        config = dict(item.alignment_config or {})
        selected = dict(config.get("selectedEngines") or {})
        selected[candidate.slide_id] = candidate.engine
        config["selectedEngines"] = selected
        item.alignment_config = config
        database.add(
            ComparisonRegistrationRevision(
                comparison_set_id=item.id,
                slide_id=candidate.slide_id,
                set_version=item.version,
                source_version=candidate.source_version,
                anchor_slide_id=candidate.anchor_slide_id,
                algorithm_version=candidate.engine[:40],
                provenance="automatic",
                registration=registration,
            )
        )
        item.status = (
            "ready"
            if len(registrations) == len(item.member_slide_ids) - 1
            and all(value.get("status") == "ready" for value in registrations.values())
            else "partial"
        )
        database.commit()
        return _json(item, _members(database, item), database=database)

    def jobs(
        set_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        if database.get(ComparisonSet, set_id) is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        return [
            {
                "id": job.id,
                "kind": job.kind,
                "memberId": (job.checkpoint or {}).get("memberId"),
                "setVersion": (job.checkpoint or {}).get("setVersion"),
                "status": job.status,
                "stage": (job.checkpoint or {}).get("stage", "queued"),
                "progress": (job.checkpoint or {}).get("progress", 0),
                "processedPatches": (job.checkpoint or {}).get("processedPatches", 0),
                "processedComponentPairs": (job.checkpoint or {}).get("processedComponentPairs", 0),
                "totalComponentPairs": (job.checkpoint or {}).get("totalComponentPairs", 0),
                "totalPatches": (job.checkpoint or {}).get("totalPatches", 0),
                "failureCode": job.failure_code,
                "createdAt": _utc_iso(job.created_at),
                "updatedAt": _utc_iso(job.updated_at),
                "heartbeatAt": _utc_iso(job.heartbeat_at) if job.heartbeat_at else None,
            }
            for job in database.scalars(
                select(Job).where(Job.kind.in_({"align", "align_benchmark"}))
            )
            if (job.checkpoint or {}).get("comparisonSetId") == set_id
        ]

    def cancel_registration(
        set_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, int]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        cancelled = 0
        now = datetime.now(UTC)
        for job in database.scalars(
            select(Job).where(
                Job.kind.in_({"align", "align_benchmark"}),
                Job.status.in_(["queued", "leased", "running", "retry_wait"]),
            )
        ):
            if (job.checkpoint or {}).get("comparisonSetId") == set_id:
                job.cancellation_requested_at = now
                cancelled += 1
        if cancelled:
            # Existing maps remain usable while the worker observes cancellation.
            # Do not leave the stack permanently claiming that alignment is running.
            item.status = _settled_registration_status(item)
        database.commit()
        return {"cancelledJobs": cancelled}

    def correct(
        set_id: str,
        slide_id: str,
        payload: CorrectionRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if (
            item is None
            or slide_id not in item.member_slide_ids
            or slide_id == item.reference_slide_id
        ):
            raise _error("COMPARISON_MEMBER_NOT_FOUND", 404)
        if payload.version != item.version:
            raise _error("COMPARISON_VERSION_CONFLICT", 409)
        anchor_id = payload.reference_slide_id or item.reference_slide_id
        if anchor_id not in item.member_slide_ids or anchor_id == slide_id:
            raise _error("REFERENCE_NOT_MEMBER")
        members = {slide.id: slide for slide in _members(database, item)}
        for member_id, points in (
            (anchor_id, payload.reference_points),
            (slide_id, payload.moving_points),
        ):
            metadata = members[member_id].slide_metadata or {}
            width, height = metadata.get("width"), metadata.get("height")
            if (
                not width
                or not height
                or any(not (0 <= x < width and 0 <= y < height) for x, y in points)
            ):
                raise _error("LANDMARK_OUTSIDE_SLIDE")
        if len(payload.reference_points) != len(payload.moving_points):
            raise _error("LANDMARK_COUNT_MISMATCH")
        transform, _ = cv2.estimateAffinePartial2D(
            np.asarray(payload.moving_points, dtype=np.float32),
            np.asarray(payload.reference_points, dtype=np.float32),
            method=cv2.LMEDS,
        )
        if transform is None:
            raise _error("LANDMARKS_DEGENERATE")
        moving = np.asarray(payload.moving_points, dtype=np.float64)
        reference = np.asarray(payload.reference_points, dtype=np.float64)
        moving_hull = cv2.contourArea(cv2.convexHull(moving.astype(np.float32)))
        reference_hull = cv2.contourArea(cv2.convexHull(reference.astype(np.float32)))
        if moving_hull < 4.0 or reference_hull < 4.0:
            raise _error("LANDMARKS_NOT_DISTRIBUTED")
        predicted = cv2.transform(moving[:, None, :].astype(np.float32), transform)[:, 0, :]
        residuals = np.linalg.norm(predicted - reference, axis=1)
        controls = [
            {
                "moving": [float(source[0]), float(source[1])],
                "reference": [float(target[0]), float(target[1])],
                "errorPixels": round(float(error), 4),
                "provenance": "manual-landmark",
            }
            for source, target, error in zip(moving, reference, residuals, strict=True)
        ]
        triangles = _registration_triangles(controls)
        for triangle in triangles:
            triangle["provenance"] = "manual-landmark"
        if not triangles:
            raise _error("LANDMARKS_NOT_DISTRIBUTED")
        median_residual = float(np.median(residuals))
        confidence = max(0.0, min(0.95, 0.9 - median_residual / 50.0))
        registrations = dict(item.registrations)
        registrations[slide_id] = {
            "status": "ready",
            "provenance": "manual",
            "anchorSlideId": anchor_id,
            "coordinateReferenceId": anchor_id,
            "movingToReference": transform.tolist(),
            "referenceSupport": None,
            "movingSupport": None,
            "confidence": round(confidence, 6),
            "controlPoints": controls,
            "triangles": triangles,
            "supportPolygons": {
                "moving": [triangle["moving"] for triangle in triangles],
                "reference": [triangle["reference"] for triangle in triangles],
            },
            "medianErrorPixels": round(median_residual, 4),
            "evidence": {
                "mode": "matched-regions",
                "anatomicalMatchCount": len(controls),
                "triangleCount": len(triangles),
                "withheldCheck": "manual-preview",
            },
        }
        if payload.preview_only:
            preview = _json(item, list(members.values()), database=database)
            for member in preview["members"]:
                if member["slideId"] == slide_id:
                    member["registration"] = registrations[slide_id]
            return preview
        # Maps depending on a corrected anchor must not retain stale coordinates.
        affected = {slide_id}
        while True:
            downstream = {
                key
                for key, value in registrations.items()
                if key not in affected and value.get("anchorSlideId") in affected
            }
            if not downstream:
                break
            affected.update(downstream)
        for key in affected - {slide_id}:
            registrations.pop(key, None)
        item.registrations = registrations
        item.version += 1
        database.add(
            ComparisonRegistrationRevision(
                comparison_set_id=item.id,
                slide_id=slide_id,
                set_version=item.version,
                source_version=item.source_versions.get(slide_id),
                anchor_slide_id=anchor_id,
                algorithm_version="piecewise-affine-v1",
                provenance="manual",
                registration=registrations[slide_id],
            )
        )
        item.status = (
            "ready"
            if len(registrations) == len(item.member_slide_ids) - 1
            and all(value.get("status") == "ready" for value in registrations.values())
            else "partial"
        )
        database.commit()
        return _json(item, _members(database, item), database=database)

    def public_share(public_id: str, database: OrmSession) -> LibraryShare:
        try:
            return active_public_share(database, target_type="collection", public_id=public_id)
        except ShareConflict as exc:
            raise _error("COMPARISON_NOT_FOUND", 404) from exc

    def shared_positions(database: OrmSession, share: LibraryShare) -> dict[str, int]:
        rows = database.execute(
            select(ShareSlide.slide_id, ShareSlide.sort_order)
            .where(ShareSlide.share_id == share.id)
            .order_by(ShareSlide.sort_order, ShareSlide.slide_id)
        ).all()
        return {slide_id: order for slide_id, order in rows}

    def stack_is_publicly_available(database: OrmSession, item: ComparisonSet) -> bool:
        members = _members(database, item)
        return bool(members) and all(
            slide.trashed_at is None and slide.state in READY_STATES for slide in members
        )

    def public_sets(
        public_id: str, database: OrmSession = Depends(database_dependency)
    ) -> list[dict[str, str]]:
        share = public_share(public_id, database)
        shared_ids = set(shared_positions(database, share))
        return [
            {"id": item.id, "name": item.name, "status": item.status}
            for item in database.scalars(
                select(ComparisonSet).order_by(ComparisonSet.updated_at.desc())
            )
            if set(item.member_slide_ids).issubset(shared_ids)
            and stack_is_publicly_available(database, item)
        ]

    def public_set(
        public_id: str, set_id: str, database: OrmSession = Depends(database_dependency)
    ) -> dict[str, Any]:
        share = public_share(public_id, database)
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        positions = shared_positions(database, share)
        if not set(item.member_slide_ids).issubset(positions) or not stack_is_publicly_available(
            database, item
        ):
            raise _error("COMPARISON_NOT_FOUND", 404)
        payload = _json(item, _members(database, item), shared=positions, database=database)
        for member in payload["members"]:
            member["tileSource"] = member["tileSource"].replace("{sharePublicId}", public_id)
        return payload

    app.add_api_route("/api/v1/admin/comparison-sets", list_sets, methods=["GET"])
    app.add_api_route(
        "/api/v1/admin/comparison-sets",
        create_set,
        methods=["POST"],
        status_code=status.HTTP_201_CREATED,
    )
    app.add_api_route("/api/v1/admin/comparison-sets/{set_id}", get_set, methods=["GET"])
    app.add_api_route("/api/v1/admin/comparison-sets/{set_id}", update_set, methods=["PATCH"])
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/members", update_members, methods=["PATCH"]
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/upload-reservations",
        reserve_stack_upload,
        methods=["POST"],
        status_code=status.HTTP_201_CREATED,
    )
    app.add_api_route("/api/v1/admin/slides/{slide_id}/stacks", slide_stacks, methods=["GET"])
    app.add_api_route(
        "/api/v1/admin/slides/{slide_id}/stack-suggestions",
        stack_suggestions,
        methods=["GET"],
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/revisions", revisions, methods=["GET"]
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/candidates", candidates, methods=["GET"]
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/benchmark",
        benchmark,
        methods=["POST"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/candidates/{candidate_id}/promote",
        promote_candidate,
        methods=["POST"],
    )
    app.add_api_route("/api/v1/admin/comparison-sets/{set_id}/jobs", jobs, methods=["GET"])
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/register",
        queue_set,
        methods=["POST"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/reregister",
        reregister,
        methods=["POST"],
        status_code=status.HTTP_202_ACCEPTED,
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/register",
        cancel_registration,
        methods=["DELETE"],
    )
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/corrections/{slide_id}", correct, methods=["PUT"]
    )
    app.add_api_route(
        "/api/v2/public/collections/{public_id}/comparisons", public_sets, methods=["GET"]
    )
    app.add_api_route(
        "/api/v2/public/collections/{public_id}/comparisons/{set_id}", public_set, methods=["GET"]
    )
