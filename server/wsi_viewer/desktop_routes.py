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
from .domain import SlideState
from .models import (
    Annotation,
    AnnotationLayer,
    AuditEvent,
    DesktopCredential,
    DesktopIngest,
    DesktopPairing,
    Session,
    Slide,
)
from .prepared_ingest import PreparedIngestError, install_prepared_package
from .storage import GIB, StorageLayout

PAIRING_MINUTES = 10
CREDENTIAL_DAYS = 90
DESKTOP_SCOPES = ["desktop:ingest", "slides:private:read", "annotations:sync"]
MAX_DESKTOP_CHUNK_BYTES = 16 * 1024 * 1024


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


def register_desktop_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    csrf_dependency: Callable[..., Any],
    storage: StorageLayout,
) -> None:
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
        stored.last_used_at = now
        database.commit()
        return stored

    def require_scope(stored: DesktopCredential, scope: str) -> None:
        if scope not in stored.scopes:
            raise HTTPException(status_code=403, detail={"code": "DESKTOP_SCOPE_REQUIRED"})

    def package_path(ingest_id: str) -> Path:
        return storage.root / "desktop-ingest" / f"{ingest_id}.plslide.partial"

    def ingest_json(ingest: DesktopIngest) -> dict[str, Any]:
        return {
            "id": ingest.id,
            "status": ingest.status,
            "receivedBytes": ingest.received_bytes,
            "packageLength": ingest.package_length,
            "slideId": ingest.slide_id,
            "errorCode": ingest.error_code,
            "uploadUrl": f"/api/v1/desktop/ingests/{ingest.id}/content",
        }

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
        active = database.scalar(
            select(DesktopIngest.id).where(
                DesktopIngest.credential_id == authenticated.id,
                DesktopIngest.status.in_(("uploading", "finalizing")),
            )
        )
        if active is not None:
            raise HTTPException(status_code=409, detail={"code": "INGEST_ALREADY_ACTIVE"})
        free = shutil.disk_usage(storage.root).free
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
            status="uploading",
        )
        database.add(ingest)
        database.commit()
        database.refresh(ingest)
        target = package_path(ingest.id)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb"):
            pass
        return ingest_json(ingest)

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
        target = package_path(ingest.id)
        if (
            ingest.status == "finalizing"
            and ingest.received_bytes == ingest.package_length
            and target.is_file()
            and target.stat().st_size == ingest.package_length
        ):
            _finalize_prepared_ingest(ingest, target, database, storage)
            database.refresh(ingest)
        response.headers["Upload-Offset"] = str(ingest.received_bytes)
        response.headers["Upload-Length"] = str(ingest.package_length)
        response.headers["Upload-Status"] = ingest.status

    @app.patch("/api/v1/desktop/ingests/{ingest_id}/content")
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
        target = package_path(ingest.id)
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
                    output.write(block)
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
            _finalize_prepared_ingest(ingest, target, database, storage)
        database.refresh(ingest)
        return ingest_json(ingest)

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
        return ingest_json(ingest)

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
        }

    @app.get("/api/v1/desktop/slides/{slide_id}/preview/{tile_path:path}")
    def desktop_slide_tile(
        slide_id: str,
        tile_path: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> FileResponse:
        require_scope(authenticated, "slides:private:read")
        slide = database.get(Slide, slide_id)
        root = storage.for_slide(slide_id).private_derivative.resolve()
        target = (root / tile_path).resolve()
        if (
            slide is None
            or slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
            or not target.is_relative_to(root)
            or target.suffix.lower() not in {".dzi", ".jpg", ".jpeg"}
            or not target.is_file()
        ):
            raise HTTPException(status_code=404, detail={"code": "TILE_NOT_FOUND"})
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


def _finalize_prepared_ingest(
    ingest: DesktopIngest,
    package: Path,
    database: OrmSession,
    storage: StorageLayout,
) -> None:
    slide = Slide(
        display_name=ingest.display_name,
        original_filename=f"{ingest.display_name}.plslide",
        source_bytes=ingest.package_length,
        reserved_bytes=0,
        state=SlideState.READY_PRIVATE,
        privacy_status="private",
    )
    database.add(slide)
    database.flush()
    destination = storage.for_slide(slide.id).private_derivative
    try:
        result = install_prepared_package(
            package,
            destination,
            expected_package_sha256=ingest.package_sha256,
            expected_artifact_revision_id=ingest.artifact_revision_id,
            expected_manifest_sha256=ingest.manifest_sha256,
        )
        provenance = result.manifest["provenance"]
        slide_info = result.manifest["slide"]
        slide.sha256 = ingest.package_sha256
        slide.derivative_bytes = result.measurement.derivative_bytes
        slide.derivative_file_count = result.measurement.file_count
        slide.thumbnail_filename = "thumbnail.jpg"
        slide.slide_metadata = {
            "width": slide_info["width"],
            "height": slide_info["height"],
            "physicalSizeX": provenance["calibration"]["pixelSizeX"],
            "physicalSizeY": provenance["calibration"]["pixelSizeY"],
            "physicalSizeUnit": provenance["calibration"]["unit"],
            "artifactRevisionId": provenance["artifactRevisionId"],
            "manifestSha256": result.manifest_sha256,
            "sourceFingerprint": provenance["sourceFingerprint"],
            "coordinateTransform": provenance["coordinateTransform"],
        }
        ingest.slide_id = slide.id
        ingest.status = "ready_private"
        owning_credential = database.get(DesktopCredential, ingest.credential_id)
        if owning_credential is None:
            raise PreparedIngestError("DESKTOP_CREDENTIAL_MISSING")
        database.add(
            AuditEvent(
                actor_user_id=owning_credential.user_id,
                action="desktop_ingest.complete",
                target_id=slide.id,
            )
        )
        database.commit()
        package.unlink(missing_ok=True)
    except (OSError, PreparedIngestError, KeyError, TypeError) as error:
        database.rollback()
        shutil.rmtree(destination, ignore_errors=True)
        failed = database.get(DesktopIngest, ingest.id)
        if failed is not None:
            failed.status = "failed"
            failed.error_code = str(error)[:80] or "PREPARED_INGEST_FAILED"
            database.commit()
        package.unlink(missing_ok=True)
