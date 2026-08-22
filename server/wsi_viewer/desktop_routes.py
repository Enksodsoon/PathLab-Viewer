# ruff: noqa: B008

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import tarfile
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
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
from .desktop_sync import (
    SCHEMA as DESKTOP_SYNC_SCHEMA,
)
from .desktop_sync import (
    change_json,
    decode_library_cursor,
    encode_library_cursor,
    record_sync_event,
    remote_folder_json,
    remote_slide_json,
    revision_for,
)
from .domain import SlideState
from .evidence_contract import load_trusted_signers, parse_evidence, validate_evidence
from .evidence_set_contract import validate_evidence_set
from .models import (
    AnalysisRun,
    Annotation,
    AnnotationLayer,
    DesktopCredential,
    DesktopIngest,
    DesktopPairing,
    DesktopSyncEvent,
    EvidenceBundle,
    EvidenceSet,
    Folder,
    ManagedResultAttachment,
    PathObjectMeasurement,
    PathObjectMetadata,
    ResultDelivery,
    Session,
    Slide,
)
from .ome_ingest import desktop_quarantine_path
from .storage import GIB, StorageLayout, admission_required
from .tile_routes import TileRouteService, authorize_tile, private_static_target
from .time_support import as_utc, utc_now

PAIRING_MINUTES = 10
CREDENTIAL_DAYS = 90
DESKTOP_SCOPES = [
    "desktop:ingest",
    "slides:private:read",
    "annotations:sync",
    "results:sync",
    "library:read",
    "slides:offline:read",
    "library:sync",
]
MAX_DESKTOP_CHUNK_BYTES = 64 * 1024 * 1024
LEGACY_DESKTOP_CHUNK_BYTES = 16 * 1024 * 1024
MAX_DERIVATIVE_FILES = 2_000_000
MIN_EXTRACTION_HEADROOM = 512 * 1024 * 1024
MAX_REQUEST_BUFFER_BYTES = 1024 * 1024
MAX_RESULT_BYTES = 2 * GIB
MAX_RESULT_OBJECTS = 2_000_000
MAX_RESULT_MASK_BYTES = 1024 * 1024 * 1024


def _now() -> datetime:
    return utc_now()


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
    derivative_file_count: int | None = Field(default=None, gt=0, le=MAX_DERIVATIVE_FILES)


class OmeIngestRequest(DesktopModel):
    display_name: str = Field(min_length=1, max_length=200)
    artifact_revision_id: str = Field(min_length=1, max_length=100)
    ome_length: int = Field(gt=0)
    ome_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    profile: str = Field(pattern=r"^ome-dynamic-v1$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    downsample: float = Field(gt=0)
    jpeg_quality: int = Field(default=75, ge=75, le=75)


class ResultDeliveryRequest(DesktopModel):
    artifact_revision_id: str = Field(min_length=1, max_length=100)
    slide_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    payload_length: int = Field(gt=0, le=MAX_RESULT_BYTES)
    payload_sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    result_schema: str = Field(alias="schema", pattern=r"^pathlab-private-results/v1$")


class DesktopSlidePatch(DesktopModel):
    expected_metadata_revision: int = Field(ge=0)
    expected_folder_revision: int = Field(ge=0)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=4000)
    case_id: str | None = Field(default=None, max_length=120)
    organ_site: str | None = Field(default=None, max_length=120)
    stain: str | None = Field(default=None, max_length=80)
    diagnosis: str | None = Field(default=None, max_length=300)
    course: str | None = Field(default=None, max_length=160)
    tags: list[str] | None = Field(default=None, max_length=50)
    teaching_note: str | None = Field(default=None, max_length=8000)
    admin_notes: str | None = Field(default=None, max_length=16000)
    folder_id: str | None = None


