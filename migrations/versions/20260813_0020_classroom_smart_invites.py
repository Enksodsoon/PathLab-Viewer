"""Add smart classroom invite lifecycle."""

import sqlalchemy as sa
from alembic import op

revision = "20260813_0020"
down_revision = "20260813_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.add_column(sa.Column("public_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("phase", sa.String(12), nullable=False, server_default="live"))
        batch.add_column(
            sa.Column("code_generation", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("folder_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("review_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("live_expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_classroom_sessions_public_id", ["public_id"])
        batch.create_foreign_key(
            "fk_classroom_sessions_folder", "folders", ["folder_id"], ["id"], ondelete="SET NULL"
        )
    with op.batch_alter_table("classroom_participants") as batch:
        batch.add_column(sa.Column("joined_live_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("classroom_participants") as batch:
        batch.drop_column("joined_live_at")
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.drop_constraint("fk_classroom_sessions_folder", type_="foreignkey")
        batch.drop_constraint("uq_classroom_sessions_public_id", type_="unique")
        batch.drop_column("started_at")
        batch.drop_column("live_expires_at")
        batch.drop_column("review_expires_at")
        batch.drop_column("folder_id")
        batch.drop_column("code_generation")
        batch.drop_column("phase")
        batch.drop_column("public_id")
