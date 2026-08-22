# ruff: noqa: B008

import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .delivery import deliver_file
from .domain import SlideState
from .models import (
    Session,
    Slide,
    StudyCourse,
    StudyInvitation,
    StudyLearnerSession,
    StudyPack,
    StudyProgress,
    StudyReadinessAggregate,
)
from .storage import StorageLayout
from .study_pack_contract import (
    MAX_PACK_BYTES,
    learner_definition,
    normalized_spatial_error,
    prepare_study_pack,
    score_task,
    validate_study_pack,
)
from .study_pack_contract import parse_json as parse_study_pack_json
from .tile_routes import private_static_target
from .time_support import as_utc, utc_now

STUDY_COOKIE = "pathlab_study"
SUBMISSION_INTERVAL_SECONDS = 30
MODEL_APPROVAL_STATUS = "public_beta_bounded_safe_actions"
PILOT_AUTHORIZATION = "closed_pilot_unapproved"
ALLOWED_AI_ACTIONS = {
    "continue",
    "offer_hint",
    "ask_confidence",
    "ask_source_check",
    "retrieve",
    "pause",
}


def _now() -> datetime:
    return utc_now()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _token(size: int = 32) -> str:
    return secrets.token_urlsafe(size)


def _formula_safe(value: str) -> str:
    return "'" + value if value[:1] in {"=", "+", "-", "@"} else value


def _release_manifest() -> dict[str, Any]:
    path = Path(__file__).with_name("trace_sim_release.json")
    try:
        manifest: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"id": "unavailable", "approvalStatus": "invalid"}
    return (
        manifest
        if isinstance(manifest, dict)
        else {"id": "unavailable", "approvalStatus": "invalid"}
    )


class StudyModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=lambda value: (
            value.split("_")[0] + "".join(word.title() for word in value.split("_")[1:])
        ),
        populate_by_name=True,
    )


class CreateCourseRequest(StudyModel):
    pack_id: str = Field(min_length=36, max_length=36)
    title: str = Field(min_length=1, max_length=240)
    retention_days: int = Field(default=30, ge=0, le=90)
    learner_limit: int = Field(default=500, ge=1, le=500)
    ends_at: datetime | None = None
    ai_mode: str = Field(
        default="deterministic", pattern=r"^(deterministic|closed_pilot_trace_sim)$"
    )
    pilot_acknowledged: bool = False


class UpdateCourseRequest(StudyModel):
    retention_days: int | None = Field(default=None, ge=0, le=90)
    ends_at: datetime | None = None


class InvitationRequest(StudyModel):
    count: int = Field(ge=1, le=500)


class RedeemRequest(StudyModel):
    code: str = Field(min_length=20, max_length=200)
    notice_accepted: bool = False


class TaskSubmission(StudyModel):
    selected_option: str | None = Field(default=None, max_length=1000)
    x: float | None = Field(default=None, ge=0, le=1)
    y: float | None = Field(default=None, ge=0, le=1)


class ReadinessReport(StudyModel):
    outcome: str = Field(pattern=r"^(ready|fallback)$")


class AiEventReport(StudyModel):
    task_id: str = Field(min_length=1, max_length=120)
    outcome: str = Field(
        pattern=r"^(continue|offer_hint|ask_confidence|ask_source_check|retrieve|pause|fallback)$"
    )


class StudyPurger:
    def __init__(self, factory: sessionmaker[OrmSession]) -> None:
        self.factory = factory
        self.task: asyncio.Task[None] | None = None
        self.stop_event = asyncio.Event()

    def start(self) -> None:
        if self.task is None:
            self.task = asyncio.create_task(self._run())

    async def close(self) -> None:
        self.stop_event.set()
        if self.task is not None:
            # A nested TestClient may enter the same app lifespan from another loop.
            # Production owns one lifespan; non-owning loops must not await its task.
            if self.task.get_loop() is not asyncio.get_running_loop():
                return
            await self.task
            self.task = None

    async def _run(self) -> None:
        while not self.stop_event.is_set():
            with self.factory() as database:
                purge_due_study_data(database)
            with suppress(TimeoutError):
                await asyncio.wait_for(self.stop_event.wait(), timeout=60 * 60)


