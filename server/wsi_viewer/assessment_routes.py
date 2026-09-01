import csv
import hashlib
import hmac
from collections.abc import Callable, Iterator
from io import StringIO
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as OrmSession

from .assessment_contract import AssessmentContractError, CompiledAssessment, compile_assessment
from .identity import staff_organization_context
from .models import (
    AssessmentAdministration,
    AssessmentDraft,
    AssessmentVersion,
    Cohort,
    CohortEnrollment,
    LearnerProfile,
    Session,
)
from .time_support import utc_now


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
            administration = AssessmentAdministration(
                organization_id=draft.organization_id,
                version_id=version.id,
                cohort_id=payload.cohort_id,
                mode=payload.mode,
                status="open" if payload.mode == "practice" else "preparing",
                duration_seconds=payload.duration_seconds,
                max_attempts=payload.max_attempts,
                settings={},
            )
            database.add(administration)
            database.commit()
        return {
            "id": version.id,
            "version": version.version,
            "schema": version.schema,
            "checksum": version.checksum,
            "learnerManifest": version.learner_manifest,
            "publicId": administration.public_id if administration is not None else None,
        }

    def owned_class(database: OrmSession, cohort_id: str, org_id: str) -> Cohort:
        cohort = database.scalar(
            select(Cohort).where(Cohort.id == cohort_id, Cohort.organization_id == org_id)
        )
        if cohort is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_CLASS_NOT_FOUND"})
        return cohort

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
