"""Bind protected Classroom fixtures to one workflow run."""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0021"
down_revision = "20260813_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.add_column(sa.Column("synthetic_run_id", sa.String(64), nullable=True))
        batch.create_unique_constraint(
            "uq_classroom_sessions_synthetic_run_id", ["synthetic_run_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.drop_constraint("uq_classroom_sessions_synthetic_run_id", type_="unique")
        batch.drop_column("synthetic_run_id")
