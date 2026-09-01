import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .domain import SlideState


def _uuid() -> str:
    return str(uuid.uuid4())


def _public_id() -> str:
    return secrets.token_urlsafe(16)


def _now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    credential_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    credential_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user: Mapped[User] = relationship()


class Organization(Base):
    __tablename__ = "organizations"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_organizations_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        CheckConstraint(
            "role IN ('owner', 'admin', 'instructor', 'teaching_assistant', "
            "'researcher', 'auditor')",
            name="ck_memberships_role",
        ),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_memberships_status"),
        Index("ix_memberships_user_status", "user_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class StaffInvitation(Base):
    __tablename__ = "staff_invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('owner', 'admin', 'instructor', 'teaching_assistant', "
            "'researcher', 'auditor')",
            name="ck_staff_invitations_role",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'revoked')",
            name="ck_staff_invitations_status",
        ),
        Index("ix_staff_invitations_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    invitee_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "teaching_pseudonym", name="uq_learners_org_pseudonym"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_learners_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    teaching_pseudonym: Mapped[str] = mapped_column(String(100), nullable=False)
    login_identifier_hash: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Cohort(Base):
    __tablename__ = "cohorts"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_cohorts_org_name"),
        CheckConstraint("status IN ('active', 'archived')", name="ck_cohorts_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class CohortEnrollment(Base):
    __tablename__ = "cohort_enrollments"
    __table_args__ = (
        UniqueConstraint("cohort_id", "learner_id", name="uq_enrollments_cohort_learner"),
        CheckConstraint("status IN ('active', 'withdrawn')", name="ck_enrollments_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cohort_id: Mapped[str] = mapped_column(
        ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False
    )
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AssessmentDraft(Base):
    __tablename__ = "assessment_drafts"
    __table_args__ = (
        CheckConstraint("revision >= 1", name="ck_assessment_drafts_revision"),
        CheckConstraint("status IN ('draft', 'archived')", name="ck_assessment_drafts_status"),
        Index("ix_assessment_drafts_org_updated", "organization_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    document: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AssessmentVersion(Base):
    __tablename__ = "assessment_versions"
    __table_args__ = (UniqueConstraint("draft_id", "version", name="uq_assessment_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    draft_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_drafts.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema: Mapped[str] = mapped_column(String(80), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    learner_manifest: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentAdministration(Base):
    __tablename__ = "assessment_administrations"
    __table_args__ = (
        CheckConstraint("mode IN ('practice', 'formative', 'quiz')", name="ck_assessment_mode"),
        CheckConstraint(
            "status IN ('preparing', 'open', 'closed', 'purged')",
            name="ck_assessment_administration_status",
        ),
        CheckConstraint("max_attempts BETWEEN 1 AND 3", name="ck_assessment_attempt_limit"),
        CheckConstraint("duration_seconds BETWEEN 1 AND 14400", name="ck_assessment_duration"),
        Index("ix_assessment_administration_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, default=_public_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    version_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_versions.id", ondelete="RESTRICT"), nullable=False
    )
    cohort_id: Mapped[str | None] = mapped_column(ForeignKey("cohorts.id", ondelete="RESTRICT"))
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="preparing")
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    access_code_hash: Mapped[str | None] = mapped_column(String(64))
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    opens_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closes_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentRosterSnapshot(Base):
    __tablename__ = "assessment_roster_snapshots"
    __table_args__ = (
        UniqueConstraint("administration_id", "learner_id", name="uq_assessment_roster_learner"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False
    )
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="RESTRICT"), nullable=False
    )
    login_identifier_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")


class AssessmentParticipant(Base):
    __tablename__ = "assessment_participants"
    __table_args__ = (
        CheckConstraint("kind IN ('roster', 'anonymous')", name="ck_assessment_participant_kind"),
        UniqueConstraint(
            "administration_id", "learner_id", name="uq_assessment_participant_learner"
        ),
        UniqueConstraint(
            "administration_id", "receipt_hash", name="uq_assessment_participant_receipt"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False
    )
    learner_id: Mapped[str | None] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="RESTRICT")
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    receipt_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentSession(Base):
    __tablename__ = "assessment_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_participants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    device_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssessmentAssetGrant(Base):
    __tablename__ = "assessment_asset_grants"
    __table_args__ = (
        UniqueConstraint("administration_id", "slide_id", name="uq_assessment_asset_slide"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="RESTRICT"), nullable=False
    )
    grant_path: Mapped[str] = mapped_column(String(500), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        UniqueConstraint("participant_id", "ordinal", name="uq_assessment_attempt_ordinal"),
        CheckConstraint("ordinal BETWEEN 1 AND 3", name="ck_assessment_attempt_ordinal"),
        CheckConstraint(
            "status IN ('active', 'submitted', 'auto_submitted')",
            name="ck_assessment_attempt_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_participants.id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    order_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AssessmentResponse(Base):
    __tablename__ = "assessment_responses"
    __table_args__ = (
        UniqueConstraint("attempt_id", "item_id", name="uq_assessment_response_item"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(String(36), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AssessmentScoreVersion(Base):
    __tablename__ = "assessment_score_versions"
    __table_args__ = (
        UniqueConstraint("attempt_id", "version", name="uq_assessment_score_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[Any] = mapped_column(Numeric(12, 3), nullable=False)
    maximum_points: Mapped[Any] = mapped_column(Numeric(12, 3), nullable=False)
    breakdown: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentGradebookRow(Base):
    __tablename__ = "assessment_gradebook_rows"
    __table_args__ = (
        UniqueConstraint("administration_id", "participant_id", name="uq_assessment_gradebook_row"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_participants.id", ondelete="CASCADE"), nullable=False
    )
    score_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("assessment_score_versions.id", ondelete="SET NULL")
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")


class AssessmentRelease(Base):
    __tablename__ = "assessment_releases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False
    )
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    released_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    released_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentAggregateSnapshot(Base):
    __tablename__ = "assessment_aggregate_snapshots"
    __table_args__ = (
        UniqueConstraint("administration_id", "version", name="uq_assessment_aggregate_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    administration_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_administrations.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    aggregate: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AssessmentAccessThrottle(Base):
    __tablename__ = "assessment_access_throttles"
    __table_args__ = (
        UniqueConstraint("scope", "key_hash", "window_started_at", name="uq_assessment_throttle"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    scope: Mapped[str] = mapped_column(String(30), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class AssessmentMutationReceipt(Base):
    __tablename__ = "assessment_mutation_receipts"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "operation", "key_hash", name="uq_assessment_mutation_receipt"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_sessions.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LearnerCredential(Base):
    __tablename__ = "learner_credentials"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked')", name="ck_learner_credentials_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    access_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    recovery_credential_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ResearchPseudonym(Base):
    __tablename__ = "research_pseudonyms"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope_id", "pseudonym", name="uq_research_scope_pseudonym"
        ),
        UniqueConstraint("learner_id", "scope_id", name="uq_research_learner_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    learner_id: Mapped[str] = mapped_column(
        ForeignKey("learner_profiles.id", ondelete="CASCADE"), nullable=False
    )
    scope_id: Mapped[str] = mapped_column(String(100), nullable=False)
    pseudonym: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class OidcIdentityLink(Base):
    __tablename__ = "oidc_identity_links"
    __table_args__ = (
        UniqueConstraint("issuer", "subject_hash", name="uq_oidc_issuer_subject"),
        CheckConstraint("status IN ('linked', 'revoked')", name="ck_oidc_links_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issuer: Mapped[str] = mapped_column(String(500), nullable=False)
    subject_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="linked")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class DesktopPairing(Base):
    __tablename__ = "desktop_pairings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    device_code_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    user_code: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    exchanged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DesktopCredential(Base):
    __tablename__ = "desktop_credentials"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_name: Mapped[str] = mapped_column(String(120), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DesktopSyncEvent(Base):
    __tablename__ = "desktop_sync_events"
    __table_args__ = (
        Index(
            "ix_desktop_sync_events_entity_sequence",
            "entity_type",
            "entity_id",
            "sequence",
        ),
    )

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(36), nullable=False)
    operation: Mapped[str] = mapped_column(String(20), nullable=False)
    revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DesktopIngest(Base):
    __tablename__ = "desktop_ingests"
    __table_args__ = (
        CheckConstraint(
            "ingest_mode IN ('prepared_v2', 'ome_dynamic_v1')",
            name="ck_desktop_ingests_mode",
        ),
        CheckConstraint("package_length > 0", name="ck_desktop_ingests_length_positive"),
        CheckConstraint(
            "received_bytes >= 0 AND received_bytes <= package_length",
            name="ck_desktop_ingests_received_range",
        ),
        Index("ix_desktop_ingests_credential_status", "credential_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("desktop_credentials.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str | None] = mapped_column(ForeignKey("slides.id", ondelete="SET NULL"))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    artifact_revision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    package_length: Mapped[int] = mapped_column(Integer, nullable=False)
    received_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    ingest_mode: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="prepared_v2",
        server_default="prepared_v2",
    )
    ome_profile: Mapped[str | None] = mapped_column(String(40))
    ome_width: Mapped[int | None] = mapped_column(Integer)
    ome_height: Mapped[int | None] = mapped_column(Integer)
    ome_downsample: Mapped[float | None] = mapped_column(Float)
    ome_jpeg_quality: Mapped[int | None] = mapped_column(Integer)
    derivative_bytes: Mapped[int | None] = mapped_column(Integer)
    derivative_file_count: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploading")
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ResultDelivery(Base):
    __tablename__ = "result_deliveries"
    __table_args__ = (
        UniqueConstraint("slide_id", "artifact_revision_id", "payload_sha256"),
        CheckConstraint(
            "received_bytes >= 0 AND received_bytes <= payload_length",
            name="ck_result_deliveries_received_range",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    credential_id: Mapped[str] = mapped_column(
        ForeignKey("desktop_credentials.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_revision_id: Mapped[str] = mapped_column(String(100), nullable=False)
    slide_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_length: Mapped[int] = mapped_column(BigInteger, nullable=False)
    received_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="uploading")
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (UniqueConstraint("slide_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    delivery_id: Mapped[str] = mapped_column(
        ForeignKey("result_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class PathObjectMetadata(Base):
    __tablename__ = "path_object_metadata"
    __table_args__ = (UniqueConstraint("slide_id", "external_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    delivery_id: Mapped[str] = mapped_column(
        ForeignKey("result_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    external_id: Mapped[str] = mapped_column(String(100), nullable=False)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parent_external_id: Mapped[str | None] = mapped_column(String(100))
    classification: Mapped[str | None] = mapped_column(String(120))
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    style: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class PathObjectMeasurement(Base):
    __tablename__ = "path_object_measurements"
    __table_args__ = (UniqueConstraint("object_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    object_id: Mapped[str] = mapped_column(
        ForeignKey("path_object_metadata.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")


class ManagedResultAttachment(Base):
    __tablename__ = "managed_result_attachments"
    __table_args__ = (UniqueConstraint("delivery_id", "sha256"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    delivery_id: Mapped[str] = mapped_column(
        ForeignKey("result_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_name: Mapped[str] = mapped_column(String(120), nullable=False)


class PasswordRecoveryCode(Base):
    __tablename__ = "password_recovery_codes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PasswordRecoveryAttempt(Base):
    __tablename__ = "password_recovery_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    client_key_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ip_key_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )


class Folder(Base):
    __tablename__ = "folders"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_folders_sort_order_nonnegative"),
        Index(
            "uq_folders_root_normalized_name",
            "normalized_name",
            unique=True,
            sqlite_where=text("parent_id IS NULL"),
            postgresql_where=text("parent_id IS NULL"),
        ),
        UniqueConstraint(
            "parent_id",
            "normalized_name",
            name="uq_folders_parent_normalized_name",
        ),
        Index("ix_folders_parent_order", "parent_id", "sort_order", "normalized_name"),
        Index("ix_folders_trashed_at", "trashed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    parent_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", ondelete="RESTRICT"), index=True
    )
    previous_parent_id: Mapped[str | None] = mapped_column(String(36))
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Slide(Base):
    __tablename__ = "slides"
    __table_args__ = (
        CheckConstraint("reserved_bytes >= 0", name="ck_slides_reserved_bytes_nonnegative"),
        CheckConstraint("derivative_bytes >= 0", name="ck_slides_derivative_bytes_nonnegative"),
        CheckConstraint(
            "derivative_file_count >= 0",
            name="ck_slides_derivative_file_count_nonnegative",
        ),
        CheckConstraint(
            "render_mode IN ('static_dzi', 'ome_dynamic')",
            name="ck_slides_render_mode",
        ),
        CheckConstraint("sort_order >= 0", name="ck_slides_sort_order_nonnegative"),
        Index("ix_slides_updated_id", "updated_at", "id"),
        Index("ix_slides_created_id", "created_at", "id"),
        Index("ix_slides_display_name_id", "display_name", "id"),
        Index("ix_slides_trashed_at", "trashed_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_id: Mapped[str] = mapped_column(String(64), unique=True, default=_public_id, index=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derivative_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    derivative_file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    render_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="static_dzi",
        server_default="static_dzi",
        index=True,
    )
    folder_id: Mapped[str | None] = mapped_column(
        ForeignKey("folders.id", ondelete="SET NULL"), index=True
    )
    previous_folder_id: Mapped[str | None] = mapped_column(String(36))
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    case_id: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    organ_site: Mapped[str] = mapped_column(String(120), nullable=False, default="", index=True)
    stain: Mapped[str] = mapped_column(String(80), nullable=False, default="", index=True)
    diagnosis: Mapped[str] = mapped_column(String(300), nullable=False, default="", index=True)
    course: Mapped[str] = mapped_column(String(160), nullable=False, default="", index=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    teaching_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    admin_notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    thumbnail_filename: Mapped[str | None] = mapped_column(String(120))
    privacy_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    privacy_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[SlideState] = mapped_column(
        Enum(
            SlideState,
            native_enum=False,
            values_callable=lambda enum: [item.value for item in enum],
        ),
        default=SlideState.UPLOADING,
        index=True,
    )
    error_code: Mapped[str | None] = mapped_column(String(80))
    error_message: Mapped[str | None] = mapped_column(Text)
    slide_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    annotation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


Index("ix_slides_organ_site_ci", func.lower(Slide.organ_site))
Index("ix_slides_stain_ci", func.lower(Slide.stain))
Index("ix_slides_diagnosis_ci", func.lower(Slide.diagnosis))
Index("ix_slides_course_ci", func.lower(Slide.course))


class AnnotationLayer(Base):
    __tablename__ = "annotation_layers"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_annotation_layers_sort_order"),
        CheckConstraint(
            "opacity >= 0 AND opacity <= 1",
            name="ck_annotation_layers_opacity",
        ),
        Index(
            "ix_annotation_layers_slide_order",
            "slide_id",
            "sort_order",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    opacity: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Annotation(Base):
    __tablename__ = "annotations"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_annotations_version"),
        CheckConstraint("vertex_count >= 1", name="ck_annotations_vertex_count"),
        CheckConstraint(
            "bbox_min_x <= bbox_max_x AND bbox_min_y <= bbox_max_y",
            name="ck_annotations_bbox_order",
        ),
        Index(
            "ix_annotations_slide_active",
            "slide_id",
            "deleted_at",
            "created_at",
            "id",
        ),
        Index(
            "ix_annotations_slide_layer_active",
            "slide_id",
            "layer_id",
            "deleted_at",
        ),
        Index(
            "ix_annotations_slide_bbox",
            "slide_id",
            "bbox_min_x",
            "bbox_max_x",
            "bbox_min_y",
            "bbox_max_y",
        ),
        Index("ix_annotations_purge_after", "purge_after"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
    )
    layer_id: Mapped[str] = mapped_column(
        ForeignKey("annotation_layers.id", ondelete="CASCADE"), nullable=False
    )
    geometry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    style: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    annotation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    bbox_min_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_min_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_y: Mapped[float] = mapped_column(Float, nullable=False)
    vertex_count: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    mutation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AnnotationRevision(Base):
    __tablename__ = "annotation_revisions"
    __table_args__ = (
        UniqueConstraint(
            "annotation_id",
            "version",
            name="uq_annotation_revisions_annotation_version",
        ),
        Index(
            "ix_annotation_revisions_annotation_created",
            "annotation_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    annotation_id: Mapped[str] = mapped_column(
        ForeignKey("annotations.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    layer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    geometry_type: Mapped[str] = mapped_column(String(30), nullable=False)
    geometry: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    style: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    annotation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    bbox_min_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_min_y: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_x: Mapped[float] = mapped_column(Float, nullable=False)
    bbox_max_y: Mapped[float] = mapped_column(Float, nullable=False)
    vertex_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mutation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Collection(Base):
    __tablename__ = "collections"
    __table_args__ = (
        Index("ix_collections_order", "sort_order", "normalized_name"),
        CheckConstraint("sort_order >= 0", name="ck_collections_sort_order_nonnegative"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class CollectionSlide(Base):
    __tablename__ = "collection_slides"
    __table_args__ = (
        UniqueConstraint(
            "collection_id",
            "slide_id",
            name="uq_collection_slides_membership",
        ),
        Index("ix_collection_slides_order", "collection_id", "sort_order", "slide_id"),
        Index("ix_collection_slides_slide", "slide_id"),
        CheckConstraint(
            "sort_order >= 0",
            name="ck_collection_slides_sort_order_nonnegative",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    collection_id: Mapped[str] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SavedView(Base):
    __tablename__ = "saved_views"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    sort: Mapped[str] = mapped_column(String(40), nullable=False, default="updated_desc")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class LibraryShare(Base):
    __tablename__ = "library_shares"
    __table_args__ = (
        CheckConstraint(
            "target_type IN ('folder', 'collection')",
            name="ck_library_shares_target_type",
        ),
        Index("ix_library_shares_target", "target_type", "target_id"),
        Index("ix_library_shares_public_id", "public_id", unique=True),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    public_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=lambda: secrets.token_urlsafe(32)
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    include_descendants: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    auto_include_new: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    folder_paths: Mapped[list[list[str]]] = mapped_column(JSON, nullable=False, default=list)
    privacy_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class ShareSlide(Base):
    __tablename__ = "share_slides"
    __table_args__ = (
        UniqueConstraint("share_id", "slide_id", name="uq_share_slides_membership"),
        Index("ix_share_slides_order", "share_id", "sort_order", "slide_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    share_id: Mapped[str] = mapped_column(
        ForeignKey("library_shares.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
    )
    folder_path: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PublicationGrant(Base):
    __tablename__ = "publication_grants"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('individual', 'share')",
            name="ck_publication_grants_source_type",
        ),
        UniqueConstraint(
            "slide_id",
            "source_type",
            "source_id",
            name="uq_publication_grants_source",
        ),
        Index("ix_publication_grants_slide", "slide_id"),
        Index("ix_publication_grants_source", "source_type", "source_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Job(Base):
    __tablename__ = "jobs"

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'blocked_classroom', 'running', 'checkpointing', "
            "'retry_wait', 'succeeded', 'failed_terminal', 'cancelled')",
            name="ck_jobs_status",
        ),
        CheckConstraint(
            "resource_class IN ('live_critical', 'interactive', 'background', 'isolated')",
            name="ck_jobs_resource_class",
        ),
        Index("ix_jobs_claim", "status", "next_attempt_at", "created_at"),
        Index(
            "uq_jobs_idempotency",
            "organization_id",
            "kind",
            "idempotency_key_hash",
            unique=True,
            sqlite_where=text("idempotency_key_hash IS NOT NULL"),
            postgresql_where=text("idempotency_key_hash IS NOT NULL"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slide_id: Mapped[str | None] = mapped_column(
        ForeignKey("slides.id", ondelete="CASCADE"), index=True
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actor_type: Mapped[str | None] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(40), default="ingest")
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    resource_class: Mapped[str] = mapped_column(
        String(20), nullable=False, default="background", server_default="background"
    )
    idempotency_key_hash: Mapped[str | None] = mapped_column(String(64))
    input_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checkpoint: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resource_limits: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    output_manifest: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    evidence_location: Mapped[str | None] = mapped_column(String(500))
    failure_code: Mapped[str | None] = mapped_column(String(100))
    audit_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_events.id", ondelete="SET NULL")
    )
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
    slide: Mapped[Slide | None] = relationship()


class RuntimeGuard(Base):
    __tablename__ = "runtime_guards"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('idle', 'draining_for_classroom', 'classroom_live', 'classroom_cooldown', "
            "'draining_for_assessment', 'assessment_live', 'assessment_cooldown')",
            name="ck_runtime_guards_mode",
        ),
    )

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="idle", server_default="idle"
    )
    classroom_session_id: Mapped[str | None] = mapped_column(String(36))
    assessment_administration_id: Mapped[str | None] = mapped_column(String(36))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_events_action_created_at", "action", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    actor_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(100))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClassroomSession(Base):
    __tablename__ = "classroom_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'ended')", name="ck_classroom_sessions_status"),
        Index(
            "uq_classroom_sessions_one_active",
            "status",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index("ix_classroom_sessions_join_code", "join_code_hash", "status"),
        Index("ix_classroom_sessions_expires", "expires_at", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    join_code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    synthetic_run_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    public_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    phase: Mapped[str] = mapped_column(
        String(12), nullable=False, default="live", server_default="live"
    )
    code_generation: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    folder_id: Mapped[str | None] = mapped_column(ForeignKey("folders.id", ondelete="SET NULL"))
    review_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    live_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="active")
    presenter_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    presenter_sequence_reserved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    control_epoch: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_slide_id: Mapped[str | None] = mapped_column(String(36))
    presenter_viewport: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    controller_participant_id: Mapped[str | None] = mapped_column(String(36))
    controller_lease_id: Mapped[str | None] = mapped_column(String(64))
    controller_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClassroomSessionSlide(Base):
    __tablename__ = "classroom_session_slides"
    __table_args__ = (
        UniqueConstraint("session_id", "slide_id", name="uq_classroom_session_slides_slide"),
        UniqueConstraint(
            "session_id", "slide_position", name="uq_classroom_session_slides_position"
        ),
        Index("ix_classroom_session_slides_session", "session_id", "slide_position"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("classroom_sessions.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(
        ForeignKey("slides.id", ondelete="RESTRICT"), nullable=False
    )
    slide_position: Mapped[int] = mapped_column(Integer, nullable=False)
    published_asset_id: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_version: Mapped[str] = mapped_column(String(100), nullable=False)
    dzi_descriptor_path: Mapped[str] = mapped_column(String(500), nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    tile_size: Mapped[int] = mapped_column(Integer, nullable=False)
    tile_format: Mapped[str] = mapped_column(String(10), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    folder_path: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=list, server_default="[]"
    )


class ClassroomParticipant(Base):
    __tablename__ = "classroom_participants"
    __table_args__ = (
        UniqueConstraint("session_id", "token_hash", name="uq_classroom_participants_token"),
        UniqueConstraint("session_id", "public_alias", name="uq_classroom_participants_alias"),
        Index(
            "ix_classroom_participants_presence",
            "session_id",
            "disconnected_at",
            "last_seen_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("classroom_sessions.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    public_alias: Mapped[str] = mapped_column(String(16), nullable=False)
    optional_display_name: Mapped[str | None] = mapped_column(String(80))
    joined_live_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClassroomQuestion(Base):
    __tablename__ = "classroom_questions"
    __table_args__ = (Index("ix_classroom_questions_pending", "session_id", "created_at", "id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("classroom_sessions.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("classroom_participants.id", ondelete="CASCADE"), nullable=False
    )
    slide_id: Mapped[str] = mapped_column(String(36), nullable=False)
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    zoom: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ClassroomQuestionReceipt(Base):
    __tablename__ = "classroom_question_receipts"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "participant_id",
            "idempotency_key_hash",
            name="uq_classroom_question_receipts_key",
        ),
        Index("ix_classroom_question_receipts_participant", "participant_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("classroom_sessions.id", ondelete="CASCADE"), nullable=False
    )
    participant_id: Mapped[str] = mapped_column(
        ForeignKey("classroom_participants.id", ondelete="CASCADE"), nullable=False
    )
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    original_question_id: Mapped[str] = mapped_column(String(36), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StudyPack(Base):
    __tablename__ = "study_packs"
    __table_args__ = (
        UniqueConstraint("pack_key", "version", name="uq_study_packs_key_version"),
        UniqueConstraint("checksum", name="uq_study_packs_checksum"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pack_key: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    definition: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StudyCourse(Base):
    __tablename__ = "study_courses"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'preparation', 'active', 'ended', 'purged')",
            name="ck_study_courses_status",
        ),
        CheckConstraint("retention_days >= 0 AND retention_days <= 90", name="ck_study_retention"),
        CheckConstraint("learner_limit >= 1 AND learner_limit <= 500", name="ck_study_learners"),
        CheckConstraint(
            "ai_mode IN ('deterministic', 'closed_pilot_trace_sim')",
            name="ck_study_courses_ai_mode",
        ),
        Index(
            "uq_study_courses_one_live",
            "status",
            unique=True,
            sqlite_where=text("status IN ('preparation', 'active')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    pack_id: Mapped[str] = mapped_column(
        ForeignKey("study_packs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    learner_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=500)
    invitations_generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    model_manifest_id: Mapped[str | None] = mapped_column(String(100))
    ai_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="deterministic")
    pilot_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class StudyInvitation(Base):
    __tablename__ = "study_invitations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('issued', 'redeemed', 'revoked')", name="ck_study_invitations_status"
        ),
        Index("ix_study_invitations_course_status", "course_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("study_courses.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="issued")
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StudyLearnerSession(Base):
    __tablename__ = "study_learner_sessions"
    __table_args__ = (
        UniqueConstraint("invitation_id", name="uq_study_session_invitation"),
        UniqueConstraint("course_id", "pseudonym", name="uq_study_session_pseudonym"),
        CheckConstraint(
            "status IN ('active', 'withdrawn', 'expired')", name="ck_study_sessions_status"
        ),
        Index("ix_study_sessions_course_status", "course_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("study_courses.id", ondelete="CASCADE"), nullable=False
    )
    invitation_id: Mapped[str] = mapped_column(
        ForeignKey("study_invitations.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    pseudonym: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    withdrew_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StudyProgress(Base):
    __tablename__ = "study_progress"
    __table_args__ = (
        UniqueConstraint("session_id", "task_id", name="uq_study_progress_task"),
        CheckConstraint("status IN ('attempted', 'completed')", name="ck_study_progress_status"),
        CheckConstraint("attempt_count >= 1", name="ck_study_attempt_count"),
        Index("ix_study_progress_session_updated", "session_id", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("study_learner_sessions.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    latest_correctness: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    model_manifest_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class StudyReadinessAggregate(Base):
    __tablename__ = "study_readiness_aggregates"
    __table_args__ = (UniqueConstraint("course_id", name="uq_study_readiness_course"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    course_id: Mapped[str] = mapped_column(
        ForeignKey("study_courses.id", ondelete="CASCADE"), nullable=False
    )
    ready_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fallback_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    continue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    offer_hint_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ask_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ask_source_check_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrieve_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pause_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
