"""Add immutable alignment revisions and editable anchor configuration."""

import sqlalchemy as sa
from alembic import op

revision = "20260920_0039"
down_revision = "20260919_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("comparison_sets") as batch:
        batch.add_column(
            sa.Column("alignment_config", sa.JSON(), nullable=False, server_default="{}")
        )
    op.create_table(
        "comparison_registration_revisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("comparison_set_id", sa.String(36), nullable=False),
        sa.Column("slide_id", sa.String(36), nullable=False),
        sa.Column("set_version", sa.Integer(), nullable=False),
        sa.Column("source_version", sa.String(128)),
        sa.Column("anchor_slide_id", sa.String(36), nullable=False),
        sa.Column("algorithm_version", sa.String(40), nullable=False),
        sa.Column("provenance", sa.String(24), nullable=False),
        sa.Column("registration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comparison_set_id"], ["comparison_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "comparison_set_id", "slide_id", "set_version", name="uq_registration_revision"
        ),
    )
    op.create_index(
        "ix_registration_revisions_set",
        "comparison_registration_revisions",
        ["comparison_set_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_registration_revisions_set", table_name="comparison_registration_revisions")
    op.drop_table("comparison_registration_revisions")
    with op.batch_alter_table("comparison_sets") as batch:
        batch.drop_column("alignment_config")
