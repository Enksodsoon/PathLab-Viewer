# ruff: noqa: B008
from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from typing import Any

import cv2
import numpy as np
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from .alignment import _registration_triangles
from .domain import SlideState
from .models import (
    ComparisonRegistrationRevision,
    ComparisonSet,
    Job,
    LibraryShare,
    ShareSlide,
    Slide,
)
from .sharing import ShareConflict, active_public_share


class ComparisonRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=160)
    slide_ids: list[str] = Field(alias="slideIds", min_length=2, max_length=12)
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
                "thumbnailUrl": tile_source.replace("slide.dzi", "thumbnail.jpg"),
                "registration": item.registrations.get(slide.id),
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
            alignment_config={},
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
        configured = (item.alignment_config or {}).get("anchors", {})
        anchors.update(
            {
                slide_id: anchor_id
                for slide_id, anchor_id in configured.items()
                if slide_id in item.member_slide_ids and anchor_id in item.member_slide_ids
            }
        )
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
                            "setVersion": item.version,
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
            item.version += 1
            item.registrations = {}
            item.status = "draft"
            for job in database.scalars(
                select(Job).where(
                    Job.kind == "align",
                    Job.status.in_(["queued", "leased", "running", "retry_wait"]),
                )
            ):
                if (job.checkpoint or {}).get("comparisonSetId") == item.id:
                    job.cancellation_requested_at = datetime.now(UTC)
        database.commit()
        return _json(item, _members(database, item))

    def reregister(
        set_id: str,
        authorization: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        item = database.get(ComparisonSet, set_id)
        if item is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        item.version += 1
        item.registrations = {}
        item.status = "draft"
        database.commit()
        return queue_set(set_id, authorization, database)

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
                "memberId": (job.checkpoint or {}).get("memberId"),
                "status": job.status,
                "stage": (job.checkpoint or {}).get("stage", "queued"),
                "progress": (job.checkpoint or {}).get("progress", 0),
                "processedPatches": (job.checkpoint or {}).get("processedPatches", 0),
                "processedComponentPairs": (job.checkpoint or {}).get("processedComponentPairs", 0),
                "totalComponentPairs": (job.checkpoint or {}).get("totalComponentPairs", 0),
                "totalPatches": (job.checkpoint or {}).get("totalPatches", 0),
                "failureCode": job.failure_code,
            }
            for job in database.scalars(select(Job).where(Job.kind == "align"))
            if (job.checkpoint or {}).get("comparisonSetId") == set_id
        ]

    def cancel_registration(
        set_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, int]:
        if database.get(ComparisonSet, set_id) is None:
            raise _error("COMPARISON_NOT_FOUND", 404)
        cancelled = 0
        now = datetime.now(UTC)
        for job in database.scalars(
            select(Job).where(
                Job.kind == "align",
                Job.status.in_(["queued", "leased", "running", "retry_wait"]),
            )
        ):
            if (job.checkpoint or {}).get("comparisonSetId") == set_id:
                job.cancellation_requested_at = now
                cancelled += 1
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
            preview = _json(item, list(members.values()))
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
    app.add_api_route("/api/v1/admin/comparison-sets/{set_id}", update_set, methods=["PATCH"])
    app.add_api_route(
        "/api/v1/admin/comparison-sets/{set_id}/revisions", revisions, methods=["GET"]
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
