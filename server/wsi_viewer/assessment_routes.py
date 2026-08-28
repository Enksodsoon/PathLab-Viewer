import csv
import hashlib
import hmac
import json
import secrets
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from io import StringIO
from typing import Annotated, Any, Literal

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
from sqlalchemy import delete, func, or_, select, text, update
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
from .assessment_branching import active_responses, reachable_section_ids
from .assessment_contract import (
    AssessmentContractError,
    CompiledAssessment,
    compile_assessment,
    score_item,
)
from .assessment_contract_v2 import V2_SCHEMA, compile_assessment_v2, document_schema
from .assessment_import_v2 import (
    clone_complete_sections,
    import_individual_items,
)
from .assessment_import_v2 import (
    document_items as import_document_items,
)
from .assessment_review import build_learner_review
from .assessment_v2_migration import migrate_v1_document
from .assessment_validation import preflight_v2
from .domain import SlideState
from .identity import staff_organization_context
from .models import (
    AssessmentAccessThrottle,
    AssessmentAdministration,
    AssessmentAssetGrant,
    AssessmentAttempt,
    AssessmentCourse,
    AssessmentCourseEnrollment,
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
    Folder,
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


def assessment_definition_items(definition: dict[str, Any]) -> list[dict[str, Any]]:
    if definition.get("schema") == V2_SCHEMA:
        return [
            item for section in definition.get("sections", []) for item in section.get("items", [])
        ]
    return list(definition.get("items", []))


class DraftCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    title: str = Field(min_length=1, max_length=200)
    document: dict[str, Any]
    course_id: str | None = Field(default=None, alias="courseId")
    cohort_id: str | None = Field(default=None, alias="classId")


class DraftPatch(BaseModel):
    document: dict[str, Any]


class DraftDuplicate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)


class DraftMigration(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class QuestionImport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    source_draft_id: str = Field(alias="sourceDraftId")
    item_ids: list[str] = Field(alias="itemIds", min_length=1, max_length=100)
    expected_revision: int = Field(alias="expectedRevision", ge=1)


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)


CourseIconKey = Literal[
    "general",
    "integumentary",
    "bone",
    "muscular",
    "neuroscience",
    "endocrine",
    "cardiology",
    "immune",
    "respiratory",
    "digestive",
    "urinary",
    "reproductive",
    "anatomy",
    "vision",
    "hearing",
    "dental",
    "microscope",
    "laboratory",
    "medicine",
    "pharmacology",
    "first_aid",
    "genetics",
    "microbiology",
    "science",
    "botany",
    "mathematics",
]


class CourseCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=160)
    course_code: str = Field(alias="courseCode", min_length=1, max_length=60)
    semester: str = Field(min_length=1, max_length=80)
    academic_year: str = Field(alias="academicYear", min_length=1, max_length=20)
    icon_key: CourseIconKey = Field(default="general", alias="iconKey")
    scoring_method: str = Field(default="percentage", alias="scoringMethod")
    description: str | None = Field(default=None, max_length=4000)
    opens_at: datetime | None = Field(default=None, alias="opensAt")
    closes_at: datetime | None = Field(default=None, alias="closesAt")
    status: str = "draft"


class CoursePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    course_code: str | None = Field(default=None, alias="courseCode", min_length=1, max_length=60)
    semester: str | None = Field(default=None, min_length=1, max_length=80)
    academic_year: str | None = Field(
        default=None, alias="academicYear", min_length=1, max_length=20
    )
    icon_key: CourseIconKey | None = Field(default=None, alias="iconKey")
    scoring_method: str | None = Field(default=None, alias="scoringMethod")
    description: str | None = Field(default=None, max_length=4000)
    opens_at: datetime | None = Field(default=None, alias="opensAt")
    closes_at: datetime | None = Field(default=None, alias="closesAt")
    status: str | None = None


class RosterRuleFilter(BaseModel):
    field: str = Field(min_length=1, max_length=180)
    values: list[str] = Field(min_length=1, max_length=100)


class ClassRosterRule(BaseModel):
    mode: Literal["all", "filters", "existing"] = "all"
    filters: list[RosterRuleFilter] = Field(default_factory=list, max_length=100)


class CourseClassCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str = Field(min_length=1, max_length=160)
    section_code: str = Field(alias="sectionCode", min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=160)
    opens_at: datetime | None = Field(default=None, alias="opensAt")
    closes_at: datetime | None = Field(default=None, alias="closesAt")
    roster_rule: ClassRosterRule = Field(default_factory=ClassRosterRule, alias="rosterRule")


class ClassRosterPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    roster_rule: ClassRosterRule = Field(alias="rosterRule")


class ClassPatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    section_code: str | None = Field(default=None, alias="sectionCode", max_length=60)
    description: str | None = Field(default=None, max_length=4000)
    location: str | None = Field(default=None, max_length=160)
    folder_id: str | None = Field(default=None, alias="folderId", max_length=36)
    opens_at: datetime | None = Field(default=None, alias="opensAt")
    closes_at: datetime | None = Field(default=None, alias="closesAt")
    status: str | None = None


def _roster_rule_json(rule: ClassRosterRule) -> dict[str, Any]:
    return rule.model_dump(mode="json")


def _learner_rule_value(learner: LearnerProfile, field: str) -> str | None:
    if field == "group":
        return learner.group_name
    if field == "subgroup":
        return learner.subgroup_name
    if field.startswith("metadata.") and len(field) > len("metadata."):
        value = (learner.roster_metadata or {}).get(field.removeprefix("metadata."))
        return str(value) if value not in (None, "") else None
    raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_CLASS_ROSTER_RULE_INVALID"})


def _resolve_roster_rule(
    learners: list[LearnerProfile],
    rule: ClassRosterRule,
    existing_ids: set[str] | None = None,
) -> set[str]:
    allowed_ids = {learner.id for learner in learners}
    if rule.mode == "all":
        return allowed_ids
    if rule.mode == "existing":
        return allowed_ids.intersection(existing_ids or set())
    if not rule.filters:
        return set()
    selected: set[str] = set()
    for learner in learners:
        matches = True
        for item in rule.filters:
            accepted = {value.strip().casefold() for value in item.values if value.strip()}
            actual = _learner_rule_value(learner, item.field)
            if not accepted or actual is None or actual.strip().casefold() not in accepted:
                matches = False
                break
        if matches:
            selected.add(learner.id)
    return selected


class EnrollmentPatch(BaseModel):
    status: str


