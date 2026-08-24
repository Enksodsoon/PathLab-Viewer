import csv
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from typing import Annotated, Any

from fastapi import (
    Cookie,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from .assessment_analytics import build_aggregate, latest_aggregate, snapshot_aggregate
from .assessment_assets import (
    AssessmentAssetError,
    definition_slide_ids,
    grant_manifest,
    prepare_asset_grants,
    remove_asset_grants,
)
from .assessment_contract import (
    AssessmentContractError,
    CompiledAssessment,
    compile_assessment,
    score_item,
)
from .domain import SlideState
from .identity import staff_organization_context
from .models import (
    AssessmentAccessThrottle,
    AssessmentAdministration,
    AssessmentAssetGrant,
    AssessmentAttempt,
    AssessmentDraft,
    AssessmentGradebookRow,
    AssessmentMutationReceipt,
    AssessmentParticipant,
    AssessmentRelease,
    AssessmentResponse,
    AssessmentRosterSnapshot,
    AssessmentScoreVersion,
    AssessmentSession,
    AssessmentVersion,
    Cohort,
    CohortEnrollment,
    LearnerProfile,
    PublicationGrant,
    Session,
    Slide,
)
from .publication import INDIVIDUAL, delivery_version
from .runtime_protection import (
    begin_assessment_cooldown,
    bind_assessment_administration,
    request_assessment_protection,
)
from .storage import StorageLayout
from .time_support import as_utc, utc_now


class DraftCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    document: dict[str, Any]


class DraftPatch(BaseModel):
    document: dict[str, Any]


class DraftDuplicate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class QuestionImport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_draft_id: str = Field(alias="sourceDraftId")
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=100)
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class ClassPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    status: str | None = None


class EnrollmentPatch(BaseModel):
    status: str


class ImportRows(BaseModel):
    rows: str = Field(min_length=1, max_length=64 * 1024)
    checksum: str | None = None


class PublishSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mode: str
    cohort_id: str | None = Field(default=None, alias="cohortId")
    duration_seconds: int = Field(default=3600, alias="durationSeconds", ge=1, le=14_400)
    max_attempts: int = Field(default=1, alias="maxAttempts", ge=1, le=3)
    access_code: str | None = Field(default=None, alias="accessCode", min_length=4, max_length=64)
    synthetic_fixture: bool = Field(default=False, alias="syntheticFixture")


class AccessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    kind: str
    public_id: str = Field(alias="publicId")
    student_identifier: str | None = Field(default=None, alias="studentIdentifier")
    access_code: str | None = Field(default=None, alias="accessCode")
    takeover: bool = False


