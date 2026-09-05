"""Bind Classroom teacher authority to the creating user."""

import sqlalchemy as sa
from alembic import op

revision = "20260905_0027"
down_revision = "20260905_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.add_column(sa.Column("created_by_user_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_classroom_sessions_created_by_user",
            "users",
            ["created_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index("ix_classroom_sessions_created_by_user_id", ["created_by_user_id"])

    # A pre-identity deployment had one global administrator. That sole case has an
    # unambiguous creator; multiple-user databases remain NULL and therefore fail closed.
    op.execute(
        sa.text(
            "UPDATE classroom_sessions "
            "SET created_by_user_id = (SELECT id FROM users) "
            "WHERE created_by_user_id IS NULL "
            "AND (SELECT COUNT(*) FROM users) = 1"
        )
    )


def downgrade() -> None:
    with op.batch_alter_table("classroom_sessions") as batch:
        batch.drop_index("ix_classroom_sessions_created_by_user_id")
        batch.drop_constraint("fk_classroom_sessions_created_by_user", type_="foreignkey")
        batch.drop_column("created_by_user_id")
