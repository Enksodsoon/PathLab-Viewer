# ruff: noqa: B008
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator
from typing import Any

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .models import ComparisonSet, Job, LibraryShare, ShareSlide, Slide
from .sharing import ShareConflict, active_public_share


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=160)
    slide_ids: list[str] = Field(alias="slideIds", min_length=2, max_length=12)
    reference_slide_id: str = Field(alias="referenceSlideId", min_length=1, max_length=64)


class CorrectionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reference_points: list[tuple[float, float]] = Field(
        alias="referencePoints", min_length=3, max_length=20
    )
    moving_points: list[tuple[float, float]] = Field(
        alias="movingPoints", min_length=3, max_length=20
    )


def _error(code: str, http_status: int = 422) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"code": code})


def _members(database: OrmSession, item: ComparisonSet) -> list[Slide]:
    slides = {
        slide.id: slide
        for slide in database.scalars(
            select(Slide).where(Slide.id.in_(item.member_slide_ids), Slide.trashed_at.is_(None))
        )
    }
    if len(slides) != len(item.member_slide_ids):
        raise _error("COMPARISON_SOURCE_CHANGED", 409)
    return [slides[slide_id] for slide_id in item.member_slide_ids]


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
    item: ComparisonSet, slides: list[Slide], *, shared: dict[str, int] | None = None
) -> dict[str, Any]:
    members = []
    for slide in slides:
        position = shared.get(slide.id) if shared is not None else None
        tile_source = (
            f"/api/v2/public/collections/{{sharePublicId}}/slides/{position}/tiles/slide.dzi"
            if position is not None
            else f"/api/v1/admin/slides/{slide.id}/preview/slide.dzi"
        )
        members.append(
            {
                "slideId": slide.id,
                "displayName": slide.display_name,
                "stain": slide.stain,
                "metadata": slide.slide_metadata,
                "tileSource": tile_source,
                "registration": item.registrations.get(slide.id),
            }
        )
    return {
        "id": item.id,
        "name": item.name,
        "referenceSlideId": item.reference_slide_id,
        "status": item.status,
        "version": item.version,
        "members": members,
    }


def register_alignment_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
    enabled: bool,
) -> None:
    if not enabled:
        return

    def list_sets(
        _: Any = Depends(admin_dependency), database: OrmSession = Depends(database_dependency)
    ) -> list[dict[str, Any]]:
        return [
            _json(item, _members(database, item))
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
            status="draft",
        )
        database.add(item)
        database.commit()
        database.refresh(item)
        return _json(item, [by_id[item] for item in ids])

    def get_set(
        set_id: str,
        _: Any = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        return _json(item, _members(database, item))

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
        secondary_anchors = {
            anchor_id for anchor_id in anchors.values() if anchor_id != item.reference_slide_id
        }
        slides = sorted(slides, key=lambda slide: slide.id not in secondary_anchors)
        queued = 0
        for slide in slides:
            if slide.id == item.reference_slide_id or slide.id in item.registrations:
                continue
            key = hashlib.sha256(f"{item.id}:{item.version}:{slide.id}".encode()).hexdigest()
            exists = database.scalar(
                select(Job.id).where(Job.kind == "align", Job.idempotency_key_hash == key)
            )
            if exists is None:
                database.add(
                    Job(
                        slide_id=slide.id,
                        kind="align",
                        resource_class="isolated",
                        idempotency_key_hash=key,
                        checkpoint={
                            "comparisonSetId": item.id,
                            "memberId": slide.id,
                            "anchorSlideId": anchors[slide.id],
                            "progress": 0,
                        },
                        resource_limits={
                            "cpuThreads": 1,
                            "memoryBytes": 2 * 1024**3,
                            "timeoutSeconds": 600,
                        },
                    )
                )
                queued += 1
        if queued:
            item.status = "queued"
        database.commit()
        return {"comparisonSetId": item.id, "queuedPairs": queued, "status": item.status}

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
        if len(payload.reference_points) != len(payload.moving_points):
            raise _error("LANDMARK_COUNT_MISMATCH")
        transform, _ = cv2.estimateAffinePartial2D(
            np.asarray(payload.moving_points, dtype=np.float32),
            np.asarray(payload.reference_points, dtype=np.float32),
            method=cv2.LMEDS,
        )
        if transform is None:
            raise _error("LANDMARKS_DEGENERATE")
        registrations = dict(item.registrations)
        registrations[slide_id] = {
            "status": "ready",
            "provenance": "manual",
            "movingToReference": transform.tolist(),
            "referenceSupport": None,
            "movingSupport": None,
            "confidence": 1.0,
        }
        item.registrations = registrations
        item.version += 1
        item.status = "ready" if len(registrations) == len(item.member_slide_ids) - 1 else "partial"
        database.commit()
        return _json(item, _members(database, item))

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
        ]

    def public_set(
        public_id: str, set_id: str, database: OrmSession = Depends(database_dependency)
    ) -> dict[str, Any]:
        share = public_share(public_id, database)
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        positions = shared_positions(database, share)
        if not set(item.member_slide_ids).issubset(positions):
            raise _error("COMPARISON_NOT_FOUND", 404)
        payload = _json(item, _members(database, item), shared=positions)
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
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/register",
        queue_set,
        methods=["POST"],
        status_code=status.HTTP_202_ACCEPTED,
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
