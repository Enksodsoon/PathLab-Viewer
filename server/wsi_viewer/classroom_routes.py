import asyncio
import hashlib
import hmac
import json
import re
import secrets
import threading
import unicodedata
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session as OrmSession
from starlette.concurrency import run_in_threadpool

from .classroom_hub import ClassroomHub
from .classroom_presenter import PresenterRuntime, PresenterSnapshot
from .classroom_prewarm import ClassroomPrewarmer, PrewarmSlide
from .config import Settings
from .domain import SlideState
from .models import (
    ClassroomParticipant,
    ClassroomQuestion,
    ClassroomQuestionReceipt,
    ClassroomSession,
    ClassroomSessionSlide,
    Folder,
    PublicationGrant,
    Session,
    Slide,
    User,
)
from .publication import INDIVIDUAL, delivery_version
from .storage import StorageLayout

PARTICIPANT_COOKIE = "pathlab_classroom_participant"
JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ALIAS_WORDS = ("MINT", "AMBER", "CORAL", "FERN", "IRIS", "JADE", "LILAC", "OAK")
ALIAS_COLLISION_RETRIES = 8
CLASSROOM_MUTATION_TIMEOUT_SECONDS = 1.0
CLASSROOM_RETRY_AFTER_SECONDS = "1"


class ClassroomMutationGate:
    def __init__(self, timeout_seconds: float = CLASSROOM_MUTATION_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds
        self.lock = threading.Lock()

    @contextmanager
    def acquire(self) -> Iterator[None]:
        acquired = self.lock.acquire(timeout=self.timeout_seconds)
        if not acquired:
            raise HTTPException(
                status_code=503,
                detail={"code": "CLASSROOM_BUSY"},
                headers={"Retry-After": CLASSROOM_RETRY_AFTER_SECONDS},
            )
        try:
            yield None
        finally:
            self.lock.release()

    def __call__(self) -> Iterator[None]:
        with self.acquire():
            yield None


class ClassroomRouteRuntime:
    def __init__(
        self,
        presenter: PresenterRuntime,
        prewarmer: ClassroomPrewarmer,
        restore_prewarm: Callable[[], None],
    ) -> None:
        self._presenter = presenter
        self._prewarmer = prewarmer
        self._restore_prewarm = restore_prewarm

    async def start(self) -> None:
        self._presenter.start()
        self._prewarmer.start()
        with suppress(Exception):
            await asyncio.to_thread(self._restore_prewarm)

    async def close(self) -> None:
        await self._presenter.close()
        await self._prewarmer.close()


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_ids: list[str] | None = Field(default=None, alias="slideIds", min_length=1, max_length=50)
    folder_id: str | None = Field(default=None, alias="folderId", min_length=1, max_length=36)
    review_expires_at: datetime | None = Field(default=None, alias="reviewExpiresAt")


class ReadinessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    folder_id: str = Field(alias="folderId", min_length=1, max_length=36)


class InviteUnlockRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    access_code: str = Field(alias="accessCode", min_length=6, max_length=16)
    display_name: str | None = Field(default=None, alias="displayName", max_length=80)


class LiveJoinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    csrf_token: str = Field(alias="csrfToken", min_length=20, max_length=200)


class JoinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    join_code: str = Field(alias="joinCode", min_length=6, max_length=16)
    display_name: str | None = Field(default=None, alias="displayName", max_length=80)


class QuestionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    idempotency_key: str = Field(alias="idempotencyKey", min_length=8, max_length=128)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    text: str = Field(min_length=1, max_length=500)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    zoom: float = Field(gt=0, le=1000)
    csrf_token: str = Field(alias="csrfToken", min_length=20, max_length=200)


class PinRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    zoom: float = Field(gt=0, le=1000)
    csrf_token: str = Field(alias="csrfToken", min_length=20, max_length=200)


class ParticipantMutationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    csrf_token: str = Field(alias="csrfToken", min_length=20, max_length=200)


class ControlRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    participant_id: str = Field(alias="participantId", min_length=1, max_length=36)
    seconds: int = Field(ge=15, le=600)


class PresenterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    csrf_token: str = Field(alias="csrfToken", min_length=20, max_length=200)
    lease_id: str = Field(alias="leaseId", min_length=20, max_length=128)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    zoom: float = Field(gt=0, le=1000)
    zoom_space: Literal["image", "viewport"] = Field(alias="zoomSpace", default="viewport")


class TeacherPresenterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    zoom: float = Field(gt=0, le=1000)
    zoom_space: Literal["image", "viewport"] = Field(alias="zoomSpace", default="viewport")


class TeacherPointerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    style: Literal["green-arrow", "red-arrow"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class TeachingPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class TeachingAnnotationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    annotation_id: str = Field(alias="id", min_length=8, max_length=64)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    tool: Literal["pen", "highlight", "line", "rectangle", "ellipse"]
    color: Literal["#ef765f", "#f6c84a", "#42b883", "#4f8be8", "#f6f2e8"]
    width: Literal[2, 4, 8]
    points: list[TeachingPoint] = Field(min_length=1, max_length=64)


class CapacitySafetyStopRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    stage_name: str = Field(alias="stageName", pattern=r"^breakpoint-(1750|2000)$")
    causes: list[Literal["cpu-sustained", "memory"]] = Field(min_length=1, max_length=2)


class SyntheticStageAckRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    stage_name: str = Field(alias="stageName", pattern=r"^[a-z0-9-]{1,64}$")
    shard_index: int = Field(alias="shardIndex", ge=0, le=5)


class SyntheticRecoveryReadyRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    epoch_ms: int = Field(alias="epochMs", ge=1, le=9_999_999_999_999)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _alias_candidate(secret_key: str, token: str, attempt: int) -> str:
    digest = hmac.new(
        secret_key.encode("utf-8"),
        f"classroom-alias:{token}:{attempt}".encode(),
        hashlib.sha256,
    ).digest()
    word = ALIAS_WORDS[digest[0] % len(ALIAS_WORDS)]
    number = int.from_bytes(digest[1:5], "big") % 100_000_000
    return f"{word}-{number:08d}"


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _display_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).strip()
    if not normalized:
        return None
    if any(unicodedata.category(character).startswith("C") for character in normalized):
        raise HTTPException(status_code=400, detail={"code": "DISPLAY_NAME_INVALID"})
    if len(normalized.encode("utf-8")) > 160:
        raise HTTPException(status_code=400, detail={"code": "DISPLAY_NAME_INVALID"})
    return normalized


def _session_slide_json(item: ClassroomSessionSlide) -> dict[str, Any]:
    return {
        "id": item.slide_id,
        "position": item.slide_position,
        "displayName": item.display_name,
        "assetVersion": item.asset_version,
        "tileSource": item.dzi_descriptor_path,
        "width": item.width,
        "height": item.height,
        "tileSize": item.tile_size,
        "format": item.tile_format,
        "folderPath": item.folder_path,
    }


def register_classroom_routes(
    app: FastAPI,
    *,
    settings: Settings,
    storage: StorageLayout,
    factory: Any,
    hub: ClassroomHub,
    database_dependency: Any,
    admin_dependency: Any,
    csrf_dependency: Any,
    pressure_metrics: dict[str, int | float],
) -> ClassroomRouteRuntime | None:
    if not settings.classroom_enabled:
        return None

    Database = Annotated[OrmSession, Depends(database_dependency)]
    AdminSession = Annotated[Session, Depends(admin_dependency)]
    CsrfSession = Annotated[Session, Depends(csrf_dependency)]
    mutation_gate = ClassroomMutationGate()
    join_queue_lock = asyncio.Lock()

    def persist_presenters(
        snapshots: Sequence[PresenterSnapshot],
    ) -> None:
        with mutation_gate.lock, factory() as database:
            for snapshot in snapshots:
                classroom = database.get(ClassroomSession, snapshot.session_id)
                if classroom is None or classroom.status != "active" or classroom.phase != "live":
                    continue
                if snapshot.sequence < classroom.presenter_sequence:
                    continue
                classroom.presenter_sequence = snapshot.sequence
                classroom.current_slide_id = snapshot.slide_id
                classroom.presenter_viewport = snapshot.viewport
            database.commit()

    def reserve_presenter_sequence(session_id: str, reserved_until: int) -> int:
        # update() is called only inside a serialized presenter mutation.
        with factory() as database:
            classroom = database.get(ClassroomSession, session_id)
            if classroom is None or classroom.status != "active" or classroom.phase != "live":
                raise RuntimeError("Cannot reserve a sequence for an inactive classroom")
            if classroom.presenter_sequence_reserved < reserved_until:
                classroom.presenter_sequence_reserved = reserved_until
                database.commit()
            return int(classroom.presenter_sequence_reserved)

    presenter_runtime = PresenterRuntime(
        persist_presenters,
        reserve=reserve_presenter_sequence,
    )
    prewarmer = ClassroomPrewarmer()

    MutationGuard = Annotated[None, Depends(mutation_gate)]
    serializer = URLSafeSerializer(settings.secret_key, salt="pathlab-classroom-participant-v1")
    unlock_attempts: dict[str, list[datetime]] = {}

    def allocate_alias(session_id: str, token: str, db: OrmSession) -> str:
        for attempt in range(ALIAS_COLLISION_RETRIES):
            candidate = _alias_candidate(settings.secret_key, token, attempt)
            collision = db.scalar(
                select(ClassroomParticipant.id)
                .where(
                    ClassroomParticipant.session_id == session_id,
                    ClassroomParticipant.public_alias == candidate,
                )
                .limit(1)
            )
            if collision is None:
                return candidate
        raise HTTPException(
            status_code=503,
            detail={"code": "CLASSROOM_BUSY"},
            headers={"Retry-After": CLASSROOM_RETRY_AFTER_SECONDS},
        )

    def participant_json(
        participant: ClassroomParticipant,
        presence: str,
        control_requests: dict[str, float],
    ) -> dict[str, Any]:
        return {
            "id": participant.id,
            "alias": participant.public_alias,
            "displayName": participant.optional_display_name,
            "controlRequested": participant.id in control_requests,
            "controlRequestedAt": control_requests.get(participant.id),
            "status": presence,
        }

    def access_code(public_id: str, generation: int) -> str:
        digest = hmac.new(
            settings.secret_key.encode("utf-8"),
            f"classroom:{public_id}:{generation}".encode(),
            hashlib.sha256,
        ).digest()
        return "".join(JOIN_ALPHABET[value % len(JOIN_ALPHABET)] for value in digest[:10])

    def static_descriptor(slide: Slide, version: str) -> tuple[int, int, int, str]:
        root = storage.individual_delivery_for(slide.public_id, version)
        descriptor = root / "slide.dzi"
        tile_root = root / "slide_files"
        try:
            if descriptor.stat().st_size > 64 * 1024 or not tile_root.is_dir():
                raise ValueError
            image = ElementTree.fromstring(descriptor.read_bytes())
            size = next(child for child in image if child.tag.rsplit("}", 1)[-1] == "Size")
            width = int(size.attrib["Width"])
            height = int(size.attrib["Height"])
            tile_size = int(image.attrib["TileSize"])
            tile_format = image.attrib["Format"].lower()
        except (OSError, ValueError, KeyError, StopIteration, ElementTree.ParseError) as error:
            raise HTTPException(
                status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"}
            ) from error
        if width <= 0 or height <= 0 or tile_size <= 0 or tile_format not in {"jpg", "jpeg"}:
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"})
        return width, height, tile_size, tile_format

    def slide_readiness(
        slide: Slide, db: OrmSession
    ) -> tuple[str | None, tuple[int, int, int, str] | None]:
        metadata = slide.slide_metadata or {}
        width = metadata.get("width")
        height = metadata.get("height")
        grant = db.scalar(
            select(PublicationGrant.id).where(
                PublicationGrant.slide_id == slide.id,
                PublicationGrant.source_type == INDIVIDUAL,
                PublicationGrant.source_id == slide.id,
            )
        )
        if (
            slide.state != SlideState.PUBLISHED
            or slide.privacy_status != "passed"
            or slide.render_mode != "static_dzi"
            or not slide.sha256
            or grant is None
        ):
            return "publication_incomplete", None
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            return "metadata_invalid", None
        if slide.derivative_file_count <= 0:
            return "delivery_missing", None
        version = delivery_version(slide)
        try:
            descriptor = static_descriptor(slide, version)
        except HTTPException:
            return "delivery_missing", None
        if descriptor[0] != width or descriptor[1] != height:
            return "metadata_invalid", None
        return None, descriptor

    def request_prewarm(session_id: str, slide_id: str, db: OrmSession) -> None:
        current = db.scalar(
            select(ClassroomSessionSlide).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == slide_id,
            )
        )
        if current is None:
            return
        window = list(
            db.scalars(
                select(ClassroomSessionSlide)
                .where(
                    ClassroomSessionSlide.session_id == session_id,
                    ClassroomSessionSlide.slide_position >= current.slide_position,
                )
                .order_by(ClassroomSessionSlide.slide_position)
                .limit(2)
            )
        )
        slides: list[PrewarmSlide] = []
        for item in window:
            slide = db.get(Slide, item.slide_id)
            if slide is None:
                continue
            slides.append(
                PrewarmSlide(
                    root=storage.individual_delivery_for(slide.public_id, item.asset_version),
                    width=item.width,
                    height=item.height,
                    tile_size=item.tile_size,
                    tile_format=item.tile_format,
                    poster_filename=slide.thumbnail_filename or "thumbnail.jpg",
                )
            )
        prewarmer.request(slides)

    def restore_prewarm() -> None:
        with factory() as database:
            classroom = database.scalar(
                select(ClassroomSession).where(ClassroomSession.status == "active")
            )
            if classroom is None:
                return
            participant_ids = list(
                database.scalars(
                    select(ClassroomParticipant.id).where(
                        ClassroomParticipant.session_id == classroom.id,
                        ClassroomParticipant.joined_live_at.is_not(None),
                    )
                )
            )
            hub.restore_participants(classroom.id, participant_ids)
            if classroom.current_slide_id is not None:
                request_prewarm(classroom.id, classroom.current_slide_id, database)

    def folder_slide_ids(folder_id: str, db: OrmSession) -> list[str]:
        folders = list(db.scalars(select(Folder).where(Folder.trashed_at.is_(None))))
        descendants = {folder_id}
        changed = True
        while changed:
            changed = False
            for folder in folders:
                if folder.parent_id in descendants and folder.id not in descendants:
                    descendants.add(folder.id)
                    changed = True
        return list(
            db.scalars(
                select(Slide.id)
                .where(Slide.folder_id.in_(descendants), Slide.trashed_at.is_(None))
                .order_by(Slide.created_at, Slide.id)
            )
        )

    def readiness_snapshot(folder_id: str, db: OrmSession) -> dict[str, Any]:
        folder = db.get(Folder, folder_id)
        if folder is None or folder.trashed_at is not None:
            raise HTTPException(status_code=404, detail={"code": "FOLDER_NOT_FOUND"})
        ready: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for slide_id in folder_slide_ids(folder_id, db):
            slide = db.get(Slide, slide_id)
            if slide is None:
                continue
            reason, _descriptor = slide_readiness(slide, db)
            item = {
                "id": slide.id,
                "displayName": slide.display_name,
                "folderPath": slide_folder_path(slide, db),
            }
            if reason:
                blocked.append({**item, "reason": reason})
            else:
                ready.append(item)
        return {"folderId": folder_id, "ready": ready, "blocked": blocked}

    def slide_folder_path(slide: Slide, db: OrmSession) -> list[str]:
        path: list[str] = []
        folder_id = slide.folder_id
        seen: set[str] = set()
        while folder_id and folder_id not in seen and len(path) < 20:
            seen.add(folder_id)
            folder = db.get(Folder, folder_id)
            if folder is None or folder.trashed_at is not None:
                break
            path.append(folder.name)
            folder_id = folder.parent_id
        path.reverse()
        return path

    def admin_from_request(request: Request) -> None:
        token = request.cookies.get("pathlab_session")
        if not token:
            raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
        with factory() as db:
            stored = db.get(Session, _hash(token))
            if stored is None or stored.expires_at < _now():
                raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})
            user = db.get(User, stored.user_id)
            if user is None or stored.credential_generation != user.credential_generation:
                raise HTTPException(status_code=401, detail={"code": "SESSION_EXPIRED"})

    def participant_from_request(
        request: Request, db: OrmSession, session_id: str
    ) -> tuple[ClassroomParticipant, str]:
        signed = request.cookies.get(PARTICIPANT_COOKIE)
        try:
            claims = serializer.loads(signed or "")
        except BadSignature as error:
            raise HTTPException(status_code=401, detail={"code": "PARTICIPANT_REQUIRED"}) from error
        if not isinstance(claims, dict) or claims.get("sessionId") != session_id:
            raise HTTPException(status_code=401, detail={"code": "PARTICIPANT_REQUIRED"})
        participant = db.get(ClassroomParticipant, claims.get("participantId"))
        raw_token = claims.get("token")
        if (
            participant is None
            or not isinstance(raw_token, str)
            or participant.session_id != session_id
            or not secrets.compare_digest(participant.token_hash, _hash(raw_token))
        ):
            raise HTTPException(status_code=401, detail={"code": "PARTICIPANT_REQUIRED"})
        return participant, raw_token

    def live_participant_from_request(
        request: Request, db: OrmSession, session_id: str
    ) -> tuple[ClassroomParticipant, str]:
        participant, raw_token = participant_from_request(request, db, session_id)
        if participant.joined_live_at is None:
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_JOIN_REQUIRED"})
        return participant, raw_token

    def require_live_classroom(
        session_id: str,
        db: OrmSession,
        *,
        code: str = "CLASSROOM_NOT_LIVE",
        status_code: int = 409,
    ) -> ClassroomSession:
        classroom = db.get(ClassroomSession, session_id)
        deadline = classroom.live_expires_at or classroom.expires_at if classroom else None
        if (
            classroom is None
            or classroom.status != "active"
            or classroom.phase != "live"
            or deadline is None
            or deadline <= _now()
        ):
            raise HTTPException(status_code=status_code, detail={"code": code})
        return classroom

    def expire_control(classroom: ClassroomSession, db: OrmSession) -> None:
        if (
            classroom.controller_participant_id is None
            or classroom.controller_expires_at is None
            or classroom.controller_expires_at > _now()
        ):
            return
        classroom.control_epoch += 1
        classroom.state_version += 1
        classroom.controller_participant_id = None
        classroom.controller_lease_id = None
        classroom.controller_expires_at = None
        db.commit()
        hub.publish(
            classroom.id,
            "control",
            {
                "stateVersion": classroom.state_version,
                "participantId": None,
                "leaseId": None,
                "controlEpoch": classroom.control_epoch,
                "expiresAt": None,
            },
            critical=True,
        )

    def presenter_json(classroom: ClassroomSession) -> dict[str, Any]:
        current = presenter_runtime.current(classroom.id)
        if current is None:
            return {
                "sequence": classroom.presenter_sequence,
                "slideId": classroom.current_slide_id,
                "viewport": classroom.presenter_viewport,
            }
        return {
            "sequence": current.sequence,
            "slideId": current.slide_id,
            "viewport": current.viewport,
        }

    @app.post("/api/v1/admin/classroom/readiness")
    def classroom_readiness(
        payload: ReadinessRequest, _: AdminSession, db: Database
    ) -> dict[str, Any]:
        return readiness_snapshot(payload.folder_id, db)

    @app.post(
        "/api/v1/admin/classroom/sessions",
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(
        payload: CreateSessionRequest,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
        synthetic_run: Annotated[str | None, Header(alias="X-PathLab-Synthetic-Run")] = None,
    ) -> dict[str, Any]:
        if synthetic_run is not None and re.fullmatch(r"[a-z0-9-]{1,64}", synthetic_run) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_RUN_INVALID"})
        now = _now()
        expired = list(
            db.scalars(
                select(ClassroomSession).where(
                    ClassroomSession.status == "active",
                    ClassroomSession.expires_at <= now,
                )
            )
        )
        for stale in expired:
            if (
                stale.public_id is not None
                and stale.review_expires_at is not None
                and stale.review_expires_at > now
            ):
                stale.phase = "review"
                stale.status = "ended"
                stale.ended_at = now
                stale.expires_at = stale.review_expires_at
                stale.state_version += 1
            else:
                db.delete(stale)
        if expired:
            db.commit()
        active = db.scalar(select(ClassroomSession).where(ClassroomSession.status == "active"))
        if active is not None:
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_ALREADY_ACTIVE"})
        is_smart_invite = payload.folder_id is not None
        if is_smart_invite:
            if payload.slide_ids is not None or payload.review_expires_at is None:
                raise HTTPException(status_code=422, detail={"code": "CLASSROOM_REQUEST_INVALID"})
            review_expires_at = payload.review_expires_at.replace(tzinfo=None)
            if review_expires_at < now + timedelta(hours=1) or review_expires_at > now + timedelta(
                days=30
            ):
                raise HTTPException(status_code=422, detail={"code": "CLASSROOM_EXPIRY_INVALID"})
            readiness = readiness_snapshot(payload.folder_id or "", db)
            if readiness["blocked"]:
                raise HTTPException(
                    status_code=409,
                    detail={"code": "CLASSROOM_SLIDES_BLOCKED", "blocked": readiness["blocked"]},
                )
            slide_ids = [item["id"] for item in readiness["ready"]]
            if not slide_ids:
                raise HTTPException(status_code=409, detail={"code": "CLASSROOM_EMPTY"})
        else:
            slide_ids = payload.slide_ids or []
            review_expires_at = None
            if not slide_ids:
                raise HTTPException(status_code=422, detail={"code": "CLASSROOM_REQUEST_INVALID"})
        slides = list(db.scalars(select(Slide).where(Slide.id.in_(slide_ids))))
        slides_by_id = {slide.id: slide for slide in slides}
        if len(slides_by_id) != len(set(slide_ids)):
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"})
        public_id = secrets.token_urlsafe(24) if is_smart_invite else None
        join_code = (
            access_code(public_id, 1)
            if public_id
            else "".join(secrets.choice(JOIN_ALPHABET) for _ in range(10))
        )
        classroom = ClassroomSession(
            join_code_hash=_hash(join_code),
            synthetic_run_id=synthetic_run,
            public_id=public_id,
            phase="preview" if is_smart_invite else "live",
            folder_id=payload.folder_id,
            review_expires_at=review_expires_at,
            expires_at=review_expires_at or (now + timedelta(hours=8)),
            live_expires_at=None if is_smart_invite else now + timedelta(hours=8),
            started_at=None if is_smart_invite else now,
            current_slide_id=slide_ids[0],
        )
        db.add(classroom)
        db.flush()
        snapshot: list[ClassroomSessionSlide] = []
        for position, slide_id in enumerate(slide_ids):
            slide = slides_by_id[slide_id]
            reason, descriptor = slide_readiness(slide, db)
            if reason or descriptor is None:
                raise HTTPException(status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"})
            version = delivery_version(slide)
            width, height, tile_size, tile_format = descriptor
            item = ClassroomSessionSlide(
                session_id=classroom.id,
                slide_id=slide.id,
                slide_position=position,
                published_asset_id=_hash(f"{slide.id}:{version}"),
                asset_version=version,
                dzi_descriptor_path=f"/tiles/{slide.public_id}/{version}/slide.dzi",
                width=width,
                height=height,
                tile_size=tile_size,
                tile_format=tile_format,
                display_name=slide.display_name,
                folder_path=slide_folder_path(slide, db),
            )
            db.add(item)
            snapshot.append(item)
        db.commit()
        request_prewarm(classroom.id, classroom.current_slide_id or slide_ids[0], db)
        return {
            "id": classroom.id,
            "syntheticRunId": classroom.synthetic_run_id,
            "joinCode": join_code,
            "publicId": classroom.public_id,
            "phase": classroom.phase,
            "reviewExpiresAt": classroom.review_expires_at.isoformat()
            if classroom.review_expires_at
            else None,
            "stateVersion": classroom.state_version,
            "slides": [_session_slide_json(item) for item in snapshot],
        }

    @app.post("/api/v1/admin/classroom/sessions/{session_id}/start")
    def start_session(
        session_id: str, _: CsrfSession, _guard: MutationGuard, db: Database
    ) -> dict[str, Any]:
        classroom = db.get(ClassroomSession, session_id)
        if (
            classroom is None
            or classroom.phase != "preview"
            or classroom.review_expires_at is None
            or classroom.review_expires_at <= _now()
        ):
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_TRANSITION_INVALID"})
        classroom.phase = "live"
        classroom.started_at = _now()
        classroom.live_expires_at = _now() + timedelta(hours=8)
        classroom.expires_at = min(classroom.review_expires_at, classroom.live_expires_at)
        classroom.state_version += 1
        db.commit()
        if classroom.current_slide_id is not None:
            request_prewarm(classroom.id, classroom.current_slide_id, db)
        return {
            "id": classroom.id,
            "phase": classroom.phase,
            "liveExpiresAt": classroom.live_expires_at.isoformat(),
        }

    @app.post("/api/v1/admin/classroom/sessions/{session_id}/end", status_code=204)
    def end_live_session(
        session_id: str, _: CsrfSession, _guard: MutationGuard, db: Database
    ) -> None:
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.phase != "live":
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_TRANSITION_INVALID"})
        classroom.phase = "review"
        classroom.status = "ended"
        classroom.expires_at = classroom.review_expires_at or _now()
        classroom.ended_at = _now()
        classroom.state_version += 1
        db.commit()
        presenter_runtime.forget(session_id)
        prewarmer.clear()
        hub.terminate_session(session_id, state_version=classroom.state_version)

    @app.delete(
        "/api/v1/admin/classroom/sessions/active",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def end_active_session(_: CsrfSession, _guard: MutationGuard, db: Database) -> None:
        classroom = db.scalar(select(ClassroomSession).where(ClassroomSession.status == "active"))
        if classroom is None:
            return
        session_id = classroom.id
        next_state_version = classroom.state_version + 1
        classroom.status = "ended"
        classroom.phase = "revoked"
        classroom.ended_at = _now()
        classroom.state_version = next_state_version
        db.commit()
        presenter_runtime.forget(session_id)
        prewarmer.clear()
        hub.terminate_session(session_id, state_version=next_state_version)

    def reserve_live_seats(
        session_id: str, db: OrmSession
    ) -> tuple[dict[str, ClassroomParticipant], set[str], int]:
        cutoff = _now() - timedelta(minutes=15)
        participants = list(
            db.scalars(
                select(ClassroomParticipant).where(
                    ClassroomParticipant.session_id == session_id,
                    ClassroomParticipant.joined_live_at.is_not(None),
                )
            )
        )
        participants_by_id = {item.id: item for item in participants}
        stale_participant_ids, active_count = hub.reserve_stale_participants(
            session_id,
            {item.id: item.last_seen_at >= cutoff for item in participants},
        )
        return participants_by_id, stale_participant_ids, active_count

    def join_locked(
        payload: JoinRequest,
        request: Request,
        response: Response,
        db: OrmSession,
    ) -> Any:
        classroom = db.scalar(
            select(ClassroomSession).where(
                ClassroomSession.join_code_hash == _hash(payload.join_code.strip().upper()),
                ClassroomSession.status == "active",
                ClassroomSession.phase == "live",
                ClassroomSession.expires_at > _now(),
            )
        )
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
        expire_control(classroom, db)
        signed = request.cookies.get(PARTICIPANT_COOKIE)
        if signed:
            try:
                claims = serializer.loads(signed)
            except BadSignature:
                claims = None
            if isinstance(claims, dict) and claims.get("sessionId") == classroom.id:
                participant = db.get(ClassroomParticipant, claims.get("participantId"))
                token = claims.get("token")
                if (
                    participant is not None
                    and isinstance(token, str)
                    and secrets.compare_digest(participant.token_hash, _hash(token))
                ):
                    participant.last_seen_at = _now()
                    db.commit()
                    hub.participant_activity(classroom.id, participant.id)
                    hub.mark_roster_changed(classroom.id)
                    return _participant_response(
                        participant,
                        token,
                        classroom.id,
                        response,
                        serializer,
                        settings.secure_cookies,
                        200,
                    )

        participants_by_id, stale_participant_ids, active_count = reserve_live_seats(
            classroom.id, db
        )
        if active_count >= settings.classroom_max_participants:
            hub.cancel_stale_reservations(classroom.id, stale_participant_ids)
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_FULL"})
        try:
            for stale_participant_id in stale_participant_ids:
                db.delete(participants_by_id[stale_participant_id])
            if stale_participant_ids:
                db.flush()
            token = secrets.token_urlsafe(32)
            alias = allocate_alias(classroom.id, token, db)
            participant = ClassroomParticipant(
                session_id=classroom.id,
                token_hash=_hash(token),
                public_alias=alias,
                optional_display_name=_display_name(payload.display_name),
                joined_live_at=_now(),
                disconnected_at=_now(),
            )
            db.add(participant)
            classroom.state_version += 1
            db.commit()
        except Exception:
            hub.cancel_stale_reservations(classroom.id, stale_participant_ids)
            raise
        hub.complete_stale_reservations(classroom.id, stale_participant_ids)
        hub.participant_activity(classroom.id, participant.id)
        hub.mark_roster_changed(classroom.id)
        response.status_code = status.HTTP_201_CREATED
        return _participant_response(
            participant,
            token,
            classroom.id,
            response,
            serializer,
            settings.secure_cookies,
            201,
        )

    def execute_join(
        payload: JoinRequest,
        request: Request,
        response: Response,
    ) -> Any:
        with mutation_gate.acquire(), factory() as db:
            return join_locked(payload, request, response, db)

    @app.post("/api/v1/classroom/join")
    async def join(
        payload: JoinRequest,
        request: Request,
        response: Response,
    ) -> Any:
        try:
            await asyncio.wait_for(join_queue_lock.acquire(), timeout=mutation_gate.timeout_seconds)
        except TimeoutError as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "CLASSROOM_BUSY"},
                headers={"Retry-After": CLASSROOM_RETRY_AFTER_SECONDS},
            ) from error
        try:
            return await run_in_threadpool(execute_join, payload, request, response)
        finally:
            join_queue_lock.release()

    def invite_classroom(public_id: str, db: OrmSession) -> ClassroomSession:
        classroom = db.scalar(
            select(ClassroomSession).where(ClassroomSession.public_id == public_id)
        )
        if (
            classroom is not None
            and classroom.phase == "live"
            and classroom.live_expires_at is not None
            and classroom.live_expires_at <= _now()
            and classroom.review_expires_at is not None
            and classroom.review_expires_at > _now()
        ):
            classroom.phase = "review"
            classroom.status = "ended"
            classroom.ended_at = _now()
            classroom.expires_at = classroom.review_expires_at
            classroom.state_version += 1
            db.commit()
            presenter_runtime.forget(classroom.id)
            prewarmer.clear()
            hub.terminate_session(classroom.id, state_version=classroom.state_version)
        if (
            classroom is None
            or classroom.phase == "revoked"
            or classroom.review_expires_at is None
            or classroom.review_expires_at <= _now()
        ):
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_INVITE_UNAVAILABLE"})
        return classroom

    @app.post("/api/v1/classroom/invites/{public_id}/unlock")
    def unlock_invite(
        public_id: str,
        payload: InviteUnlockRequest,
        request: Request,
        response: Response,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, Any]:
        key = f"{request.client.host if request.client else 'unknown'}:{public_id}"
        cutoff = _now() - timedelta(minutes=5)
        attempts = [attempt for attempt in unlock_attempts.get(key, []) if attempt >= cutoff]
        if len(attempts) >= 8:
            raise HTTPException(status_code=429, detail={"code": "CLASSROOM_INVITE_UNAVAILABLE"})
        classroom = invite_classroom(public_id, db)
        review_expires_at = classroom.review_expires_at
        assert review_expires_at is not None
        candidate = payload.access_code.strip().upper()
        if not secrets.compare_digest(classroom.join_code_hash, _hash(candidate)):
            attempts.append(_now())
            unlock_attempts[key] = attempts
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_INVITE_UNAVAILABLE"})
        unlock_attempts.pop(key, None)
        signed = request.cookies.get(PARTICIPANT_COOKIE)
        if signed:
            try:
                claims = serializer.loads(signed)
            except BadSignature:
                claims = None
            if isinstance(claims, dict) and claims.get("sessionId") == classroom.id:
                participant = db.get(ClassroomParticipant, claims.get("participantId"))
                token = claims.get("token")
                if (
                    participant is not None
                    and isinstance(token, str)
                    and secrets.compare_digest(participant.token_hash, _hash(token))
                ):
                    return _participant_response(
                        participant,
                        token,
                        classroom.id,
                        response,
                        serializer,
                        settings.secure_cookies,
                        200,
                        max_age_seconds=max(1, int((review_expires_at - _now()).total_seconds())),
                    )
        token = secrets.token_urlsafe(32)
        alias = allocate_alias(classroom.id, token, db)
        participant = ClassroomParticipant(
            session_id=classroom.id,
            token_hash=_hash(token),
            public_alias=alias,
            optional_display_name=_display_name(payload.display_name),
            disconnected_at=_now(),
        )
        db.add(participant)
        db.commit()
        result = _participant_response(
            participant,
            token,
            classroom.id,
            response,
            serializer,
            settings.secure_cookies,
            201,
            max_age_seconds=max(1, int((review_expires_at - _now()).total_seconds())),
        )
        return {**result, "publicId": public_id, "phase": classroom.phase}

    @app.get("/api/v1/classroom/invites/{public_id}")
    def invite_state(public_id: str, request: Request, db: Database) -> dict[str, Any]:
        classroom = invite_classroom(public_id, db)
        review_expires_at = classroom.review_expires_at
        assert review_expires_at is not None
        participant, raw_token = participant_from_request(request, db, classroom.id)
        slides = list(
            db.scalars(
                select(ClassroomSessionSlide)
                .where(ClassroomSessionSlide.session_id == classroom.id)
                .order_by(ClassroomSessionSlide.slide_position)
            )
        )
        return {
            "sessionId": classroom.id,
            "publicId": public_id,
            "phase": classroom.phase,
            "reviewExpiresAt": review_expires_at.isoformat(),
            "participant": {"id": participant.id, "alias": participant.public_alias},
            "csrfToken": raw_token,
            "slides": [_session_slide_json(item) for item in slides],
        }

    @app.get("/api/v1/classroom/invites/{public_id}/phase")
    def invite_phase(public_id: str, request: Request, db: Database) -> dict[str, Any]:
        classroom = invite_classroom(public_id, db)
        review_expires_at = classroom.review_expires_at
        assert review_expires_at is not None
        participant_from_request(request, db, classroom.id)
        return {
            "sessionId": classroom.id,
            "phase": classroom.phase,
            "reviewExpiresAt": review_expires_at.isoformat(),
        }

    @app.post("/api/v1/classroom/sessions/{session_id}/live-join")
    def join_live(
        session_id: str,
        payload: LiveJoinRequest,
        request: Request,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, Any]:
        participant, raw_token = participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        classroom = require_live_classroom(session_id, db)
        if participant.joined_live_at is None:
            participants_by_id, stale_participant_ids, live_count = reserve_live_seats(
                session_id, db
            )
            if live_count >= settings.classroom_max_participants:
                hub.cancel_stale_reservations(session_id, stale_participant_ids)
                raise HTTPException(status_code=409, detail={"code": "CLASSROOM_FULL"})
            try:
                for stale_participant_id in stale_participant_ids:
                    db.delete(participants_by_id[stale_participant_id])
                if stale_participant_ids:
                    db.flush()
                participant.joined_live_at = _now()
                classroom.state_version += 1
                db.commit()
            except Exception:
                hub.cancel_stale_reservations(session_id, stale_participant_ids)
                raise
            hub.complete_stale_reservations(session_id, stale_participant_ids)
            hub.participant_activity(classroom.id, participant.id)
            hub.mark_roster_changed(classroom.id)
        return {"sessionId": session_id, "phase": classroom.phase}

    @app.get("/api/v1/admin/classroom/sessions/{session_id}")
    def teacher_state(
        session_id: str, _: AdminSession, _guard: MutationGuard, db: Database
    ) -> dict[str, Any]:
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
        participants = list(
            db.scalars(
                select(ClassroomParticipant)
                .where(
                    ClassroomParticipant.session_id == session_id,
                    ClassroomParticipant.joined_live_at.is_not(None),
                )
                .order_by(ClassroomParticipant.created_at)
                .limit(300)
            )
        )
        participant_count = int(
            db.scalar(
                select(func.count())
                .select_from(ClassroomParticipant)
                .where(
                    ClassroomParticipant.session_id == session_id,
                    ClassroomParticipant.joined_live_at.is_not(None),
                )
            )
            or 0
        )
        questions = list(
            db.scalars(
                select(ClassroomQuestion)
                .where(ClassroomQuestion.session_id == session_id)
                .order_by(ClassroomQuestion.created_at)
                .limit(200)
            )
        )
        participants_by_id = {item.id: item for item in participants}
        presence_by_id, roster_version = hub.participant_roster_snapshot(
            session_id, [item.id for item in participants]
        )
        control_requests = hub.control_requests(session_id)
        return {
            "session": {
                "id": classroom.id,
                "status": classroom.status,
                "phase": classroom.phase,
                "publicId": classroom.public_id,
                "syntheticRunId": classroom.synthetic_run_id,
                "joinCode": access_code(classroom.public_id, classroom.code_generation)
                if classroom.public_id
                else None,
                "reviewExpiresAt": classroom.review_expires_at.isoformat()
                if classroom.review_expires_at
                else None,
            },
            "stateVersion": classroom.state_version,
            "participantCount": participant_count,
            "rosterVersion": roster_version,
            "presenter": presenter_json(classroom),
            "controller": {
                "participantId": classroom.controller_participant_id,
                "leaseId": classroom.controller_lease_id,
                "controlEpoch": classroom.control_epoch,
                "expiresAt": (
                    classroom.controller_expires_at.isoformat()
                    if classroom.controller_expires_at
                    else None
                ),
            },
            "participants": [
                participant_json(item, presence_by_id[item.id], control_requests)
                for item in participants
            ],
            "pendingQuestions": [
                {
                    "id": item.id,
                    "participantId": item.participant_id,
                    "slideId": item.slide_id,
                    "text": item.text,
                    "x": item.x,
                    "y": item.y,
                    "zoom": item.zoom,
                }
                for item in questions
            ],
            "activePins": [
                {
                    **pin,
                    "alias": participants_by_id[pin["participantId"]].public_alias,
                }
                for pin in hub.active_pins(session_id)
                if pin.get("participantId") in participants_by_id
            ],
            "teacherPointer": hub.teacher_pointer(session_id),
            "teachingAnnotations": hub.teaching_annotations(session_id),
        }

    @app.get("/api/v1/admin/classroom/sessions/{session_id}/participants")
    def teacher_participants(
        session_id: str,
        _: AdminSession,
        _guard: MutationGuard,
        db: Database,
        after: Annotated[str | None, Query(max_length=16)] = None,
        limit: Annotated[int, Query(ge=1, le=100)] = 100,
        q: Annotated[str | None, Query(max_length=80)] = None,
        requested: bool = False,
    ) -> dict[str, Any]:
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})

        filters: list[Any] = [
            ClassroomParticipant.session_id == session_id,
            ClassroomParticipant.joined_live_at.is_not(None),
        ]
        control_requests = hub.control_requests(session_id)
        if requested:
            filters.append(ClassroomParticipant.id.in_(tuple(control_requests)))
        normalized_q = unicodedata.normalize("NFKC", q or "").strip().casefold()
        if normalized_q:
            filters.append(
                or_(
                    func.lower(ClassroomParticipant.public_alias).contains(
                        normalized_q, autoescape=True
                    ),
                    func.lower(
                        func.coalesce(ClassroomParticipant.optional_display_name, "")
                    ).contains(normalized_q, autoescape=True),
                )
            )
        total = int(
            db.scalar(select(func.count()).select_from(ClassroomParticipant).where(*filters)) or 0
        )
        page_filters = list(filters)
        cursor = (after or "").strip().upper()
        if cursor:
            page_filters.append(ClassroomParticipant.public_alias > cursor)
        participants = list(
            db.scalars(
                select(ClassroomParticipant)
                .where(*page_filters)
                .order_by(ClassroomParticipant.public_alias)
                .limit(limit + 1)
            )
        )
        has_more = len(participants) > limit
        page = participants[:limit]
        presence_by_id, roster_version = hub.participant_roster_snapshot(
            session_id, [item.id for item in page]
        )
        return {
            "items": [
                participant_json(item, presence_by_id[item.id], control_requests) for item in page
            ],
            "total": total,
            "nextCursor": page[-1].public_alias if has_more and page else None,
            "rosterVersion": roster_version,
        }

    @app.get("/api/v1/admin/classroom/metrics")
    def operational_metrics(_: AdminSession) -> dict[str, int | float | str | list[str]]:
        return {
            **hub.metrics(),
            **pressure_metrics,
            "presenterPersistenceWrites": presenter_runtime.persistence_writes,
        }

    @app.post(
        "/api/v1/admin/classroom/sessions/{session_id}/synthetic-safety-stop",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def signal_synthetic_safety_stop(
        session_id: str,
        body: CapacitySafetyStopRequest,
        _: CsrfSession,
        db: Database,
        synthetic_run: Annotated[str | None, Header(alias="X-PathLab-Synthetic-Run")] = None,
        plan_digest: Annotated[str | None, Header(alias="X-PathLab-Plan-Digest")] = None,
        stage_nonce: Annotated[str | None, Header(alias="X-PathLab-Stage-Nonce")] = None,
    ) -> None:
        if synthetic_run is None or re.fullmatch(r"[a-z0-9-]{1,64}", synthetic_run) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_RUN_REQUIRED"})
        if plan_digest is None or re.fullmatch(r"[0-9a-f]{64}", plan_digest) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_PLAN_REQUIRED"})
        if stage_nonce is None or re.fullmatch(r"[A-Za-z0-9._-]{32,128}", stage_nonce) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_NONCE_REQUIRED"})
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.status != "active" or classroom.phase != "live":
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_TRANSITION_INVALID"})
        hub.signal_capacity_safety_stop(
            session_id,
            body.stage_name,
            plan_digest,
            hashlib.sha256(stage_nonce.encode()).hexdigest(),
            set(body.causes),
        )

    @app.post("/api/v1/admin/classroom/sessions/{session_id}/synthetic-stage-ack")
    def acknowledge_synthetic_stage(
        session_id: str,
        body: SyntheticStageAckRequest,
        _: CsrfSession,
        db: Database,
        synthetic_run: Annotated[str | None, Header(alias="X-PathLab-Synthetic-Run")] = None,
    ) -> dict[str, int | bool]:
        if synthetic_run is None or re.fullmatch(r"[a-z0-9-]{1,64}", synthetic_run) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_RUN_REQUIRED"})
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.status != "active" or classroom.phase != "live":
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_TRANSITION_INVALID"})
        count = hub.acknowledge_synthetic_stage(
            session_id, synthetic_run, body.stage_name, body.shard_index
        )
        return {"acknowledgedShards": count, "complete": count == 6}

    @app.post(
        "/api/v1/admin/classroom/sessions/{session_id}/synthetic-recovery-ready",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def mark_synthetic_recovery_ready(
        session_id: str,
        body: SyntheticRecoveryReadyRequest,
        _: CsrfSession,
        db: Database,
        synthetic_run: Annotated[str | None, Header(alias="X-PathLab-Synthetic-Run")] = None,
    ) -> None:
        if synthetic_run is None or re.fullmatch(r"[a-z0-9-]{1,64}", synthetic_run) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_RUN_REQUIRED"})
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.status != "active" or classroom.phase != "live":
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_TRANSITION_INVALID"})
        hub.mark_recovery_ready(session_id, body.epoch_ms)

    @app.get("/api/v1/admin/classroom/sessions")
    def list_classroom_sessions(_: AdminSession, db: Database) -> dict[str, Any]:
        sessions = list(
            db.scalars(
                select(ClassroomSession)
                .where(
                    ClassroomSession.public_id.is_not(None),
                    ClassroomSession.phase.in_(("preview", "live", "review")),
                    ClassroomSession.review_expires_at > _now(),
                )
                .order_by(ClassroomSession.created_at.desc())
                .limit(20)
            )
        )
        return {
            "sessions": [
                {
                    "id": item.id,
                    "publicId": item.public_id,
                    "phase": item.phase,
                    "joinCode": access_code(item.public_id or "", item.code_generation),
                    "reviewExpiresAt": item.review_expires_at.isoformat()
                    if item.review_expires_at
                    else None,
                }
                for item in sessions
            ]
        }

    @app.get("/api/v1/classroom/sessions/{session_id}")
    def student_state(session_id: str, request: Request, db: Database) -> dict[str, Any]:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        classroom = require_live_classroom(
            session_id, db, code="CLASSROOM_NOT_FOUND", status_code=404
        )
        expire_control(classroom, db)
        slides = list(
            db.scalars(
                select(ClassroomSessionSlide)
                .where(ClassroomSessionSlide.session_id == session_id)
                .order_by(ClassroomSessionSlide.slide_position)
            )
        )
        pending_ids = list(
            db.scalars(
                select(ClassroomQuestion.id).where(
                    ClassroomQuestion.session_id == session_id,
                    ClassroomQuestion.participant_id == participant.id,
                )
            )
        )
        active_pin = next(
            (
                pin
                for pin in hub.active_pins(session_id)
                if pin.get("participantId") == participant.id
            ),
            None,
        )
        if active_pin is not None:
            active_pin = {
                key: active_pin[key] for key in ("participantId", "slideId", "x", "y", "zoom")
            }
        return {
            "session": {
                "id": classroom.id,
                "status": classroom.status,
                "phase": classroom.phase,
                "publicId": classroom.public_id,
            },
            "participant": {
                "id": participant.id,
                "alias": participant.public_alias,
            },
            "csrfToken": raw_token,
            "stateVersion": classroom.state_version,
            "presenter": presenter_json(classroom),
            "control": {
                "isController": classroom.controller_participant_id == participant.id,
                "requested": participant.id in hub.control_requests(session_id),
                "leaseId": (
                    classroom.controller_lease_id
                    if classroom.controller_participant_id == participant.id
                    else None
                ),
                "controlEpoch": classroom.control_epoch,
                "expiresAt": (
                    classroom.controller_expires_at.isoformat()
                    if classroom.controller_participant_id == participant.id
                    and classroom.controller_expires_at
                    else None
                ),
            },
            "slides": [_session_slide_json(item) for item in slides],
            "pendingQuestionIds": pending_ids,
            "activePin": active_pin,
            "teacherPointer": hub.teacher_pointer(session_id),
            "teachingAnnotations": hub.teaching_annotations(session_id),
        }

    @app.post(
        "/api/v1/classroom/sessions/{session_id}/pin",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def publish_pin(
        session_id: str,
        payload: PinRequest,
        request: Request,
        db: Database,
    ) -> None:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        classroom = require_live_classroom(session_id, db, code="PIN_NOT_ACCEPTED")
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if slide_exists is None:
            raise HTTPException(status_code=409, detail={"code": "PIN_NOT_ACCEPTED"})
        pin = {
            "participantId": participant.id,
            "alias": participant.public_alias,
            "slideId": payload.slide_id,
            "x": payload.x,
            "y": payload.y,
            "zoom": payload.zoom,
        }
        hub.set_pin(session_id, participant.id, pin)
        hub.publish(
            session_id,
            "pin-updated",
            {"stateVersion": classroom.state_version, **pin},
            critical=True,
            audience="teacher",
        )

    @app.delete(
        "/api/v1/classroom/sessions/{session_id}/pin",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def clear_pin(
        session_id: str,
        payload: ParticipantMutationRequest,
        request: Request,
        db: Database,
    ) -> None:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        require_live_classroom(session_id, db, code="PIN_NOT_ACCEPTED")
        if hub.clear_pin(session_id, participant.id):
            hub.publish(
                session_id,
                "pin-removed",
                {"participantId": participant.id},
                critical=True,
                audience="teacher",
            )

    @app.post(
        "/api/v1/classroom/sessions/{session_id}/control-request",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def request_control(
        session_id: str,
        payload: ParticipantMutationRequest,
        request: Request,
        db: Database,
    ) -> None:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        classroom = require_live_classroom(
            session_id, db, code="CLASSROOM_NOT_FOUND", status_code=404
        )
        if hub.request_control(session_id, participant.id):
            control_requests = hub.control_requests(session_id)
            hub.publish(
                session_id,
                "control-requested",
                {
                    "stateVersion": classroom.state_version,
                    "participantId": participant.id,
                    "participant": participant_json(
                        participant,
                        hub.participant_presence(session_id, participant.id),
                        control_requests,
                    ),
                },
                critical=True,
                audience="teacher",
            )

    @app.delete(
        "/api/v1/classroom/sessions/{session_id}/control-request",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def cancel_control_request(
        session_id: str,
        payload: ParticipantMutationRequest,
        request: Request,
        db: Database,
    ) -> None:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        require_live_classroom(session_id, db, code="CLASSROOM_NOT_FOUND", status_code=404)
        if hub.cancel_control_request(session_id, participant.id):
            hub.publish(
                session_id,
                "control-request-cancelled",
                {"participantId": participant.id},
                critical=True,
                audience="teacher",
            )

    @app.post(
        "/api/v1/classroom/sessions/{session_id}/questions",
        status_code=status.HTTP_201_CREATED,
    )
    def ask_question(
        session_id: str,
        payload: QuestionRequest,
        request: Request,
        response: Response,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, str]:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        classroom = require_live_classroom(session_id, db, code="QUESTION_NOT_ACCEPTED")
        receipt_hash = _hash(payload.idempotency_key)
        existing = db.scalar(
            select(ClassroomQuestionReceipt).where(
                ClassroomQuestionReceipt.session_id == session_id,
                ClassroomQuestionReceipt.participant_id == participant.id,
                ClassroomQuestionReceipt.idempotency_key_hash == receipt_hash,
            )
        )
        if existing is not None:
            response.status_code = 200
            return {"status": "already_processed", "questionId": existing.original_question_id}
        if not payload.text.strip():
            raise HTTPException(status_code=400, detail={"code": "QUESTION_INVALID"})
        receipt_count = db.scalar(
            select(func.count())
            .select_from(ClassroomQuestionReceipt)
            .where(ClassroomQuestionReceipt.participant_id == participant.id)
        )
        if int(receipt_count or 0) >= 500:
            raise HTTPException(status_code=409, detail={"code": "QUESTION_LIMIT_REACHED"})
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        pending = db.scalar(
            select(func.count())
            .select_from(ClassroomQuestion)
            .where(ClassroomQuestion.session_id == session_id)
        )
        if slide_exists is None or int(pending or 0) >= 200:
            raise HTTPException(status_code=409, detail={"code": "QUESTION_NOT_ACCEPTED"})
        question = ClassroomQuestion(
            session_id=session_id,
            participant_id=participant.id,
            slide_id=payload.slide_id,
            text=payload.text.strip(),
            x=payload.x,
            y=payload.y,
            zoom=payload.zoom,
        )
        db.add(question)
        db.flush()
        db.add(
            ClassroomQuestionReceipt(
                session_id=session_id,
                participant_id=participant.id,
                idempotency_key_hash=receipt_hash,
                original_question_id=question.id,
            )
        )
        classroom.state_version += 1
        db.commit()
        hub.publish(
            session_id,
            "question-added",
            {
                "stateVersion": classroom.state_version,
                "questionId": question.id,
                "participantId": participant.id,
                "slideId": payload.slide_id,
                "text": payload.text.strip(),
                "x": payload.x,
                "y": payload.y,
                "zoom": payload.zoom,
            },
            critical=True,
            audience="teacher",
        )
        return {"status": "created", "questionId": question.id}

    @app.delete(
        "/api/v1/admin/classroom/sessions/{session_id}/questions/{question_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def delete_question(
        session_id: str,
        question_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> None:
        question = db.get(ClassroomQuestion, question_id)
        classroom = require_live_classroom(
            session_id, db, code="QUESTION_NOT_FOUND", status_code=404
        )
        if question is None or question.session_id != session_id:
            raise HTTPException(status_code=404, detail={"code": "QUESTION_NOT_FOUND"})
        participant_id = question.participant_id
        question_pin = (question.slide_id, question.x, question.y)
        db.delete(question)
        classroom.state_version += 1
        db.commit()
        hub.publish(
            session_id,
            "question-removed",
            {
                "stateVersion": classroom.state_version,
                "questionId": question_id,
            },
            critical=True,
        )
        if hub.clear_pin_if(
            session_id,
            participant_id,
            slide_id=question_pin[0],
            x=question_pin[1],
            y=question_pin[2],
        ):
            hub.publish(
                session_id,
                "pin-removed",
                {"participantId": participant_id},
                critical=True,
                audience="teacher",
            )

    @app.post("/api/v1/admin/classroom/sessions/{session_id}/control")
    def grant_control(
        session_id: str,
        payload: ControlRequest,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, Any]:
        classroom = require_live_classroom(session_id, db, code="CONTROL_NOT_AVAILABLE")
        participant = db.get(ClassroomParticipant, payload.participant_id)
        if participant is None or participant.session_id != session_id:
            raise HTTPException(status_code=409, detail={"code": "CONTROL_NOT_AVAILABLE"})
        expire_control(classroom, db)
        classroom.control_epoch += 1
        classroom.state_version += 1
        classroom.controller_participant_id = participant.id
        classroom.controller_lease_id = secrets.token_urlsafe(32)
        classroom.controller_expires_at = _now() + timedelta(seconds=payload.seconds)
        hub.cancel_control_request(session_id, participant.id)
        db.commit()
        hub.publish(
            session_id,
            "control",
            {
                "stateVersion": classroom.state_version,
                "participantId": participant.id,
                "controlEpoch": classroom.control_epoch,
                "expiresAt": classroom.controller_expires_at.isoformat(),
            },
            critical=True,
        )
        return {
            "leaseId": classroom.controller_lease_id,
            "controlEpoch": classroom.control_epoch,
            "expiresAt": classroom.controller_expires_at.isoformat(),
        }

    @app.delete(
        "/api/v1/admin/classroom/sessions/{session_id}/control",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def revoke_control(
        session_id: str, _: CsrfSession, _guard: MutationGuard, db: Database
    ) -> None:
        classroom = require_live_classroom(
            session_id, db, code="CLASSROOM_NOT_FOUND", status_code=404
        )
        classroom.control_epoch += 1
        classroom.state_version += 1
        classroom.controller_participant_id = None
        classroom.controller_lease_id = None
        classroom.controller_expires_at = None
        db.commit()
        hub.publish(
            session_id,
            "control",
            {
                "stateVersion": classroom.state_version,
                "participantId": None,
                "leaseId": None,
                "controlEpoch": classroom.control_epoch,
                "expiresAt": None,
            },
            critical=True,
        )

    @app.post("/api/v1/classroom/sessions/{session_id}/presenter")
    def publish_presenter(
        session_id: str,
        payload: PresenterRequest,
        request: Request,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, int]:
        participant, raw_token = live_participant_from_request(request, db, session_id)
        classroom = require_live_classroom(session_id, db, code="CONTROL_LEASE_STALE")
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        if not hub.allow_presenter(participant.id):
            raise HTTPException(status_code=429, detail={"code": "PRESENTER_RATE_LIMITED"})
        if (
            classroom.controller_participant_id != participant.id
            or classroom.controller_lease_id is None
            or not secrets.compare_digest(classroom.controller_lease_id, payload.lease_id)
            or classroom.controller_expires_at is None
            or classroom.controller_expires_at <= _now()
            or slide_exists is None
        ):
            raise HTTPException(status_code=409, detail={"code": "CONTROL_LEASE_STALE"})
        snapshot, slide_changed = presenter_runtime.update(
            session_id,
            classroom.presenter_sequence,
            classroom.presenter_sequence_reserved,
            classroom.current_slide_id,
            payload.slide_id,
            {"x": payload.x, "y": payload.y, "zoom": payload.zoom, "zoomSpace": payload.zoom_space},
        )
        if slide_changed:
            classroom.presenter_sequence = snapshot.sequence
            classroom.current_slide_id = snapshot.slide_id
            classroom.presenter_viewport = snapshot.viewport
            db.commit()
            presenter_runtime.mark_persisted(session_id, snapshot.sequence)
            request_prewarm(session_id, snapshot.slide_id, db)
        hub.publish(
            session_id,
            "presenter",
            {
                "presenterSequence": snapshot.sequence,
                "slideId": snapshot.slide_id,
                "viewport": snapshot.viewport,
            },
            critical=False,
        )
        return {"presenterSequence": snapshot.sequence}

    @app.post("/api/v1/admin/classroom/sessions/{session_id}/presenter")
    def teacher_presenter(
        session_id: str,
        payload: TeacherPresenterRequest,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, int]:
        classroom = require_live_classroom(session_id, db, code="PRESENTER_NOT_ACCEPTED")
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if slide_exists is None:
            raise HTTPException(status_code=409, detail={"code": "PRESENTER_NOT_ACCEPTED"})
        took_control = classroom.controller_participant_id is not None
        if took_control:
            classroom.control_epoch += 1
            classroom.state_version += 1
            classroom.controller_participant_id = None
            classroom.controller_lease_id = None
            classroom.controller_expires_at = None
        snapshot, slide_changed = presenter_runtime.update(
            session_id,
            classroom.presenter_sequence,
            classroom.presenter_sequence_reserved,
            classroom.current_slide_id,
            payload.slide_id,
            {"x": payload.x, "y": payload.y, "zoom": payload.zoom, "zoomSpace": payload.zoom_space},
        )
        if slide_changed:
            classroom.presenter_sequence = snapshot.sequence
            classroom.current_slide_id = snapshot.slide_id
            classroom.presenter_viewport = snapshot.viewport
        if took_control or slide_changed:
            db.commit()
        if slide_changed:
            presenter_runtime.mark_persisted(session_id, snapshot.sequence)
            request_prewarm(session_id, snapshot.slide_id, db)
        if took_control:
            hub.publish(
                session_id,
                "control",
                {
                    "stateVersion": classroom.state_version,
                    "participantId": None,
                    "leaseId": None,
                    "controlEpoch": classroom.control_epoch,
                    "expiresAt": None,
                },
                critical=True,
            )
        hub.publish(
            session_id,
            "presenter",
            {
                "presenterSequence": snapshot.sequence,
                "slideId": snapshot.slide_id,
                "viewport": snapshot.viewport,
            },
            critical=False,
        )
        return {"presenterSequence": snapshot.sequence}

    @app.post(
        "/api/v1/admin/classroom/sessions/{session_id}/pointer",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def teacher_pointer(
        session_id: str,
        payload: TeacherPointerRequest,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> None:
        require_live_classroom(session_id, db, code="POINTER_NOT_ACCEPTED")
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if slide_exists is None:
            raise HTTPException(status_code=409, detail={"code": "POINTER_NOT_ACCEPTED"})
        pointer = {
            "slideId": payload.slide_id,
            "style": payload.style,
            "x": payload.x,
            "y": payload.y,
        }
        hub.set_teacher_pointer(session_id, pointer)
        hub.publish(session_id, "pointer", pointer, critical=False)

    @app.delete(
        "/api/v1/admin/classroom/sessions/{session_id}/pointer",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def clear_teacher_pointer(
        session_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> None:
        require_live_classroom(session_id, db, code="POINTER_NOT_ACCEPTED")
        if hub.clear_teacher_pointer(session_id):
            hub.publish(session_id, "pointer-removed", {}, critical=True)

    @app.post(
        "/api/v1/admin/classroom/sessions/{session_id}/annotations",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def add_teaching_annotation(
        session_id: str,
        payload: TeachingAnnotationRequest,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> None:
        require_live_classroom(session_id, db, code="ANNOTATION_NOT_ACCEPTED")
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if slide_exists is None:
            raise HTTPException(status_code=409, detail={"code": "ANNOTATION_NOT_ACCEPTED"})
        annotation = {
            "id": payload.annotation_id,
            "slideId": payload.slide_id,
            "tool": payload.tool,
            "color": payload.color,
            "width": payload.width,
            "points": [point.model_dump() for point in payload.points],
        }
        hub.add_teaching_annotation(session_id, annotation)
        hub.publish(
            session_id,
            "teaching-annotation-added",
            {"annotation": annotation},
            critical=True,
        )

    @app.delete(
        "/api/v1/admin/classroom/sessions/{session_id}/annotations/{annotation_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def remove_teaching_annotation(
        session_id: str,
        annotation_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> None:
        require_live_classroom(session_id, db, code="ANNOTATION_NOT_ACCEPTED")
        if hub.remove_teaching_annotation(session_id, annotation_id):
            hub.publish(
                session_id,
                "teaching-annotation-removed",
                {"annotationId": annotation_id},
                critical=True,
            )

    @app.delete(
        "/api/v1/admin/classroom/sessions/{session_id}/annotations",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def clear_teaching_annotations(
        session_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> None:
        require_live_classroom(session_id, db, code="ANNOTATION_NOT_ACCEPTED")
        if hub.clear_teaching_annotations(session_id):
            hub.publish(session_id, "teaching-annotations-cleared", {}, critical=True)

    @app.post("/api/v1/admin/classroom/sessions/{session_id}/questions/{question_id}/open")
    def open_question(
        session_id: str,
        question_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
    ) -> dict[str, int]:
        classroom = require_live_classroom(
            session_id, db, code="QUESTION_NOT_FOUND", status_code=404
        )
        question = db.get(ClassroomQuestion, question_id)
        if question is None or question.session_id != session_id:
            raise HTTPException(status_code=404, detail={"code": "QUESTION_NOT_FOUND"})
        classroom.control_epoch += 1
        classroom.state_version += 1
        classroom.controller_participant_id = None
        classroom.controller_lease_id = None
        classroom.controller_expires_at = None
        snapshot, slide_changed = presenter_runtime.update(
            session_id,
            classroom.presenter_sequence,
            classroom.presenter_sequence_reserved,
            classroom.current_slide_id,
            question.slide_id,
            {"x": question.x, "y": question.y, "zoom": question.zoom},
        )
        classroom.presenter_sequence = snapshot.sequence
        classroom.current_slide_id = snapshot.slide_id
        classroom.presenter_viewport = snapshot.viewport
        db.commit()
        presenter_runtime.mark_persisted(session_id, snapshot.sequence)
        if slide_changed:
            request_prewarm(session_id, snapshot.slide_id, db)
        hub.publish(
            session_id,
            "control",
            {
                "stateVersion": classroom.state_version,
                "participantId": None,
                "leaseId": None,
                "controlEpoch": classroom.control_epoch,
                "expiresAt": None,
            },
            critical=True,
        )
        hub.publish(
            session_id,
            "presenter",
            {
                "presenterSequence": snapshot.sequence,
                "slideId": snapshot.slide_id,
                "viewport": snapshot.viewport,
            },
            critical=False,
        )
        return {"presenterSequence": snapshot.sequence}

    @app.delete(
        "/api/v1/admin/classroom/sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def end_session(
        session_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
        synthetic_run: Annotated[str | None, Header(alias="X-PathLab-Synthetic-Run")] = None,
    ) -> None:
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
        if classroom.synthetic_run_id is not None and not (
            synthetic_run is not None
            and secrets.compare_digest(classroom.synthetic_run_id, synthetic_run)
        ):
            raise HTTPException(status_code=409, detail={"code": "SYNTHETIC_RUN_MISMATCH"})
        if classroom.synthetic_run_id is not None:
            final_state_version = classroom.state_version + 1
            db.delete(classroom)
            db.commit()
            presenter_runtime.forget(session_id)
            prewarmer.clear()
            hub.terminate_session(session_id, state_version=final_state_version)
            return
        classroom.status = "ended"
        classroom.phase = "revoked"
        classroom.ended_at = _now()
        classroom.state_version += 1
        db.commit()
        presenter_runtime.forget(session_id)
        prewarmer.clear()
        hub.terminate_session(session_id, state_version=classroom.state_version)

    @app.post(
        "/api/v1/admin/classroom/sessions/{session_id}/synthetic-reset",
        status_code=status.HTTP_204_NO_CONTENT,
    )
    def reset_synthetic_session(
        session_id: str,
        _: CsrfSession,
        _guard: MutationGuard,
        db: Database,
        synthetic_run: Annotated[str | None, Header(alias="X-PathLab-Synthetic-Run")] = None,
    ) -> None:
        if synthetic_run is None or re.fullmatch(r"[a-z0-9-]{1,64}", synthetic_run) is None:
            raise HTTPException(status_code=400, detail={"code": "SYNTHETIC_RUN_REQUIRED"})
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.status != "active" or classroom.phase != "live":
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_TRANSITION_INVALID"})
        hub.reset_session(session_id)
        presenter_runtime.forget(session_id)
        db.execute(
            delete(ClassroomQuestionReceipt).where(
                ClassroomQuestionReceipt.session_id == session_id
            )
        )
        db.execute(delete(ClassroomQuestion).where(ClassroomQuestion.session_id == session_id))
        db.execute(
            delete(ClassroomParticipant).where(ClassroomParticipant.session_id == session_id)
        )
        first_slide = db.scalar(
            select(ClassroomSessionSlide.slide_id)
            .where(ClassroomSessionSlide.session_id == session_id)
            .order_by(ClassroomSessionSlide.slide_position)
            .limit(1)
        )
        classroom.presenter_sequence = 0
        classroom.presenter_sequence_reserved = 0
        classroom.current_slide_id = first_slide
        classroom.presenter_viewport = None
        classroom.controller_participant_id = None
        classroom.controller_lease_id = None
        classroom.controller_expires_at = None
        classroom.control_epoch += 1
        classroom.state_version += 1
        db.commit()

    def stream_state_version(session_id: str) -> int | None:
        with factory() as db:
            classroom = db.get(ClassroomSession, session_id)
            deadline = classroom.live_expires_at or classroom.expires_at if classroom else None
            if (
                classroom is None
                or classroom.status != "active"
                or classroom.phase != "live"
                or deadline is None
                or deadline <= _now()
            ):
                return None
            return int(classroom.state_version)

    async def event_stream(
        session_id: str,
        audience: str,
        participant_id: str | None = None,
    ) -> Any:
        stream_audience: Literal["teacher", "student"] = (
            "teacher" if audience == "teacher" else "student"
        )
        async with hub.subscribe(
            session_id, stream_audience, participant_id=participant_id
        ) as subscriber:
            if not hub.subscription_is_current(session_id, subscriber):
                return
            initial_event_sequence = hub.event_sequence(session_id, stream_audience)
            state_version = await run_in_threadpool(stream_state_version, session_id)
            if state_version is None or not hub.subscription_is_current(session_id, subscriber):
                return
            ready = {
                "type": "stream-ready",
                "hubEpoch": hub.hub_epoch,
                "eventSequence": initial_event_sequence,
                "stateVersion": state_version,
            }
            yield f"event: stream-ready\ndata: {json.dumps(ready, separators=(',', ':'))}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(subscriber.next_event(), timeout=15)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                    continue
                if event is None:
                    return
                encoded = event.get("_encoded") or json.dumps(event, separators=(",", ":"))
                yield f"event: {event['type']}\ndata: {encoded}\n\n"

    def stream_response(
        session_id: str,
        audience: str,
        participant_id: str | None = None,
    ) -> StreamingResponse:
        return StreamingResponse(
            event_stream(session_id, audience, participant_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-store",
                "X-Accel-Buffering": "no",
                "Referrer-Policy": "no-referrer",
            },
        )

    @app.get("/api/v1/admin/classroom/sessions/{session_id}/events")
    def teacher_events(session_id: str, request: Request) -> StreamingResponse:
        admin_from_request(request)
        return stream_response(session_id, "teacher")

    @app.get("/api/v1/classroom/sessions/{session_id}/events")
    def participant_events(session_id: str, request: Request) -> StreamingResponse:
        with factory() as db:
            participant, _ = live_participant_from_request(request, db, session_id)
            participant_id = participant.id
        return stream_response(session_id, "student", participant_id)

    return ClassroomRouteRuntime(presenter_runtime, prewarmer, restore_prewarm)


def _participant_response(
    participant: ClassroomParticipant,
    raw_token: str,
    session_id: str,
    response: Response,
    serializer: URLSafeSerializer,
    secure_cookies: bool,
    status_code: int,
    max_age_seconds: int = 8 * 60 * 60,
) -> dict[str, Any]:
    response.status_code = status_code
    response.set_cookie(
        PARTICIPANT_COOKIE,
        serializer.dumps(
            {"sessionId": session_id, "participantId": participant.id, "token": raw_token}
        ),
        httponly=True,
        secure=secure_cookies,
        samesite="strict",
        max_age=max_age_seconds,
        path="/api/v1/classroom",
    )
    return {
        "sessionId": session_id,
        "participant": {
            "id": participant.id,
            "alias": participant.public_alias,
            "displayName": participant.optional_display_name,
        },
        "csrfToken": raw_token,
    }
