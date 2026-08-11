"""Add the feature-gated lightweight classroom domain."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260811_0015"
down_revision: str | None = "20260730_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "classroom_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("join_code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("presenter_sequence", sa.Integer(), nullable=False),
        sa.Column("control_epoch", sa.Integer(), nullable=False),
        sa.Column("state_version", sa.Integer(), nullable=False),
        sa.Column("current_slide_id", sa.String(36)),
        sa.Column("presenter_viewport", sa.JSON()),
        sa.Column("controller_participant_id", sa.String(36)),
        sa.Column("controller_lease_id", sa.String(64)),
        sa.Column("controller_expires_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'ended')", name="ck_classroom_sessions_status"),
    )
    op.create_index(
        "uq_classroom_sessions_one_active",
        "classroom_sessions",
        ["status"],
        unique=True,
        sqlite_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_classroom_sessions_join_code",
        "classroom_sessions",
        ["join_code_hash", "status"],
    )
    op.create_index("ix_classroom_sessions_expires", "classroom_sessions", ["expires_at", "status"])
    op.create_table(
        "classroom_session_slides",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("classroom_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "slide_id",
            sa.String(36),
            sa.ForeignKey("slides.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("slide_position", sa.Integer(), nullable=False),
        sa.Column("published_asset_id", sa.String(100), nullable=False),
        sa.Column("asset_version", sa.String(100), nullable=False),
        sa.Column("dzi_descriptor_path", sa.String(500), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("tile_size", sa.Integer(), nullable=False),
        sa.Column("tile_format", sa.String(10), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.UniqueConstraint("session_id", "slide_id", name="uq_classroom_session_slides_slide"),
        sa.UniqueConstraint(
            "session_id", "slide_position", name="uq_classroom_session_slides_position"
        ),
    )
    op.create_index(
        "ix_classroom_session_slides_session",
        "classroom_session_slides",
        ["session_id", "slide_position"],
    )
    op.create_table(
        "classroom_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("classroom_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("public_alias", sa.String(16), nullable=False),
        sa.Column("optional_display_name", sa.String(80)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("disconnected_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "token_hash", name="uq_classroom_participants_token"),
        sa.UniqueConstraint("session_id", "public_alias", name="uq_classroom_participants_alias"),
    )
    op.create_index(
        "ix_classroom_participants_presence",
        "classroom_participants",
        ["session_id", "disconnected_at", "last_seen_at"],
    )
    op.create_table(
        "classroom_questions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("classroom_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            sa.String(36),
            sa.ForeignKey("classroom_participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("slide_id", sa.String(36), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("zoom", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_classroom_questions_pending",
        "classroom_questions",
        ["session_id", "created_at", "id"],
    )
    op.create_table(
        "classroom_question_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(36),
            sa.ForeignKey("classroom_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            sa.String(36),
            sa.ForeignKey("classroom_participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("idempotency_key_hash", sa.String(64), nullable=False),
        sa.Column("original_question_id", sa.String(36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "session_id",
            "participant_id",
            "idempotency_key_hash",
            name="uq_classroom_question_receipts_key",
        ),
    )
    op.create_index(
        "ix_classroom_question_receipts_participant",
        "classroom_question_receipts",
        ["participant_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_table("classroom_question_receipts")
    op.drop_table("classroom_questions")
    op.drop_table("classroom_participants")
    op.drop_table("classroom_session_slides")
    op.drop_table("classroom_sessions")
