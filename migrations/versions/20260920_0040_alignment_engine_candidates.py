"""add alignment engine candidates

Revision ID: 20260920_0040
Revises: 20260920_0039
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0040"
down_revision: str | None = "20260920_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comparison_registration_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("comparison_set_id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("set_version", sa.Integer(), nullable=False),
        sa.Column("anchor_slide_id", sa.String(length=36), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=True),
        sa.Column("anchor_version", sa.String(length=128), nullable=True),
        sa.Column("engine", sa.String(length=40), nullable=False),
        sa.Column("engine_version", sa.String(length=64), nullable=False),
        sa.Column("settings_digest", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("validation_state", sa.String(length=24), nullable=False),
        sa.Column("registration", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("artifact_path", sa.String(length=500), nullable=True),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comparison_set_id"], ["comparison_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_registration_candidate_identity",
        "comparison_registration_candidates",
        [
            "comparison_set_id",
            "slide_id",
            "set_version",
            "anchor_slide_id",
            "engine",
            "source_version",
            "anchor_version",
            "settings_digest",
        ],
        unique=False,
    )
    op.create_index(
        "ix_registration_candidates_set",
        "comparison_registration_candidates",
        ["comparison_set_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_registration_candidate_identity",
        table_name="comparison_registration_candidates",
    )
    op.drop_index(
        "ix_registration_candidates_set",
        table_name="comparison_registration_candidates",
    )
    op.drop_table("comparison_registration_candidates")
