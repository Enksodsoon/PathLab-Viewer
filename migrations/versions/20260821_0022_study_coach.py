"""Add privacy-bounded Study Coach storage."""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0022"
down_revision = "20260821_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "study_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pack_key", sa.String(120), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pack_key", "version", name="uq_study_packs_key_version"),
        sa.UniqueConstraint("checksum", name="uq_study_packs_checksum"),
    )
    op.create_table(
        "study_courses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "pack_id",
            sa.String(36),
            sa.ForeignKey("study_packs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=False),
        sa.Column("learner_limit", sa.Integer(), nullable=False),
        sa.Column("invitations_generated_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("purge_after", sa.DateTime(timezone=True)),
        sa.Column("model_manifest_id", sa.String(100)),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'preparation', 'active', 'ended', 'purged')",
            name="ck_study_courses_status",
        ),
        sa.CheckConstraint(
            "retention_days >= 0 AND retention_days <= 90", name="ck_study_retention"
        ),
        sa.CheckConstraint("learner_limit >= 1 AND learner_limit <= 500", name="ck_study_learners"),
    )
    op.create_index("ix_study_courses_pack_id", "study_courses", ["pack_id"])
    op.create_index("ix_study_courses_purge_after", "study_courses", ["purge_after"])
    op.create_index(
        "uq_study_courses_one_live",
        "study_courses",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status IN ('preparation', 'active')"),
    )
    op.create_table(
        "study_invitations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(36),
            sa.ForeignKey("study_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('issued', 'redeemed', 'revoked')", name="ck_study_invitations_status"
        ),
    )
    op.create_index(
        "ix_study_invitations_course_status", "study_invitations", ["course_id", "status"]
    )
    op.create_table(
        "study_learner_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(36),
            sa.ForeignKey("study_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "invitation_id",
            sa.String(36),
            sa.ForeignKey("study_invitations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("pseudonym", sa.String(24), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrew_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("invitation_id", name="uq_study_session_invitation"),
        sa.UniqueConstraint("course_id", "pseudonym", name="uq_study_session_pseudonym"),
        sa.CheckConstraint(
            "status IN ('active', 'withdrawn', 'expired')", name="ck_study_sessions_status"
        ),
    )
    op.create_index(
        "ix_study_sessions_course_status", "study_learner_sessions", ["course_id", "status"]
    )
    op.create_table(
        "study_progress",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("study_learner_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("task_id", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("latest_correctness", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("model_manifest_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "task_id", name="uq_study_progress_task"),
        sa.CheckConstraint("status IN ('attempted', 'completed')", name="ck_study_progress_status"),
        sa.CheckConstraint("attempt_count >= 1", name="ck_study_attempt_count"),
    )
    op.create_index(
        "ix_study_progress_session_updated", "study_progress", ["session_id", "updated_at"]
    )
    op.create_table(
        "study_readiness_aggregates",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "course_id",
            sa.String(36),
            sa.ForeignKey("study_courses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ready_count", sa.Integer(), nullable=False),
        sa.Column("fallback_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("course_id", name="uq_study_readiness_course"),
    )


def downgrade() -> None:
    op.drop_table("study_readiness_aggregates")
    op.drop_table("study_progress")
    op.drop_table("study_learner_sessions")
    op.drop_table("study_invitations")
    op.drop_index("uq_study_courses_one_live", table_name="study_courses")
    op.drop_index("ix_study_courses_purge_after", table_name="study_courses")
    op.drop_index("ix_study_courses_pack_id", table_name="study_courses")
    op.drop_table("study_courses")
    op.drop_table("study_packs")