class LearnerProfilePatch(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    student_id: str = Field(alias="studentId", min_length=1, max_length=200)
    first_name: str = Field(alias="firstName", min_length=1, max_length=160)
    last_name: str | None = Field(default=None, alias="lastName", max_length=160)
    group_name: str | None = Field(default=None, alias="group", max_length=100)
    subgroup_name: str | None = Field(default=None, alias="subgroup", max_length=100)
    email: str | None = Field(default=None, max_length=254)
    metadata: dict[str, str] = Field(default_factory=dict, max_length=50)


class ImportRows(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    rows: str = Field(min_length=1, max_length=8 * 1024 * 1024)
    checksum: str | None = None
    confirm_warnings: bool = Field(default=False, alias="confirmWarnings")


class CollectionSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    manual_acceptance: bool = Field(default=True, alias="manualAcceptance")
    closes_at: datetime | None = Field(default=None, alias="closesAt")
    response_limit: int | None = Field(default=None, alias="responseLimit", ge=1, le=500)
    closed_message: str | None = Field(default=None, alias="closedMessage", max_length=1_000)


class PublishReleasePolicy(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    timing: str = "manual"
    show_score: bool = Field(default=True, alias="showScore")
    show_answers: bool = Field(default=False, alias="showAnswers")
    show_authored_feedback: bool = Field(default=False, alias="showAuthoredFeedback")
    show_manual_feedback: bool = Field(default=False, alias="showManualFeedback")
    show_annotations: bool = Field(default=False, alias="showAnnotations")


class PublishSettings(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    mode: str
    cohort_id: str | None = Field(default=None, alias="cohortId")
    cohort_ids: list[str] = Field(default_factory=list, alias="classIds", max_length=100)
    duration_seconds: int = Field(default=3600, alias="durationSeconds", ge=1, le=14_400)
    max_attempts: int = Field(default=1, alias="maxAttempts", ge=1, le=3)
    access_code: str | None = Field(default=None, alias="accessCode", min_length=4, max_length=64)
    collection: CollectionSettings = Field(default_factory=CollectionSettings)
    release_policy: PublishReleasePolicy = Field(
        default_factory=PublishReleasePolicy, alias="releasePolicy"
    )
    synthetic_fixture: bool = Field(default=False, alias="syntheticFixture")


class AdministrationStatusPatch(BaseModel):
    status: str


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
    feedback: str | None = Field(default=None, max_length=4_000)


class ManualGradeBatchRequest(BaseModel):
    grades: list[ManualGradeRequest] = Field(min_length=1, max_length=100)


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    show_score: bool = Field(default=True, alias="showScore")
    show_answers: bool = Field(default=False, alias="showAnswers")
    show_feedback: bool = Field(default=False, alias="showFeedback")
    show_authored_feedback: bool | None = Field(default=None, alias="showAuthoredFeedback")
    show_manual_feedback: bool = Field(default=False, alias="showManualFeedback")
    show_annotations: bool = Field(default=False, alias="showAnnotations")


class DraftJson(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    title: str
    status: str
    revision: int
    document: dict[str, Any]
    course_id: str | None = Field(serialization_alias="courseId")
    cohort_id: str | None = Field(serialization_alias="classId")


def _draft_json(draft: AssessmentDraft, database: OrmSession | None = None) -> dict[str, Any]:
    value = DraftJson.model_validate(draft).model_dump(by_alias=True)
    course = (
        database.get(AssessmentCourse, draft.course_id) if database and draft.course_id else None
    )
    cohort = database.get(Cohort, draft.cohort_id) if database and draft.cohort_id else None
    value["courseName"] = course.name if course is not None else None
    value["className"] = cohort.name if cohort is not None else None
    return value


@dataclass(frozen=True)
class RosterRow:
    identifier: str
    student_id: str | None
    first_name: str | None
    last_name: str | None
    display_name: str | None
    group_name: str | None = None
    subgroup_name: str | None = None
    email: str | None = None
    metadata: dict[str, str] | None = None


_ROSTER_HEADER_ALIASES = {
    "student_id": {"student_id", "student_number", "student_no", "id", "รหัสนักศึกษา"},
    "first_name": {"first_name", "given_name", "name", "ชื่อ"},
    "last_name": {"last_name", "surname", "family_name", "นามสกุล"},
    "display_name": {"display_name", "full_name"},
    "group_name": {"group", "group_name", "class_group", "กลุ่ม"},
    "subgroup_name": {"subgroup", "sub_group", "subgroup_name", "กลุ่มย่อย"},
    "email": {"email", "email_address", "e_mail", "อีเมล"},
}

MAX_ASSESSMENT_ROSTER = 5000


def _header_key(value: str) -> str:
    return "_".join(value.lstrip("\ufeff").strip().casefold().replace("-", " ").split())


def _parse_rows(raw: str, *, require_structured: bool = False) -> list[RosterRow]:
    source = list(csv.reader(StringIO(raw)))
    if not source:
        raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_INVALID"})
    first = [_header_key(value) for value in source[0]]
    known = {alias: field for field, aliases in _ROSTER_HEADER_ALIASES.items() for alias in aliases}
    mapped = {index: known[value] for index, value in enumerate(first) if value in known}
    structured = "student_id" in mapped.values()
    if require_structured and not structured:
        raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_HEADER_REQUIRED"})
    if structured and "first_name" not in mapped.values():
        raise HTTPException(
            status_code=400, detail={"code": "ASSESSMENT_ROSTER_NAME_COLUMNS_REQUIRED"}
        )
    data_rows = source[1:] if structured else source
    parsed: list[RosterRow] = []
    seen: set[str] = set()
    for row in data_rows:
        if not row or not row[0].strip():
            continue
        if structured:
            values = {
                field: (row[index].strip() if index < len(row) else "")
                for index, field in mapped.items()
            }
            identifier = values.get("student_id", "")
            first_name = values.get("first_name", "")
            last_name = values.get("last_name", "")
            if not identifier or not first_name:
                raise HTTPException(
                    status_code=400, detail={"code": "ASSESSMENT_ROSTER_REQUIRED_VALUE"}
                )
            display_name = values.get("display_name") or f"{first_name} {last_name}".strip()
            recognized_indexes = set(mapped)
            metadata = {
                (first[index] or f"column_{index + 1}"): value.strip()
                for index, value in enumerate(row)
                if index not in recognized_indexes and value.strip()
            }
            roster_row = RosterRow(
                identifier=identifier,
                student_id=identifier,
                first_name=first_name[:160],
                last_name=last_name[:160] or None,
                display_name=display_name[:160],
                group_name=values.get("group_name", "")[:100] or None,
                subgroup_name=values.get("subgroup_name", "")[:100] or None,
                email=values.get("email", "")[:254] or None,
                metadata=metadata,
            )
        else:
            identifier = row[0].strip()
            optional_display_name = (
                row[1].strip()[:160] if len(row) > 1 and row[1].strip() else None
            )
            roster_row = RosterRow(identifier, None, None, None, optional_display_name)
        if len(identifier) > 200 or identifier.casefold() in seen:
            raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_INVALID"})
        seen.add(identifier.casefold())
        parsed.append(roster_row)
    if not parsed or len(parsed) > MAX_ASSESSMENT_ROSTER:
        raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"})
    return parsed


def _rows_checksum(rows: list[RosterRow]) -> str:
    canonical = "\n".join(
        json.dumps(
            {
                "studentId": row.identifier.casefold(),
                "firstName": row.first_name,
                "lastName": row.last_name,
                "displayName": row.display_name,
                "group": row.group_name,
                "subgroup": row.subgroup_name,
                "email": row.email,
                "metadata": row.metadata or {},
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        for row in rows
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _identifier_metadata_keys(metadata: dict[str, str] | None) -> set[str]:
    keys: set[str] = set()
    for key in metadata or {}:
        normalized = _header_key(key)
        if (
            normalized.endswith("_id")
            or "identifier" in normalized
            or normalized
            in {"passport", "passport_number", "national_id", "registration_number", "username"}
        ):
            keys.add(key)
    return keys


def _roster_import_warnings(
    database: OrmSession,
    course_id: str,
    rows: list[RosterRow],
) -> list[dict[str, str]]:
    existing = database.scalars(
        select(LearnerProfile)
        .join(
            AssessmentCourseEnrollment, AssessmentCourseEnrollment.learner_id == LearnerProfile.id
        )
        .where(AssessmentCourseEnrollment.course_id == course_id)
    ).all()
    warnings: list[dict[str, str]] = []
    by_student_id = {
        learner.student_id.casefold(): learner for learner in existing if learner.student_id
    }
    by_full_name: dict[tuple[str, str], list[LearnerProfile]] = {}
    for learner in existing:
        if learner.first_name and learner.last_name:
            by_full_name.setdefault(
                (learner.first_name.casefold(), learner.last_name.casefold()), []
            ).append(learner)
    for row in rows:
        student_id = row.student_id or row.identifier
        exact = by_student_id.get(student_id.casefold())
        if exact is not None:
            warnings.append(
                {
                    "code": "existing_student_id",
                    "studentId": student_id,
                    "matchedStudentId": exact.student_id or "",
                    "message": (
                        f"Student ID {student_id} is already in this roster and will be skipped."
                    ),
                }
            )
            continue
        if row.first_name and row.last_name:
            for match in by_full_name.get(
                (row.first_name.casefold(), row.last_name.casefold()), []
            ):
                warnings.append(
                    {
                        "code": "matching_full_name",
                        "studentId": student_id,
                        "matchedStudentId": match.student_id or "",
                        "message": (
                            f"{row.display_name} matches an existing full name with a "
                            "different student ID."
                        ),
                    }
                )
                break
        row_identifiers = {
            key: value.casefold()
            for key, value in (row.metadata or {}).items()
            if key in _identifier_metadata_keys(row.metadata) and value
        }
        if row.email:
            row_identifiers["email"] = row.email.casefold()
        if not row_identifiers:
            continue
        for match in existing:
            match_identifiers = {
                key: value.casefold()
                for key, value in (match.roster_metadata or {}).items()
                if key in row_identifiers and value
            }
            if match.email:
                match_identifiers["email"] = match.email.casefold()
            matched_key = next(
                (
                    key
                    for key, value in row_identifiers.items()
                    if match_identifiers.get(key) == value
                ),
                None,
            )
            if matched_key:
                warnings.append(
                    {
                        "code": "matching_identifier",
                        "studentId": student_id,
                        "matchedStudentId": match.student_id or "",
                        "field": matched_key,
                        "message": (
                            f"{student_id} shares the same "
                            f"{matched_key.replace('_', ' ')} with another learner."
                        ),
                    }
                )
                break
    return warnings


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

    def editable_draft(database: OrmSession, draft_id: str, org_id: str) -> AssessmentDraft:
        draft = owned_draft(database, draft_id, org_id)
        if draft.status == "archived":
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_DRAFT_ARCHIVED"},
            )
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
        if attempt is not None and manifest.get("settings", {}).get("shuffleQuestions") is True:
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
        collection = administration.settings.get("collection", {})
        if collection.get("manualAcceptance", True) is False:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_NOT_ACCEPTING"})
        if administration.closes_at is not None and as_utc(administration.closes_at) <= utc_now():
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_COLLECTION_CLOSED"})
        response_limit = collection.get("responseLimit")
        if isinstance(response_limit, int):
            submitted_count = int(
                database.scalar(
                    select(func.count(AssessmentAttempt.id)).where(
                        AssessmentAttempt.administration_id == administration.id,
                        AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
                    )
                )
                or 0
            )
            if submitted_count >= response_limit:
                raise HTTPException(
                    status_code=409, detail={"code": "ASSESSMENT_RESPONSE_LIMIT_REACHED"}
                )
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
            raise HTTPException(status_code=413, detail={"code": "ASSESSMENT_RESPONSE_BATCH_LIMIT"})
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
        if administration.closes_at is not None and as_utc(administration.closes_at) <= utc_now():
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
                detail={"code": "ASSESSMENT_COLLECTION_EXPIRED", "result": result},
            )
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
        definition_items = assessment_definition_items(version.definition)
        if version.definition.get("schema") == V2_SCHEMA:
            latest = active_responses(version.definition, latest)
            reachable_sections = set(reachable_section_ids(version.definition, latest))
            definition_items = [
                item
                for section in version.definition.get("sections", [])
                if section["id"] in reachable_sections
                for item in section.get("items", [])
            ]
        required_missing = [
            item["id"]
            for item in definition_items
            if item.get("required") and item["id"] not in latest
        ]
        if enforce_required and required_missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "ASSESSMENT_REQUIRED_MISSING", "itemIds": required_missing},
            )
        scored = [score_item(item, latest.get(item["id"], {})) for item in definition_items]
        points = sum((value for value in scored if value is not None), start=Decimal("0"))
        maximum = sum(
            (
                Decimal(str(item.get("points", "0")))
                for item in definition_items
                if item.get("type") not in {"information", "section-information"}
            ),
            start=Decimal("0"),
        )
        needs_grading = any(
            value is None and item.get("type") != "information" and item["id"] in latest
            for item, value in zip(definition_items, scored, strict=True)
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
                for item, value in zip(definition_items, scored, strict=True)
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
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
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
        responses = {
            response.item_id: response.response
            for response in database.scalars(
                select(AssessmentResponse).where(AssessmentResponse.attempt_id == attempt.id)
            )
        }
        result["review"] = build_learner_review(
            definition=version.definition,
            responses=responses,
            breakdown=score.breakdown,
            manual_feedback=score.manual_feedback or {},
            policy=policy,
        )
        return result

    @app.get("/api/v2/admin/assessment/drafts")
    def list_drafts(
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
        cohort_id: str | None = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        statement = select(AssessmentDraft).where(AssessmentDraft.organization_id == org_id)
        if cohort_id is not None:
            owned_class(database, cohort_id, org_id)
            linked_drafts = (
                select(AssessmentVersion.draft_id)
                .join(
                    AssessmentAdministration,
                    AssessmentAdministration.version_id == AssessmentVersion.id,
                )
                .where(AssessmentAdministration.cohort_id == cohort_id)
            )
            statement = statement.where(
                or_(AssessmentDraft.cohort_id == cohort_id, AssessmentDraft.id.in_(linked_drafts))
            )
        drafts = database.scalars(
            statement.order_by(AssessmentDraft.updated_at.desc(), AssessmentDraft.id)
        ).all()
        return {"items": [_draft_json(item, database) for item in drafts], "total": len(drafts)}

    @app.post("/api/v2/admin/assessment/drafts", status_code=status.HTTP_201_CREATED)
    def create_draft(
        payload: DraftCreate,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        course: AssessmentCourse | None = None
        cohort: Cohort | None = None
        if payload.course_id is not None:
            course = owned_course(database, payload.course_id, org_id)
        if payload.cohort_id is not None:
            cohort = owned_class(database, payload.cohort_id, org_id)
            if course is None and cohort.assessment_course_id is not None:
                course = owned_course(database, cohort.assessment_course_id, org_id)
            if course is None or cohort.assessment_course_id != course.id:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "ASSESSMENT_DRAFT_CLASS_COURSE_MISMATCH"},
                )
        draft = AssessmentDraft(
            organization_id=org_id,
            course_id=course.id if course is not None else None,
            cohort_id=cohort.id if cohort is not None else None,
            title=payload.title,
            document=payload.document,
            created_by_user_id=authenticated.user_id,
        )
        database.add(draft)
        database.commit()
        return _draft_json(draft, database)

    @app.get("/api/v2/admin/assessment/drafts/{draft_id}")
    def get_draft(
        draft_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        return _draft_json(editable_draft(database, draft_id, org_id), database)

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
        draft = editable_draft(database, draft_id, org_id)
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
        return _draft_json(draft, database)

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
        source = editable_draft(database, draft_id, org_id)
        document = json.loads(json.dumps(source.document))
        if document_schema(document) == V2_SCHEMA:
            document["sections"] = clone_complete_sections(document.get("sections", []))
        else:
            document["items"] = [fresh_item(item) for item in document.get("items", [])]
        document["title"] = payload.title or f"{source.title} copy"
        duplicate = AssessmentDraft(
            organization_id=org_id,
            course_id=source.course_id,
            cohort_id=source.cohort_id,
            title=document["title"],
            document=document,
            created_by_user_id=authenticated.user_id,
        )
        database.add(duplicate)
        database.commit()
        return _draft_json(duplicate, database)

    @app.post("/api/v2/admin/assessment/drafts/{draft_id}/import-questions")
    def import_questions(
        draft_id: str,
        payload: QuestionImport,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        destination = editable_draft(database, draft_id, org_id)
        source = editable_draft(database, payload.source_draft_id, org_id)
        if destination.revision != payload.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_DRAFT_CONFLICT", "revision": destination.revision},
            )
        requested = set(payload.item_ids)
        try:
            document, selected = import_individual_items(
                destination.document, source.document, requested
            )
        except KeyError as error:
            raise HTTPException(
                status_code=404, detail={"code": "ASSESSMENT_ITEM_NOT_FOUND"}
            ) from error
        if len(import_document_items(destination.document)) + len(selected) > 100:
            raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ITEM_LIMIT"})
        destination.document = document
        destination.revision += 1
        destination.updated_at = utc_now()
        database.commit()
        return _draft_json(destination, database)

    @app.post(
        "/api/v2/admin/assessment/drafts/{draft_id}/migrate-v2",
        status_code=status.HTTP_201_CREATED,
    )
    def migrate_draft_v2(
        draft_id: str,
        payload: DraftMigration,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        source = editable_draft(database, draft_id, org_id)
        if source.revision != payload.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={"code": "ASSESSMENT_DRAFT_CONFLICT", "revision": source.revision},
            )
        if document_schema(source.document) == V2_SCHEMA:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_ALREADY_V2"})
        document = migrate_v1_document(source.document, source.id)
        migrated = AssessmentDraft(
            organization_id=source.organization_id,
            course_id=source.course_id,
            cohort_id=source.cohort_id,
            title=f"{source.title} — v2",
            document=document,
            created_by_user_id=authenticated.user_id,
        )
        database.add(migrated)
        database.commit()
        return _draft_json(migrated, database)

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
        return _draft_json(draft, database)

    @app.post("/api/v2/admin/assessment/drafts/{draft_id}/restore")
    def restore_draft(
        draft_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        draft = owned_draft(database, draft_id, org_id)
        draft.status = "draft"
        draft.archived_at = None
        draft.updated_at = utc_now()
        database.commit()
        return _draft_json(draft, database)

    def compile_owned(
        draft_id: str, authenticated: Session, database: OrmSession, requested_org: str | None
    ) -> tuple[AssessmentDraft, CompiledAssessment]:
        draft = editable_draft(
            database, draft_id, organization_id(authenticated, database, requested_org)
        )
        try:
            compiled = (
                compile_assessment_v2(draft.document)
                if document_schema(draft.document) == V2_SCHEMA
                else compile_assessment(draft.document)
            )
            return draft, compiled
        except AssessmentContractError as error:
            raise HTTPException(status_code=422, detail={"code": str(error)}) from error

    @app.post("/api/v2/admin/assessment/drafts/{draft_id}/preflight")
    def preflight_draft(
        draft_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        draft = editable_draft(
            database,
            draft_id,
            organization_id(authenticated, database, requested_org),
        )
        if document_schema(draft.document) == V2_SCHEMA:
            return preflight_v2(draft.document)
        try:
            compiled = compile_assessment(draft.document)
        except AssessmentContractError as error:
            return {
                "valid": False,
                "errors": [
                    {
                        "code": str(error),
                        "path": "/",
                        "message": "The assessment contract is not publishable.",
                        "level": "error",
                    }
                ],
                "warnings": [],
                "metrics": {},
            }
        return {
            "valid": True,
            "errors": [],
            "warnings": [],
            "metrics": {"items": len(assessment_definition_items(compiled.definition))},
        }

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
        version = database.scalar(
            select(AssessmentVersion).where(AssessmentVersion.checksum == compiled.checksum)
        )
        if version is None:
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
                schema=str(compiled.definition["schema"]),
                checksum=compiled.checksum,
                definition=compiled.definition,
                learner_manifest=compiled.learner_manifest,
            )
            database.add(version)
            database.flush()

        administrations: list[tuple[AssessmentAdministration, str | None]] = []
        if payload is not None:
            if payload.mode not in {"practice", "formative", "quiz"}:
                raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_MODE_INVALID"})
            legacy_cohort_ids = [payload.cohort_id] if payload.cohort_id else []
            cohort_ids = list(dict.fromkeys([*payload.cohort_ids, *legacy_cohort_ids]))
            if payload.mode == "quiz" and not cohort_ids:
                raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_ROSTER_REQUIRED"})
            if (
                payload.mode == "quiz"
                and payload.access_code is None
                and document_schema(draft.document) != V2_SCHEMA
            ):
                raise HTTPException(
                    status_code=422, detail={"code": "ASSESSMENT_ACCESS_CODE_REQUIRED"}
                )
            for cohort_id in cohort_ids:
                owned_class(database, cohort_id, draft.organization_id)
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
            targets: list[str | None] = list(cohort_ids) if cohort_ids else [None]
            release_policy = payload.release_policy.model_dump(mode="json", by_alias=True)
            manual_items = any(
                item.get("type") == "paragraph"
                or (item.get("type") == "short-answer" and item.get("manual", False))
                for item in assessment_definition_items(compiled.definition)
            )
            if release_policy.get("timing") == "immediate" and manual_items:
                release_policy["timing"] = "manual"
                release_policy["convertedFromImmediate"] = True
            collection = payload.collection.model_dump(mode="json", by_alias=True)
            for target_cohort_id in targets:
                raw_code = payload.access_code
                if payload.mode == "quiz" and raw_code is None:
                    raw_code = secrets.token_urlsafe(6)
                administration = AssessmentAdministration(
                    organization_id=draft.organization_id,
                    version_id=version.id,
                    cohort_id=target_cohort_id,
                    mode=payload.mode,
                    status="open" if payload.mode == "practice" else "preparing",
                    duration_seconds=payload.duration_seconds,
                    max_attempts=payload.max_attempts,
                    access_code_hash=(
                        hmac.new(
                            identifier_secret.encode(),
                            raw_code.encode(),
                            hashlib.sha256,
                        ).hexdigest()
                        if raw_code is not None
                        else None
                    ),
                    settings={
                        "syntheticFixture": payload.synthetic_fixture,
                        "collection": collection,
                        "releasePolicy": release_policy,
                    },
                    closes_at=payload.collection.closes_at,
                )
                database.add(administration)
                database.flush()
                if target_cohort_id is not None:
                    learners = database.scalars(
                        select(LearnerProfile)
                        .join(
                            CohortEnrollment,
                            CohortEnrollment.learner_id == LearnerProfile.id,
                        )
                        .where(
                            CohortEnrollment.cohort_id == target_cohort_id,
                            CohortEnrollment.status == "active",
                        )
                        .limit(501)
                    ).all()
                    if len(learners) > MAX_ASSESSMENT_ROSTER:
                        raise HTTPException(
                            status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"}
                        )
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
                administrations.append((administration, raw_code))
        database.commit()
        response = {
            "id": version.id,
            "version": version.version,
            "schema": version.schema,
            "checksum": version.checksum,
            "learnerManifest": version.learner_manifest,
            "administrations": [
                {
                    "id": administration.id,
                    "publicId": administration.public_id,
                    "classId": administration.cohort_id,
                    "accessCode": raw_code,
                }
                for administration, raw_code in administrations
            ],
        }
        if len(administrations) == 1:
            administration, raw_code = administrations[0]
            response.update(
                {
                    "publicId": administration.public_id,
                    "administrationId": administration.id,
                    "accessCode": raw_code,
                }
            )
        else:
            response.update({"publicId": None, "administrationId": None})
        return response

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
                    "tileSource": (f"/tiles/{slide.public_id}/{delivery_version(slide)}/slide.dzi"),
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
        cohort_id: str | None = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        statement = (
            select(AssessmentAdministration, AssessmentVersion, AssessmentDraft)
            .join(AssessmentVersion, AssessmentVersion.id == AssessmentAdministration.version_id)
            .join(AssessmentDraft, AssessmentDraft.id == AssessmentVersion.draft_id)
            .where(AssessmentAdministration.organization_id == org_id)
            .order_by(AssessmentAdministration.created_at.desc(), AssessmentAdministration.id)
        )
        if cohort_id is not None:
            owned_class(database, cohort_id, org_id)
            statement = statement.where(AssessmentAdministration.cohort_id == cohort_id)
        rows = database.execute(statement).all()
        return {
            "items": [
                {
                    "id": administration.id,
                    "draftId": draft.id,
                    "cohortId": administration.cohort_id,
                    "publicId": administration.public_id,
                    "title": draft.title,
                    "version": version.version,
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
                    "expectedParticipants": (
                        int(
                            database.scalar(
                                select(func.count(AssessmentRosterSnapshot.id)).where(
                                    AssessmentRosterSnapshot.administration_id == administration.id,
                                    AssessmentRosterSnapshot.status == "active",
                                )
                            )
                            or 0
                        )
                        if administration.cohort_id is not None
                        else None
                    ),
                    "completedParticipants": int(
                        database.scalar(
                            select(
                                func.count(func.distinct(AssessmentAttempt.participant_id))
                            ).where(
                                AssessmentAttempt.administration_id == administration.id,
                                AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
                            )
                        )
                        or 0
                    ),
                }
                for administration, version, draft in rows
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

    @app.patch("/api/v2/admin/assessment/administrations/{administration_id}/status")
    def change_administration_status(
        administration_id: str,
        payload: AdministrationStatusPatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        target = payload.status.casefold()
        if target not in {"draft", "open", "closed"}:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_STATE_INVALID"})
        if administration.status == target:
            return {"id": administration.id, "status": administration.status}

        if target in {"draft", "closed"}:
            was_live = administration.status in {"preparing", "open"}
            administration.status = target
            if was_live:
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
            return {"id": administration.id, "status": administration.status}

        if administration.status not in {"draft", "closed", "preparing"}:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_STATE_INVALID"})
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_VERSION_MISSING"})
        slide_ids = definition_slide_ids(version.definition)
        if administration.mode == "practice":
            administration.status = "preparing"
            try:
                prepare_asset_grants(database, storage, administration, slide_ids)
            except AssessmentAssetError as error:
                database.rollback()
                raise HTTPException(status_code=409, detail={"code": error.code}) from error
            administration.status = "open"
            administration.opens_at = utc_now()
            administration.closes_at = None
            database.commit()
            return {"id": administration.id, "status": administration.status}
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
                detail={"code": "ASSESSMENT_DRAINING", "runningJobs": protection.running_jobs},
                headers={"Retry-After": "2"},
            )
        administration.status = "preparing"
        try:
            prepare_asset_grants(database, storage, administration, slide_ids)
        except AssessmentAssetError as error:
            database.rollback()
            raise HTTPException(status_code=409, detail={"code": error.code}) from error
        administration.status = "open"
        administration.opens_at = utc_now()
        administration.closes_at = None
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

    @app.patch("/api/v2/admin/assessment/administrations/{administration_id}/collection")
    def update_collection(
        administration_id: str,
        payload: CollectionSettings,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        settings = dict(administration.settings)
        collection = payload.model_dump(mode="json", by_alias=True)
        settings["collection"] = collection
        administration.settings = settings
        administration.closes_at = payload.closes_at
        database.commit()
        return {"id": administration.id, "collection": collection}

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
        active_sessions = int(
            database.scalar(
                select(func.count(AssessmentSession.id)).where(
                    AssessmentSession.participant_id.in_(participant_ids),
                    AssessmentSession.revoked_at.is_(None),
                    AssessmentSession.expires_at > utc_now(),
                )
            )
            or 0
        )
        active_attempts = int(
            database.scalar(
                select(func.count(AssessmentAttempt.id)).where(
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentAttempt.status == "active",
                )
            )
            or 0
        )
        submitted = int(
            database.scalar(
                select(func.count(AssessmentAttempt.id)).where(
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentAttempt.status == "submitted",
                )
            )
            or 0
        )
        auto_submitted = int(
            database.scalar(
                select(func.count(AssessmentAttempt.id)).where(
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentAttempt.status == "auto_submitted",
                )
            )
            or 0
        )
        needs_grading = int(
            database.scalar(
                select(func.count(AssessmentGradebookRow.id)).where(
                    AssessmentGradebookRow.administration_id == administration.id,
                    AssessmentGradebookRow.status == "needs_grading",
                )
            )
            or 0
        )
        expected = int(
            database.scalar(
                select(func.count(AssessmentRosterSnapshot.id)).where(
                    AssessmentRosterSnapshot.administration_id == administration.id
                )
            )
            or 0
        )
        entered = int(
            database.scalar(
                select(func.count(AssessmentParticipant.id)).where(
                    AssessmentParticipant.administration_id == administration.id
                )
            )
            or 0
        )
        return {
            "expected": expected,
            "entered": entered,
            "active": active_attempts,
            "submitted": submitted,
            "autoSubmitted": auto_submitted,
            "stale": max(active_attempts - active_sessions, 0),
            "needsGrading": needs_grading,
            "activeSessions": active_sessions,
            "activeAttempts": active_attempts,
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

    def apply_manual_grades(
        administration: AssessmentAdministration,
        grades: list[ManualGradeRequest],
        grader_id: str,
        database: OrmSession,
    ) -> list[dict[str, Any]]:
        definition_version = database.get(AssessmentVersion, administration.version_id)
        if definition_version is None:
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_SCORE_MISSING"})
        items = {
            item["id"]: item for item in assessment_definition_items(definition_version.definition)
        }
        grouped: dict[str, list[ManualGradeRequest]] = {}
        for grade in grades:
            grouped.setdefault(grade.attempt_id, []).append(grade)
        results: list[dict[str, Any]] = []
        for attempt_id, attempt_grades in grouped.items():
            attempt = database.scalar(
                select(AssessmentAttempt).where(
                    AssessmentAttempt.id == attempt_id,
                    AssessmentAttempt.administration_id == administration.id,
                    AssessmentAttempt.status.in_(("submitted", "auto_submitted")),
                )
            )
            if attempt is None:
                raise HTTPException(
                    status_code=404, detail={"code": "ASSESSMENT_ATTEMPT_NOT_FOUND"}
                )
            latest = database.scalar(
                select(AssessmentScoreVersion)
                .where(AssessmentScoreVersion.attempt_id == attempt.id)
                .order_by(AssessmentScoreVersion.version.desc())
            )
            if latest is None:
                raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_SCORE_MISSING"})
            if any(grade.expected_score_version != latest.version for grade in attempt_grades):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "ASSESSMENT_GRADING_CONFLICT",
                        "attemptId": attempt.id,
                        "currentScoreVersion": latest.version,
                    },
                )
            breakdown = dict(latest.breakdown)
            feedback = dict(latest.manual_feedback or {})
            for grade in attempt_grades:
                item = items.get(grade.item_id)
                if item is None or not (
                    item.get("type") == "paragraph"
                    or (item.get("type") == "short-answer" and item.get("manual", False))
                ):
                    raise HTTPException(
                        status_code=422, detail={"code": "ASSESSMENT_ITEM_NOT_MANUAL"}
                    )
                maximum = Decimal(str(item.get("points", "0")))
                points = grade.points.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
                if points < 0 or points > maximum:
                    raise HTTPException(
                        status_code=422, detail={"code": "ASSESSMENT_POINTS_INVALID"}
                    )
                breakdown[grade.item_id] = f"{points:.3f}"
                if grade.feedback is not None:
                    feedback[grade.item_id] = grade.feedback
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
                manual_feedback=feedback,
                graded_by_user_id=grader_id,
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
                    "needs_grading"
                    if any(value is None for value in breakdown.values())
                    else "graded"
                )
            results.append(
                {
                    "attemptId": attempt.id,
                    "scoreVersion": score.version,
                    "points": f"{total:.3f}",
                    "maximumPoints": f"{Decimal(str(score.maximum_points)):.3f}",
                    "status": row.status if row is not None else "aggregate_only",
                }
            )
        if administration.status == "closed":
            snapshot_aggregate(database, administration)
        return results

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
        result = apply_manual_grades(administration, [payload], authenticated.user_id, database)[0]
        database.commit()
        return result

    @app.post("/api/v2/admin/assessment/administrations/{administration_id}/manual-grades")
    def manual_grade_batch(
        administration_id: str,
        payload: ManualGradeBatchRequest,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        administration = owned_administration(
            administration_id, authenticated, database, requested_org
        )
        results = apply_manual_grades(
            administration, payload.grades, authenticated.user_id, database
        )
        database.commit()
        return {"items": results}

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
        if policy["showAuthoredFeedback"] is None:
            policy["showAuthoredFeedback"] = policy["showFeedback"]
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
        export_version = database.get(AssessmentVersion, administration.version_id)
        export_definition = export_version.definition if export_version is not None else {}
        export_sections = export_definition.get("sections", [])
        export_items = [
            (section.get("title", ""), item)
            for section in export_sections
            for item in section.get("items", [])
            if item.get("type") != "section-information"
        ] or [
            ("", item)
            for item in export_definition.get("items", [])
            if item.get("type") != "information"
        ]

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
            metadata_query = (
                select(LearnerProfile.roster_metadata)
                .join(
                    AssessmentParticipant,
                    AssessmentParticipant.learner_id == LearnerProfile.id,
                )
                .where(AssessmentParticipant.administration_id == administration.id)
            )
            metadata_keys = sorted(
                {
                    key
                    for metadata in database.scalars(metadata_query)
                    for key, value in (metadata or {}).items()
                    if value
                }
            )[:50]
            writer.writerow(
                (
                    "student_id",
                    "first_name",
                    "last_name",
                    "display_name",
                    "group",
                    "subgroup",
                    "email",
                    *metadata_keys,
                    "status",
                    "points",
                    "maximum_points",
                    "score_version",
                    "learner_number",
                    "section",
                    "item_id",
                    "item_type",
                    "response",
                    "branch_reachable",
                    "education_metadata",
                    "item_points",
                    "manual_feedback",
                )
            )
            yield buffer.getvalue()
            query = (
                select(
                    LearnerProfile.student_id,
                    LearnerProfile.first_name,
                    LearnerProfile.last_name,
                    AssessmentRosterSnapshot.display_name,
                    LearnerProfile.group_name,
                    LearnerProfile.subgroup_name,
                    LearnerProfile.email,
                    LearnerProfile.roster_metadata,
                    AssessmentGradebookRow.status,
                    AssessmentScoreVersion.points,
                    AssessmentScoreVersion.maximum_points,
                    AssessmentScoreVersion.version,
                    AssessmentAttempt.id,
                    AssessmentScoreVersion.breakdown,
                    AssessmentScoreVersion.manual_feedback,
                )
                .join(
                    AssessmentParticipant,
                    AssessmentParticipant.id == AssessmentGradebookRow.participant_id,
                )
                .join(
                    AssessmentAttempt, AssessmentAttempt.participant_id == AssessmentParticipant.id
                )
                .join(
                    AssessmentRosterSnapshot,
                    (AssessmentRosterSnapshot.administration_id == administration.id)
                    & (AssessmentRosterSnapshot.learner_id == AssessmentParticipant.learner_id),
                )
                .join(LearnerProfile, LearnerProfile.id == AssessmentParticipant.learner_id)
                .outerjoin(
                    AssessmentScoreVersion,
                    AssessmentScoreVersion.id == AssessmentGradebookRow.score_version_id,
                )
                .where(AssessmentGradebookRow.administration_id == administration.id)
                .order_by(AssessmentRosterSnapshot.display_name, AssessmentGradebookRow.id)
                .execution_options(yield_per=100)
            )
            for learner_number, row in enumerate(database.execute(query), 1):
                profile_values = row[:7]
                metadata = row[7] or {}
                result_values = row[8:12]
                attempt_id, breakdown, manual_feedback = row[12], row[13] or {}, row[14] or {}
                responses = response_map = {
                    response.item_id: response.response
                    for response in database.scalars(
                        select(AssessmentResponse).where(
                            AssessmentResponse.attempt_id == attempt_id
                        )
                    )
                }
                reachable_sections = (
                    set(reachable_section_ids(export_definition, responses))
                    if export_sections
                    else set()
                )
                for section_title, item in export_items:
                    section_id = next(
                        (
                            section.get("id")
                            for section in export_sections
                            if item in section.get("items", [])
                        ),
                        None,
                    )
                    rendered_response = json.dumps(
                        response_map.get(item.get("id"), {}),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    buffer.seek(0)
                    buffer.truncate(0)
                    writer.writerow(
                        tuple(
                            safe_cell(value)
                            for value in (
                                *profile_values,
                                *(metadata.get(key, "") for key in metadata_keys),
                                *result_values,
                                learner_number,
                                section_title,
                                item.get("id", ""),
                                item.get("type", ""),
                                rendered_response,
                                section_id in reachable_sections if export_sections else True,
                                json.dumps(
                                    item.get("education", {}),
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                                breakdown.get(item.get("id"), ""),
                                manual_feedback.get(item.get("id"), "")
                                if isinstance(manual_feedback, dict)
                                else "",
                            )
                        )
                    )
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
                LearnerProfile.student_id,
                LearnerProfile.first_name,
                LearnerProfile.last_name,
                LearnerProfile.group_name,
                LearnerProfile.subgroup_name,
                LearnerProfile.email,
                LearnerProfile.roster_metadata,
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
            .join(LearnerProfile, LearnerProfile.id == AssessmentParticipant.learner_id)
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
                    select(AssessmentResponse).where(AssessmentResponse.attempt_id == attempt_id)
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
                        "studentId": student_id,
                        "firstName": first_name,
                        "lastName": last_name,
                        "displayName": display_name,
                        "group": group_name,
                        "subgroup": subgroup_name,
                        "email": email,
                        "metadata": roster_metadata or {},
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
                    for (
                        attempt,
                        display_name,
                        student_id,
                        first_name,
                        last_name,
                        group_name,
                        subgroup_name,
                        email,
                        roster_metadata,
                        grade_status,
                        score,
                    ) in individual_rows
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
        if not administration.settings.get("syntheticFixture", False) and (
            eligible_at is None or eligible_at > utc_now()
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

    def owned_course(database: OrmSession, course_id: str, org_id: str) -> AssessmentCourse:
        course = database.scalar(
            select(AssessmentCourse).where(
                AssessmentCourse.id == course_id,
                AssessmentCourse.organization_id == org_id,
            )
        )
        if course is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_COURSE_NOT_FOUND"})
        return course

    def validate_course_values(
        scoring_method: str,
        course_status: str,
        opens_at: datetime | None,
        closes_at: datetime | None,
    ) -> None:
        if scoring_method not in {"points", "percentage", "weighted", "pass_fail"}:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_COURSE_INVALID"})
        if course_status not in {"draft", "active", "archived"}:
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_COURSE_INVALID"})
        if opens_at is not None and closes_at is not None and as_utc(closes_at) <= as_utc(opens_at):
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_COURSE_DATES_INVALID"})

    def course_json(
        database: OrmSession, course: AssessmentCourse, *, detail: bool = False
    ) -> dict[str, Any]:
        roster_count = int(
            database.scalar(
                select(func.count(AssessmentCourseEnrollment.id)).where(
                    AssessmentCourseEnrollment.course_id == course.id,
                    AssessmentCourseEnrollment.status == "active",
                )
            )
            or 0
        )
        class_rows = database.execute(
            select(Cohort, func.count(CohortEnrollment.id))
            .outerjoin(
                CohortEnrollment,
                (CohortEnrollment.cohort_id == Cohort.id) & (CohortEnrollment.status == "active"),
            )
            .where(Cohort.assessment_course_id == course.id)
            .group_by(Cohort.id)
            .order_by(Cohort.name, Cohort.id)
        ).all()
        value: dict[str, Any] = {
            "id": course.id,
            "name": course.name,
            "courseCode": course.course_code,
            "semester": course.semester,
            "academicYear": course.academic_year,
            "iconKey": course.icon_key,
            "scoringMethod": course.scoring_method,
            "description": course.description,
            "opensAt": as_utc(course.opens_at) if course.opens_at else None,
            "closesAt": as_utc(course.closes_at) if course.closes_at else None,
            "status": course.status,
            "rosterCount": roster_count,
            "classCount": len(class_rows),
        }
        if detail:
            value["classes"] = [
                {
                    "id": cohort.id,
                    "name": cohort.name,
                    "sectionCode": cohort.section_code,
                    "description": cohort.description,
                    "location": cohort.location,
                    "folderId": cohort.folder_id,
                    "rosterRule": cohort.roster_rule or {"mode": "existing", "filters": []},
                    "opensAt": as_utc(cohort.opens_at) if cohort.opens_at else None,
                    "closesAt": as_utc(cohort.closes_at) if cohort.closes_at else None,
                    "status": cohort.status,
                    "studentCount": int(student_count),
                }
                for cohort, student_count in class_rows
            ]
        return value

    @app.get("/api/v2/admin/assessment/courses")
    def list_courses(
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        courses = database.scalars(
            select(AssessmentCourse)
            .where(AssessmentCourse.organization_id == org_id)
            .order_by(AssessmentCourse.updated_at.desc(), AssessmentCourse.id)
        ).all()
        return {
            "items": [course_json(database, course) for course in courses],
            "total": len(courses),
        }

    @app.post("/api/v2/admin/assessment/courses", status_code=status.HTTP_201_CREATED)
    def create_course(
        payload: CourseCreate,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        validate_course_values(
            payload.scoring_method, payload.status, payload.opens_at, payload.closes_at
        )
        course = AssessmentCourse(
            organization_id=org_id,
            name=payload.name.strip(),
            course_code=payload.course_code.strip(),
            semester=payload.semester.strip(),
            academic_year=payload.academic_year,
            icon_key=payload.icon_key,
            scoring_method=payload.scoring_method,
            description=payload.description.strip() if payload.description else None,
            opens_at=payload.opens_at,
            closes_at=payload.closes_at,
            status=payload.status,
            created_by_user_id=authenticated.user_id,
        )
        database.add(course)
        try:
            database.commit()
        except IntegrityError as exc:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_COURSE_CODE_EXISTS"}
            ) from exc
        return course_json(database, course, detail=True)

    @app.get("/api/v2/admin/assessment/courses/{course_id}")
    def get_course(
        course_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        course = owned_course(
            database, course_id, organization_id(authenticated, database, requested_org)
        )
        return course_json(database, course, detail=True)

    @app.patch("/api/v2/admin/assessment/courses/{course_id}")
    def update_course(
        course_id: str,
        payload: CoursePatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        course = owned_course(
            database, course_id, organization_id(authenticated, database, requested_org)
        )
        updates = payload.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(course, key, value.strip() if isinstance(value, str) else value)
        validate_course_values(
            course.scoring_method, course.status, course.opens_at, course.closes_at
        )
        try:
            database.commit()
        except IntegrityError as exc:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_COURSE_CODE_EXISTS"}
            ) from exc
        return course_json(database, course, detail=True)

    @app.post("/api/v2/admin/assessment/courses/{course_id}/roster/import/preview")
    def preview_course_roster(
        course_id: str,
        payload: ImportRows,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        owned_course(database, course_id, organization_id(authenticated, database, requested_org))
        rows = _parse_rows(payload.rows, require_structured=True)
        warnings = _roster_import_warnings(database, course_id, rows)
        return {
            "validCount": len(rows),
            "checksum": _rows_checksum(rows),
            "warningCount": len(warnings),
            "warnings": warnings[:50],
            "preview": [
                {
                    "studentId": row.student_id,
                    "firstName": row.first_name,
                    "lastName": row.last_name,
                    "displayName": row.display_name,
                    "group": row.group_name,
                    "subgroup": row.subgroup_name,
                    "metadata": row.metadata or {},
                }
                for row in rows[:20]
            ],
        }

    @app.post(
        "/api/v2/admin/assessment/courses/{course_id}/roster/import/commit",
        status_code=status.HTTP_201_CREATED,
    )
    def commit_course_roster(
        course_id: str,
        payload: ImportRows,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, int]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_course(database, course_id, org_id)
        rows = _parse_rows(payload.rows, require_structured=True)
        if payload.checksum is None or not hmac.compare_digest(
            payload.checksum, _rows_checksum(rows)
        ):
            raise HTTPException(status_code=409, detail={"code": "ASSESSMENT_IMPORT_CHANGED"})
        warnings = _roster_import_warnings(database, course_id, rows)
        if warnings and not payload.confirm_warnings:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ASSESSMENT_ROSTER_CONFIRMATION_REQUIRED",
                    "warningCount": len(warnings),
                    "warnings": warnings[:50],
                },
            )
        existing_count = int(
            database.scalar(
                select(func.count(AssessmentCourseEnrollment.id)).where(
                    AssessmentCourseEnrollment.course_id == course_id,
                    AssessmentCourseEnrollment.status == "active",
                )
            )
            or 0
        )
        created = 0
        skipped = 0
        for row in rows:
            identifier_hash = hmac.new(
                identifier_secret.encode(), row.identifier.casefold().encode(), hashlib.sha256
            ).hexdigest()
            learner = database.scalar(
                select(LearnerProfile).where(
                    LearnerProfile.organization_id == org_id,
                    (LearnerProfile.student_id == row.student_id)
                    | (LearnerProfile.login_identifier_hash == identifier_hash),
                )
            )
            enrollment = (
                None
                if learner is None
                else database.scalar(
                    select(AssessmentCourseEnrollment).where(
                        AssessmentCourseEnrollment.course_id == course_id,
                        AssessmentCourseEnrollment.learner_id == learner.id,
                    )
                )
            )
            if learner is not None and enrollment is not None and enrollment.status == "active":
                skipped += 1
                continue
            if learner is None:
                learner = LearnerProfile(
                    organization_id=org_id,
                    teaching_pseudonym=f"learner-{identifier_hash[:12]}",
                    login_identifier_hash=identifier_hash,
                    created_by_user_id=authenticated.user_id,
                )
                database.add(learner)
                database.flush()
                learner.student_id = row.student_id
                learner.first_name = row.first_name
                learner.last_name = row.last_name
                learner.display_name = row.display_name
                learner.group_name = row.group_name
                learner.subgroup_name = row.subgroup_name
                learner.email = row.email
                learner.roster_metadata = row.metadata or {}
            if enrollment is None:
                if existing_count + created >= MAX_ASSESSMENT_ROSTER:
                    raise HTTPException(status_code=400, detail={"code": "ASSESSMENT_ROSTER_LIMIT"})
                database.add(
                    AssessmentCourseEnrollment(
                        organization_id=org_id,
                        course_id=course_id,
                        learner_id=learner.id,
                        created_by_user_id=authenticated.user_id,
                    )
                )
                created += 1
            elif enrollment.status == "withdrawn":
                enrollment.status = "active"
                created += 1
        database.commit()
        return {"created": created, "skipped": skipped}

    @app.get("/api/v2/admin/assessment/courses/{course_id}/roster")
    def list_course_roster(
        course_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
        query: str = "",
        sort_by: str = "name",
        sort_direction: str = "asc",
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_course(database, course_id, org_id)
        sort_columns = {
            "name": (
                LearnerProfile.first_name,
                LearnerProfile.last_name,
                LearnerProfile.student_id,
            ),
            "student_id": (LearnerProfile.student_id,),
            "group": (
                LearnerProfile.group_name,
                LearnerProfile.subgroup_name,
                LearnerProfile.first_name,
            ),
            "subgroup": (
                LearnerProfile.subgroup_name,
                LearnerProfile.group_name,
                LearnerProfile.first_name,
            ),
            "email": (LearnerProfile.email, LearnerProfile.first_name),
            "status": (AssessmentCourseEnrollment.status, LearnerProfile.first_name),
        }
        columns = sort_columns.get(sort_by, sort_columns["name"])
        descending = sort_direction.casefold() == "desc"
        order = [
            func.coalesce(column, "").desc() if descending else func.coalesce(column, "").asc()
            for column in columns
        ]
        filters = [AssessmentCourseEnrollment.course_id == course_id]
        if query.strip():
            pattern = f"%{query.strip()}%"
            filters.append(
                LearnerProfile.student_id.ilike(pattern)
                | LearnerProfile.first_name.ilike(pattern)
                | LearnerProfile.last_name.ilike(pattern)
                | LearnerProfile.group_name.ilike(pattern)
                | LearnerProfile.subgroup_name.ilike(pattern)
            )
        statement = (
            select(LearnerProfile, AssessmentCourseEnrollment)
            .join(
                AssessmentCourseEnrollment,
                AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
            )
            .where(*filters)
            .order_by(*order, LearnerProfile.id)
        )
        total = int(database.scalar(select(func.count()).select_from(statement.subquery())) or 0)
        column_rows = database.execute(
            select(
                LearnerProfile.group_name,
                LearnerProfile.subgroup_name,
                LearnerProfile.email,
                LearnerProfile.roster_metadata,
            )
            .join(
                AssessmentCourseEnrollment,
                AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
            )
            .where(*filters)
        ).all()
        visible_columns = [
            {"key": "student_id", "label": "Student ID", "sortable": True},
            {"key": "name", "label": "Name", "sortable": True},
        ]
        if any(row.group_name for row in column_rows):
            visible_columns.append({"key": "group", "label": "Group", "sortable": True})
        if any(row.subgroup_name for row in column_rows):
            visible_columns.append({"key": "subgroup", "label": "Subgroup", "sortable": True})
        if any(row.email for row in column_rows):
            visible_columns.append({"key": "email", "label": "Email", "sortable": True})
        metadata_keys: list[str] = []
        for column_row in column_rows:
            for key, value in (column_row.roster_metadata or {}).items():
                if value and key not in metadata_keys and len(metadata_keys) < 20:
                    metadata_keys.append(key)
        visible_columns.extend(
            {
                "key": f"metadata:{key}",
                "label": key.replace("_", " ").strip().title(),
                "sortable": False,
            }
            for key in metadata_keys
        )
        visible_columns.append({"key": "status", "label": "Status", "sortable": True})
        rows = database.execute(
            statement.offset(max(0, offset)).limit(max(1, min(limit, 200)))
        ).all()
        return {
            "items": [
                {
                    "id": learner.id,
                    "studentId": learner.student_id,
                    "firstName": learner.first_name,
                    "lastName": learner.last_name,
                    "displayName": learner.display_name,
                    "group": learner.group_name,
                    "subgroup": learner.subgroup_name,
                    "email": learner.email,
                    "metadata": learner.roster_metadata or {},
                    "status": enrollment.status,
                }
                for learner, enrollment in rows
            ],
            "columns": visible_columns,
            "total": total,
            "limit": min(limit, 200),
            "offset": max(0, offset),
        }

    @app.get("/api/v2/admin/assessment/courses/{course_id}/roster/export")
    def export_course_roster(
        course_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> StreamingResponse:
        org_id = organization_id(authenticated, database, requested_org)
        course = owned_course(database, course_id, org_id)
        rows = database.execute(
            select(LearnerProfile, AssessmentCourseEnrollment)
            .join(
                AssessmentCourseEnrollment,
                AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
            )
            .where(AssessmentCourseEnrollment.course_id == course_id)
            .order_by(LearnerProfile.student_id, LearnerProfile.id)
        ).all()
        include_email = any(learner.email for learner, _ in rows)
        metadata_keys: list[str] = []
        for learner, _ in rows:
            for key, value in (learner.roster_metadata or {}).items():
                if value and key not in metadata_keys:
                    metadata_keys.append(key)
        output = StringIO()
        writer = csv.writer(output, lineterminator="\r\n")
        header = ["student_id", "first_name", "last_name", "group", "subgroup"]
        if include_email:
            header.append("email")
        header.extend(metadata_keys)
        header.append("status")
        writer.writerow(header)
        for learner, enrollment in rows:
            values = [
                learner.student_id or "",
                learner.first_name or "",
                learner.last_name or "",
                learner.group_name or "",
                learner.subgroup_name or "",
            ]
            if include_email:
                values.append(learner.email or "")
            values.extend((learner.roster_metadata or {}).get(key, "") for key in metadata_keys)
            values.append(enrollment.status)
            writer.writerow(values)
        safe_code = "".join(
            character if character.isalnum() or character in "-_" else "-"
            for character in course.course_code
        )
        return StreamingResponse(
            iter(["\ufeff" + output.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_code}-roster.csv"'},
        )

    @app.patch("/api/v2/admin/assessment/courses/{course_id}/roster/{learner_id}")
    def update_course_enrollment(
        course_id: str,
        learner_id: str,
        payload: EnrollmentPatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, str]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_course(database, course_id, org_id)
        if payload.status not in {"active", "withdrawn"}:
            raise HTTPException(
                status_code=422, detail={"code": "ASSESSMENT_COURSE_ROSTER_INVALID"}
            )
        enrollment = database.scalar(
            select(AssessmentCourseEnrollment).where(
                AssessmentCourseEnrollment.course_id == course_id,
                AssessmentCourseEnrollment.learner_id == learner_id,
                AssessmentCourseEnrollment.organization_id == org_id,
            )
        )
        if enrollment is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_STUDENT_NOT_FOUND"})
        enrollment.status = payload.status
        if payload.status == "withdrawn":
            database.execute(
                update(CohortEnrollment)
                .where(
                    CohortEnrollment.learner_id == learner_id,
                    CohortEnrollment.cohort_id.in_(
                        select(Cohort.id).where(Cohort.assessment_course_id == course_id)
                    ),
                )
                .values(status="withdrawn")
            )
        database.commit()
        return {"learnerId": learner_id, "status": enrollment.status}

    @app.patch("/api/v2/admin/assessment/courses/{course_id}/roster/{learner_id}/profile")
    def update_course_learner_profile(
        course_id: str,
        learner_id: str,
        payload: LearnerProfilePatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_course(database, course_id, org_id)
        learner = database.scalar(
            select(LearnerProfile)
            .join(
                AssessmentCourseEnrollment,
                AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
            )
            .where(
                AssessmentCourseEnrollment.course_id == course_id,
                LearnerProfile.id == learner_id,
                LearnerProfile.organization_id == org_id,
            )
        )
        if learner is None:
            raise HTTPException(status_code=404, detail={"code": "ASSESSMENT_STUDENT_NOT_FOUND"})
        metadata: dict[str, str] = {}
        reserved = {
            "student_id",
            "first_name",
            "last_name",
            "group",
            "subgroup",
            "email",
            "status",
            "name",
        }
        for raw_key, raw_value in payload.metadata.items():
            key = _header_key(raw_key)[:80]
            value = raw_value.strip()[:1000]
            if key and value and key not in reserved:
                metadata[key] = value
        student_id = payload.student_id.strip()
        first_name = payload.first_name.strip()
        last_name = payload.last_name.strip() if payload.last_name else None
        learner.student_id = student_id
        learner.first_name = first_name
        learner.last_name = last_name or None
        learner.display_name = f"{first_name} {last_name or ''}".strip()
        learner.group_name = payload.group_name.strip() if payload.group_name else None
        learner.subgroup_name = payload.subgroup_name.strip() if payload.subgroup_name else None
        learner.email = payload.email.strip() if payload.email else None
        learner.roster_metadata = metadata
        learner.login_identifier_hash = hmac.new(
            identifier_secret.encode(),
            student_id.casefold().encode(),
            hashlib.sha256,
        ).hexdigest()
        try:
            database.commit()
        except IntegrityError as exc:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_STUDENT_ID_EXISTS"}
            ) from exc
        enrollment = database.scalar(
            select(AssessmentCourseEnrollment).where(
                AssessmentCourseEnrollment.course_id == course_id,
                AssessmentCourseEnrollment.learner_id == learner_id,
            )
        )
        return {
            "id": learner.id,
            "studentId": learner.student_id,
            "firstName": learner.first_name,
            "lastName": learner.last_name,
            "displayName": learner.display_name,
            "group": learner.group_name,
            "subgroup": learner.subgroup_name,
            "email": learner.email,
            "metadata": learner.roster_metadata or {},
            "status": enrollment.status if enrollment else "active",
        }

    @app.delete("/api/v2/admin/assessment/courses/{course_id}/roster")
    def remove_all_course_learners(
        course_id: str,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, int]:
        org_id = organization_id(authenticated, database, requested_org)
        owned_course(database, course_id, org_id)
        learner_ids = list(
            database.scalars(
                select(AssessmentCourseEnrollment.learner_id).where(
                    AssessmentCourseEnrollment.course_id == course_id,
                    AssessmentCourseEnrollment.organization_id == org_id,
                )
            ).all()
        )
        if learner_ids:
            database.execute(
                delete(CohortEnrollment).where(
                    CohortEnrollment.learner_id.in_(learner_ids),
                    CohortEnrollment.cohort_id.in_(
                        select(Cohort.id).where(Cohort.assessment_course_id == course_id)
                    ),
                )
            )
            database.execute(
                delete(AssessmentCourseEnrollment).where(
                    AssessmentCourseEnrollment.course_id == course_id,
                    AssessmentCourseEnrollment.organization_id == org_id,
                )
            )
        database.commit()
        return {"removed": len(learner_ids)}

    @app.post(
        "/api/v2/admin/assessment/courses/{course_id}/classes", status_code=status.HTTP_201_CREATED
    )
    def create_course_class(
        course_id: str,
        payload: CourseClassCreate,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        course = owned_course(database, course_id, org_id)
        opens_at = payload.opens_at if payload.opens_at is not None else course.opens_at
        closes_at = payload.closes_at if payload.closes_at is not None else course.closes_at
        if opens_at is not None and closes_at is not None and as_utc(closes_at) <= as_utc(opens_at):
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_CLASS_DATES_INVALID"})
        learners = list(
            database.scalars(
                select(LearnerProfile)
                .join(
                    AssessmentCourseEnrollment,
                    AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
                )
                .where(
                    AssessmentCourseEnrollment.course_id == course_id,
                    AssessmentCourseEnrollment.status == "active",
                )
            ).all()
        )
        selected_ids = _resolve_roster_rule(learners, payload.roster_rule)
        cohort = Cohort(
            organization_id=org_id,
            assessment_course_id=course_id,
            name=payload.name.strip(),
            section_code=payload.section_code.strip(),
            description=payload.description,
            location=payload.location,
            roster_rule=_roster_rule_json(payload.roster_rule),
            opens_at=opens_at,
            closes_at=closes_at,
            created_by_user_id=authenticated.user_id,
        )
        database.add(cohort)
        try:
            database.flush()
            for learner_id in selected_ids:
                database.add(
                    CohortEnrollment(
                        organization_id=org_id,
                        cohort_id=cohort.id,
                        learner_id=learner_id,
                        created_by_user_id=authenticated.user_id,
                    )
                )
            database.commit()
        except IntegrityError as exc:
            database.rollback()
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_CLASS_NAME_EXISTS"}
            ) from exc
        return {
            "id": cohort.id,
            "name": cohort.name,
            "sectionCode": cohort.section_code,
            "studentCount": len(selected_ids),
            "status": cohort.status,
        }

    @app.put("/api/v2/admin/assessment/classes/{cohort_id}/roster")
    def replace_class_roster(
        cohort_id: str,
        payload: ClassRosterPatch,
        authenticated: CsrfSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, int]:
        org_id = organization_id(authenticated, database, requested_org)
        cohort = owned_class(database, cohort_id, org_id)
        if cohort.assessment_course_id is None:
            raise HTTPException(
                status_code=409, detail={"code": "ASSESSMENT_CLASS_COURSE_REQUIRED"}
            )
        learners = list(
            database.scalars(
                select(LearnerProfile)
                .join(
                    AssessmentCourseEnrollment,
                    AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
                )
                .where(
                    AssessmentCourseEnrollment.course_id == cohort.assessment_course_id,
                    AssessmentCourseEnrollment.status == "active",
                )
            ).all()
        )
        existing = {
            item.learner_id: item
            for item in database.scalars(
                select(CohortEnrollment).where(CohortEnrollment.cohort_id == cohort_id)
            ).all()
        }
        selected_ids = _resolve_roster_rule(learners, payload.roster_rule, set(existing))
        for learner_id, enrollment in existing.items():
            enrollment.status = "active" if learner_id in selected_ids else "withdrawn"
        for learner_id in selected_ids - existing.keys():
            database.add(
                CohortEnrollment(
                    organization_id=org_id,
                    cohort_id=cohort_id,
                    learner_id=learner_id,
                    created_by_user_id=authenticated.user_id,
                )
            )
        cohort.roster_rule = _roster_rule_json(payload.roster_rule)
        database.commit()
        return {"active": len(selected_ids)}

    @app.get("/api/v2/admin/assessment/classes/{cohort_id}/roster-selection")
    def class_roster_selection(
        cohort_id: str,
        authenticated: AdminSession,
        database: Database,
        requested_org: ActiveOrganization = None,
    ) -> dict[str, Any]:
        org_id = organization_id(authenticated, database, requested_org)
        cohort = owned_class(database, cohort_id, org_id)
        if cohort.assessment_course_id is None:
            return {"items": [], "total": 0}
        selected_ids = set(
            database.scalars(
                select(CohortEnrollment.learner_id).where(
                    CohortEnrollment.cohort_id == cohort_id, CohortEnrollment.status == "active"
                )
            ).all()
        )
        rows = database.execute(
            select(LearnerProfile, AssessmentCourseEnrollment)
            .join(
                AssessmentCourseEnrollment,
                AssessmentCourseEnrollment.learner_id == LearnerProfile.id,
            )
            .where(
                AssessmentCourseEnrollment.course_id == cohort.assessment_course_id,
                AssessmentCourseEnrollment.status == "active",
            )
            .order_by(LearnerProfile.display_name, LearnerProfile.id)
        ).all()
        return {
            "items": [
                {
                    "id": learner.id,
                    "studentId": learner.student_id,
                    "displayName": learner.display_name,
                    "group": learner.group_name,
                    "subgroup": learner.subgroup_name,
                    "metadata": learner.roster_metadata or {},
                    "selected": learner.id in selected_ids,
                }
                for learner, _ in rows
            ],
            "rosterRule": cohort.roster_rule or {"mode": "existing", "filters": []},
            "total": len(rows),
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
        for field in ("section_code", "description", "location", "opens_at", "closes_at"):
            if field in payload.model_fields_set:
                setattr(cohort, field, getattr(payload, field))
        if "folder_id" in payload.model_fields_set:
            if payload.folder_id is not None:
                folder = database.scalar(
                    select(Folder).where(
                        Folder.id == payload.folder_id,
                        Folder.trashed_at.is_(None),
                    )
                )
                if folder is None:
                    raise HTTPException(
                        status_code=422, detail={"code": "ASSESSMENT_CLASS_FOLDER_INVALID"}
                    )
            cohort.folder_id = payload.folder_id
        if payload.status is not None:
            cohort.status = payload.status
        if (
            cohort.opens_at is not None
            and cohort.closes_at is not None
            and as_utc(cohort.closes_at) <= as_utc(cohort.opens_at)
        ):
            raise HTTPException(status_code=422, detail={"code": "ASSESSMENT_CLASS_DATES_INVALID"})
        database.commit()
        return {
            "id": cohort.id,
            "name": cohort.name,
            "sectionCode": cohort.section_code,
            "folderId": cohort.folder_id,
            "status": cohort.status,
        }

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
            "preview": [{"displayName": row.display_name} for row in rows[:20]],
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
        for row in rows:
            identifier_hash = hmac.new(
                identifier_secret.encode(), row.identifier.casefold().encode(), hashlib.sha256
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
                    display_name=row.display_name,
                    created_by_user_id=authenticated.user_id,
                )
                database.add(learner)
                database.flush()
            if row.student_id is not None:
                learner.student_id = row.student_id
                learner.first_name = row.first_name
                learner.last_name = row.last_name
                learner.display_name = row.display_name
                learner.group_name = row.group_name
                learner.subgroup_name = row.subgroup_name
                learner.email = row.email
                learner.roster_metadata = row.metadata or {}
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
            if existing + created > MAX_ASSESSMENT_ROSTER:
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

    @app.patch("/api/v2/admin/assessment/classes/{cohort_id}/students/{learner_id}")
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
