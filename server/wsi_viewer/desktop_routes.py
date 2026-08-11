# ruff: noqa: B008

import hashlib
import hmac
import os
import secrets
import shutil
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .annotations import (
    AnnotationBatchRequest,
    AnnotationError,
    annotation_json,
    apply_batch,
    calibration_json,
    layer_json,
    slide_bounds,
)
from .desktop_finalizer import PreparedIngestFinalizer, desktop_upload_path
from .domain import SlideState
from .models import (
    Annotation,
    AnnotationLayer,
    DesktopCredential,
    DesktopIngest,
    DesktopPairing,
    Session,
    Slide,
)
from .ome_ingest import desktop_quarantine_path
from .storage import GIB, StorageLayout, admission_required
from .tile_routes import TileRouteService, authorize_tile, private_static_target

PAIRING_MINUTES = 10
CREDENTIAL_DAYS = 90
DESKTOP_SCOPES = ["desktop:ingest", "slides:private:read", "annotations:sync"]
MAX_DESKTOP_CHUNK_BYTES = 64 * 1024 * 1024
LEGACY_DESKTOP_CHUNK_BYTES = 16 * 1024 * 1024
MAX_DERIVATIVE_FILES = 2_000_000
MIN_EXTRACTION_HEADROOM = 512 * 1024 * 1024
MAX_REQUEST_BUFFER_BYTES = 1024 * 1024


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token(bytes_count: int = 32) -> str:
    return secrets.token_urlsafe(bytes_count)


def _user_code() -> str:
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    raw = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _camel(value: str) -> str:
    words = value.split("_")
    return words[0] + "".join(word.title() for word in words[1:])


class DesktopModel(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True)


class PairingStartRequest(DesktopModel):
    device_name: str = Field(min_length=1, max_length=120)


class PairingApproveRequest(DesktopModel):
    user_code: str = Field(min_length=9, max_length=9)


class PairingExchangeRequest(DesktopModel):
    device_code: str = Field(min_length=20, max_length=200)
    device_secret: str = Field(min_length=20, max_length=200)


class PreparedIngestRequest(DesktopModel):
    display_name: str = Field(min_length=1, max_length=200)
    artifact_revision_id: str = Field(min_length=1, max_length=100)
    package_length: int = Field(gt=0)
    package_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    manifest_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    derivative_bytes: int | None = Field(default=None, gt=0)
    derivative_file_count: int | None = Field(
        default=None, gt=0, le=MAX_DERIVATIVE_FILES
    )


