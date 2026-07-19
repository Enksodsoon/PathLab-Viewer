"""Add one-time admin password recovery."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0002"
down_revision: str | None = "20260719_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_recovery_codes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("invalidated_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_password_recovery_codes_user_id", "password_recovery_codes", ["user_id"])
    op.create_index(
        "ix_password_recovery_codes_expires_at", "password_recovery_codes", ["expires_at"]
    )
    op.create_table(
        "password_recovery_attempts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("client_key_hash", sa.String(64), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_password_recovery_attempts_client_key_hash",
        "password_recovery_attempts",
        ["client_key_hash"],
    )
    op.create_index(
        "ix_password_recovery_attempts_attempted_at",
        "password_recovery_attempts",
        ["attempted_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_recovery_attempts_attempted_at", table_name="password_recovery_attempts"
    )
    op.drop_index(
        "ix_password_recovery_attempts_client_key_hash", table_name="password_recovery_attempts"
    )
    op.drop_table("password_recovery_attempts")
    op.drop_index("ix_password_recovery_codes_expires_at", table_name="password_recovery_codes")
    op.drop_index("ix_password_recovery_codes_user_id", table_name="password_recovery_codes")
    op.drop_table("password_recovery_codes")
