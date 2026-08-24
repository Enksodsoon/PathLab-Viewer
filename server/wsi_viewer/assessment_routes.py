import csv
import hashlib
import hmac
import secrets
from collections.abc import Callable, Iterator
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from .assessment_contract import (
    AssessmentContractError,
    CompiledAssessment,
    compile_assessment,
    score_item,
)
from .identity import staff_organization_context
from .models import (
    AssessmentAdministration,
    AssessmentAssetGrant,
    AssessmentAttempt,
    AssessmentDraft,
    AssessmentGradebookRow,
    AssessmentParticipant,
    AssessmentResponse,
    AssessmentRosterSnapshot,
    AssessmentScoreVersion,
    AssessmentSession,
    AssessmentVersion,
    Cohort,
    CohortEnrollment,
    LearnerProfile,
    Session,
)
from .time_support import as_utc, utc_now


class DraftCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    document: dict[str, Any]


class DraftPatch(BaseModel):
    document: dict[str, Any]


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


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


class AccessRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    kind: str
    public_id: str = Field(alias="publicId")
    student_identifier: str | None = Field(default=None, alias="studentIdentifier")
    access_code: str | None = Field(default=None, alias="accessCode")


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
            "manifest": version.learner_manifest,
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

    @app.post("/api/v2/assessment/access", status_code=status.HTTP_201_CREATED)
    def access_assessment(
        payload: AccessRequest,
        response: Response,
        database: Database,
    ) -> dict[str, Any]:
        administration = database.scalar(
            select(AssessmentAdministration).where(
                AssessmentAdministration.public_id == payload.public_id,
                AssessmentAdministration.status == "open",
            )
        )
        if administration is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_ACCESS_INVALID"})
        receipt: str | None = None
        participant: AssessmentParticipant | None = None
        if payload.kind == "anonymous" and administration.mode == "formative":
            receipt = secrets.token_urlsafe(32)
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
        raw_token = secrets.token_urlsafe(32)
        csrf_token = secrets.token_urlsafe(32)
        database.add(
            AssessmentSession(
                id=hashlib.sha256(raw_token.encode()).hexdigest(),
                participant_id=participant.id,
                csrf_token=csrf_token,
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

    @app.post("/api/v2/assessment/attempts", status_code=status.HTTP_201_CREATED)
    def start_attempt(
        database: Database,
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
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
        database.commit()
        return {"id": attempt.id, "ordinal": attempt.ordinal, "status": attempt.status}

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
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        attempt = owned_attempt(database, attempt_id, stored_session)
        if attempt.status != "active":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ATTEMPT_CLOSED"})
        for incoming in payload.responses:
            existing = database.scalar(
                select(AssessmentResponse).where(
                    AssessmentResponse.attempt_id == attempt.id,
                    AssessmentResponse.item_id == incoming.item_id,
                )
            )
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
        database.commit()
        return {"saved": len(payload.responses)}

    @app.post("/api/v2/assessment/attempts/{attempt_id}/submit")
    def submit_attempt(
        attempt_id: str,
        database: Database,
        raw_token: Annotated[str | None, Cookie(alias="pathlab_assessment_session")] = None,
        csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
    ) -> dict[str, Any]:
        stored_session = student_session(database, raw_token, csrf_token)
        attempt = owned_attempt(database, attempt_id, stored_session)
        if attempt.status != "active":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_ATTEMPT_CLOSED"})
        administration = database.get(AssessmentAdministration, attempt.administration_id)
        version = (
            database.get(AssessmentVersion, administration.version_id)
            if administration is not None
            else None
        )
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
        if required_missing:
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
                if item.get("type") not in {"information", "paragraph"}
            ),
            start=Decimal("0"),
        )
        score = AssessmentScoreVersion(
            attempt_id=attempt.id,
            version=1,
            points=points,
            maximum_points=maximum,
            breakdown={
                item["id"]: str(value) if value is not None else None
                for item, value in zip(version.definition["items"], scored, strict=True)
            },
        )
        attempt.status = "submitted"
        attempt.submitted_at = utc_now()
        database.add(score)
        database.flush()
        participant = database.get(AssessmentParticipant, stored_session.participant_id)
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
            gradebook.status = "graded"
        database.commit()
        return {
            "status": "submitted",
            "score": {"points": str(score.points), "maximumPoints": str(score.maximum_points)},
            "anonymousAggregateOnly": participant is None or participant.kind == "anonymous",
        }

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
                settings={},
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
        administration.status = "open"
        administration.opens_at = utc_now()
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

    @app.get("/api/v2/admin/assessment/administrations/{administration_id}/results")
    def administration_results(
        administration_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        submitted = int(
            database.scalar(
                select(func.count(AssessmentAttempt.id)).where(
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
                )
            )
            or 0
        )
        average = database.scalar(
            select(func.avg(AssessmentScoreVersion.points))
            .join(
                AssessmentAttempt,
                AssessmentAttempt.id == AssessmentScoreVersion.attempt_id,
            )
            .where(AssessmentAttempt.administration_id == administration.id)
        )
        return {
            "summary": {
                "responses": submitted,
                "averagePoints": f"{Decimal(str(average or 0)):.3f}",
            },
            "administration": {
                "id": administration.id,
                "mode": administration.mode,
                "status": administration.status,
            },
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
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        if administration.settings.get("hold", False):
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_HOLD_ACTIVE"})
        if administration.status != "closed":
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        database.execute(
            delete(AssessmentParticipant).where(
                AssessmentParticipant.administration_id == administration.id
            )
        )
        database.execute(
            delete(AssessmentAssetGrant).where(
                AssessmentAssetGrant.administration_id == administration.id
            )
        )
        administration.status = "purged"
        database.commit()
        return {"id": administration.id, "status": administration.status}

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
        if existing + len(rows) > 500:
            raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"})
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
            database.add(
                CohortEnrollment(
                    organization_id=org_id,
                    cohort_id=cohort_id,
                    learner_id=learner.id,
                    created_by_user_id=authenticated.user_id,
                )
            )
        database.commit()
        return {"created": len(rows)}

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
            select(LearnerProfile)
            .join(CohortEnrollment, CohortEnrollment.learner_id == LearnerProfile.id)
            .where(CohortEnrollment.cohort_id == cohort_id)
            .order_by(LearnerProfile.display_name, LearnerProfile.id)
        )
        total = int(database.scalar(select(func.count()).select_from(query.subquery())) or 0)
        learners = database.scalars(
            query.offset(max(0, offset)).limit(max(1, min(limit, 100)))
        ).all()
        return {
            "items": [
                {"id": item.id, "displayName": item.display_name, "status": item.status}
                for item in learners
            ],
            "total": total,
        }
