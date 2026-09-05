"""Add shared credential admission and indexed pairing expiry."""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0026"
down_revision = "20260822_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admission_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("namespace", sa.String(20), nullable=False),
        sa.Column("client_key_hash", sa.String(64), nullable=True),
        sa.Column("subject_key_hash", sa.String(64), nullable=True),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_admission_namespace_time", "admission_attempts", ["namespace", "attempted_at"]
    )
    op.create_index("ix_desktop_pairings_expires_at", "desktop_pairings", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_desktop_pairings_expires_at", table_name="desktop_pairings")
    op.drop_index("ix_admission_namespace_time", table_name="admission_attempts")
    op.drop_table("admission_attempts")
