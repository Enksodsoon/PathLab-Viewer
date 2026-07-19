"""Version sessions against atomic credential transitions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260719_0003"
down_revision: str | None = "20260719_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("credential_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "sessions",
        sa.Column("credential_generation", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "password_recovery_attempts",
        sa.Column("ip_key_hash", sa.String(64), nullable=True),
    )
    op.create_index(
        "ix_password_recovery_attempts_ip_key_hash",
        "password_recovery_attempts",
        ["ip_key_hash"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_password_recovery_attempts_ip_key_hash",
        table_name="password_recovery_attempts",
    )
    op.drop_column("password_recovery_attempts", "ip_key_hash")
    op.drop_column("sessions", "credential_generation")
    op.drop_column("users", "credential_generation")
