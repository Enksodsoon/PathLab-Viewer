"""Add dormant multi-slide share privacy evidence fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0007"
down_revision: str | None = "20260723_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("slides") as batch:
        batch.add_column(
            sa.Column(
                "privacy_status",
                sa.String(length=30),
                nullable=False,
                server_default="pending",
            )
        )
        batch.add_column(sa.Column("privacy_scanned_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_slides_privacy_status", ["privacy_status"])


def downgrade() -> None:
    with op.batch_alter_table("slides") as batch:
        batch.drop_index("ix_slides_privacy_status")
        batch.drop_column("privacy_scanned_at")
        batch.drop_column("privacy_status")
