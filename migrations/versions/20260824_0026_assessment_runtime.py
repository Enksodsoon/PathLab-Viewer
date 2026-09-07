"""Add the manual-first Assessment draft and runtime persistence model."""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0026"
down_revision = "20260822_0025"
branch_labels = None
depends_on = None

ID = lambda: sa.Column("id", sa.String(36), primary_key=True)  # noqa: E731
CREATED = lambda: sa.Column(  # noqa: E731
    "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
)


def _fk(name: str, table: str, *, nullable: bool = False, delete: str = "CASCADE") -> sa.Column:
    return sa.Column(
        name,
        sa.String(36),
        sa.ForeignKey(f"{table}.id", ondelete=delete),
        nullable=nullable,
    )


def upgrade() -> None:
    op.add_column("learner_profiles", sa.Column("login_identifier_hash", sa.String(64)))
    op.add_column("learner_profiles", sa.Column("display_name", sa.String(160)))
    op.create_index(
        "uq_learner_profiles_org_login_hash",
        "learner_profiles",
        ["organization_id", "login_identifier_hash"],
        unique=True,
    )

    op.create_table(
        "assessment_drafts",
        ID(),
        _fk("organization_id", "organizations"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("document", sa.JSON, nullable=False),
        _fk("created_by_user_id", "users", delete="RESTRICT"),
        sa.Column("archived_at", sa.DateTime(timezone=True)),
        CREATED(),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint("revision >= 1", name="ck_assessment_drafts_revision"),
        sa.CheckConstraint("status IN ('draft', 'archived')", name="ck_assessment_drafts_status"),
    )
    op.create_index(
        "ix_assessment_drafts_org_updated",
        "assessment_drafts",
        ["organization_id", "updated_at", "id"],
    )
    op.create_table(
        "assessment_versions",
        ID(),
        _fk("organization_id", "organizations"),
        _fk("draft_id", "assessment_drafts", delete="RESTRICT"),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("schema", sa.String(80), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False, unique=True),
        sa.Column("definition", sa.JSON, nullable=False),
        sa.Column("learner_manifest", sa.JSON, nullable=False),
        sa.Column(
            "published_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("draft_id", "version", name="uq_assessment_version"),
    )
    op.create_index(
        "ix_assessment_versions_organization_id", "assessment_versions", ["organization_id"]
    )
    op.create_table(
        "assessment_administrations",
        ID(),
        sa.Column("public_id", sa.String(64), nullable=False, unique=True),
        _fk("organization_id", "organizations"),
        _fk("version_id", "assessment_versions", delete="RESTRICT"),
        _fk("cohort_id", "cohorts", nullable=True, delete="RESTRICT"),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="preparing"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="1"),
        sa.Column("duration_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("access_code_hash", sa.String(64)),
        sa.Column("settings", sa.JSON, nullable=False),
        sa.Column("opens_at", sa.DateTime(timezone=True)),
        sa.Column("closes_at", sa.DateTime(timezone=True)),
        CREATED(),
        sa.CheckConstraint("mode IN ('practice', 'formative', 'quiz')", name="ck_assessment_mode"),
        sa.CheckConstraint(
            "status IN ('preparing', 'open', 'closed', 'purged')",
            name="ck_assessment_administration_status",
        ),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 3", name="ck_assessment_attempt_limit"),
        sa.CheckConstraint("duration_seconds BETWEEN 1 AND 14400", name="ck_assessment_duration"),
    )
    op.create_index(
        "ix_assessment_administration_org_status",
        "assessment_administrations",
        ["organization_id", "status"],
    )
    op.create_table(
        "assessment_roster_snapshots",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        _fk("learner_id", "learner_profiles", delete="RESTRICT"),
        sa.Column("login_identifier_hash", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(160)),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.UniqueConstraint("administration_id", "learner_id", name="uq_assessment_roster_learner"),
    )
    op.create_table(
        "assessment_participants",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        _fk("learner_id", "learner_profiles", nullable=True, delete="RESTRICT"),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("receipt_hash", sa.String(64)),
        CREATED(),
        sa.CheckConstraint(
            "kind IN ('roster', 'anonymous')", name="ck_assessment_participant_kind"
        ),
        sa.UniqueConstraint(
            "administration_id", "learner_id", name="uq_assessment_participant_learner"
        ),
        sa.UniqueConstraint(
            "administration_id", "receipt_hash", name="uq_assessment_participant_receipt"
        ),
    )
    op.create_table(
        "assessment_sessions",
        sa.Column("id", sa.String(64), primary_key=True),
        _fk("participant_id", "assessment_participants"),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("device_generation", sa.Integer, nullable=False, server_default="1"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index(
        "ix_assessment_sessions_participant_id", "assessment_sessions", ["participant_id"]
    )
    op.create_table(
        "assessment_asset_grants",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        _fk("slide_id", "slides", delete="RESTRICT"),
        sa.Column("grant_path", sa.String(500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("administration_id", "slide_id", name="uq_assessment_asset_slide"),
    )
    op.create_table(
        "assessment_attempts",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        _fk("participant_id", "assessment_participants"),
        sa.Column("ordinal", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("order_seed", sa.String(64), nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("participant_id", "ordinal", name="uq_assessment_attempt_ordinal"),
        sa.CheckConstraint("ordinal BETWEEN 1 AND 3", name="ck_assessment_attempt_ordinal"),
        sa.CheckConstraint(
            "status IN ('active', 'submitted', 'auto_submitted')",
            name="ck_assessment_attempt_status",
        ),
    )
    op.create_index(
        "ix_assessment_attempts_administration_id", "assessment_attempts", ["administration_id"]
    )
    op.create_table(
        "assessment_responses",
        ID(),
        _fk("attempt_id", "assessment_attempts"),
        sa.Column("item_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("response", sa.JSON, nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("attempt_id", "item_id", name="uq_assessment_response_item"),
    )
    op.create_table(
        "assessment_score_versions",
        ID(),
        _fk("attempt_id", "assessment_attempts"),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("points", sa.Numeric(12, 3), nullable=False),
        sa.Column("maximum_points", sa.Numeric(12, 3), nullable=False),
        sa.Column("breakdown", sa.JSON, nullable=False),
        CREATED(),
        sa.UniqueConstraint("attempt_id", "version", name="uq_assessment_score_version"),
    )
    op.create_table(
        "assessment_gradebook_rows",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        _fk("participant_id", "assessment_participants"),
        _fk("score_version_id", "assessment_score_versions", nullable=True, delete="SET NULL"),
        sa.Column("status", sa.String(20), nullable=False, server_default="in_progress"),
        sa.UniqueConstraint(
            "administration_id", "participant_id", name="uq_assessment_gradebook_row"
        ),
    )
    op.create_table(
        "assessment_releases",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        sa.Column("policy", sa.JSON, nullable=False),
        _fk("released_by_user_id", "users", delete="RESTRICT"),
        sa.Column(
            "released_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "assessment_aggregate_snapshots",
        ID(),
        _fk("administration_id", "assessment_administrations"),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("aggregate", sa.JSON, nullable=False),
        CREATED(),
        sa.UniqueConstraint("administration_id", "version", name="uq_assessment_aggregate_version"),
    )
    op.create_table(
        "assessment_access_throttles",
        ID(),
        sa.Column("scope", sa.String(30), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="1"),
        sa.UniqueConstraint(
            "scope", "key_hash", "window_started_at", name="uq_assessment_throttle"
        ),
    )


def downgrade() -> None:
    for table in (
        "assessment_access_throttles",
        "assessment_aggregate_snapshots",
        "assessment_releases",
        "assessment_gradebook_rows",
        "assessment_score_versions",
        "assessment_responses",
        "assessment_attempts",
        "assessment_asset_grants",
        "assessment_sessions",
        "assessment_participants",
        "assessment_roster_snapshots",
        "assessment_administrations",
        "assessment_versions",
        "assessment_drafts",
    ):
        op.drop_table(table)
    op.drop_index("uq_learner_profiles_org_login_hash", table_name="learner_profiles")
    op.drop_column("learner_profiles", "display_name")
    op.drop_column("learner_profiles", "login_identifier_hash")
