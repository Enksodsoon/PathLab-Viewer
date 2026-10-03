"""Add independent immutable regional correction revisions."""

import sqlalchemy as sa
from alembic import op

revision = "20261003_0043"
down_revision = "20260921_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "comparison_region_corrections",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("comparison_set_id", sa.String(36), nullable=False),
        sa.Column("region_id", sa.String(36), nullable=False),
        sa.Column("source_slide_id", sa.String(36), nullable=False),
        sa.Column("target_slide_id", sa.String(36), nullable=False),
        sa.Column("source_version", sa.String(128), nullable=False),
        sa.Column("target_version", sa.String(128), nullable=False),
        sa.Column("set_version", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(10), nullable=False),
        sa.Column("source_bounds", sa.JSON(), nullable=False),
        sa.Column("registration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comparison_set_id"], ["comparison_sets.id"], ondelete="CASCADE"),
        sa.CheckConstraint("operation IN ('save', 'clear')", name="ck_region_correction_operation"),
        sa.UniqueConstraint(
            "comparison_set_id", "region_id", "set_version", name="uq_region_correction_revision"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_region_corrections_set",
        "comparison_region_corrections",
        ["comparison_set_id", "set_version"],
    )


def downgrade() -> None:
    op.drop_index("ix_region_corrections_set", table_name="comparison_region_corrections")
    op.drop_table("comparison_region_corrections")
