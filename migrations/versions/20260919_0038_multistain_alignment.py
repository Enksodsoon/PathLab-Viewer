"""Add reusable multi-stain comparison sets."""

import sqlalchemy as sa
from alembic import op

revision = "20260919_0038"
down_revision = "20260907_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comparison_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("reference_slide_id", sa.String(36), nullable=False),
        sa.Column("member_slide_ids", sa.JSON(), nullable=False),
        sa.Column("source_versions", sa.JSON(), nullable=False),
        sa.Column("registrations", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_comparison_sets_version"),
        sa.CheckConstraint(
            "status IN ('draft', 'queued', 'running', 'ready', 'partial', 'failed')",
            name="ck_comparison_sets_status",
        ),
        sa.ForeignKeyConstraint(["reference_slide_id"], ["slides.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_comparison_sets_reference_slide_id", "comparison_sets", ["reference_slide_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_comparison_sets_reference_slide_id", table_name="comparison_sets")
    op.drop_table("comparison_sets")
