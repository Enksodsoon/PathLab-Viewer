import asyncio
import hashlib
import json
import secrets
import threading
import unicodedata
import xml.etree.ElementTree as ElementTree
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from itsdangerous import BadSignature, URLSafeSerializer
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession
from starlette.concurrency import run_in_threadpool

from .classroom_hub import ClassroomHub
from .classroom_presenter import PresenterRuntime, PresenterSnapshot
from .config import Settings
from .domain import SlideState
from .models import (
    ClassroomParticipant,
    ClassroomQuestion,
    ClassroomQuestionReceipt,
    ClassroomSession,
    ClassroomSessionSlide,
    Folder,
    Session,
    Slide,
    User,
)
from .publication import delivery_version
from .storage import StorageLayout

PARTICIPANT_COOKIE = "pathlab_classroom_participant"
JOIN_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ALIAS_WORDS = ("MINT", "AMBER", "CORAL", "FERN", "IRIS", "JADE", "LILAC", "OAK")


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_ids: list[str] = Field(alias="slideIds", min_length=1, max_length=50)


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


class TeacherPresenterRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    zoom: float = Field(gt=0, le=1000)


class TeacherPointerRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    style: Literal["laser", "green-arrow", "red-arrow"]
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class TeachingPoint(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class TeachingAnnotationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    annotation_id: str = Field(alias="id", min_length=8, max_length=64)
    slide_id: str = Field(alias="slideId", min_length=1, max_length=36)
    tool: Literal["pen", "highlight"]
    color: Literal["#ef765f", "#f6c84a", "#42b883", "#4f8be8", "#f6f2e8"]
    width: Literal[2, 4, 8]
    points: list[TeachingPoint] = Field(min_length=1, max_length=64)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


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
) -> PresenterRuntime | None:
    if not settings.classroom_enabled:
        return None

    Database = Annotated[OrmSession, Depends(database_dependency)]
    AdminSession = Annotated[Session, Depends(admin_dependency)]
    CsrfSession = Annotated[Session, Depends(csrf_dependency)]
    mutation_lock = threading.Lock()
    join_queue_lock = asyncio.Lock()

    def persist_presenters(
        snapshots: Sequence[PresenterSnapshot],
    ) -> None:
        with mutation_lock, factory() as database:
            for snapshot in snapshots:
                classroom = database.get(ClassroomSession, snapshot.session_id)
                if classroom is None or classroom.status != "active":
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
            if classroom is None or classroom.status != "active":
                raise RuntimeError("Cannot reserve a sequence for an inactive classroom")
            if classroom.presenter_sequence_reserved < reserved_until:
                classroom.presenter_sequence_reserved = reserved_until
                database.commit()
            return int(classroom.presenter_sequence_reserved)

    presenter_runtime = PresenterRuntime(
        persist_presenters,
        reserve=reserve_presenter_sequence,
    )

    def serialized_mutation() -> Iterator[None]:
        mutation_lock.acquire()
        try:
            yield None
        finally:
            mutation_lock.release()

    MutationGuard = Annotated[None, Depends(serialized_mutation)]
    serializer = URLSafeSerializer(settings.secret_key, salt="pathlab-classroom-participant-v1")

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

    @app.post(
        "/api/v1/admin/classroom/sessions",
        status_code=status.HTTP_201_CREATED,
    )
    def create_session(
        payload: CreateSessionRequest, _: CsrfSession, _guard: MutationGuard, db: Database
    ) -> dict[str, Any]:
        expired = list(
            db.scalars(
                select(ClassroomSession).where(
                    ClassroomSession.status == "active",
                    ClassroomSession.expires_at <= _now(),
                )
            )
        )
        for stale in expired:
            db.delete(stale)
        if expired:
            db.commit()
        active = db.scalar(select(ClassroomSession).where(ClassroomSession.status == "active"))
        if active is not None:
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_ALREADY_ACTIVE"})
        slides = list(db.scalars(select(Slide).where(Slide.id.in_(payload.slide_ids))))
        slides_by_id = {slide.id: slide for slide in slides}
        if len(slides_by_id) != len(set(payload.slide_ids)):
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"})
        join_code = ""
        for _attempt in range(10):
            candidate = "".join(secrets.choice(JOIN_ALPHABET) for _ in range(10))
            collision = db.scalar(
                select(ClassroomSession.id).where(
                    ClassroomSession.join_code_hash == _hash(candidate)
                )
            )
            if collision is None:
                join_code = candidate
                break
        if not join_code:
            raise HTTPException(status_code=503, detail={"code": "JOIN_CODE_UNAVAILABLE"})
        classroom = ClassroomSession(
            join_code_hash=_hash(join_code),
            expires_at=_now() + timedelta(hours=8),
            current_slide_id=payload.slide_ids[0],
        )
        db.add(classroom)
        db.flush()
        snapshot: list[ClassroomSessionSlide] = []
        for position, slide_id in enumerate(payload.slide_ids):
            slide = slides_by_id[slide_id]
            metadata = slide.slide_metadata or {}
            width = metadata.get("width")
            height = metadata.get("height")
            if (
                slide.state != SlideState.PUBLISHED
                or slide.render_mode != "static_dzi"
                or not slide.sha256
                or not isinstance(width, int)
                or not isinstance(height, int)
                or width <= 0
                or height <= 0
                or slide.derivative_file_count <= 0
            ):
                raise HTTPException(status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"})
            version = delivery_version(slide)
            width, height, tile_size, tile_format = static_descriptor(slide, version)
            if width != metadata.get("width") or height != metadata.get("height"):
                raise HTTPException(status_code=409, detail={"code": "CLASSROOM_SLIDE_NOT_READY"})
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
        return {
            "id": classroom.id,
            "joinCode": join_code,
            "stateVersion": classroom.state_version,
            "slides": [_session_slide_json(item) for item in snapshot],
        }

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
                    return _participant_response(
                        participant,
                        token,
                        classroom.id,
                        response,
                        serializer,
                        settings.secure_cookies,
                        200,
                    )

        cutoff = _now() - timedelta(minutes=15)
        stale_participants = list(
            db.scalars(
                select(ClassroomParticipant).where(
                    ClassroomParticipant.session_id == classroom.id,
                    ClassroomParticipant.last_seen_at < cutoff,
                )
            )
        )
        for stale in stale_participants:
            hub.clear_participant(classroom.id, stale.id)
            db.delete(stale)
        if stale_participants:
            db.flush()
        active_count = db.scalar(
            select(func.count())
            .select_from(ClassroomParticipant)
            .where(
                ClassroomParticipant.session_id == classroom.id,
                ClassroomParticipant.last_seen_at >= cutoff,
            )
        )
        if int(active_count or 0) >= 300:
            raise HTTPException(status_code=409, detail={"code": "CLASSROOM_FULL"})
        token = secrets.token_urlsafe(32)
        existing_aliases = set(
            db.scalars(
                select(ClassroomParticipant.public_alias).where(
                    ClassroomParticipant.session_id == classroom.id
                )
            )
        )
        alias = ""
        for _ in range(50):
            candidate = f"{secrets.choice(ALIAS_WORDS)}-{secrets.randbelow(90) + 10}"
            if candidate not in existing_aliases:
                alias = candidate
                break
        if not alias:
            alias = secrets.token_hex(4).upper()
        participant = ClassroomParticipant(
            session_id=classroom.id,
            token_hash=_hash(token),
            public_alias=alias,
            optional_display_name=_display_name(payload.display_name),
            disconnected_at=_now(),
        )
        db.add(participant)
        classroom.state_version += 1
        db.commit()
        hub.publish(
            classroom.id,
            "participant-joined",
            {
                "stateVersion": classroom.state_version,
                "participantId": participant.id,
                "alias": participant.public_alias,
            },
            critical=True,
            audience="teacher",
        )
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
        with mutation_lock, factory() as db:
            return join_locked(payload, request, response, db)

    @app.post("/api/v1/classroom/join")
    async def join(
        payload: JoinRequest,
        request: Request,
        response: Response,
    ) -> Any:
        async with join_queue_lock:
            return await run_in_threadpool(execute_join, payload, request, response)

    @app.get("/api/v1/admin/classroom/sessions/{session_id}")
    def teacher_state(session_id: str, _: AdminSession, db: Database) -> dict[str, Any]:
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
        participants = list(
            db.scalars(
                select(ClassroomParticipant)
                .where(ClassroomParticipant.session_id == session_id)
                .order_by(ClassroomParticipant.created_at)
                .limit(300)
            )
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
        control_requests = hub.control_requests(session_id)
        return {
            "session": {"id": classroom.id, "status": classroom.status},
            "stateVersion": classroom.state_version,
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
                {
                    "id": item.id,
                    "alias": item.public_alias,
                    "displayName": item.optional_display_name,
                    "controlRequested": item.id in control_requests,
                    "controlRequestedAt": control_requests.get(item.id),
                    "status": (
                        "connected"
                        if hub.participant_is_connected(session_id, item.id)
                        else "reconnecting"
                        if item.disconnected_at is not None
                        and item.disconnected_at >= _now() - timedelta(seconds=60)
                        else "disconnected"
                    ),
                }
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

    @app.get("/api/v1/admin/classroom/metrics")
    def operational_metrics(_: AdminSession) -> dict[str, int]:
        return {
            **hub.metrics(),
            "presenterPersistenceWrites": presenter_runtime.persistence_writes,
        }

    @app.get("/api/v1/classroom/sessions/{session_id}")
    def student_state(session_id: str, request: Request, db: Database) -> dict[str, Any]:
        participant, raw_token = participant_from_request(request, db, session_id)
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.status != "active":
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
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
                key: active_pin[key]
                for key in ("participantId", "slideId", "x", "y", "zoom")
            }
        return {
            "session": {"id": classroom.id, "status": classroom.status},
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
        participant, raw_token = participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        classroom = db.get(ClassroomSession, session_id)
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if classroom is None or classroom.status != "active" or slide_exists is None:
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
        participant, raw_token = participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
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
        participant, raw_token = participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None or classroom.status != "active":
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
        if hub.request_control(session_id, participant.id):
            hub.publish(
                session_id,
                "control-requested",
                {
                    "stateVersion": classroom.state_version,
                    "participantId": participant.id,
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
        participant, raw_token = participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
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
        participant, raw_token = participant_from_request(request, db, session_id)
        if not secrets.compare_digest(payload.csrf_token, raw_token):
            raise HTTPException(status_code=403, detail={"code": "CSRF_INVALID"})
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
        classroom = db.get(ClassroomSession, session_id)
        if classroom is not None:
            classroom.state_version += 1
        db.commit()
        hub.publish(
            session_id,
            "question-added",
            {
                "stateVersion": classroom.state_version if classroom is not None else 0,
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
        if question is None or question.session_id != session_id:
            raise HTTPException(status_code=404, detail={"code": "QUESTION_NOT_FOUND"})
        participant_id = question.participant_id
        question_pin = (question.slide_id, question.x, question.y)
        db.delete(question)
        classroom = db.get(ClassroomSession, session_id)
        if classroom is not None:
            classroom.state_version += 1
        db.commit()
        hub.publish(
            session_id,
            "question-removed",
            {
                "stateVersion": classroom.state_version if classroom is not None else 0,
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
        classroom = db.get(ClassroomSession, session_id)
        participant = db.get(ClassroomParticipant, payload.participant_id)
        if (
            classroom is None
            or classroom.status != "active"
            or participant is None
            or participant.session_id != session_id
        ):
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
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
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
        participant, raw_token = participant_from_request(request, db, session_id)
        classroom = db.get(ClassroomSession, session_id)
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
            classroom is None
            or classroom.status != "active"
            or classroom.controller_participant_id != participant.id
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
            {"x": payload.x, "y": payload.y, "zoom": payload.zoom},
        )
        if slide_changed:
            classroom.presenter_sequence = snapshot.sequence
            classroom.current_slide_id = snapshot.slide_id
            classroom.presenter_viewport = snapshot.viewport
            db.commit()
            presenter_runtime.mark_persisted(session_id, snapshot.sequence)
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
        classroom = db.get(ClassroomSession, session_id)
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if classroom is None or classroom.status != "active" or slide_exists is None:
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
            {"x": payload.x, "y": payload.y, "zoom": payload.zoom},
        )
        if slide_changed:
            classroom.presenter_sequence = snapshot.sequence
            classroom.current_slide_id = snapshot.slide_id
            classroom.presenter_viewport = snapshot.viewport
        if took_control or slide_changed:
            db.commit()
        if slide_changed:
            presenter_runtime.mark_persisted(session_id, snapshot.sequence)
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
        classroom = db.get(ClassroomSession, session_id)
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if classroom is None or classroom.status != "active" or slide_exists is None:
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
    ) -> None:
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
        classroom = db.get(ClassroomSession, session_id)
        slide_exists = db.scalar(
            select(ClassroomSessionSlide.id).where(
                ClassroomSessionSlide.session_id == session_id,
                ClassroomSessionSlide.slide_id == payload.slide_id,
            )
        )
        if classroom is None or classroom.status != "active" or slide_exists is None:
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
    ) -> None:
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
    ) -> None:
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
        classroom = db.get(ClassroomSession, session_id)
        question = db.get(ClassroomQuestion, question_id)
        if (
            classroom is None
            or classroom.status != "active"
            or question is None
            or question.session_id != session_id
        ):
            raise HTTPException(status_code=404, detail={"code": "QUESTION_NOT_FOUND"})
        classroom.control_epoch += 1
        classroom.state_version += 1
        classroom.controller_participant_id = None
        classroom.controller_lease_id = None
        classroom.controller_expires_at = None
        snapshot, _slide_changed = presenter_runtime.update(
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
        session_id: str, _: CsrfSession, _guard: MutationGuard, db: Database
    ) -> None:
        classroom = db.get(ClassroomSession, session_id)
        if classroom is None:
            raise HTTPException(status_code=404, detail={"code": "CLASSROOM_NOT_FOUND"})
        db.delete(classroom)
        db.commit()
        presenter_runtime.forget(session_id)
        hub.clear_session(session_id)
        hub.publish(
            session_id,
            "session-ended",
            {"stateVersion": classroom.state_version + 1},
            critical=True,
        )

    async def event_stream(
        session_id: str,
        audience: str,
        participant_id: str | None = None,
    ) -> Any:
        if participant_id is not None:
            first_connection = hub.participant_connected(session_id, participant_id)
            if first_connection:
                with factory() as db:
                    participant = db.get(ClassroomParticipant, participant_id)
                    classroom = db.get(ClassroomSession, session_id)
                    if participant is not None and classroom is not None:
                        participant.disconnected_at = None
                        participant.last_seen_at = _now()
                        classroom.state_version += 1
                        db.commit()
                        hub.publish(
                            session_id,
                            "participant-reconnected",
                            {
                                "stateVersion": classroom.state_version,
                                "participantId": participant_id,
                            },
                            critical=True,
                            audience="teacher",
                        )
        stream_audience: Literal["teacher", "student"] = (
            "teacher" if audience == "teacher" else "student"
        )
        async with hub.subscribe(session_id, stream_audience) as subscriber:
            try:
                with factory() as db:
                    classroom = db.get(ClassroomSession, session_id)
                    if classroom is None:
                        return
                    state_version = classroom.state_version
                ready = {
                    "type": "stream-ready",
                    "hubEpoch": hub.hub_epoch,
                    "eventSequence": hub.event_sequence(session_id, stream_audience),
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
                    encoded = json.dumps(event, separators=(",", ":"))
                    yield f"event: {event['type']}\ndata: {encoded}\n\n"
            finally:
                if participant_id is not None and hub.participant_disconnected(
                    session_id, participant_id
                ):
                    with factory() as db:
                        participant = db.get(ClassroomParticipant, participant_id)
                        classroom = db.get(ClassroomSession, session_id)
                        if participant is not None and classroom is not None:
                            participant.disconnected_at = _now()
                            participant.last_seen_at = _now()
                            classroom.state_version += 1
                            db.commit()
                            hub.publish(
                                session_id,
                                "participant-left",
                                {
                                    "stateVersion": classroom.state_version,
                                    "participantId": participant_id,
                                },
                                critical=True,
                                audience="teacher",
                            )

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
            participant, _ = participant_from_request(request, db, session_id)
            participant_id = participant.id
        return stream_response(session_id, "student", participant_id)

    return presenter_runtime


def _participant_response(
    participant: ClassroomParticipant,
    raw_token: str,
    session_id: str,
    response: Response,
    serializer: URLSafeSerializer,
    secure_cookies: bool,
    status_code: int,
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
        max_age=8 * 60 * 60,
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
