"""Snapshot public folder paths for shared slides."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_0010"
down_revision: str | None = "20260726_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "library_shares",
        sa.Column(
            "folder_paths",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        )
    )
    op.add_column(
        "share_slides",
        sa.Column(
            "folder_path",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        )
    )


def downgrade() -> None:
    op.drop_column("share_slides", "folder_path")
    op.drop_column("library_shares", "folder_paths")