def purge_due_study_data(database: OrmSession, now: datetime | None = None) -> int:
    current = now or _now()
    due = list(
        database.scalars(
            select(StudyCourse).where(
                StudyCourse.status == "ended",
                StudyCourse.purge_after.is_not(None),
                StudyCourse.purge_after <= current,
            )
        )
    )
    for course in due:
        database.execute(
            delete(StudyLearnerSession).where(StudyLearnerSession.course_id == course.id)
        )
        database.execute(delete(StudyInvitation).where(StudyInvitation.course_id == course.id))
        database.execute(
            delete(StudyReadinessAggregate).where(StudyReadinessAggregate.course_id == course.id)
        )
        course.status = "purged"
    if due:
        database.commit()
    return len(due)


def register_study_routes(
    app: FastAPI,
    *,
    factory: sessionmaker[OrmSession],
    storage: StorageLayout,
    database_dependency: Callable[[], Iterator[OrmSession]],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
    enabled: bool,
    ai_enabled: bool,
    pilot_enabled: bool,
    csrf_secret: str,
    max_learners: int,
    secure_cookies: bool,
    internal_file_redirects: bool,
) -> StudyPurger:
    purger = StudyPurger(factory)
    submission_times: dict[str, float] = {}
    ai_event_times: dict[str, float] = {}

    def require_enabled() -> None:
        if not enabled:
            raise HTTPException(status_code=404, detail={"code": "STUDY_MODE_DISABLED"})

    def csrf_value(token: str) -> str:
        return hmac.new(
            csrf_secret.encode("utf-8"),
            ("pathlab-study-csrf:" + token).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def pilot_eligible(course: StudyCourse, manifest: dict[str, Any]) -> bool:
        return bool(
            ai_enabled
            and pilot_enabled
            and course.ai_mode == "closed_pilot_trace_sim"
            and course.pilot_acknowledged_at is not None
            and course.model_manifest_id == manifest.get("id")
            and manifest.get("pilotAuthorization") == PILOT_AUTHORIZATION
        )

    def learner_session(
        database: OrmSession = Depends(database_dependency),
        token: str | None = Cookie(default=None, alias=STUDY_COOKIE),
    ) -> StudyLearnerSession:
        require_enabled()
        if not token:
            raise HTTPException(status_code=401, detail={"code": "STUDY_SESSION_REQUIRED"})
        stored = database.scalar(
            select(StudyLearnerSession).where(StudyLearnerSession.token_hash == _hash(token))
        )
        now = _now()
        if stored is None or stored.status != "active" or as_utc(stored.expires_at) <= now:
            raise HTTPException(status_code=401, detail={"code": "STUDY_SESSION_EXPIRED"})
        course = database.get(StudyCourse, stored.course_id)
        if course is None or course.status not in {"preparation", "active"}:
            raise HTTPException(status_code=410, detail={"code": "STUDY_COURSE_UNAVAILABLE"})
        if course.ends_at is not None and as_utc(course.ends_at) <= now:
            course.status = "ended"
            course.ended_at = now
            course.purge_after = now + timedelta(days=course.retention_days)
            database.commit()
            raise HTTPException(status_code=410, detail={"code": "STUDY_COURSE_ENDED"})
        return stored

    def learner_csrf(
        stored: StudyLearnerSession = Depends(learner_session),
        csrf_token: str | None = Header(default=None, alias="X-Study-CSRF"),
        token: str | None = Cookie(default=None, alias=STUDY_COOKIE),
    ) -> StudyLearnerSession:
        if not token or not csrf_token or not hmac.compare_digest(csrf_token, csrf_value(token)):
            raise HTTPException(status_code=403, detail={"code": "STUDY_CSRF_INVALID"})
        return stored

    def course_json(course: StudyCourse, database: OrmSession) -> dict[str, Any]:
        issued = (
            database.scalar(
                select(func.count())
                .select_from(StudyInvitation)
                .where(StudyInvitation.course_id == course.id)
            )
            or 0
        )
        redeemed = (
            database.scalar(
                select(func.count())
                .select_from(StudyLearnerSession)
                .where(StudyLearnerSession.course_id == course.id)
            )
            or 0
        )
        readiness = database.scalar(
            select(StudyReadinessAggregate).where(StudyReadinessAggregate.course_id == course.id)
        )
        return {
            "id": course.id,
            "packId": course.pack_id,
            "title": course.title,
            "status": course.status,
            "retentionDays": course.retention_days,
            "learnerLimit": course.learner_limit,
            "invitations": issued,
            "redeemed": redeemed,
            "endsAt": course.ends_at.replace(tzinfo=UTC).isoformat() if course.ends_at else None,
            "purgeAfter": course.purge_after.replace(tzinfo=UTC).isoformat()
            if course.purge_after
            else None,
            "aiMode": course.ai_mode,
            "modelManifestId": course.model_manifest_id,
            "pilotAcknowledgedAt": course.pilot_acknowledged_at.replace(tzinfo=UTC).isoformat()
            if course.pilot_acknowledged_at
            else None,
            "readiness": {
                "ready": readiness.ready_count if readiness else 0,
                "fallback": readiness.fallback_count if readiness else 0,
            },
            "aiActions": {
                action: getattr(readiness, f"{action}_count", 0) if readiness else 0
                for action in sorted(ALLOWED_AI_ACTIONS)
            },
        }

    def session_json(stored: StudyLearnerSession, database: OrmSession) -> dict[str, Any]:
        course = database.get(StudyCourse, stored.course_id)
        if course is None:
            raise HTTPException(status_code=410, detail={"code": "STUDY_COURSE_UNAVAILABLE"})
        pack = database.get(StudyPack, course.pack_id)
        if pack is None:
            raise HTTPException(status_code=410, detail={"code": "STUDY_PACK_UNAVAILABLE"})
        manifest = _release_manifest()
        ai_eligible = pilot_eligible(course, manifest) or (
            ai_enabled and manifest.get("approvalStatus") == MODEL_APPROVAL_STATUS
        )
        progress = list(
            database.scalars(
                select(StudyProgress)
                .where(StudyProgress.session_id == stored.id)
                .order_by(StudyProgress.created_at)
            )
        )
        return {
            "pseudonym": stored.pseudonym,
            "course": {
                "id": course.id,
                "title": course.title,
                "status": course.status,
                "retentionDays": course.retention_days,
                "endsAt": course.ends_at.replace(tzinfo=UTC).isoformat()
                if course.ends_at
                else None,
            },
            "pack": learner_definition(pack.definition),
            "progress": [
                {
                    "taskId": item.task_id,
                    "status": item.status,
                    "latestCorrectness": item.latest_correctness,
                    "attemptCount": item.attempt_count,
                    "modelManifestId": item.model_manifest_id,
                    "createdAt": item.created_at.replace(tzinfo=UTC).isoformat(),
                    "updatedAt": item.updated_at.replace(tzinfo=UTC).isoformat(),
                }
                for item in progress
            ],
            "ai": {
                "eligible": ai_eligible,
                "manifest": manifest if ai_eligible else None,
                "coldStartDistinctTasks": 5,
                "allowedActions": sorted(ALLOWED_AI_ACTIONS),
                "authorizationMode": (
                    "closed_pilot" if pilot_eligible(course, manifest) else "approved"
                ),
            },
        }

    @app.get("/api/v1/admin/study/packs")
    def list_packs(
        _: Session = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        require_enabled()
        return [
            {
                "id": pack.id,
                "packKey": pack.pack_key,
                "version": pack.version,
                "title": pack.title,
                "checksum": pack.checksum,
                "createdAt": pack.created_at.replace(tzinfo=UTC).isoformat(),
            }
            for pack in database.scalars(select(StudyPack).order_by(StudyPack.created_at.desc()))
        ]

    def accepted_study_slides(database: OrmSession) -> list[Slide]:
        return list(
            database.scalars(
                select(Slide)
                .where(
                    Slide.render_mode == "static_dzi",
                    Slide.privacy_status == "passed",
                    Slide.state.in_([SlideState.READY_PRIVATE, SlideState.PUBLISHED]),
                    Slide.trashed_at.is_(None),
                )
                .order_by(Slide.display_name)
            )
        )

    def verify_pack_slides(definition: dict[str, Any], database: OrmSession) -> None:
        accepted = {slide.id: slide for slide in accepted_study_slides(database)}
        for reference in definition["slides"]:
            slide = accepted.get(reference["viewerSlideId"])
            if slide is None or slide.sha256 != reference["sha256"]:
                raise HTTPException(
                    status_code=409, detail={"code": "STUDY_PACK_SLIDE_NOT_ACCEPTED"}
                )

    async def study_pack_body(request: Request) -> dict[str, Any]:
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > MAX_PACK_BYTES:
                raise HTTPException(status_code=413, detail={"code": "STUDY_PACK_SIZE_INVALID"})
        try:
            return parse_study_pack_json(bytes(body))
        except (ValueError, json.JSONDecodeError) as error:
            code = str(error) if str(error).startswith("STUDY_") else "STUDY_PACK_INVALID"
            raise HTTPException(status_code=422, detail={"code": code}) from error

    @app.get("/api/v1/admin/study/authoring/slides")
    def authoring_slides(
        _: Session = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, str]]:
        require_enabled()
        return [
            {"id": slide.id, "displayName": slide.display_name, "sha256": slide.sha256 or ""}
            for slide in accepted_study_slides(database)
        ]

    @app.post("/api/v1/admin/study/packs/validate")
    async def validate_pack_for_preview(
        request: Request,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        definition = await study_pack_body(request)
        try:
            core, checksum = prepare_study_pack(definition)
        except ValueError as error:
            raise HTTPException(status_code=422, detail={"code": str(error)}) from error
        verify_pack_slides(core, database)
        return {"canonicalCore": core, "checksum": checksum}

    @app.post("/api/v1/admin/study/packs", status_code=status.HTTP_201_CREATED)
    async def publish_viewer_pack(
        request: Request,
        authenticated: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        definition = await study_pack_body(request)
        try:
            checksum = validate_study_pack(definition)
        except ValueError as error:
            raise HTTPException(status_code=422, detail={"code": str(error)}) from error
        verify_pack_slides(definition, database)
        existing = database.scalar(
            select(StudyPack).where(
                StudyPack.pack_key == definition["packKey"],
                StudyPack.version == definition["version"],
            )
        )
        if existing is not None:
            if existing.checksum != checksum:
                raise HTTPException(
                    status_code=409, detail={"code": "STUDY_PACK_VERSION_IMMUTABLE"}
                )
            stored = existing
        else:
            stored = StudyPack(
                pack_key=definition["packKey"],
                version=definition["version"],
                title=definition["title"],
                checksum=checksum,
                definition=definition,
                created_by_user_id=authenticated.user_id,
            )
            database.add(stored)
            try:
                database.commit()
            except IntegrityError as error:
                database.rollback()
                raise HTTPException(
                    status_code=409, detail={"code": "STUDY_PACK_VERSION_IMMUTABLE"}
                ) from error
        return {
            "id": stored.id,
            "packKey": stored.pack_key,
            "version": stored.version,
            "title": stored.title,
            "checksum": stored.checksum,
            "createdAt": stored.created_at.replace(tzinfo=UTC).isoformat(),
        }

    @app.get("/api/v1/admin/study/courses")
    def list_courses(
        _: Session = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> list[dict[str, Any]]:
        require_enabled()
        purge_due_study_data(database)
        return [
            course_json(course, database)
            for course in database.scalars(
                select(StudyCourse).order_by(StudyCourse.created_at.desc())
            )
        ]

    @app.post("/api/v1/admin/study/courses", status_code=status.HTTP_201_CREATED)
    def create_course(
        payload: CreateCourseRequest,
        authenticated: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        if payload.learner_limit > max_learners or database.get(StudyPack, payload.pack_id) is None:
            raise HTTPException(status_code=422, detail={"code": "STUDY_COURSE_INVALID"})
        ends_at = as_utc(payload.ends_at) if payload.ends_at else None
        if ends_at is not None and ends_at <= _now():
            raise HTTPException(status_code=422, detail={"code": "STUDY_END_DATE_INVALID"})
        manifest = _release_manifest()
        is_pilot = payload.ai_mode == "closed_pilot_trace_sim"
        if is_pilot and (not pilot_enabled or not payload.pilot_acknowledged):
            raise HTTPException(status_code=422, detail={"code": "STUDY_AI_PILOT_ACK_REQUIRED"})
        course = StudyCourse(
            pack_id=payload.pack_id,
            title=payload.title.strip(),
            retention_days=payload.retention_days,
            learner_limit=payload.learner_limit,
            ends_at=ends_at,
            ai_mode=payload.ai_mode,
            pilot_acknowledged_at=_now() if is_pilot else None,
            model_manifest_id=manifest.get("id") if is_pilot else None,
            created_by_user_id=authenticated.user_id,
        )
        database.add(course)
        database.commit()
        return course_json(course, database)

    @app.patch("/api/v1/admin/study/courses/{course_id}")
    def update_course(
        course_id: str,
        payload: UpdateCourseRequest,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        course = database.get(StudyCourse, course_id)
        if course is None or course.status in {"ended", "purged"}:
            raise HTTPException(status_code=404, detail={"code": "STUDY_COURSE_NOT_FOUND"})
        locked = course.invitations_generated_at is not None
        if payload.retention_days is not None:
            if locked and payload.retention_days > course.retention_days:
                raise HTTPException(
                    status_code=409, detail={"code": "STUDY_RETENTION_EXTENSION_FORBIDDEN"}
                )
            course.retention_days = payload.retention_days
        if payload.ends_at is not None:
            next_end = as_utc(payload.ends_at)
            if next_end <= _now() or (
                locked and course.ends_at is not None and next_end > as_utc(course.ends_at)
            ):
                raise HTTPException(
                    status_code=409, detail={"code": "STUDY_END_EXTENSION_FORBIDDEN"}
                )
            course.ends_at = next_end
        database.commit()
        return course_json(course, database)

    @app.post("/api/v1/admin/study/courses/{course_id}/prepare")
    def prepare_course(
        course_id: str,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        course = database.get(StudyCourse, course_id)
        if course is None or course.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "STUDY_TRANSITION_INVALID"})
        course.status = "preparation"
        try:
            database.commit()
        except IntegrityError as error:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "STUDY_LIVE_COURSE_EXISTS"}
            ) from error
        return course_json(course, database)

    @app.post("/api/v1/admin/study/courses/{course_id}/activate")
    def activate_course(
        course_id: str,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        course = database.get(StudyCourse, course_id)
        invitation_count = (
            database.scalar(
                select(func.count())
                .select_from(StudyInvitation)
                .where(
                    StudyInvitation.course_id == course_id,
                    StudyInvitation.status == "issued",
                )
            )
            or 0
        )
        if course is None or course.status != "preparation" or invitation_count < 1:
            raise HTTPException(status_code=409, detail={"code": "STUDY_TRANSITION_INVALID"})
        course.status = "active"
        database.commit()
        return course_json(course, database)

    @app.post("/api/v1/admin/study/courses/{course_id}/end")
    def end_course(
        course_id: str,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        course = database.get(StudyCourse, course_id)
        if course is None or course.status not in {"preparation", "active"}:
            raise HTTPException(status_code=409, detail={"code": "STUDY_TRANSITION_INVALID"})
        now = _now()
        course.status = "ended"
        course.ended_at = now
        course.purge_after = now + timedelta(days=course.retention_days)
        database.commit()
        return course_json(course, database)

    @app.post("/api/v1/admin/study/courses/{course_id}/purge")
    def purge_course(
        course_id: str,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        course = database.get(StudyCourse, course_id)
        if course is None or course.status not in {"ended", "purged"}:
            raise HTTPException(status_code=409, detail={"code": "STUDY_TRANSITION_INVALID"})
        if course.status != "purged":
            course.purge_after = _now()
            database.commit()
            purge_due_study_data(database)
        return course_json(course, database)

    @app.post("/api/v1/admin/study/courses/{course_id}/invitations")
    def create_invitations(
        course_id: str,
        payload: InvitationRequest,
        _: Session = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> StreamingResponse:
        require_enabled()
        course = database.get(StudyCourse, course_id)
        existing = (
            database.scalar(
                select(func.count())
                .select_from(StudyInvitation)
                .where(
                    StudyInvitation.course_id == course_id,
                    StudyInvitation.status != "revoked",
                )
            )
            or 0
        )
        if (
            course is None
            or course.status not in {"draft", "preparation"}
            or existing + payload.count > course.learner_limit
        ):
            raise HTTPException(status_code=409, detail={"code": "STUDY_INVITATION_LIMIT"})
        codes: list[str] = []
        for _index in range(payload.count):
            code = "SC-" + _token(24)
            codes.append(code)
            database.add(StudyInvitation(course_id=course.id, code_hash=_hash(code)))
        course.invitations_generated_at = course.invitations_generated_at or _now()
        database.commit()
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(["course_pseudonym_mapping", "invitation_code"])
        for code in codes:
            writer.writerow(["", _formula_safe(code)])
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="study-invitations-{course.id}.csv"'
            },
        )

    @app.get("/api/v1/admin/study/courses/{course_id}/progress.csv")
    def export_progress(
        course_id: str,
        _: Session = Depends(admin_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> StreamingResponse:
        require_enabled()
        rows = database.execute(
            select(StudyLearnerSession.pseudonym, StudyProgress)
            .join(StudyProgress, StudyProgress.session_id == StudyLearnerSession.id)
            .where(StudyLearnerSession.course_id == course_id)
        ).all()
        output = io.StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerow(
            [
                "pseudonym",
                "task_id",
                "status",
                "latest_correctness",
                "attempt_count",
                "model_manifest_id",
                "created_at",
                "updated_at",
            ]
        )
        for pseudonym, item in rows:
            writer.writerow(
                [
                    _formula_safe(pseudonym),
                    item.task_id,
                    item.status,
                    "true" if item.latest_correctness else "false",
                    item.attempt_count,
                    item.model_manifest_id or "",
                    item.created_at.isoformat(),
                    item.updated_at.isoformat(),
                ]
            )
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8")

    @app.post("/api/v1/study/redeem", status_code=status.HTTP_201_CREATED)
    def redeem(
        payload: RedeemRequest,
        response: Response,
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        require_enabled()
        if not payload.notice_accepted:
            raise HTTPException(status_code=422, detail={"code": "STUDY_NOTICE_REQUIRED"})
        invitation = database.scalar(
            select(StudyInvitation).where(StudyInvitation.code_hash == _hash(payload.code))
        )
        if invitation is None or invitation.status != "issued":
            raise HTTPException(status_code=404, detail={"code": "STUDY_INVITATION_INVALID"})
        course = database.get(StudyCourse, invitation.course_id)
        if course is None or course.status not in {"preparation", "active"}:
            raise HTTPException(status_code=409, detail={"code": "STUDY_COURSE_UNAVAILABLE"})
        current_count = (
            database.scalar(
                select(func.count())
                .select_from(StudyLearnerSession)
                .where(StudyLearnerSession.course_id == course.id)
            )
            or 0
        )
        if current_count >= course.learner_limit:
            raise HTTPException(status_code=409, detail={"code": "STUDY_COURSE_FULL"})
        token = _token(48)
        csrf_token = csrf_value(token)
        expires_at = course.ends_at or (_now() + timedelta(days=90))
        stored = StudyLearnerSession(
            course_id=course.id,
            invitation_id=invitation.id,
            token_hash=_hash(token),
            csrf_hash=_hash(csrf_token),
            pseudonym="Learner-" + secrets.token_hex(4).upper(),
            expires_at=expires_at,
        )
        invitation.status = "redeemed"
        invitation.redeemed_at = _now()
        database.add(stored)
        database.commit()
        response.set_cookie(
            STUDY_COOKIE,
            token,
            httponly=True,
            secure=secure_cookies,
            samesite="lax",
            path="/api/v1/study",
            max_age=max(1, int((as_utc(expires_at) - _now()).total_seconds())),
        )
        return {"csrfToken": csrf_token, **session_json(stored, database)}

    @app.get("/api/v1/study/session")
    def get_session(
        stored: StudyLearnerSession = Depends(learner_session),
        database: OrmSession = Depends(database_dependency),
        token: str | None = Cookie(default=None, alias=STUDY_COOKIE),
    ) -> dict[str, Any]:
        if token is None:
            raise HTTPException(status_code=401, detail={"code": "STUDY_SESSION_REQUIRED"})
        return {"csrfToken": csrf_value(token), **session_json(stored, database)}

    @app.post("/api/v1/study/tasks/{task_id}/submit")
    def submit_task(
        task_id: str,
        payload: TaskSubmission,
        stored: StudyLearnerSession = Depends(learner_csrf),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        course = database.get(StudyCourse, stored.course_id)
        pack = database.get(StudyPack, course.pack_id) if course else None
        if course is None or pack is None or course.status != "active":
            raise HTTPException(status_code=409, detail={"code": "STUDY_NOT_ACTIVE"})
        now_mono = time.monotonic()
        last = submission_times.get(stored.id)
        if last is not None and now_mono - last < SUBMISSION_INTERVAL_SECONDS:
            retry = max(1, int(SUBMISSION_INTERVAL_SECONDS - (now_mono - last)))
            raise HTTPException(
                status_code=429,
                detail={"code": "STUDY_SUBMISSION_THROTTLED", "retryAfterSeconds": retry},
            )
        task = next((item for item in pack.definition["tasks"] if item["id"] == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail={"code": "STUDY_TASK_NOT_FOUND"})
        try:
            submission = payload.model_dump(by_alias=True, exclude_none=True)
            correct = score_task(task, submission)
        except ValueError as error:
            raise HTTPException(status_code=422, detail={"code": str(error)}) from error
        progress = database.scalar(
            select(StudyProgress).where(
                StudyProgress.session_id == stored.id,
                StudyProgress.task_id == task_id,
            )
        )
        if progress is None:
            progress = StudyProgress(
                session_id=stored.id,
                task_id=task_id,
                status="completed" if correct else "attempted",
                latest_correctness=correct,
                attempt_count=1,
                model_manifest_id=course.model_manifest_id,
            )
            database.add(progress)
        else:
            progress.attempt_count += 1
            progress.latest_correctness = correct
            if correct:
                progress.status = "completed"
        database.commit()
        submission_times[stored.id] = now_mono
        result = {
            "taskId": task_id,
            "correct": correct,
            "status": progress.status,
            "attemptCount": progress.attempt_count,
            "hints": task.get("hints", []),
            "explanation": task["explanation"],
            "sources": task["sources"],
        }
        spatial_error = normalized_spatial_error(task, submission)
        if spatial_error is not None:
            result["spatialError"] = spatial_error
        return result

    @app.get("/api/v1/study/readiness")
    def readiness(stored: StudyLearnerSession = Depends(learner_session)) -> dict[str, Any]:
        manifest = _release_manifest()
        with factory() as database:
            course = database.get(StudyCourse, stored.course_id)
            eligible = course is not None and (
                pilot_eligible(course, manifest)
                or (ai_enabled and manifest.get("approvalStatus") == MODEL_APPROVAL_STATUS)
            )
        return {"aiEligible": eligible, "manifest": manifest if eligible else None}

    @app.post("/api/v1/study/readiness", status_code=status.HTTP_204_NO_CONTENT)
    def report_readiness(
        payload: ReadinessReport,
        stored: StudyLearnerSession = Depends(learner_csrf),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        aggregate = database.scalar(
            select(StudyReadinessAggregate).where(
                StudyReadinessAggregate.course_id == stored.course_id
            )
        )
        if aggregate is None:
            aggregate = StudyReadinessAggregate(course_id=stored.course_id)
            database.add(aggregate)
        if payload.outcome == "ready":
            aggregate.ready_count = (aggregate.ready_count or 0) + 1
        else:
            aggregate.fallback_count = (aggregate.fallback_count or 0) + 1
        database.commit()

    @app.post("/api/v1/study/ai-events", status_code=status.HTTP_204_NO_CONTENT)
    def report_ai_event(
        payload: AiEventReport,
        stored: StudyLearnerSession = Depends(learner_csrf),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        manifest = _release_manifest()
        course = database.get(StudyCourse, stored.course_id)
        if course is None or not pilot_eligible(course, manifest):
            raise HTTPException(status_code=404, detail={"code": "STUDY_AI_UNAVAILABLE"})
        progress = database.scalar(
            select(StudyProgress).where(
                StudyProgress.session_id == stored.id,
                StudyProgress.task_id == payload.task_id,
            )
        )
        now_mono = time.monotonic()
        if progress is None or now_mono - ai_event_times.get(stored.id, float("-inf")) < 1:
            raise HTTPException(status_code=409, detail={"code": "STUDY_AI_EVENT_INVALID"})
        aggregate = database.scalar(
            select(StudyReadinessAggregate).where(
                StudyReadinessAggregate.course_id == stored.course_id
            )
        )
        if aggregate is None:
            aggregate = StudyReadinessAggregate(course_id=stored.course_id)
            database.add(aggregate)
        if payload.outcome == "fallback":
            aggregate.fallback_count = (aggregate.fallback_count or 0) + 1
        else:
            setattr(
                aggregate,
                f"{payload.outcome}_count",
                (getattr(aggregate, f"{payload.outcome}_count") or 0) + 1,
            )
        database.commit()
        ai_event_times[stored.id] = now_mono

    @app.post("/api/v1/study/withdraw", status_code=status.HTTP_204_NO_CONTENT)
    def withdraw(
        response: Response,
        stored: StudyLearnerSession = Depends(learner_csrf),
        database: OrmSession = Depends(database_dependency),
    ) -> None:
        submission_times.pop(stored.id, None)
        ai_event_times.pop(stored.id, None)
        database.delete(stored)
        database.commit()
        response.delete_cookie(STUDY_COOKIE, path="/api/v1/study")

    @app.post("/api/v1/study/cleanup-ack", status_code=status.HTTP_204_NO_CONTENT)
    def cleanup_ack(_: StudyLearnerSession = Depends(learner_csrf)) -> None:
        return None

    @app.get("/api/v1/study/assets/{asset_name}")
    def study_model_asset(
        asset_name: str,
        stored: StudyLearnerSession = Depends(learner_session),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        manifest = _release_manifest()
        expected_name = manifest.get("assetFile")
        course = database.get(StudyCourse, stored.course_id)
        eligible = course is not None and (
            pilot_eligible(course, manifest)
            or (ai_enabled and manifest.get("approvalStatus") == MODEL_APPROVAL_STATUS)
        )
        if (
            not eligible
            or not isinstance(expected_name, str)
            or asset_name != expected_name
        ):
            raise HTTPException(status_code=404, detail={"code": "STUDY_AI_UNAVAILABLE"})
        target = storage.root / "private" / "study-models" / expected_name
        expected_bytes = manifest.get("artifactBytes")
        expected_hash = manifest.get("artifactSha256")
        if (
            not target.is_file()
            or target.stat().st_size != expected_bytes
            or not isinstance(expected_hash, str)
            or hashlib.sha256(target.read_bytes()).hexdigest() != expected_hash
        ):
            raise HTTPException(status_code=404, detail={"code": "STUDY_AI_UNAVAILABLE"})
        return deliver_file(
            target,
            data_root=storage.root,
            internal_redirects=internal_file_redirects,
            media_type="application/octet-stream",
            cache_control="private, max-age=31536000, immutable",
            headers={"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"},
        )

    @app.get("/api/v1/study/slides/{slide_id}/tiles/{tile_path:path}")
    def study_tile(
        slide_id: str,
        tile_path: str,
        stored: StudyLearnerSession = Depends(learner_session),
        database: OrmSession = Depends(database_dependency),
    ) -> Response:
        course = database.get(StudyCourse, stored.course_id)
        pack = database.get(StudyPack, course.pack_id) if course else None
        allowed = pack is not None and any(
            item.get("viewerSlideId") == slide_id for item in pack.definition.get("slides", [])
        )
        slide = database.get(Slide, slide_id) if allowed else None
        if (
            slide is None
            or slide.render_mode != "static_dzi"
            or slide.privacy_status != "passed"
            or slide.state not in {SlideState.READY_PRIVATE, SlideState.PUBLISHED}
        ):
            raise HTTPException(status_code=404, detail={"code": "STUDY_SLIDE_NOT_FOUND"})
        target = private_static_target(storage, slide.id, tile_path)
        media_type = "application/xml" if target.suffix.lower() == ".dzi" else "image/jpeg"
        return deliver_file(
            target,
            data_root=storage.root,
            internal_redirects=internal_file_redirects,
            media_type=media_type,
            cache_control="private, max-age=3600",
            headers={"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer"},
        )

    return purger