def register_desktop_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    csrf_dependency: Callable[..., Any],
    storage: StorageLayout,
    tile_routes: Callable[[], TileRouteService],
    ome_dynamic_enabled: bool = True,
    max_upload_bytes: int = 5 * GIB,
    evidence_trusted_signers_path: Path | None = None,
) -> PreparedIngestFinalizer:
    finalizer = PreparedIngestFinalizer(database_dependency, storage)
    trusted_evidence_signers = load_trusted_signers(evidence_trusted_signers_path)
    trusted_evidence_set_signers = load_trusted_signers(
        evidence_trusted_signers_path, "evidence-set"
    )
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
        if stored is None or stored.revoked_at is not None or as_utc(stored.expires_at) <= now:
            raise HTTPException(status_code=401, detail={"code": "DESKTOP_CREDENTIAL_INVALID"})
        if (
            stored.last_used_at is None
            or as_utc(stored.last_used_at) <= now - timedelta(minutes=15)
        ):
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

    def result_path(delivery_id: str) -> Path:
        return storage.root / "staging" / "results" / f"{delivery_id}.plresults"

    def result_json(delivery: ResultDelivery) -> dict[str, Any]:
        return {
            "id": delivery.id,
            "status": delivery.status,
            "receivedBytes": delivery.received_bytes,
            "payloadLength": delivery.payload_length,
            "errorCode": delivery.error_code,
            "uploadUrl": (
                f"/api/v2/desktop/slides/{delivery.slide_id}/result-deliveries/"
                f"{delivery.id}/content"
            ),
        }

    def apply_result_bundle(delivery: ResultDelivery, database: OrmSession) -> None:
        target = result_path(delivery.id)
        payload_digest = hashlib.sha256()
        with target.open("rb") as file_input:
            while block := file_input.read(MAX_REQUEST_BUFFER_BYTES):
                payload_digest.update(block)
        if payload_digest.hexdigest() != delivery.payload_sha256:
            raise ValueError("RESULT_HASH_MISMATCH")
        run_ids: dict[str, str] = {}
        object_ids: dict[str, str] = {}
        attachment_bytes = 0
        with tarfile.open(target, "r:gz") as archive:
            members = archive.getmembers()
            if sum(member.size for member in members) > MAX_RESULT_BYTES:
                raise ValueError("RESULT_EXPANDED_SIZE_LIMIT")
            names = {member.name for member in members}
            required = {"manifest.json", "objects.ndjson", "measurements.ndjson", "runs.ndjson"}
            if not required.issubset(names):
                raise ValueError("RESULT_SCHEMA_INVALID")
            for member in members:
                if (
                    member.name.startswith("/")
                    or ".." in Path(member.name).parts
                    or member.issym()
                    or member.islnk()
                ):
                    raise ValueError("RESULT_ARCHIVE_PATH_INVALID")
            manifest_file = archive.extractfile("manifest.json")
            if manifest_file is None:
                raise ValueError("RESULT_SCHEMA_INVALID")
            manifest = json.load(manifest_file)
            if (
                manifest.get("schema") != delivery.schema
                or manifest.get("artifactRevisionId") != delivery.artifact_revision_id
                or manifest.get("slideSha256") != delivery.slide_sha256
            ):
                raise ValueError("RESULT_SCHEMA_INVALID")
            if "evidence.json" in names:
                evidence_member = archive.getmember("evidence.json")
                if not evidence_member.isfile() or evidence_member.size > 2 * 1024 * 1024:
                    raise ValueError("AI_EVIDENCE_SIZE_INVALID")
                evidence_input = archive.extractfile(evidence_member)
                if evidence_input is None:
                    raise ValueError("AI_EVIDENCE_SCHEMA_INVALID")
                evidence = parse_evidence(evidence_input.read())
                evidence_sha = validate_evidence(
                    evidence,
                    slide_sha256=delivery.slide_sha256,
                    slide_revision=delivery.artifact_revision_id,
                    trusted_signers=trusted_evidence_signers,
                )
                if (
                    database.scalar(
                        select(EvidenceBundle.id).where(
                            EvidenceBundle.manifest_sha256 == evidence_sha
                        )
                    )
                    is not None
                ):
                    raise ValueError("AI_EVIDENCE_DUPLICATED")
                database.add(
                    EvidenceBundle(
                        delivery_id=delivery.id,
                        slide_id=delivery.slide_id,
                        bundle_id=evidence["bundleId"],
                        manifest_sha256=evidence_sha,
                        pack_id=evidence["pack"]["id"],
                        pack_version=evidence["pack"]["version"],
                        status=evidence["status"],
                        validation_status=evidence["pack"]["validationStatus"],
                        manifest=evidence,
                    )
                )
                database.flush()
            if "evidence-set.json" in names:
                member = archive.getmember("evidence-set.json")
                if not member.isfile() or member.size > 2 * 1024 * 1024:
                    raise ValueError("AI_EVIDENCE_SET_SIZE_INVALID")
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("AI_EVIDENCE_SET_SCHEMA_INVALID")
                evidence_set = parse_evidence(source.read())
                known_hashes = set(database.scalars(select(EvidenceBundle.manifest_sha256).where(
                    EvidenceBundle.slide_id == delivery.slide_id
                )))
                set_sha = validate_evidence_set(
                    evidence_set,
                    slide_sha256=delivery.slide_sha256,
                    slide_revision=delivery.artifact_revision_id,
                    trusted_signers=trusted_evidence_set_signers,
                    known_bundle_hashes=known_hashes,
                )
                if database.scalar(select(EvidenceSet.id).where(
                    EvidenceSet.manifest_sha256 == set_sha
                )) is not None:
                    raise ValueError("AI_EVIDENCE_SET_DUPLICATED")
                database.add(EvidenceSet(
                    slide_id=delivery.slide_id,
                    set_id=evidence_set["setId"],
                    manifest_sha256=set_sha,
                    status=evidence_set["status"],
                    manifest=evidence_set,
                ))

            def documents(name: str) -> Iterator[dict[str, Any]]:
                source = archive.extractfile(name)
                if source is None:
                    raise ValueError("RESULT_SCHEMA_INVALID")
                for raw in source:
                    if len(raw) > MAX_REQUEST_BUFFER_BYTES:
                        raise ValueError("RESULT_RECORD_TOO_LARGE")
                    if raw.strip():
                        value = json.loads(raw)
                        if not isinstance(value, dict):
                            raise ValueError("RESULT_SCHEMA_INVALID")
                        yield value

            runs = documents("runs.ndjson")
            objects = documents("objects.ndjson")
            measurements = documents("measurements.ndjson")
            for item in runs:
                external_id = str(item["id"])
                run = AnalysisRun(
                    delivery_id=delivery.id,
                    slide_id=delivery.slide_id,
                    external_id=external_id,
                    status=str(item.get("status", "complete")),
                    stale=bool(item.get("stale", False)),
                    provenance=dict(item.get("provenance", {})),
                )
                database.add(run)
                database.flush()
                run_ids[external_id] = run.id
            for object_count, item in enumerate(objects, start=1):
                if object_count > MAX_RESULT_OBJECTS:
                    raise ValueError("RESULT_OBJECT_LIMIT")
                external_id = str(item["id"])
                obj = PathObjectMetadata(
                    delivery_id=delivery.id,
                    slide_id=delivery.slide_id,
                    run_id=run_ids.get(str(item.get("runId", ""))),
                    external_id=external_id,
                    object_type=str(item["type"]),
                    parent_external_id=item.get("parentId") or None,
                    classification=item.get("classification") or None,
                    geometry=dict(item.get("geometry", {})),
                    style=dict(item.get("style", {})),
                    hidden=True,
                )
                database.add(obj)
                database.flush()
                object_ids[external_id] = obj.id
            for item in measurements:
                object_id = object_ids.get(str(item.get("objectId", "")))
                if object_id is None:
                    raise ValueError("RESULT_OBJECT_REFERENCE_INVALID")
                database.add(
                    PathObjectMeasurement(
                        object_id=object_id,
                        name=str(item["name"]),
                        value=float(item["value"]),
                        unit=str(item.get("unit", "")),
                    )
                )
            for member in members:
                if not member.isfile() or not member.name.startswith("attachments/"):
                    continue
                attachment_input = archive.extractfile(member)
                if attachment_input is None:
                    raise ValueError("RESULT_ATTACHMENT_INVALID")
                destination = storage.root / "results" / delivery.slide_id / Path(member.name).name
                destination.parent.mkdir(parents=True, exist_ok=True)
                partial = destination.with_suffix(destination.suffix + ".partial")
                digest_state = hashlib.sha256()
                member_bytes = 0
                with partial.open("wb") as output:
                    while block := attachment_input.read(MAX_REQUEST_BUFFER_BYTES):
                        member_bytes += len(block)
                        attachment_bytes += len(block)
                        if attachment_bytes > MAX_RESULT_MASK_BYTES:
                            raise ValueError("RESULT_MASK_LIMIT")
                        digest_state.update(block)
                        output.write(block)
                digest = digest_state.hexdigest()
                expected = Path(member.name).name.split(".", 1)[0].lower()
                if digest != expected:
                    partial.unlink(missing_ok=True)
                    raise ValueError("RESULT_ATTACHMENT_HASH_MISMATCH")
                os.replace(partial, destination)
                database.add(
                    ManagedResultAttachment(
                        delivery_id=delivery.id,
                        sha256=digest,
                        bytes=member_bytes,
                        storage_name=destination.name,
                    )
                )
        database.flush()
        for obj in database.scalars(
            select(PathObjectMetadata).where(PathObjectMetadata.delivery_id == delivery.id)
        ):
            obj.hidden = False
        delivery.status = "complete"
        delivery.error_code = None

    @app.post("/api/v1/desktop/pairings", status_code=status.HTTP_201_CREATED)
    def start_pairing(
        payload: PairingStartRequest,
        request: Request,
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        device_code = _token()
        device_secret = _token()
        code = _user_code()
        while (
            database.scalar(select(DesktopPairing.id).where(DesktopPairing.user_code == code))
            is not None
        ):
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
        verification_url = str(request.base_url).rstrip("/") + f"/admin/connect?code={code}"
        return {
            "pairingId": pairing.id,
            "deviceCode": device_code,
            "deviceSecret": device_secret,
            "userCode": code,
            "verificationUrl": verification_url,
            "verificationUrlComplete": verification_url,
            "pollIntervalSeconds": 5,
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
            select(DesktopPairing).where(DesktopPairing.user_code == payload.user_code.upper())
        )
        if (
            pairing is None
            or as_utc(pairing.expires_at) <= _now()
            or pairing.status != "pending"
        ):
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
            or not hmac.compare_digest(pairing.device_secret_hash, _hash(payload.device_secret))
            or as_utc(pairing.expires_at) <= _now()
        ):
            raise HTTPException(status_code=401, detail={"code": "PAIRING_INVALID"})
        if pairing.status == "pending":
            raise HTTPException(status_code=409, detail={"code": "PAIRING_PENDING"})
        if pairing.status != "approved" or pairing.user_id is None:
            raise HTTPException(status_code=409, detail={"code": "PAIRING_ALREADY_EXCHANGED"})
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
                    "jpegQuality": 75,
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
            "resultSchemas": ["pathlab-private-results/v1"],
            "maxResultBytes": MAX_RESULT_BYTES,
            "maxResultObjects": MAX_RESULT_OBJECTS,
            "maxMaskBytes": MAX_RESULT_MASK_BYTES,
        }

    @app.get("/api/v2/desktop/library/items")
    def desktop_library_items(
        limit: int = Query(default=48, ge=1, le=100),
        cursor_value: str = Query(default="", alias="cursor"),
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "library:read")
        statement = select(Slide).where(
            Slide.state.in_([SlideState.READY_PRIVATE, SlideState.PUBLISHED]),
            Slide.trashed_at.is_(None),
        )
        if cursor_value:
            try:
                cursor_time, cursor_id = decode_library_cursor(cursor_value)
            except ValueError as error:
                raise HTTPException(
                    status_code=400,
                    detail={"code": str(error)},
                ) from error
            statement = statement.where(
                (Slide.updated_at > cursor_time)
                | ((Slide.updated_at == cursor_time) & (Slide.id > cursor_id))
            )
        slides = list(
            database.scalars(statement.order_by(Slide.updated_at, Slide.id).limit(limit + 1))
        )
        page = slides[:limit]
        folders = list(
            database.scalars(
                select(Folder)
                .where(Folder.trashed_at.is_(None))
                .order_by(Folder.parent_id, Folder.sort_order, Folder.normalized_name)
                .limit(100)
            )
        )
        return {
            "schema": DESKTOP_SYNC_SCHEMA,
            "items": [remote_slide_json(slide) for slide in page],
            "folders": [remote_folder_json(folder) for folder in folders],
            "nextCursor": (
                encode_library_cursor(page[-1]) if len(slides) > limit and page else None
            ),
        }

    @app.get("/api/v2/desktop/library/changes")
    def desktop_library_changes(
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "library:read")
        events = list(
            database.scalars(
                select(DesktopSyncEvent)
                .where(DesktopSyncEvent.sequence > after)
                .order_by(DesktopSyncEvent.sequence)
                .limit(limit)
            )
        )
        return {
            "schema": DESKTOP_SYNC_SCHEMA,
            "changes": [change_json(event) for event in events],
            "nextCursor": str(events[-1].sequence if events else after),
        }

    def offline_slide(
        slide_id: str,
        authenticated: DesktopCredential,
        database: OrmSession,
    ) -> tuple[Slide, Path]:
        require_scope(authenticated, "slides:offline:read")
        slide = database.get(Slide, slide_id)
        if (
            slide is None
            or slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
            or slide.render_mode != "ome_dynamic"
            or slide.sha256 is None
        ):
            raise HTTPException(status_code=404, detail={"code": "OFFLINE_SLIDE_NOT_FOUND"})
        target = storage.for_slide(slide.id).original
        if not target.is_file() or target.stat().st_size != slide.source_bytes:
            raise HTTPException(status_code=409, detail={"code": "OFFLINE_CONTENT_UNAVAILABLE"})
        return slide, target

    def offline_headers(slide: Slide, length: int) -> dict[str, str]:
        return {
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "ETag": f'"{slide.sha256}"',
            "X-PathLab-SHA256": slide.sha256 or "",
            "Cache-Control": "private, no-store",
        }

    @app.head("/api/v2/desktop/slides/{slide_id}/content")
    def head_desktop_slide_content(
        slide_id: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        slide, _ = offline_slide(slide_id, authenticated, database)
        return Response(headers=offline_headers(slide, slide.source_bytes))

    @app.get("/api/v2/desktop/slides/{slide_id}/content")
    def get_desktop_slide_content(
        slide_id: str,
        range_value: str | None = Header(default=None, alias="Range"),
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        slide, target = offline_slide(slide_id, authenticated, database)
        start = 0
        status_code = status.HTTP_200_OK
        headers = offline_headers(slide, slide.source_bytes)
        if range_value:
            if (
                not range_value.startswith("bytes=")
                or "," in range_value
                or not range_value.removeprefix("bytes=").endswith("-")
            ):
                raise HTTPException(status_code=416, detail={"code": "RANGE_NOT_SATISFIABLE"})
            raw_start = range_value.removeprefix("bytes=")[:-1]
            if not raw_start.isdigit():
                raise HTTPException(status_code=416, detail={"code": "RANGE_NOT_SATISFIABLE"})
            start = int(raw_start)
            if start >= slide.source_bytes:
                raise HTTPException(status_code=416, detail={"code": "RANGE_NOT_SATISFIABLE"})
            status_code = status.HTTP_206_PARTIAL_CONTENT
            headers["Content-Length"] = str(slide.source_bytes - start)
            headers["Content-Range"] = (
                f"bytes {start}-{slide.source_bytes - 1}/{slide.source_bytes}"
            )

        def blocks() -> Iterator[bytes]:
            with target.open("rb") as source:
                source.seek(start)
                while block := source.read(MAX_REQUEST_BUFFER_BYTES):
                    yield block

        return StreamingResponse(
            blocks(),
            status_code=status_code,
            media_type="image/tiff",
            headers=headers,
        )

    @app.patch("/api/v2/desktop/slides/{slide_id}")
    def patch_desktop_slide(
        slide_id: str,
        payload: DesktopSlidePatch,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "library:sync")
        slide = database.get(Slide, slide_id)
        if slide is None or slide.trashed_at is not None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        if slide.state == SlideState.PUBLISHED:
            raise HTTPException(status_code=409, detail={"code": "SLIDE_PUBLIC"})
        current_revision = revision_for(slide.updated_at)
        if (
            payload.expected_metadata_revision != current_revision
            or payload.expected_folder_revision != current_revision
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DESKTOP_SYNC_CONFLICT",
                    "metadataRevision": current_revision,
                    "folderRevision": current_revision,
                },
            )
        if "folder_id" in payload.model_fields_set:
            if payload.folder_id is not None:
                folder = database.get(Folder, payload.folder_id)
                if folder is None or folder.trashed_at is not None:
                    raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
            slide.folder_id = payload.folder_id
        fields = {
            "display_name": payload.display_name,
            "description": payload.description,
            "case_id": payload.case_id,
            "organ_site": payload.organ_site,
            "stain": payload.stain,
            "diagnosis": payload.diagnosis,
            "course": payload.course,
            "tags": payload.tags,
            "teaching_note": payload.teaching_note,
            "admin_notes": payload.admin_notes,
        }
        for field, value in fields.items():
            if field in payload.model_fields_set:
                setattr(slide, field, value.strip() if isinstance(value, str) else value)
        if not slide.display_name:
            raise HTTPException(status_code=422, detail={"code": "DISPLAY_NAME_REQUIRED"})
        slide.updated_at = _now()
        database.flush()
        next_revision = revision_for(slide.updated_at)
        record_sync_event(database, "slide", slide.id, "upsert", next_revision)
        database.commit()
        database.refresh(slide)
        return remote_slide_json(slide)

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
        if (payload.derivative_bytes is None) != (payload.derivative_file_count is None):
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
            raise HTTPException(status_code=409, detail={"code": "OME_DYNAMIC_DISABLED"})
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
        if (
            ingest is None
            or ingest.credential_id != authenticated.id
            or ingest.status == "cancelled"
        ):
            raise HTTPException(status_code=404, detail={"code": "INGEST_NOT_FOUND"})
        response.headers["Upload-Offset"] = str(ingest.received_bytes)
        response.headers["Upload-Length"] = str(ingest.package_length)
        response.headers["Upload-Status"] = ingest.status

    @app.delete("/api/v2/desktop/ingests/{ingest_id}", status_code=status.HTTP_204_NO_CONTENT)
    def cancel_incomplete_ingest(
        ingest_id: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        require_scope(authenticated, "desktop:ingest")
        ingest = database.get(DesktopIngest, ingest_id)
        if ingest is None or ingest.credential_id != authenticated.id:
            raise HTTPException(status_code=404, detail={"code": "INGEST_NOT_FOUND"})
        if ingest.status != "uploading":
            raise HTTPException(status_code=409, detail={"code": "INGEST_NOT_CANCELLABLE"})
        target = upload_path(ingest)
        target.unlink(missing_ok=True)
        ingest.status = "cancelled"
        ingest.error_code = None
        database.commit()

    @app.post(
        "/api/v2/desktop/slides/{slide_id}/result-deliveries",
        status_code=status.HTTP_201_CREATED,
    )
    def create_result_delivery(
        slide_id: str,
        payload: ResultDeliveryRequest,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "results:sync")
        slide = database.get(Slide, slide_id)
        if (
            slide is None
            or slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
            or slide.sha256 != payload.slide_sha256.lower()
        ):
            raise HTTPException(status_code=409, detail={"code": "SLIDE_IDENTITY_MISMATCH"})
        existing = database.scalar(
            select(ResultDelivery).where(
                ResultDelivery.slide_id == slide_id,
                ResultDelivery.artifact_revision_id == payload.artifact_revision_id,
                ResultDelivery.payload_sha256 == payload.payload_sha256.lower(),
            )
        )
        if existing is not None:
            return result_json(existing)
        conflict = database.scalar(
            select(ResultDelivery.id).where(
                ResultDelivery.slide_id == slide_id,
                ResultDelivery.status == "complete",
            )
        )
        if conflict is not None:
            raise HTTPException(status_code=409, detail={"code": "RESULT_CONFLICT"})
        remote_edits = database.scalar(
            select(func.count(Annotation.id)).where(Annotation.slide_id == slide_id)
        )
        if remote_edits:
            raise HTTPException(status_code=409, detail={"code": "RESULT_CONFLICT"})
        delivery = ResultDelivery(
            credential_id=authenticated.id,
            slide_id=slide_id,
            artifact_revision_id=payload.artifact_revision_id,
            slide_sha256=payload.slide_sha256.lower(),
            payload_length=payload.payload_length,
            payload_sha256=payload.payload_sha256.lower(),
            schema=payload.result_schema,
            status="uploading",
        )
        database.add(delivery)
        database.commit()
        database.refresh(delivery)
        target = result_path(delivery.id)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.touch(exist_ok=False)
        return result_json(delivery)

    @app.head("/api/v2/desktop/slides/{slide_id}/result-deliveries/{delivery_id}/content")
    def result_delivery_offset(
        slide_id: str,
        delivery_id: str,
        response: Response,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        require_scope(authenticated, "results:sync")
        delivery = database.get(ResultDelivery, delivery_id)
        if (
            delivery is None
            or delivery.slide_id != slide_id
            or delivery.credential_id != authenticated.id
        ):
            raise HTTPException(status_code=404, detail={"code": "RESULT_DELIVERY_NOT_FOUND"})
        response.headers["Upload-Offset"] = str(delivery.received_bytes)
        response.headers["Upload-Length"] = str(delivery.payload_length)

    @app.patch(
        "/api/v2/desktop/slides/{slide_id}/result-deliveries/{delivery_id}/content",
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def upload_result_delivery(
        slide_id: str,
        delivery_id: str,
        request: Request,
        upload_offset: int = Header(alias="Upload-Offset", ge=0),
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "results:sync")
        delivery = database.get(ResultDelivery, delivery_id)
        if (
            delivery is None
            or delivery.slide_id != slide_id
            or delivery.credential_id != authenticated.id
        ):
            raise HTTPException(status_code=404, detail={"code": "RESULT_DELIVERY_NOT_FOUND"})
        if delivery.status != "uploading" or upload_offset != delivery.received_bytes:
            raise HTTPException(status_code=409, detail={"code": "UPLOAD_OFFSET_MISMATCH"})
        target = result_path(delivery.id)
        received = 0
        with target.open("r+b") as output:
            output.seek(upload_offset)
            async for block in request.stream():
                received += len(block)
                if (
                    received > MAX_DESKTOP_CHUNK_BYTES
                    or upload_offset + received > delivery.payload_length
                ):
                    output.truncate(upload_offset)
                    raise HTTPException(status_code=413, detail={"code": "RESULT_CHUNK_TOO_LARGE"})
                for start in range(0, len(block), MAX_REQUEST_BUFFER_BYTES):
                    output.write(block[start : start + MAX_REQUEST_BUFFER_BYTES])
            output.flush()
            os.fsync(output.fileno())
        delivery.received_bytes += received
        database.commit()
        if delivery.received_bytes == delivery.payload_length:
            try:
                apply_result_bundle(delivery, database)
                database.commit()
            except (ValueError, KeyError, OSError, json.JSONDecodeError, tarfile.TarError):
                database.rollback()
                shutil.rmtree(storage.root / "results" / slide_id, ignore_errors=True)
                failed = database.get(ResultDelivery, delivery_id)
                if failed is not None:
                    failed.status = "failed"
                    failed.error_code = "RESULT_BUNDLE_INVALID"
                    database.commit()
        database.refresh(delivery)
        return result_json(delivery)

    @app.get("/api/v2/desktop/slides/{slide_id}/result-deliveries/{delivery_id}")
    def result_delivery_status(
        slide_id: str,
        delivery_id: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_scope(authenticated, "results:sync")
        delivery = database.get(ResultDelivery, delivery_id)
        if (
            delivery is None
            or delivery.slide_id != slide_id
            or delivery.credential_id != authenticated.id
        ):
            raise HTTPException(status_code=404, detail={"code": "RESULT_DELIVERY_NOT_FOUND"})
        return result_json(delivery)

    @app.delete(
        "/api/v2/desktop/slides/{slide_id}/result-deliveries/{delivery_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def cancel_result_delivery(
        slide_id: str,
        delivery_id: str,
        authenticated: DesktopCredential = Depends(credential),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        require_scope(authenticated, "results:sync")
        delivery = database.get(ResultDelivery, delivery_id)
        if (
            delivery is None
            or delivery.slide_id != slide_id
            or delivery.credential_id != authenticated.id
        ):
            raise HTTPException(status_code=404, detail={"code": "RESULT_DELIVERY_NOT_FOUND"})
        if delivery.status == "complete":
            raise HTTPException(status_code=409, detail={"code": "RESULT_DELIVERY_NOT_CANCELLABLE"})
        result_path(delivery.id).unlink(missing_ok=True)
        database.delete(delivery)
        database.commit()

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
                    raise HTTPException(status_code=413, detail={"code": "DESKTOP_CHUNK_TOO_LARGE"})
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
            media_type="application/xml" if target.suffix.lower() == ".dzi" else "image/jpeg",
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
                select(func.count(Annotation.id)).where(Annotation.slide_id == slide.id)
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
            "nextOffset": offset + len(items) if offset + len(items) < total else None,
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
        candidate = (
            payload.model_copy(update={"base_version": slide.annotation_version})
            if merged
            else payload
        )
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

    @app.post(
        "/api/v1/admin/capacity-sentinels/{run_id}/desktop-cleanup",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def cleanup_capacity_desktop(
        run_id: str,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
        synthetic_run: str | None = Header(default=None, alias="X-PathLab-Synthetic-Run"),
    ) -> None:
        if re.fullmatch(r"[a-z0-9-]{1,64}", run_id) is None or synthetic_run != run_id:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_RUN_REQUIRED"})
        marker = f"capacity-{run_id}"
        device_name = f"Synthetic capacity {run_id}"
        database.execute(delete(DesktopIngest).where(DesktopIngest.artifact_revision_id == marker))
        now = _now()
        for item in database.scalars(
            select(DesktopCredential).where(DesktopCredential.device_name == device_name)
        ):
            item.revoked_at = now
        database.execute(delete(DesktopPairing).where(DesktopPairing.device_name == device_name))
        database.commit()

    return finalizer
