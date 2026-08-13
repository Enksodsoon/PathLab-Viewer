"""Snapshot classroom slide folder paths for lightweight navigation."""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0019"
down_revision = "20260813_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classroom_session_slides") as batch:
        batch.add_column(
            sa.Column(
                "folder_path",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("classroom_session_slides") as batch:
        batch.drop_column("folder_path")