class ResponseSave(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    item_id: str = Field(alias="itemId")
    revision: int = Field(ge=1)
    response: dict[str, Any]


class ResponseBatch(BaseModel):
    responses: list[ResponseSave] = Field(min_length=1, max_length=10)


class RetentionPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    retention_days: int = Field(alias="retentionDays", ge=1, le=3650)
    hold: bool


class ManualGradeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    attempt_id: str = Field(alias="attemptId")
    item_id: str = Field(alias="itemId")
    points: Decimal
    expected_score_version: int = Field(alias="expectedScoreVersion", ge=1)


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    show_score: bool = Field(default=True, alias="showScore")
    show_answers: bool = Field(default=False, alias="showAnswers")
    show_feedback: bool = Field(default=False, alias="showFeedback")


class DraftJson(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    status: str
    revision: int
    document: dict[str, Any]


def _draft_json(draft: AssessmentDraft) -> dict[str, Any]:
    return DraftJson.model_validate(draft).model_dump()


def _parse_rows(raw: str) -> list[tuple[str, str | None]]:
    parsed: list[tuple[str, str | None]] = []
    seen: set[str] = set()
    for row in csv.reader(StringIO(raw)):
        if not row or not row[0].strip():
            continue
        identifier = row[0].strip()
        if len(identifier) > 200 or identifier.casefold() in seen:
            raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_INVALID"})
        seen.add(identifier.casefold())
        display_name = row[1].strip()[:160] if len(row) > 1 and row[1].strip() else None
        parsed.append((identifier, display_name))
    if not parsed or len(parsed) > 500:
        raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"})
    return parsed


def _rows_checksum(rows: list[tuple[str, str | None]]) -> str:
    canonical = "\n".join(f"{identifier.casefold()}\t{name or ''}" for identifier, name in rows)
    return hashlib.sha256(canonical.encode()).hexdigest()


def register_assessment_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[..., Iterator[OrmSession]],
    admin_dependency: Callable[..., Session],
    csrf_dependency: Callable[..., Session],
    identifier_secret: str,
    secure_cookies: bool,
    storage: StorageLayout,
) -> None:
    Database = Annotated[OrmSession, Depends(database_dependency)]
    AdminSession = Annotated[Session, Depends(admin_dependency)]
    CsrfSession = Annotated[Session, Depends(csrf_dependency)]
    ActiveOrganization = Annotated[str | None, Header(alias="X-PathLab-Organization")]

    def organization_id(authenticated: Session, database: OrmSession, requested: str | None) -> str:
        context = staff_organization_context(database, authenticated.user_id, requested)
        if context is None:
            raise HTTPException(status_code=403, detail={"code": "ORGANIZATION_FORBIDDEN"})
        return context.organization.id

    def owned_draft(database: OrmSession, draft_id: str, org_id: str) -> AssessmentDraft:
        draft = database.scalar(
            select(AssessmentDraft).where(
                AssessmentDraft.id == draft_id, AssessmentDraft.organization_id == org_id
            )
        )
        if draft is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_DRAFT_NOT_FOUND"})
        return draft

    @app.get("/api/v2/assessment/administrations/{public_id}")
    def administration_metadata(
        public_id: str, response: Response, _: Database
    ) -> dict[str, object]:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        administration = _.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.public_id == public_id,
                AssessmentAdministration.status != "purged",
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        version = _.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        return {
            "publicId": administration.public_id,
            "mode": administration.mode,
            "status": administration.status,
            "durationSeconds": administration.duration_seconds,
            "closesAt": administration.closes_at,
            "manifest": version.learner_manifest,
            "assets": grant_manifest(_, administration.id),
        }

    @app.get("/api/v2/assessment/practice/{public_id}")
    def practice_bundle(public_id: str, database: Database) -> dict[str, object]:
        administration = database.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.public_id == public_id,
                AssessmentAdministration.mode == "practice",
                AssessmentAdministration.status == "open",
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        return {
            "publicId": public_id,
            "storage": "browser-local",
            "definition": version.definition,
            "assets": grant_manifest(database, administration.id),
        }

    def student_session(
        database: OrmSession,
        raw_token: str | None,
        csrf_token: str | None,
    ) -> AssessmentSession:
        if raw_token is None:
            raise HTTPException(status_code=401, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        stored = database.get(AssessmentSession, hashlib.sha256(raw_token.encode()).hexdigest())
        if (
            stored is None
            or stored.revoked_at is not None
            or as_utc(stored.expires_at) <= utc_now()
            or csrf_token is None
            or not hmac.compare_digest(stored.csrf_token, csrf_token)
        ):
            raise HTTPException(status_code=403, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        return stored

    def mutation_receipt(
        database: OrmSession,
        stored_session: AssessmentSession,
        operation: str,
        idempotency_key: str,
        request_payload: object,
    ) -> tuple[AssessmentMutationReceipt | None, str, str]:
        if not 1 <= len(idempotency_key) <= 200:
            raise HTTPException(
                status_code=400, detail={"code": "ASSESSMENT_IDEMPOTENCY_KEY_INVALID"}
            )
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()
        request_hash = hashlib.sha256(
            json.dumps(
                request_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode()
        ).hexdigest()
        existing = database.scalar(
            select(AssessmentMutationReceipt).where(
                AssessmentMutationReceipt.session_id == stored_session.id,
                AssessmentMutationReceipt.operation == operation,
                AssessmentMutationReceipt.key_hash == key_hash,
            )
        )
        if existing is not None and not hmac.compare_digest(existing.request_hash, request_hash):
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IDEMPOTENCY_CONFLICT"})
        return existing, key_hash, request_hash

    def persist_receipt(
        database: OrmSession,
        stored_session: AssessmentSession,
        operation: str,
        key_hash: str,
        request_hash: str,
        response_payload: dict[str, Any],
        status_code: int,
    ) -> None:
        database.add(
            AssessmentMutationReceipt(
                session_id=stored_session.id,
                operation=operation,
                key_hash=key_hash,
                request_hash=request_hash,
                response=response_payload,
                status_code=status_code,
            )
        )

    def consume_access_throttle(
        database: OrmSession,
        request: Request,
        payload: AccessRequest,
    ) -> None:
        if payload.kind != "roster":
            return
        now = utc_now()
        window = now.replace(minute=(now.minute // 5) * 5, second=0, microsecond=0)
        network = request.client.host if request.client is not None else "unknown"
        identifier = (payload.student_identifier or "missing").casefold()
        key_hash = hmac.new(
            identifier_secret.encode(),
            f"{payload.public_id}\0{network}\0{identifier}".encode(),
            hashlib.sha256,
        ).hexdigest()
        throttle = database.scalar(
            select(AssessmentAccessThrottle).where(
                AssessmentAccessThrottle.scope == "roster-access",
                AssessmentAccessThrottle.key_hash == key_hash,
                AssessmentAccessThrottle.window_started_at == window,
            )
        )
        if throttle is not None and throttle.attempts >= 10:
            raise HTTPException(
                status_code=429,
                detail={"code": "ASSESSMENT_ACCESS_INVALID"},
                headers={"Retry-After": "300"},
            )
        if throttle is None:
            database.add(
                AssessmentAccessThrottle(
                    scope="roster-access",
                    key_hash=key_hash,
                    window_started_at=window,
                )
            )
        else:
            throttle.attempts += 1
        database.commit()

    @app.post("/api/v2/assessment/access", status_code=status.HTTP_201_CREATED)
    def access_assessment(
        payload: AccessRequest,
        request: Request,
        response: Response,
        database: Database,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ) -> dict[str, Any]:
        if not 1 <= len(idempotency_key) <= 200:
            raise HTTPException(
                status_code=400, detail={"code": "ASSESSMENT_IDEMPOTENCY_KEY_INVALID"}
            )
        consume_access_throttle(database, request, payload)
        administration = database.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.public_id == payload.public_id,
                AssessmentAdministration.status == "open",
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        session_material = f"access-session\0{payload.public_id}\0{idempotency_key}"
        raw_token = hmac.new(
            identifier_secret.encode(), session_material.encode(), hashlib.sha256
        ).hexdigest()
        csrf_token = hmac.new(
            identifier_secret.encode(), f"csrf\0{session_material}".encode(), hashlib.sha256
        ).hexdigest()
        session_id = hashlib.sha256(raw_token.encode()).hexdigest()
        existing_session = database.get(AssessmentSession, session_id)
        receipt: str | None = None
        participant: AssessmentParticipant | None = None
        if payload.kind == "anonymous" and administration.mode == "formative":
            receipt = hmac.new(
                identifier_secret.encode(),
                f"anonymous-receipt\0{payload.public_id}\0{idempotency_key}".encode(),
                hashlib.sha256,
            ).hexdigest()
            if existing_session is not None:
                existing_participant = database.get(
                    AssessmentParticipant, existing_session.participant_id
                )
                if (
                    existing_participant is None
                    or existing_participant.administration_id != administration.id
                    or existing_participant.kind != "anonymous"
                ):
                    raise HTTPException(
                        status_code=409,
                        detail={"code": "ASSESSMENT_IDEMPOTENCY_CONFLICT"},
                    )
                participant = existing_participant
            else:
                participant = AssessmentParticipant(
                    administration_id=administration.id,
                    kind="anonymous",
                    receipt_hash=hashlib.sha256(receipt.encode()).hexdigest(),
                )
                database.add(participant)
                database.flush()
        elif (
            payload.kind == "roster"
            and administration.mode in {"formative", "quiz"}
            and payload.student_identifier is not None
            and payload.access_code is not None
            and administration.access_code_hash is not None
        ):
            code_hash = hmac.new(
                identifier_secret.encode(),
                payload.access_code.encode(),
                hashlib.sha256,
            ).hexdigest()
            identifier_hash = hmac.new(
                identifier_secret.encode(),
                payload.student_identifier.casefold().encode(),
                hashlib.sha256,
            ).hexdigest()
            snapshot = database.scalar(
                select(AssessmentRosterSnapshot).where(
                    AssessmentRosterSnapshot.administration_id == administration.id,
                    AssessmentRosterSnapshot.login_identifier_hash == identifier_hash,
                )
            )
            if snapshot is None or not hmac.compare_digest(
                administration.access_code_hash, code_hash
            ):
                raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
            participant = database.scalar(
                select(AssessmentParticipant).where(
                    AssessmentParticipant.administration_id == administration.id,
                    AssessmentParticipant.learner_id == snapshot.learner_id,
                )
            )
            if participant is None:
                participant = AssessmentParticipant(
                    administration_id=administration.id,
                    learner_id=snapshot.learner_id,
                    kind="roster",
                )
                database.add(participant)
                database.flush()
        else:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        if participant is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        if existing_session is not None:
            if existing_session.participant_id != participant.id:
                raise HTTPException(
                    status_code=409, detail={"code": "ASSESSMENT_IDEMPOTENCY_CONFLICT"}
                )
            existing_session.expires_at = utc_now() + timedelta(hours=5)
            database.commit()
            response.set_cookie(
                "pathlab_assessment_session",
                raw_token,
                httponly=True,
                secure=secure_cookies,
                samesite="lax",
                max_age=5 * 3600,
            )
            return {
                "kind": participant.kind,
                "publicId": administration.public_id,
                "csrfToken": csrf_token,
                **({"receipt": receipt} if receipt is not None else {}),
            }
        active_sessions = database.scalars(
            select(AssessmentSession).where(
                AssessmentSession.participant_id == participant.id,
                AssessmentSession.revoked_at.is_(None),
                AssessmentSession.expires_at > utc_now(),
            )
        ).all()
        if participant.kind == "roster" and active_sessions and not payload.takeover:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_DEVICE_ACTIVE"})
        generation = max((item.device_generation for item in active_sessions), default=0) + 1
        if payload.takeover:
            for active_session in active_sessions:
                active_session.revoked_at = utc_now()
        database.add(
            AssessmentSession(
                id=session_id,
                participant_id=participant.id,
                csrf_token=csrf_token,
                device_generation=generation,
                expires_at=utc_now() + timedelta(hours=5),
            )
        )
        database.commit()
        response.set_cookie(
            "pathlab_assessment_session",
            raw_token,
            httponly=True,
            secure=secure_cookies,
            samesite="lax",
            max_age=5 * 3600,
        )
        return {
            "kind": participant.kind,
            "publicId": administration.public_id,
            "csrfToken": csrf_token,
            **({"receipt": receipt} if receipt is not None else {}),
        }

    @app.get("/api/v2/assessment/session")
    def restore_session(
        database: Database,
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        participant = database.get(AssessmentParticipant, stored_session.participant_id)
        administration = (
            database.get(AssessmentAdministration, participant.administration_id)
            if participant is not None
            else None
        )
        version = (
            database.get(AssessmentVersion, administration.version_id)
            if administration is not None
            else None
        )
        if participant is None or administration is None or version is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        attempt = database.scalar(
            select(AssessmentAttempt)
            .where(
                AssessmentAttempt.participant_id == participant.id,
                AssessmentAttempt.status == "active",
            )
            .order_by(AssessmentAttempt.ordinal.desc())
        )
        responses: list[dict[str, Any]] = []
        if attempt is not None:
            responses = [
                {
                    "itemId": item.item_id,
                    "revision": item.revision,
                    "response": item.response,
                }
                for item in database.scalars(
                    select(AssessmentResponse)
                    .where(AssessmentResponse.attempt_id == attempt.id)
                    .order_by(AssessmentResponse.item_id)
                )
            ]
        manifest = json.loads(json.dumps(version.learner_manifest))
        if (
            attempt is not None
            and manifest.get("settings", {}).get("shuffleQuestions") is True
        ):
            manifest["items"] = sorted(
                manifest.get("items", []),
                key=lambda item: hashlib.sha256(
                    f"{attempt.order_seed}:{item.get('id', '')}".encode()
                ).digest(),
            )
        return {
            "kind": participant.kind,
            "publicId": administration.public_id,
            "status": administration.status,
            "manifest": manifest,
            "deviceGeneration": stored_session.device_generation,
            "attempt": (
                {
                    "id": attempt.id,
                    "ordinal": attempt.ordinal,
                    "status": attempt.status,
                    "startedAt": attempt.started_at,
                    "responses": responses,
                }
                if attempt is not None
                else None
            ),
        }

    @app.post("/api/v2/assessment/session/logout", status_code=status.HTTP_204_NO_CONTENT)
    def logout_session(
        response: Response,
        database: Database,
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> None:
        stored_session = student_session(database, raw_token, csrf_token)
        stored_session.revoked_at = utc_now()
        database.commit()
        response.delete_cookie(
            "pathlab_assessment_session",
            httponly=True,
            secure=secure_cookies,
            samesite="lax",
        )

    @app.post("/api/v2/assessment/attempts", status_code=status.HTTP_201_CREATED)
    def start_attempt(
        database: Database,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        receipt, key_hash, request_hash = mutation_receipt(
            database, stored_session, "attempt:start", idempotency_key, {}
        )
        if receipt is not None:
            return receipt.response
        participant = database.get(AssessmentParticipant, stored_session.participant_id)
        if participant is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        administration = database.get(AssessmentAdministration, participant.administration_id)
        if administration is None or administration.status != "open":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_NOT_OPEN"})
        count = int(
            database.scalar(
                select(func.count(AssessmentAttempt.id)).where(
                    AssessmentAttempt.participant_id == participant.id
                )
            )
            or 0
        )
        if count >= administration.max_attempts:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ATTEMPT_LIMIT"})
        attempt = AssessmentAttempt(
            administration_id=administration.id,
            participant_id=participant.id,
            ordinal=count + 1,
            order_seed=hashlib.sha256(f"{participant.id}:{count + 1}".encode()).hexdigest(),
        )
        database.add(attempt)
        database.flush()
        result = {
            "id": attempt.id,
            "ordinal": attempt.ordinal,
            "status": attempt.status,
            "startedAt": attempt.started_at.isoformat(),
        }
        persist_receipt(
            database,
            stored_session,
            "attempt:start",
            key_hash,
            request_hash,
            result,
            status.HTTP_201_CREATED,
        )
        database.commit()
        return result

    def owned_attempt(
        database: OrmSession, attempt_id: str, stored_session: AssessmentSession
    ) -> AssessmentAttempt:
        attempt = database.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.id == attempt_id,
                AssessmentAttempt.participant_id == stored_session.participant_id,
            )
        )
        if attempt is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ATTEMPT_NOT_FOUND"})
        return attempt

    @app.patch("/api/v2/assessment/attempts/{attempt_id}/responses")
    def save_responses(
        attempt_id: str,
        payload: ResponseBatch,
        database: Database,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        if len(payload.model_dump_json(by_alias=True).encode()) > 64 * 1024:
            raise HTTPException(
                status_code=413, detail={"code": "ASSESSMENT_RESPONSE_BATCH_LIMIT"}
            )
        receipt, key_hash, request_hash = mutation_receipt(
            database,
            stored_session,
            f"attempt:{attempt_id}:responses",
            idempotency_key,
            payload.model_dump(mode="json", by_alias=True),
        )
        if receipt is not None:
            return receipt.response
        attempt = owned_attempt(database, attempt_id, stored_session)
        if attempt.status != "active":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ATTEMPT_CLOSED"})
        administration = database.get(AssessmentAdministration, attempt.administration_id)
        if administration is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_NOT_FOUND"})
        if (
            as_utc(attempt.started_at) + timedelta(seconds=administration.duration_seconds)
            <= utc_now()
        ):
            result = finalize_attempt(
                database,
                attempt,
                administration,
                enforce_required=False,
                final_status="auto_submitted",
            )
            database.commit()
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_DEADLINE_SUBMITTED", "result": result},
            )
        existing_by_item = {
            item.item_id: item
            for item in database.scalars(
                select(AssessmentResponse).where(
                    AssessmentResponse.attempt_id == attempt.id,
                    AssessmentResponse.item_id.in_([item.item_id for item in payload.responses]),
                )
            )
        }
        conflicts = [
            {
                "itemId": incoming.item_id,
                "revision": existing.revision,
                "response": existing.response,
            }
            for incoming in payload.responses
            if (existing := existing_by_item.get(incoming.item_id)) is not None
            and (
                incoming.revision < existing.revision
                or (
                    incoming.revision == existing.revision
                    and incoming.response != existing.response
                )
            )
        ]
        if conflicts:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_RESPONSE_CONFLICT",
                    "authoritative": conflicts,
                },
            )
        for incoming in payload.responses:
            existing = existing_by_item.get(incoming.item_id)
            if existing is None:
                database.add(
                    AssessmentResponse(
                        attempt_id=attempt.id,
                        item_id=incoming.item_id,
                        revision=incoming.revision,
                        response=incoming.response,
                    )
                )
            elif incoming.revision > existing.revision:
                existing.revision = incoming.revision
                existing.response = incoming.response
                existing.updated_at = utc_now()
        result = {"saved": len(payload.responses)}
        persist_receipt(
            database,
            stored_session,
            f"attempt:{attempt_id}:responses",
            key_hash,
            request_hash,
            result,
            status.HTTP_200_OK,
        )
        database.commit()
        return result

    def finalize_attempt(
        database: OrmSession,
        attempt: AssessmentAttempt,
        administration: AssessmentAdministration,
        *,
        enforce_required: bool,
        final_status: str,
    ) -> dict[str, Any]:
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_VERSION_MISSING"})
        latest = {
            item.item_id: item.response
            for item in database.scalars(
                select(AssessmentResponse).where(AssessmentResponse.attempt_id == attempt.id)
            )
        }
        required_missing = [
            item["id"]
            for item in version.definition["items"]
            if item.get("required") and item["id"] not in latest
        ]
        if enforce_required and required_missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSESSMENT_REQUIRED_MISSING", "itemIds": required_missing},
            )
        scored = [
            score_item(item, latest.get(item["id"], {})) for item in version.definition["items"]
        ]
        points = sum((value for value in scored if value is not None), start=Decimal("0"))
        maximum = sum(
            (
                Decimal(str(item.get("points", "0")))
                for item in version.definition["items"]
                if item.get("type") != "information"
            ),
            start=Decimal("0"),
        )
        needs_grading = any(
            value is None and item.get("type") != "information" and item["id"] in latest
            for item, value in zip(version.definition["items"], scored, strict=True)
        )
        score_version = (
            int(
                database.scalar(
                    select(func.coalesce(func.max(AssessmentScoreVersion.version), 0)).where(
                        AssessmentScoreVersion.attempt_id == attempt.id
                    )
                )
                or 0
            )
            + 1
        )
        score = AssessmentScoreVersion(
            attempt_id=attempt.id,
            version=score_version,
            points=points,
            maximum_points=maximum,
            breakdown={
                item["id"]: str(value) if value is not None else None
                for item, value in zip(version.definition["items"], scored, strict=True)
            },
        )
        attempt.status = final_status
        attempt.submitted_at = utc_now()
        database.add(score)
        database.flush()
        participant = database.get(AssessmentParticipant, attempt.participant_id)
        if participant is not None and participant.kind == "roster":
            gradebook = database.scalar(
                select(AssessmentGradebookRow).where(
                    AssessmentGradebookRow.administration_id == attempt.administration_id,
                    AssessmentGradebookRow.participant_id == participant.id,
                )
            )
            if gradebook is None:
                gradebook = AssessmentGradebookRow(
                    administration_id=attempt.administration_id,
                    participant_id=participant.id,
                )
                database.add(gradebook)
            gradebook.score_version_id = score.id
            gradebook.status = "needs_grading" if needs_grading else "graded"
        return {
            "status": final_status,
            "score": {
                "points": f"{Decimal(str(score.points)):.3f}",
                "maximumPoints": f"{Decimal(str(score.maximum_points)):.3f}",
            },
            "anonymousAggregateOnly": participant is None or participant.kind == "anonymous",
            "needsGrading": needs_grading,
            "requiredMissing": required_missing,
        }

    @app.post("/api/v2/assessment/attempts/{attempt_id}/submit")
    def submit_attempt(
        attempt_id: str,
        database: Database,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        receipt, key_hash, request_hash = mutation_receipt(
            database,
            stored_session,
            f"attempt:{attempt_id}:submit",
            idempotency_key,
            {},
        )
        if receipt is not None:
            return receipt.response
        attempt = owned_attempt(database, attempt_id, stored_session)
        if attempt.status != "active":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ATTEMPT_CLOSED"})
        administration = database.get(AssessmentAdministration, attempt.administration_id)
        if administration is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_NOT_FOUND"})
        expired = (
            as_utc(attempt.started_at) + timedelta(seconds=administration.duration_seconds)
            <= utc_now()
        )
        result = finalize_attempt(
            database,
            attempt,
            administration,
            enforce_required=not expired,
            final_status="auto_submitted" if expired else "submitted",
        )
        public_result = dict(result)
        if administration.mode == "quiz":
            # Quiz answers and scores remain unavailable until a deliberate release.
            public_result.pop("score", None)
        persist_receipt(
            database,
            stored_session,
            f"attempt:{attempt_id}:submit",
            key_hash,
            request_hash,
            public_result,
            status.HTTP_200_OK,
        )
        database.commit()
        return public_result

    @app.get("/api/v2/assessment/attempts/{attempt_id}/result")
    def attempt_result(
        attempt_id: str,
        database: Database,
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        attempt = owned_attempt(database, attempt_id, stored_session)
        if attempt.status == "active":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ATTEMPT_ACTIVE"})
        administration = database.get(AssessmentAdministration, attempt.administration_id)
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        release = database.scalar(
            select(AssessmentRelease)
            .where(AssessmentRelease.administration_id == administration.id)
            .order_by(AssessmentRelease.released_at.desc(), AssessmentRelease.id.desc())
        )
        if administration.mode == "quiz" and release is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_RESULT_NOT_RELEASED"})
        policy = (
            release.policy
            if release is not None
            else {"showScore": True, "showAnswers": False, "showFeedback": True}
        )
        score = database.scalar(
            select(AssessmentScoreVersion)
            .where(AssessmentScoreVersion.attempt_id == attempt.id)
            .order_by(AssessmentScoreVersion.version.desc())
        )
        if score is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_RESULT_NOT_FOUND"})
        result: dict[str, Any] = {
            "status": attempt.status,
            "released": release is not None,
            "policy": policy,
            "scoreVersion": score.version,
        }
        if policy.get("showScore", False):
            result["score"] = {
                "points": f"{Decimal(str(score.points)):.3f}",
                "maximumPoints": f"{Decimal(str(score.maximum_points)):.3f}",
            }
        if policy.get("showAnswers", False):
            result["breakdown"] = score.breakdown
        return result

    @app.get("/api/v2/admin/assessment/drafts")
    def list_drafts(
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        drafts = database.scalars(
            select(AssessmentDraft)
            .where(AssessmentDraft.organization_id == org_id)
            .order_by(AssessmentDraft.updated_at.desc(), AssessmentDraft.id)
        ).all()
        return {"items": [_draft_json(item) for item in drafts], "total": len(drafts)}

    @app.post("/api/v2/admin/assessment/drafts", status_code=status.HTTP_201_CREATED)
    def create_draft(
        payload: DraftCreate,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        draft = AssessmentDraft(
            organization_id=org_id,
            title=payload.title,
            document=payload.document,
            created_by_user_id=authenticated.user_id,
        )
        database.add(draft)
        database.commit()
        return _draft_json(draft)

    @app.get("/api/v2/admin/assessment/drafts/{draft_id}")
    def get_draft(
        draft_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        return _draft_json(owned_draft(database, draft_id, org_id))

    @app.patch("/api/v2/admin/assessment/drafts/{draft_id}")
    def save_draft(
        draft_id: str,
        payload: DraftPatch,
        authenticated: CsrfSession,
        database: Database,
        expected_revision: Annotated[str | None, Header(alias="If-Match")] = None,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        draft = owned_draft(database, draft_id, org_id)
        if expected_revision is None or expected_revision.strip('"') != str(draft.revision):
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_DRAFT_CONFLICT", "revision": draft.revision},
            )
        draft.document = payload.document
        draft.title = str(payload.document.get("title", draft.title))[:200]
        draft.revision += 1
        draft.updated_at = utc_now()
        database.commit()
        return _draft_json(draft)

    def fresh_item(source: dict[str, Any]) -> dict[str, Any]:
        item: dict[str, Any] = json.loads(json.dumps(source))
        item["id"] = secrets.token_hex(16)
        option_ids: dict[str, str] = {}
        for option in item.get("options", []):
            old_id = str(option.get("id", ""))
            option["id"] = secrets.token_hex(16)
            option_ids[old_id] = option["id"]
        answer = item.get("answerKey")
        if isinstance(answer, dict) and isinstance(answer.get("optionIds"), list):
            answer["optionIds"] = [
                option_ids[value] for value in answer["optionIds"] if value in option_ids
            ]
        return item

    @app.post(
        "/api/v2/admin/assessment/drafts/{draft_id}/duplicate",
        status_code=status.HTTP_201_CREATED,
    )
    def duplicate_draft(
        draft_id: str,
        payload: DraftDuplicate,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        source = owned_draft(database, draft_id, org_id)
        document = json.loads(json.dumps(source.document))
        document["items"] = [fresh_item(item) for item in document.get("items", [])]
        document["title"] = payload.title or f"{source.title} copy"
        duplicate = AssessmentDraft(
            organization_id=org_id,
            title=document["title"],
            document=document,
            created_by_user_id=authenticated.user_id,
        )
        database.add(duplicate)
        database.commit()
        return _draft_json(duplicate)

    @app.post("/api/v2/admin/assessment/drafts/{draft_id}/import-questions")
    def import_questions(
        draft_id: str,
        payload: QuestionImport,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        destination = owned_draft(database, draft_id, org_id)
        source = owned_draft(database, payload.source_draft_id, org_id)
        if destination.revision != payload.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_DRAFT_CONFLICT", "revision": destination.revision},
            )
        requested = set(payload.item_ids)
        selected = [
            fresh_item(item)
            for item in source.document.get("items", [])
            if item.get("id") in requested
        ]
        if len(selected) != len(requested):
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ITEM_NOT_FOUND"})
        if len(destination.document.get("items", [])) + len(selected) > 100:
            raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ITEM_LIMIT"})
        document = json.loads(json.dumps(destination.document))
        document["items"] = [*document.get("items", []), *selected]
        destination.document = document
        destination.revision += 1
        destination.updated_at = utc_now()
        database.commit()
        return _draft_json(destination)

    @app.post("/api/v2/admin/assessment/drafts/{draft_id}/archive")
    def archive_draft(
        draft_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        draft = owned_draft(database, draft_id, org_id)
        draft.status = "archived"
        draft.archived_at = utc_now()
        database.commit()
        return _draft_json(draft)

    def compile_owned(
        draft_id: str, authenticated: Session, database: OrmSession, requested_org: str | None
    ) -> tuple[AssessmentDraft, CompiledAssessment]:
        draft = owned_draft(
            database, draft_id, organization_id(authenticated, database, requested_org)
        )
        try:
            return draft, compile_assessment(draft.document)
        except AssessmentContractError as error:
            raise HTTPException(status_code=422, detail={"code": str(error)}) from error

    @app.post("/api/v2/admin/assessment/drafts/{draft_id}/preview")
    def preview_draft(
        draft_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        _, compiled = compile_owned(draft_id, authenticated, database, requested_org)
        return {"learnerManifest": compiled.learner_manifest, "checksum": compiled.checksum}

    @app.post(
        "/api/v2/admin/assessment/drafts/{draft_id}/publish",
        status_code=status.HTTP_201_CREATED,
    )
    def publish_draft(
        draft_id: str,
        authenticated: CsrfSession,
        database: Database,
        payload: PublishSettings | None = None,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        draft, compiled = compile_owned(draft_id, authenticated, database, requested_org)
        version_number = (
            int(
                database.scalar(
                    select(func.coalesce(func.max(AssessmentVersion.version), 0)).where(
                        AssessmentVersion.draft_id == draft.id
                    )
                )
                or 0
            )
            + 1
        )
        version = AssessmentVersion(
            organization_id=draft.organization_id,
            draft_id=draft.id,
            version=version_number,
            schema="pathlab.assessment/1",
            checksum=compiled.checksum,
            definition=compiled.definition,
            learner_manifest=compiled.learner_manifest,
        )
        database.add(version)
        try:
            database.commit()
        except IntegrityError:
            database.rollback()
            existing = database.scalar(
                select(AssessmentVersion).where(AssessmentVersion.checksum == compiled.checksum)
            )
            if existing is None:
                raise
            version = existing
        administration = None
        if payload is not None:
            if payload.mode not in {"practice", "formative", "quiz"}:
                raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_MODE_INVALID"})
            if payload.mode == "quiz" and payload.cohort_id is None:
                raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_ROSTER_REQUIRED"})
            if payload.mode == "quiz" and payload.access_code is None:
                raise HTTPException(
                    status_code=422, detail={"code": "ASSESSMENT_ACCESS_CODE_REQUIRED"}
                )
            if payload.mode != "practice":
                cooldown_cutoff = utc_now() - timedelta(seconds=120)
                busy = database.scalar(
                    select(AssessmentAdministration.id).where(
                        AssessmentAdministration.mode.in_(("formative", "quiz")),
                        AssessmentAdministration.status.in_(("preparing", "open"))
                        | (
                            (AssessmentAdministration.status == "closed")
                            & (AssessmentAdministration.closes_at > cooldown_cutoff)
                        ),
                    )
                )
                if busy is not None:
                    raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_RUNTIME_BUSY"})
            administration = AssessmentAdministration(
                organization_id=draft.organization_id,
                version_id=version.id,
                cohort_id=payload.cohort_id,
                mode=payload.mode,
                status="open" if payload.mode == "practice" else "preparing",
                duration_seconds=payload.duration_seconds,
                max_attempts=payload.max_attempts,
                access_code_hash=(
                    hmac.new(
                        identifier_secret.encode(),
                        payload.access_code.encode(),
                        hashlib.sha256,
                    ).hexdigest()
                    if payload.access_code is not None
                    else None
                ),
                settings={"syntheticFixture": payload.synthetic_fixture},
            )
            database.add(administration)
            database.flush()
            if payload.cohort_id is not None:
                learners = database.scalars(
                    select(LearnerProfile)
                    .join(
                        CohortEnrollment,
                        CohortEnrollment.learner_id == LearnerProfile.id,
                    )
                    .where(
                        CohortEnrollment.cohort_id == payload.cohort_id,
                        CohortEnrollment.status == "active",
                    )
                    .limit(501)
                ).all()
                if len(learners) > 500:
                    raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"})
                for learner in learners:
                    if learner.login_identifier_hash is None:
                        raise HTTPException(
                            status_code=422,
                            detail={"code": "ASSESSMENT_LEARNER_IDENTIFIER_MISSING"},
                        )
                    database.add(
                        AssessmentRosterSnapshot(
                            administration_id=administration.id,
                            learner_id=learner.id,
                            login_identifier_hash=learner.login_identifier_hash,
                            display_name=learner.display_name,
                        )
                    )
            if payload.mode == "practice":
                try:
                    prepare_asset_grants(
                        database,
                        storage,
                        administration,
                        definition_slide_ids(version.definition),
                    )
                except AssessmentAssetError as error:
                    database.rollback()
                    raise HTTPException(status_code=409, detail={"code": error.code}) from error
            database.commit()
        return {
            "id": version.id,
            "version": version.version,
            "schema": version.schema,
            "checksum": version.checksum,
            "learnerManifest": version.learner_manifest,
            "publicId": administration.public_id if administration is not None else None,
            "administrationId": administration.id if administration is not None else None,
        }

    @app.get("/api/v2/admin/assessment/slides")
    def eligible_slides(
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
        query: str = "",
        limit: int = 20,
    ) -> dict[str, Any]:
        organization_id(authenticated, database, requested_org)
        statement = (
            select(Slide)
            .join(
                PublicationGrant,
                (PublicationGrant.slide_id == Slide.id)
                & (PublicationGrant.source_type == INDIVIDUAL)
                & (PublicationGrant.source_id == Slide.id),
            )
            .where(
                Slide.state == SlideState.PUBLISHED,
                Slide.privacy_status == "passed",
                Slide.render_mode == "static_dzi",
                Slide.trashed_at.is_(None),
                Slide.sha256.is_not(None),
                Slide.derivative_file_count > 0,
            )
            .order_by(Slide.updated_at.desc(), Slide.id)
            .limit(max(1, min(limit, 50)))
        )
        if query.strip():
            statement = statement.where(Slide.display_name.ilike(f"%{query.strip()}%"))
        slides = database.scalars(statement).all()
        return {
            "items": [
                {
                    "id": slide.id,
                    "publicId": slide.public_id,
                    "displayName": slide.display_name,
                    "tileSource": (
                        f"/tiles/{slide.public_id}/{delivery_version(slide)}/slide.dzi"
                    ),
                    "thumbnail": (
                        f"/tiles/{slide.public_id}/thumbnail.jpg"
                        if slide.thumbnail_filename is not None
                        else None
                    ),
                }
                for slide in slides
            ]
        }

    @app.get("/api/v2/admin/assessment/administrations")
    def list_administrations(
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        rows = database.execute(
            select(AssessmentAdministration, AssessmentVersion, AssessmentDraft)
            .join(AssessmentVersion, AssessmentVersion.id == AssessmentAdministration.version_id)
            .join(AssessmentDraft, AssessmentDraft.id == AssessmentVersion.draft_id)
            .where(AssessmentAdministration.organization_id == org_id)
            .order_by(AssessmentAdministration.created_at.desc(), AssessmentAdministration.id)
        ).all()
        return {
            "items": [
                {
                    "id": administration.id,
                    "publicId": administration.public_id,
                    "title": draft.title,
                    "mode": administration.mode,
                    "status": administration.status,
                    "createdAt": administration.created_at,
                    "responses": int(
                        database.scalar(
                            select(func.count(AssessmentAttempt.id)).where(
                                AssessmentAttempt.administration_id == administration.id,
                                AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
                            )
                        )
                        or 0
                    ),
                }
                for administration, _, draft in rows
            ],
            "total": len(rows),
        }

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/prepare")
    def prepare_administration(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if administration.status != "preparing":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_VERSION_MISSING"})
        slide_ids = definition_slide_ids(version.definition)
        protection = request_assessment_protection(
            database, assessment_administration_id=administration.id
        )
        if protection.conflicting_runtime:
            database.commit()
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_RUNTIME_BUSY"},
                headers={"Retry-After": "120"},
            )
        if protection.running_jobs:
            database.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_DRAINING",
                    "runningJobs": protection.running_jobs,
                },
                headers={"Retry-After": "2"},
            )
        try:
            grants = prepare_asset_grants(database, storage, administration, slide_ids)
        except AssessmentAssetError as error:
            database.rollback()
            raise HTTPException(status_code=409, detail={"code": error.code}) from error
        database.commit()
        return {
            "id": administration.id,
            "status": administration.status,
            "slidesPrepared": len(grants),
            "assets": grant_manifest(database, administration.id),
        }

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/close")
    def close_administration(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        administration = database.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.id == administration_id,
                AssessmentAdministration.organization_id == org_id,
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        administration.status = "closed"
        administration.closes_at = utc_now()
        if administration.mode != "practice":
            begin_assessment_cooldown(database, now=administration.closes_at)
        for grant in database.scalars(
            select(AssessmentAssetGrant).where(
                AssessmentAssetGrant.administration_id == administration.id
            )
        ):
            grant.expires_at = administration.closes_at + timedelta(hours=24)
        snapshot_aggregate(database, administration)
        database.commit()
        return {
            "id": administration.id,
            "status": administration.status,
            "cooldownSeconds": 120 if administration.mode != "practice" else 0,
        }

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/open")
    def open_administration(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        administration = database.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.id == administration_id,
                AssessmentAdministration.organization_id == org_id,
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        if administration.status != "preparing":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_VERSION_MISSING"})
        required_slides = definition_slide_ids(version.definition)
        grants = int(
            database.scalar(
                select(func.count(AssessmentAssetGrant.id)).where(
                    AssessmentAssetGrant.administration_id == administration.id
                )
            )
            or 0
        )
        if grants != len(required_slides):
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ASSETS_NOT_PREPARED"})
        administration.status = "open"
        administration.opens_at = utc_now()
        bind_assessment_administration(database, administration.id)
        database.commit()
        return {"id": administration.id, "status": administration.status}

    def owned_administration(
        administration_id: str,
        authenticated: Session,
        database: OrmSession,
        requested_org: str | None,
    ) -> AssessmentAdministration:
        org_id = organization_id(authenticated, database, requested_org)
        administration = database.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.id == administration_id,
                AssessmentAdministration.organization_id == org_id,
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_NOT_FOUND"})
        return administration

    @app.get("/api/v2/admin/assessment/administrations/{administration_id}/monitor")
    def monitor_administration(
        administration_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, int]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        participant_ids = select(AssessmentParticipant.id).where(
            AssessmentParticipant.administration_id == administration.id
        )
        return {
            "activeSessions": int(
                database.scalar(
                    select(func.count(AssessmentSession.id)).where(
                        AssessmentSession.participant_id.in_(participant_ids),
                        AssessmentSession.revoked_at.is_(None),
                        AssessmentSession.expires_at > utc_now(),
                    )
                )
                or 0
            ),
            "activeAttempts": int(
                database.scalar(
                    select(func.count(AssessmentAttempt.id)).where(
                        AssessmentAttempt.administration_id == administration.id,
                        AssessmentAttempt.status == "active",
                    )
                )
                or 0
            ),
            "submitted": int(
                database.scalar(
                    select(func.count(AssessmentAttempt.id)).where(
                        AssessmentAttempt.administration_id == administration.id,
                        AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
                    )
                )
                or 0
            ),
            "needsGrading": int(
                database.scalar(
                    select(func.count(AssessmentGradebookRow.id)).where(
                        AssessmentGradebookRow.administration_id == administration.id,
                        AssessmentGradebookRow.status == "needs_grading",
                    )
                )
                or 0
            ),
        }

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/deadlines/sweep")
    def sweep_deadlines(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, int]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if database.bind is not None and database.bind.dialect.name == "postgresql":
            lock_key = int.from_bytes(
                hashlib.sha256(administration.id.encode()).digest()[:8],
                byteorder="big",
                signed=True,
            )
            acquired = bool(
                database.scalar(
                    text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
                    {"lock_key": lock_key},
                )
            )
            if not acquired:
                raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_SWEEPER_BUSY"})
        attempts = database.scalars(
            select(AssessmentAttempt)
            .where(
                AssessmentAttempt.administration_id == administration.id,
                AssessmentAttempt.status == "active",
            )
            .with_for_update(skip_locked=True)
        ).all()
        now = utc_now()
        expired = [
            attempt
            for attempt in attempts
            if as_utc(attempt.started_at) + timedelta(seconds=administration.duration_seconds)
            <= now
        ]
        for attempt in expired:
            finalize_attempt(
                database,
                attempt,
                administration,
                enforce_required=False,
                final_status="auto_submitted",
            )
        database.commit()
        return {"scanned": len(attempts), "autoSubmitted": len(expired)}

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/manual-grade")
    def manual_grade(
        administration_id: str,
        payload: ManualGradeRequest,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        attempt = database.scalar(
            select(AssessmentAttempt).where(
                AssessmentAttempt.id == payload.attempt_id,
                AssessmentAttempt.administration_id == administration.id,
                AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
            )
        )
        if attempt is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ATTEMPT_NOT_FOUND"})
        version = database.get(AssessmentVersion, administration.version_id)
        latest = database.scalar(
            select(AssessmentScoreVersion)
            .where(AssessmentScoreVersion.attempt_id == attempt.id)
            .order_by(AssessmentScoreVersion.version.desc())
        )
        if version is None or latest is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_SCORE_MISSING"})
        if latest.version != payload.expected_score_version:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_GRADING_CONFLICT",
                    "currentScoreVersion": latest.version,
                },
            )
        item = next(
            (
                candidate
                for candidate in version.definition["items"]
                if candidate["id"] == payload.item_id
            ),
            None,
        )
        if item is None or not (
            item.get("type") == "paragraph"
            or (item.get("type") == "short-answer" and item.get("manual", False))
        ):
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_ITEM_NOT_MANUAL"})
        maximum = Decimal(str(item.get("points", "0")))
        points = payload.points.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        if points < 0 or points > maximum:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_POINTS_INVALID"})
        breakdown = dict(latest.breakdown)
        breakdown[payload.item_id] = f"{points:.3f}"
        total = sum(
            (Decimal(str(value)) for value in breakdown.values() if value is not None),
            start=Decimal("0"),
        ).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        score = AssessmentScoreVersion(
            attempt_id=attempt.id,
            version=latest.version + 1,
            points=total,
            maximum_points=latest.maximum_points,
            breakdown=breakdown,
        )
        database.add(score)
        database.flush()
        row = database.scalar(
            select(AssessmentGradebookRow).where(
                AssessmentGradebookRow.administration_id == administration.id,
                AssessmentGradebookRow.participant_id == attempt.participant_id,
            )
        )
        if row is not None:
            row.score_version_id = score.id
            row.status = (
                "needs_grading" if any(value is None for value in breakdown.values()) else "graded"
            )
        if administration.status == "closed":
            snapshot_aggregate(database, administration)
        database.commit()
        return {
            "attemptId": attempt.id,
            "scoreVersion": score.version,
            "points": f"{total:.3f}",
            "maximumPoints": f"{Decimal(str(score.maximum_points)):.3f}",
            "status": row.status if row is not None else "aggregate_only",
        }

    @app.post(
        "/api/v2/admin/assessment/administrations/{administration_id}/release",
        status_code=status.HTTP_201_CREATED,
    )
    def release_results(
        administration_id: str,
        payload: ReleaseRequest,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if administration.status != "closed":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        needs_grading = int(
            database.scalar(
                select(func.count(AssessmentGradebookRow.id)).where(
                    AssessmentGradebookRow.administration_id == administration.id,
                    AssessmentGradebookRow.status == "needs_grading",
                )
            )
            or 0
        )
        if needs_grading:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_GRADING_INCOMPLETE",
                    "needsGrading": needs_grading,
                },
            )
        policy = payload.model_dump(mode="json", by_alias=True)
        release = AssessmentRelease(
            administration_id=administration.id,
            policy=policy,
            released_by_user_id=authenticated.user_id,
        )
        database.add(release)
        database.commit()
        return {"id": release.id, "releasedAt": release.released_at, "policy": policy}

    @app.get("/api/v2/admin/assessment/administrations/{administration_id}/export.csv")
    def export_results(
        administration_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> StreamingResponse:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )

        def safe_cell(value: object) -> str:
            rendered = "" if value is None else str(value)
            return (
                f"'{rendered}"
                if rendered.startswith(("=", "+", "-", "@", "\t", "\r"))
                else rendered
            )

        def stream_rows() -> Iterator[str]:
            buffer = StringIO()
            writer = csv.writer(buffer, lineterminator="\n")
            writer.writerow(("student", "status", "points", "maximum_points", "score_version"))
            yield buffer.getvalue()
            query = (
                select(
                    AssessmentRosterSnapshot.display_name,
                    AssessmentGradebookRow.status,
                    AssessmentScoreVersion.points,
                    AssessmentScoreVersion.maximum_points,
                    AssessmentScoreVersion.version,
                )
                .join(
                    AssessmentParticipant,
                    AssessmentParticipant.id == AssessmentGradebookRow.participant_id,
                )
                .join(
                    AssessmentRosterSnapshot,
                    (AssessmentRosterSnapshot.administration_id == administration.id)
                    & (AssessmentRosterSnapshot.learner_id == AssessmentParticipant.learner_id),
                )
                .outerjoin(
                    AssessmentScoreVersion,
                    AssessmentScoreVersion.id == AssessmentGradebookRow.score_version_id,
                )
                .where(AssessmentGradebookRow.administration_id == administration.id)
                .order_by(AssessmentRosterSnapshot.display_name, AssessmentGradebookRow.id)
                .execution_options(yield_per=100)
            )
            for row in database.execute(query):
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow(tuple(safe_cell(value) for value in row))
                yield buffer.getvalue()

        filename = f"assessment-{administration.public_id}.csv"
        return StreamingResponse(
            stream_rows(),
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Cache-Control": "no-store",
            },
        )

    @app.get("/api/v2/admin/assessment/administrations/{administration_id}/results")
    def administration_results(
        administration_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        persisted = latest_aggregate(database, administration.id)
        aggregate = (
            persisted.aggregate
            if administration.status in {"closed", "purged"} and persisted is not None
            else build_aggregate(database, administration)
        )
        individual_query = (
            select(
                AssessmentAttempt,
                AssessmentRosterSnapshot.display_name,
                AssessmentGradebookRow.status,
                AssessmentScoreVersion,
            )
            .join(
                AssessmentParticipant,
                AssessmentParticipant.id == AssessmentAttempt.participant_id,
            )
            .join(
                AssessmentRosterSnapshot,
                (AssessmentRosterSnapshot.administration_id == administration.id)
                & (AssessmentRosterSnapshot.learner_id == AssessmentParticipant.learner_id),
            )
            .outerjoin(
                AssessmentGradebookRow,
                (AssessmentGradebookRow.administration_id == administration.id)
                & (AssessmentGradebookRow.participant_id == AssessmentParticipant.id),
            )
            .outerjoin(
                AssessmentScoreVersion,
                AssessmentScoreVersion.id == AssessmentGradebookRow.score_version_id,
            )
            .where(AssessmentAttempt.administration_id == administration.id)
            .order_by(AssessmentRosterSnapshot.display_name, AssessmentAttempt.id)
        )
        individual_total = int(
            database.scalar(select(func.count()).select_from(individual_query.subquery())) or 0
        )
        individual_rows = (
            database.execute(
                individual_query.offset(max(0, offset)).limit(max(1, min(limit, 100)))
            ).all()
            if administration.status != "purged"
            else []
        )

        def response_map(attempt_id: str) -> dict[str, dict[str, Any]]:
            return {
                response.item_id: response.response
                for response in database.scalars(
                    select(AssessmentResponse).where(
                        AssessmentResponse.attempt_id == attempt_id
                    )
                )
            }

        return {
            "summary": aggregate,
            "administration": {
                "id": administration.id,
                "mode": administration.mode,
                "status": administration.status,
            },
            "individuals": {
                "total": individual_total if administration.status != "purged" else 0,
                "items": [
                    {
                        "attemptId": attempt.id,
                        "displayName": display_name,
                        "status": grade_status or attempt.status,
                        "scoreVersion": score.version if score is not None else None,
                        "points": (
                            f"{Decimal(str(score.points)):.3f}" if score is not None else None
                        ),
                        "maximumPoints": (
                            f"{Decimal(str(score.maximum_points)):.3f}"
                            if score is not None
                            else None
                        ),
                        "breakdown": score.breakdown if score is not None else {},
                        "responses": response_map(attempt.id),
                    }
                    for attempt, display_name, grade_status, score in individual_rows
                ],
            },
        }

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/aggregates/reconcile")
    def reconcile_aggregates(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if administration.status not in {"closed", "purged"}:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        if administration.status == "purged":
            existing = latest_aggregate(database, administration.id)
            if existing is None:
                raise HTTPException(
                    status_code=409, detail={"code": "ASSESSMENT_AGGREGATE_MISSING"}
                )
            return {
                "version": existing.version,
                "aggregate": existing.aggregate,
                "source": "preserved",
            }
        snapshot = snapshot_aggregate(database, administration)
        database.commit()
        return {
            "version": snapshot.version,
            "aggregate": snapshot.aggregate,
            "source": "recomputed",
        }

    @app.patch("/api/v2/admin/assessment/administrations/{administration_id}/retention")
    def update_retention(
        administration_id: str,
        payload: RetentionPatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        administration.settings = {
            **administration.settings,
            "retentionDays": payload.retention_days,
            "hold": payload.hold,
        }
        database.commit()
        return {
            "retentionDays": payload.retention_days,
            "hold": payload.hold,
        }

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/purge")
    def purge_administration(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
        batch_size: Annotated[int, Query(alias="batchSize", ge=1, le=100)] = 100,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if administration.settings.get("hold", False):
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_HOLD_ACTIVE"})
        if administration.status != "closed":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        retention_days = int(administration.settings.get("retentionDays", 365))
        eligible_at = (
            as_utc(administration.closes_at) + timedelta(days=retention_days)
            if administration.closes_at is not None
            else None
        )
        if (
            not administration.settings.get("syntheticFixture", False)
            and (eligible_at is None or eligible_at > utc_now())
        ):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_RETENTION_ACTIVE",
                    "eligibleAt": eligible_at.isoformat() if eligible_at is not None else None,
                },
            )
        participant_ids = list(
            database.scalars(
                select(AssessmentParticipant.id)
                .where(AssessmentParticipant.administration_id == administration.id)
                .order_by(AssessmentParticipant.id)
                .limit(batch_size)
            )
        )
        if participant_ids:
            database.execute(
                delete(AssessmentParticipant).where(AssessmentParticipant.id.in_(participant_ids))
            )
            database.flush()
        remaining = int(
            database.scalar(
                select(func.count(AssessmentParticipant.id)).where(
                    AssessmentParticipant.administration_id == administration.id
                )
            )
            or 0
        )
        if remaining == 0:
            remove_asset_grants(database, storage, administration)
            administration.status = "purged"
        database.commit()
        return {
            "id": administration.id,
            "status": administration.status,
            "deleted": len(participant_ids),
            "remaining": remaining,
        }

    @app.post(
        "/api/v2/admin/assessment/administrations/{administration_id}/synthetic-fixture/cleanup"
    )
    def cleanup_synthetic_fixture(
        administration_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, bool]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if not administration.settings.get("syntheticFixture", False):
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_NOT_SYNTHETIC_FIXTURE"}
            )
        if administration.status != "purged":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_VERSION_MISSING"})
        version_count = int(
            database.scalar(
                select(func.count(AssessmentVersion.id)).where(
                    AssessmentVersion.draft_id == version.draft_id
                )
            )
            or 0
        )
        administration_count = int(
            database.scalar(
                select(func.count(AssessmentAdministration.id)).where(
                    AssessmentAdministration.version_id == version.id
                )
            )
            or 0
        )
        if version_count != 1 or administration_count != 1:
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_SYNTHETIC_FIXTURE_REUSED"}
            )
        cohort_id = administration.cohort_id
        learner_ids = (
            list(
                database.scalars(
                    select(CohortEnrollment.learner_id).where(
                        CohortEnrollment.cohort_id == cohort_id
                    )
                )
            )
            if cohort_id is not None
            else []
        )
        public_id = administration.public_id
        draft_id = version.draft_id
        database.delete(administration)
        database.flush()
        database.delete(version)
        database.flush()
        draft = database.get(AssessmentDraft, draft_id)
        if draft is not None:
            database.delete(draft)
        if cohort_id is not None:
            cohort = database.get(Cohort, cohort_id)
            if cohort is not None:
                database.delete(cohort)
        database.flush()
        for learner_id in learner_ids:
            remaining_enrollments = int(
                database.scalar(
                    select(func.count(CohortEnrollment.id)).where(
                        CohortEnrollment.learner_id == learner_id
                    )
                )
                or 0
            )
            if remaining_enrollments == 0:
                learner = database.get(LearnerProfile, learner_id)
                if learner is not None:
                    database.delete(learner)
        database.commit()
        return {
            "fixturesRemoved": True,
            "grantsRemoved": not storage.assessment_delivery_for(public_id).exists(),
            "sessionsRemoved": True,
            "administrationPurged": True,
        }

    def owned_class(database: OrmSession, cohort_id: str, org_id: str) -> Cohort:
        cohort = database.scalar(
            select(Cohort).where(Cohort.id == cohort_id, Cohort.organization_id == org_id)
        )
        if cohort is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_CLASS_NOT_FOUND"})
        return cohort

    @app.get("/api/v2/admin/assessment/classes")
    def list_classes(
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        rows = database.execute(
            select(Cohort, func.count(CohortEnrollment.id))
            .outerjoin(
                CohortEnrollment,
                (CohortEnrollment.cohort_id == Cohort.id) & (CohortEnrollment.status == "active"),
            )
            .where(Cohort.organization_id == org_id)
            .group_by(Cohort.id)
            .order_by(Cohort.updated_at.desc(), Cohort.id)
        ).all()
        return {
            "items": [
                {
                    "id": cohort.id,
                    "name": cohort.name,
                    "status": cohort.status,
                    "studentCount": int(student_count),
                }
                for cohort, student_count in rows
            ],
            "total": len(rows),
        }

    @app.post("/api/v2/admin/assessment/classes", status_code=status.HTTP_201_CREATED)
    def create_class(
        payload: ClassCreate,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        cohort = Cohort(
            organization_id=org_id,
            name=payload.name,
            created_by_user_id=authenticated.user_id,
        )
        database.add(cohort)
        database.commit()
        return {"id": cohort.id, "name": cohort.name, "status": cohort.status}

    @app.patch("/api/v2/admin/assessment/classes/{cohort_id}")
    def update_class(
        cohort_id: str,
        payload: ClassPatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        cohort = owned_class(
            database,
            cohort_id,
            organization_id(authenticated, database, requested_org),
        )
        if payload.status is not None and payload.status not in {"active", "archived"}:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_CLASS_INVALID"})
        if payload.name is not None:
            cohort.name = payload.name
        if payload.status is not None:
            cohort.status = payload.status
        database.commit()
        return {"id": cohort.id, "name": cohort.name, "status": cohort.status}

    @app.post("/api/v2/admin/assessment/classes/{cohort_id}/import/preview")
    def preview_import(
        cohort_id: str,
        payload: ImportRows,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        owned_class(database, cohort_id, organization_id(authenticated, database, requested_org))
        rows = _parse_rows(payload.rows)
        return {
            "validCount": len(rows),
            "checksum": _rows_checksum(rows),
            "preview": [{"displayName": name} for _, name in rows[:20]],
        }

    @app.post(
        "/api/v2/admin/assessment/classes/{cohort_id}/import/commit",
        status_code=status.HTTP_201_CREATED,
    )
    def commit_import(
        cohort_id: str,
        payload: ImportRows,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, int]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_class(database, cohort_id, org_id)
        rows = _parse_rows(payload.rows)
        if payload.checksum is None or not hmac.compare_digest(
            payload.checksum, _rows_checksum(rows)
        ):
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IMPORT_CHANGED"})
        existing = int(
            database.scalar(
                select(func.count(CohortEnrollment.id)).where(
                    CohortEnrollment.cohort_id == cohort_id,
                    CohortEnrollment.status == "active",
                )
            )
            or 0
        )
        created = 0
        for identifier, display_name in rows:
            identifier_hash = hmac.new(
                identifier_secret.encode(), identifier.casefold().encode(), hashlib.sha256
            ).hexdigest()
            learner = database.scalar(
                select(LearnerProfile).where(
                    LearnerProfile.organization_id == org_id,
                    LearnerProfile.login_identifier_hash == identifier_hash,
                )
            )
            if learner is None:
                learner = LearnerProfile(
                    organization_id=org_id,
                    teaching_pseudonym=f"learner-{identifier_hash[:12]}",
                    login_identifier_hash=identifier_hash,
                    display_name=display_name,
                    created_by_user_id=authenticated.user_id,
                )
                database.add(learner)
                database.flush()
            enrollment = database.scalar(
                select(CohortEnrollment).where(
                    CohortEnrollment.cohort_id == cohort_id,
                    CohortEnrollment.learner_id == learner.id,
                )
            )
            if enrollment is not None:
                if enrollment.status == "withdrawn":
                    enrollment.status = "active"
                    created += 1
                continue
            created += 1
            if existing + created > 500:
                raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"})
            database.add(
                CohortEnrollment(
                    organization_id=org_id,
                    cohort_id=cohort_id,
                    learner_id=learner.id,
                    created_by_user_id=authenticated.user_id,
                )
            )
        database.commit()
        return {"created": created}

    @app.get("/api/v2/admin/assessment/classes/{cohort_id}/students")
    def list_students(
        cohort_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_class(database, cohort_id, org_id)
        query = (
            select(LearnerProfile, CohortEnrollment)
            .join(CohortEnrollment, CohortEnrollment.learner_id == LearnerProfile.id)
            .where(CohortEnrollment.cohort_id == cohort_id)
            .order_by(LearnerProfile.display_name, LearnerProfile.id)
        )
        total = int(database.scalar(select(func.count()).select_from(query.subquery())) or 0)
        learners = database.execute(
            query.offset(max(0, offset)).limit(max(1, min(limit, 100)))
        ).all()
        return {
            "items": [
                {
                    "id": learner.id,
                    "displayName": learner.display_name,
                    "status": enrollment.status,
                }
                for learner, enrollment in learners
            ],
            "total": total,
        }

    @app.patch(
        "/api/v2/admin/assessment/classes/{cohort_id}/students/{learner_id}"
    )
    def update_enrollment(
        cohort_id: str,
        learner_id: str,
        payload: EnrollmentPatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_class(database, cohort_id, org_id)
        if payload.status not in {"active", "withdrawn"}:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_CLASS_INVALID"})
        enrollment = database.scalar(
            select(CohortEnrollment).where(
                CohortEnrollment.cohort_id == cohort_id,
                CohortEnrollment.learner_id == learner_id,
                CohortEnrollment.organization_id == org_id,
            )
        )
        if enrollment is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_STUDENT_NOT_FOUND"})
        enrollment.status = payload.status
        database.commit()
        return {"learnerId": learner_id, "status": enrollment.status}
