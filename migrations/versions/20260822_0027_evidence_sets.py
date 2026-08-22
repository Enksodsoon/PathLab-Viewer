"""Add multi-pack evidence sets for Study Pack v3."""

import sqlalchemy as sa
from alembic import op

revision = "20260822_0027"
down_revision = "20260822_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_sets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "slide_id", sa.String(36), sa.ForeignKey("slides.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("set_id", sa.String(160), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column(
            "reviewed_by_user_id", sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("manifest_sha256", name="uq_evidence_sets_manifest"),
        sa.UniqueConstraint("slide_id", "set_id", name="uq_evidence_sets_slide_set"),
        sa.CheckConstraint(
            "status IN ('completed', 'partial', 'abstained')",
            name="ck_evidence_sets_status",
        ),
    )
    op.create_index("ix_evidence_sets_slide_id", "evidence_sets", ["slide_id"])


def downgrade() -> None:
    op.drop_index("ix_evidence_sets_slide_id", table_name="evidence_sets")
    op.drop_table("evidence_sets")
