"""Add Program 1 identity, organization, learner, and cohort foundations."""

import sqlalchemy as sa
from alembic import op

revision = "20260822_0025"
down_revision = "20260822_0024"
branch_labels = None
depends_on = None

DEFAULT_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_AUDIT_EVENT_ID = "00000000-0000-4000-8000-000000000002"


def _durable_columns() -> list[sa.Column]:
    return [
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_by_user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="SET NULL")
        ),
        sa.Column(
            "audit_event_id", sa.String(36), sa.ForeignKey("audit_events.id", ondelete="SET NULL")
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_durable_columns(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_organizations_status"),
    )
    op.create_table(
        "organization_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_durable_columns(),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'instructor', 'teaching_assistant', "
            "'researcher', 'auditor')",
            name="ck_memberships_role",
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_memberships_status"),
    )
    op.create_index("ix_memberships_user_status", "organization_memberships", ["user_id", "status"])
    op.create_index(
        "ix_organization_memberships_organization_id",
        "organization_memberships",
        ["organization_id"],
    )
    op.create_table(
        "staff_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("invitee_identifier_hash", sa.String(64), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        *_durable_columns(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "role IN ('owner', 'admin', 'instructor', 'teaching_assistant', "
            "'researcher', 'auditor')",
            name="ck_staff_invitations_role",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'revoked')",
            name="ck_staff_invitations_status",
        ),
    )
    op.create_index(
        "ix_staff_invitations_org_status", "staff_invitations", ["organization_id", "status"]
    )
    op.create_table(
        "learner_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("teaching_pseudonym", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_durable_columns(),
        sa.Column("disabled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "organization_id", "teaching_pseudonym", name="uq_learners_org_pseudonym"
        ),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_learners_status"),
    )
    op.create_index("ix_learner_profiles_organization_id", "learner_profiles", ["organization_id"])
    op.create_table(
        "cohorts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_durable_columns(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("organization_id", "name", name="uq_cohorts_org_name"),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_cohorts_status"),
    )
    op.create_index("ix_cohorts_organization_id", "cohorts", ["organization_id"])
    op.create_table(
        "cohort_enrollments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "cohort_id",
            sa.String(36),
            sa.ForeignKey("cohorts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_durable_columns(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("cohort_id", "learner_id", name="uq_enrollments_cohort_learner"),
        sa.CheckConstraint("status IN ('active', 'withdrawn')", name="ck_enrollments_status"),
    )
    op.create_index(
        "ix_cohort_enrollments_organization_id", "cohort_enrollments", ["organization_id"]
    )
    op.create_table(
        "learner_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("recovery_credential_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        *_durable_columns(),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_learner_credentials_status"),
    )
    op.create_index(
        "ix_learner_credentials_organization_id", "learner_credentials", ["organization_id"]
    )
    op.create_index("ix_learner_credentials_learner_id", "learner_credentials", ["learner_id"])
    op.create_table(
        "research_pseudonyms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "learner_id",
            sa.String(36),
            sa.ForeignKey("learner_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scope_id", sa.String(100), nullable=False),
        sa.Column("pseudonym", sa.String(100), nullable=False),
        *_durable_columns(),
        sa.UniqueConstraint(
            "organization_id", "scope_id", "pseudonym", name="uq_research_scope_pseudonym"
        ),
        sa.UniqueConstraint("learner_id", "scope_id", name="uq_research_learner_scope"),
    )
    op.create_index(
        "ix_research_pseudonyms_organization_id", "research_pseudonyms", ["organization_id"]
    )
    op.create_table(
        "oidc_identity_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "organization_id",
            sa.String(36),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("issuer", sa.String(500), nullable=False),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="linked"),
        *_durable_columns(),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("issuer", "subject_hash", name="uq_oidc_issuer_subject"),
        sa.CheckConstraint("status IN ('linked', 'revoked')", name="ck_oidc_links_status"),
    )
    op.create_index(
        "ix_oidc_identity_links_organization_id", "oidc_identity_links", ["organization_id"]
    )
    op.create_index("ix_oidc_identity_links_user_id", "oidc_identity_links", ["user_id"])

    op.execute(
        sa.text(
            "INSERT INTO audit_events "
            "(id, actor_user_id, action, target_id, created_at) "
            "SELECT :audit_id, MIN(id), 'identity.default_organization_backfilled', "
            ":organization_id, CURRENT_TIMESTAMP FROM users HAVING COUNT(*) > 0"
        ).bindparams(
            audit_id=DEFAULT_AUDIT_EVENT_ID,
            organization_id=DEFAULT_ORGANIZATION_ID,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO organizations "
            "(id, slug, display_name, status, schema_version, created_by_user_id, "
            "audit_event_id, created_at, updated_at) "
            "SELECT :organization_id, 'default', 'PathLab', 'active', 1, "
            "MIN(id), :audit_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP "
            "FROM users HAVING COUNT(*) > 0"
        ).bindparams(
            organization_id=DEFAULT_ORGANIZATION_ID,
            audit_id=DEFAULT_AUDIT_EVENT_ID,
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO organization_memberships "
            "(id, organization_id, user_id, role, status, schema_version, "
            "created_by_user_id, audit_event_id, created_at, updated_at) "
            "SELECT id, :organization_id, id, 'owner', 'active', 1, "
            "id, :audit_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP FROM users"
        ).bindparams(
            organization_id=DEFAULT_ORGANIZATION_ID,
            audit_id=DEFAULT_AUDIT_EVENT_ID,
        )
    )


def downgrade() -> None:
    for table in (
        "oidc_identity_links",
        "research_pseudonyms",
        "learner_credentials",
        "cohort_enrollments",
        "cohorts",
        "learner_profiles",
        "staff_invitations",
        "organization_memberships",
        "organizations",
    ):
        op.drop_table(table)
    op.execute(
        sa.text("DELETE FROM audit_events WHERE id = :audit_id").bindparams(
            audit_id=DEFAULT_AUDIT_EVENT_ID
        )
    )