class OmeIngestRequest(DesktopModel):
    display_name: str = Field(min_length=1, max_length=200)
    artifact_revision_id: str = Field(min_length=1, max_length=100)
    ome_length: int = Field(gt=0)
    ome_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    profile: str = Field(pattern=r"^ome-dynamic-v1$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    downsample: float = Field(gt=0)
    jpeg_quality: int = Field(default=75, ge=1, le=100)


def register_desktop_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    csrf_dependency: Callable[..., Any],
    storage: StorageLayout,
    tile_routes: Callable[[], TileRouteService],
    ome_dynamic_enabled: bool = True,
    max_upload_bytes: int = 5 * GIB,
) -> PreparedIngestFinalizer:
    finalizer = PreparedIngestFinalizer(database_dependency, storage)
    app.state.desktop_ingest_finalizer = finalizer

    def credential(
        database: OrmSession = Depends(database_dependency),
        authorization: str | None = Header(default=None),
    ) -> DesktopCredential:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail={"code": "DESKTOP_AUTH_REQUIRED"})
        token = authorization.removeprefix("Bearer ").strip()
        stored = database.get(DesktopCredential, _hash(token))
        now = _now()
        if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
            raise HTTPException(
                status_code=401, detail={"code": "DESKTOP_CREDENTIAL_INVALID"}
            )
        if stored.last_used_at is None or stored.last_used_at <= now - timedelta(minutes=15):
            stored.last_used_at = now
            database.commit()
        return stored

    def require_scope(stored: DesktopCredential, scope: str) -> None:
        if scope not in stored.scopes:
            raise HTTPException(status_code=403, detail={"code": "DESKTOP_SCOPE_REQUIRED"})

    def upload_path(ingest: DesktopIngest) -> Path:
        return desktop_upload_path(storage, ingest)

    def ingest_json(ingest: DesktopIngest, database: OrmSession) -> dict[str, Any]:
        document = {
            "id": ingest.id,
            "status": "finalizing" if ingest.status == "installing" else ingest.status,
            "receivedBytes": ingest.received_bytes,
            "packageLength": ingest.package_length,
            "slideId": ingest.slide_id,
            "errorCode": ingest.error_code,
            "uploadUrl": f"/api/v1/desktop/ingests/{ingest.id}/content",
            "ingestMode": ingest.ingest_mode,
        }
        if ingest.status == "ready_private" and ingest.slide_id is not None:
            slide = database.get(Slide, ingest.slide_id)
            if (
                slide is not None
                and slide.state in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
                and slide.sha256 is not None
            ):
                document["slideSha256"] = slide.sha256
        return document

    @app.post("/api/v1/desktop/pairings", status_code=status.HTTP_201_CREATED)
    def start_pairing(
        payload: PairingStartRequest,
        request: Request,
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        device_code = _token()
        device_secret = _token()
        code = _user_code()
        while database.scalar(
            select(DesktopPairing.id).where(DesktopPairing.user_code == code)
        ) is not None:
            code = _user_code()
        expires = _now() + timedelta(minutes=PAIRING_MINUTES)
        pairing = DesktopPairing(
            device_code_hash=_hash(device_code),
            device_secret_hash=_hash(device_secret),
            user_code=code,
            device_name=payload.device_name.strip(),
            status="pending",
            expires_at=expires,
        )
        database.add(pairing)
        database.commit()
        return {
            "pairingId": pairing.id,
            "deviceCode": device_code,
            "deviceSecret": device_secret,
            "userCode": code,
            "verificationUrl": (
                str(request.base_url).rstrip("/") + f"/admin/connect?code={code}"
            ),
            "expiresAt": expires.replace(tzinfo=UTC).isoformat(),
        }

    @app.post(
        "/api/v1/desktop/pairings/approve",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def approve_pairing(
        payload: PairingApproveRequest,
        authenticated: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        pairing = database.scalar(
            select(DesktopPairing).where(
                DesktopPairing.user_code == payload.user_code.upper()
            )
        )
        if pairing is None or pairing.expires_at <= _now() or pairing.status != "pending":
            raise HTTPException(status_code=404, detail={"code": "PAIRING_NOT_FOUND"})
        pairing.user_id = authenticated.user_id
        pairing.status = "approved"
        pairing.approved_at = _now()
        database.commit()

    @app.post("/api/v1/desktop/pairings/exchange")
    def exchange_pairing(
        payload: PairingExchangeRequest,
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        pairing = database.scalar(
            select(DesktopPairing).where(
                DesktopPairing.device_code_hash == _hash(payload.device_code)
            )
        )
        if (
            pairing is None
            or not hmac.compare_digest(
                pairing.device_secret_hash, _hash(payload.device_secret)
            )
            or pairing.expires_at <= _now()
        ):
            raise HTTPException(status_code=401, detail={"code": "PAIRING_INVALID"})
        if pairing.status == "pending":
            raise HTTPException(status_code=409, detail={"code": "PAIRING_PENDING"})
        if pairing.status != "approved" or pairing.user_id is None:
            raise HTTPException(
                status_code=409, detail={"code": "PAIRING_ALREADY_EXCHANGED"}
            )
        access_token = _token(48)
        expires = _now() + timedelta(days=CREDENTIAL_DAYS)
        database.add(
            DesktopCredential(
                id=_hash(access_token),
                user_id=pairing.user_id,
                device_name=pairing.device_name,
                scopes=list(DESKTOP_SCOPES),
                expires_at=expires,
            )
        )
        pairing.status = "exchanged"
        pairing.exchanged_at = _now()
        database.commit()
        return {
            "accessToken": access_token,
            "tokenType": "Bearer",
            "scopes": list(DESKTOP_SCOPES),
            "expiresAt": expires.replace(tzinfo=UTC).isoformat(),
        }

    @app.get("/api/v1/desktop/credential")
    def credential_status(
        authenticated: DesktopCredential = Depends(credential),
    ) -> dict[str, Any]:
        return {
            "deviceName": authenticated.device_name,
            "scopes": authenticated.scopes,
            "expiresAt": authenticated.expires_at.replace(tzinfo=UTC).isoformat(),
            "revoked": authenticated.revoked_at is not None,
        }

    @app.get("/api/v1/desktop/capabilities")
    def desktop_capabilities(
        authenticated: DesktopCredential = Depends(credential),
    ) -> dict[str, Any]:
        require_scope(authenticated, "desktop:ingest")
        ingest_modes = ["prepared-v2"]
        ome_profiles: list[dict[str, Any]] = []
        if ome_dynamic_enabled:
            ingest_modes.append("ome-dynamic-v1")
            ome_profiles.append(
                {
                    "id": "ome-dynamic-v1",
                    "pixelType": "uint8",
                    "channels": 3,
                    "colorSpace": "sRGB",
                    "tileWidth": 512,
                    "tileHeight": 512,
                    "pyramidFactor": 2,
                    "compression": "jpeg",
                    "tiffKinds": ["classic", "bigtiff"],
                    "nativeJpegTiles": True,
                    "persistedSha256": True,
                }
            )
        return {
            "desktopApiVersion": "pathlab-desktop-ingest/v1",
            "ingestModes": ingest_modes,
            "omeProfiles": ome_profiles,
            "packageSchemas": ["pathlab-prepared-slide/v2"],
            "inventoryFormats": ["manifest-files-v1", "ndjson-v1"],
            "maxChunkBytes": MAX_DESKTOP_CHUNK_BYTES,
            "recommendedChunkBytes": MAX_DESKTOP_CHUNK_BYTES,
            "legacyChunkBytes": LEGACY_DESKTOP_CHUNK_BYTES,
            "maxDerivativeFiles": MAX_DERIVATIVE_FILES,
            "maxUploadBytes": max_upload_bytes,
        }

    @app.post(
        "/api/v1/desktop/credential/revoke",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def revoke_credential(
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        authenticated.revoked_at = _now()
        database.commit()

    @app.post("/api/v1/desktop/ingests", status_code=status.HTTP_201_CREATED)
    def create_prepared_ingest(
        payload: PreparedIngestRequest,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "desktop:ingest")
        if payload.package_length > max_upload_bytes:
            raise HTTPException(status_code=413, detail={"code": "UPLOAD_TOO_LARGE"})
        active = database.scalar(
            select(DesktopIngest.id).where(
                DesktopIngest.credential_id == authenticated.id,
                DesktopIngest.status.in_(("uploading", "finalizing", "installing")),
            )
        )
        if active is not None:
            raise HTTPException(status_code=409, detail={"code": "INGEST_ALREADY_ACTIVE"})
        free = shutil.disk_usage(storage.root).free
        if (payload.derivative_bytes is None) != (
            payload.derivative_file_count is None
        ):
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_DERIVATIVE_DECLARATION"},
            )
        if payload.derivative_bytes is not None:
            required = (
                payload.package_length
                + payload.derivative_bytes
                + max(MIN_EXTRACTION_HEADROOM, payload.derivative_bytes // 10)
            )
        else:
            required = payload.package_length * 2 + 5 * GIB
        if free < required or storage.usage() + required > storage.cap_bytes:
            raise HTTPException(status_code=507, detail={"code": "INSUFFICIENT_STORAGE"})
        ingest = DesktopIngest(
            credential_id=authenticated.id,
            display_name=payload.display_name.strip(),
            artifact_revision_id=payload.artifact_revision_id.strip(),
            package_length=payload.package_length,
            package_sha256=payload.package_sha256.lower(),
            manifest_sha256=payload.manifest_sha256.lower(),
            derivative_bytes=payload.derivative_bytes,
            derivative_file_count=payload.derivative_file_count,
            ingest_mode="prepared_v2",
            status="uploading",
        )
        database.add(ingest)
        database.commit()
        database.refresh(ingest)
        target = upload_path(ingest)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb"):
            pass
        return ingest_json(ingest, database)

    @app.post("/api/v1/desktop/ome-ingests", status_code=status.HTTP_201_CREATED)
    def create_ome_ingest(
        payload: OmeIngestRequest,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "desktop:ingest")
        if not ome_dynamic_enabled:
            raise HTTPException(
                status_code=409, detail={"code": "OME_DYNAMIC_DISABLED"}
            )
        if payload.ome_length > max_upload_bytes:
            raise HTTPException(status_code=413, detail={"code": "UPLOAD_TOO_LARGE"})
        active = database.scalar(
            select(DesktopIngest.id).where(
                DesktopIngest.credential_id == authenticated.id,
                DesktopIngest.status.in_(("uploading", "finalizing", "installing")),
            )
        )
        if active is not None:
            raise HTTPException(status_code=409, detail={"code": "INGEST_ALREADY_ACTIVE"})
        required = admission_required(payload.ome_length, render_mode="ome_dynamic")
        free = shutil.disk_usage(storage.root).free
        if free < required or storage.usage() + required > storage.cap_bytes:
            raise HTTPException(status_code=507, detail={"code": "INSUFFICIENT_STORAGE"})
        ingest = DesktopIngest(
            credential_id=authenticated.id,
            display_name=payload.display_name.strip(),
            artifact_revision_id=payload.artifact_revision_id.strip(),
            package_length=payload.ome_length,
            package_sha256=payload.ome_sha256.lower(),
            manifest_sha256=payload.ome_sha256.lower(),
            ingest_mode="ome_dynamic_v1",
            ome_profile=payload.profile,
            ome_width=payload.width,
            ome_height=payload.height,
            ome_downsample=payload.downsample,
            ome_jpeg_quality=payload.jpeg_quality,
            status="uploading",
        )
        database.add(ingest)
        database.commit()
        database.refresh(ingest)
        target = upload_path(ingest)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb"):
            pass
        return ingest_json(ingest, database)

    @app.head("/api/v1/desktop/ingests/{ingest_id}/content")
    def prepared_ingest_offset(
        ingest_id: str,
        response: Response,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        require_scope(authenticated, "desktop:ingest")
        ingest = database.get(DesktopIngest, ingest_id)
        if ingest is None or ingest.credential_id != authenticated.id:
            raise HTTPException(status_code=404, detail={"code": "INGEST_NOT_FOUND"})
        response.headers["Upload-Offset"] = str(ingest.received_bytes)
        response.headers["Upload-Length"] = str(ingest.package_length)
        response.headers["Upload-Status"] = ingest.status

    @app.patch(
        "/api/v1/desktop/ingests/{ingest_id}/content",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_prepared_ingest(
        ingest_id: str,
        request: Request,
        upload_offset: int = Header(alias="Upload-Offset", ge=0),
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "desktop:ingest")
        ingest = database.get(DesktopIngest, ingest_id)
        if ingest is None or ingest.credential_id != authenticated.id:
            raise HTTPException(status_code=404, detail={"code": "INGEST_NOT_FOUND"})
        retry_failed_finalization = (
            ingest.status == "failed"
            and upload_offset == ingest.received_bytes
            and ingest.received_bytes == ingest.package_length
        )
        if retry_failed_finalization:
            if await request.body():
                raise HTTPException(
                    status_code=409, detail={"code": "FINALIZATION_RETRY_MUST_BE_EMPTY"}
                )
            target = upload_path(ingest)
            quarantine = desktop_quarantine_path(storage, ingest.id)
            if not target.is_file() and quarantine.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(quarantine, target)
            if not target.is_file() or target.stat().st_size != ingest.package_length:
                raise HTTPException(
                    status_code=409, detail={"code": "FAILED_UPLOAD_NOT_RECOVERABLE"}
                )
            ingest.status = "finalizing"
            ingest.error_code = None
            database.commit()
            finalizer.enqueue(ingest.id)
            database.refresh(ingest)
            return ingest_json(ingest, database)
        if ingest.status != "uploading" or upload_offset != ingest.received_bytes:
            raise HTTPException(status_code=409, detail={"code": "UPLOAD_OFFSET_MISMATCH"})
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > MAX_DESKTOP_CHUNK_BYTES:
                    raise HTTPException(
                        status_code=413, detail={"code": "DESKTOP_CHUNK_TOO_LARGE"}
                    )
            except ValueError as error:
                raise HTTPException(
                    status_code=400, detail={"code": "INVALID_CONTENT_LENGTH"}
                ) from error
        received = 0
        target = upload_path(ingest)
        try:
            with target.open("r+b") as output:
                output.seek(upload_offset)
                async for block in request.stream():
                    received += len(block)
                    if (
                        received > MAX_DESKTOP_CHUNK_BYTES
                        or upload_offset + received > ingest.package_length
                    ):
                        raise HTTPException(
                            status_code=413, detail={"code": "DESKTOP_CHUNK_TOO_LARGE"}
                        )
                    view = memoryview(block)
                    for start in range(0, len(view), MAX_REQUEST_BUFFER_BYTES):
                        output.write(view[start : start + MAX_REQUEST_BUFFER_BYTES])
                output.flush()
                os.fsync(output.fileno())
        except HTTPException:
            with target.open("r+b") as output:
                output.truncate(upload_offset)
            raise
        ingest.received_bytes += received
        if ingest.received_bytes == ingest.package_length:
            ingest.status = "finalizing"
        database.commit()
        if ingest.status == "finalizing":
            finalizer.enqueue(ingest.id)
        database.refresh(ingest)
        return ingest_json(ingest, database)

    @app.get("/api/v1/desktop/ingests/{ingest_id}")
    def prepared_ingest_status(
        ingest_id: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "desktop:ingest")
        ingest = database.get(DesktopIngest, ingest_id)
        if ingest is None or ingest.credential_id != authenticated.id:
            raise HTTPException(status_code=404, detail={"code": "INGEST_NOT_FOUND"})
        return ingest_json(ingest, database)

    @app.get("/api/v1/desktop/slides/{slide_id}")
    def desktop_slide(
        slide_id: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "slides:private:read")
        slide = database.get(Slide, slide_id)
        if slide is None or slide.state not in {
            SlideState.READY_PRIVATE,
            SlideState.PUBLISHED,
        }:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        return {
            "id": slide.id,
            "displayName": slide.display_name,
            "state": slide.state.value,
            "metadata": slide.slide_metadata,
            "annotationVersion": slide.annotation_version,
            "tileSource": f"/api/v1/desktop/slides/{slide.id}/preview/slide.dzi",
            "thumbnailUrl": (
                f"/api/v1/desktop/slides/{slide.id}/preview/thumbnail.jpg"
                if slide.thumbnail_filename or slide.render_mode == "ome_dynamic"
                else None
            ),
        }

    @app.get("/api/v1/desktop/slides/{slide_id}/preview/{tile_path:path}")
    def desktop_slide_tile(
        slide_id: str,
        tile_path: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        require_scope(authenticated, "slides:private:read")
        slide = database.get(Slide, slide_id)
        if (
            slide is None
            or slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
            or slide.trashed_at is not None
        ):
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
        authorized = authorize_tile(
            slide_id=slide.id,
            slide_sha256=slide.sha256,
            render_mode=slide.render_mode,
            relative_path=tile_path,
            cache_control="private, max-age=86400, immutable",
        )
        if authorized.render_mode == "ome_dynamic":
            return tile_routes().dynamic_response(authorized)
        target = private_static_target(storage, slide.id, tile_path)
        return FileResponse(
            target,
            media_type="application/xml"
            if target.suffix.lower() == ".dzi"
            else "image/jpeg",
            headers={"Cache-Control": "private, max-age=86400, immutable"},
        )

    @app.get("/api/v1/desktop/slides/{slide_id}/annotations")
    def desktop_annotations(
        slide_id: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=1_000, ge=1, le=5_000),
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "annotations:sync")
        if not app.state.settings.annotations_enabled:
            raise HTTPException(status_code=404, detail={"code": "ANNOTATIONS_DISABLED"})
        slide = database.get(Slide, slide_id)
        if slide is None or slide.state not in {
            SlideState.READY_PRIVATE,
            SlideState.PUBLISHED,
        }:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        width, height = slide_bounds(slide)
        total = int(
            database.scalar(
                select(func.count(Annotation.id)).where(
                    Annotation.slide_id == slide.id
                )
            )
            or 0
        )
        items = list(
            database.scalars(
                select(Annotation)
                .where(Annotation.slide_id == slide.id)
                .order_by(Annotation.created_at, Annotation.id)
                .offset(offset)
                .limit(limit)
            )
        )
        layers = database.scalars(
            select(AnnotationLayer)
            .where(AnnotationLayer.slide_id == slide.id)
            .order_by(AnnotationLayer.sort_order, AnnotationLayer.created_at)
        )
        return {
            "slideId": slide.id,
            "version": slide.annotation_version,
            "bounds": {"width": width, "height": height},
            "calibration": calibration_json(slide),
            "layers": [layer_json(layer) for layer in layers],
            "items": [annotation_json(item, slide) for item in items],
            "total": total,
            "nextOffset": offset + len(items)
            if offset + len(items) < total
            else None,
        }

    @app.post("/api/v1/desktop/slides/{slide_id}/annotations/batch")
    def desktop_annotation_batch(
        slide_id: str,
        payload: AnnotationBatchRequest,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "annotations:sync")
        if not app.state.settings.annotations_enabled:
            raise HTTPException(status_code=404, detail={"code": "ANNOTATIONS_DISABLED"})
        slide = database.get(Slide, slide_id)
        if slide is None or slide.state not in {
            SlideState.READY_PRIVATE,
            SlideState.PUBLISHED,
        }:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        merged = payload.base_version != slide.annotation_version
        candidate = payload.model_copy(
            update={"base_version": slide.annotation_version}
        ) if merged else payload
        try:
            result = apply_batch(
                database,
                slide,
                candidate,
                actor_user_id=authenticated.user_id,
            )
        except AnnotationError as error:
            database.rollback()
            raise HTTPException(
                status_code=error.status_code,
                detail={"code": error.code, **error.detail},
            ) from error
        return {**result, "autoMerged": merged}

    return finalizer
