"""Persist Assessment mutation idempotency receipts."""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0027"
down_revision = "20260824_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_mutation_receipts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(64),
            sa.ForeignKey("assessment_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer, nullable=False),
        sa.Column("response", sa.JSON, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "session_id", "operation", "key_hash", name="uq_assessment_mutation_receipt"
        ),
    )


def downgrade() -> None:
    op.drop_table("assessment_mutation_receipts")
