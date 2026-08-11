"""Reserve presenter sequences without persisting every viewport movement."""

import sqlalchemy as sa
from alembic import op

revision = "20260811_0016"
down_revision = "20260811_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.add_column(
            sa.Column(
                "presenter_sequence_reserved",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.drop_column("presenter_sequence_reserved")
