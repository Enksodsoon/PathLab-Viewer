"""Add structured multilingual learner roster fields."""

import sqlalchemy as sa
from alembic import op

revision = "20260825_0031"
down_revision = "20260825_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("student_id", sa.String(length=100)),
        sa.Column("first_name", sa.String(length=160)),
        sa.Column("last_name", sa.String(length=160)),
        sa.Column("group_name", sa.String(length=100)),
        sa.Column("subgroup_name", sa.String(length=100)),
        sa.Column("email", sa.String(length=254)),
        sa.Column("roster_metadata", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    ):
        op.add_column("learner_profiles", column)
    op.create_index(
        "uq_learners_org_student_id",
        "learner_profiles",
        ["organization_id", "student_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_learners_org_student_id", table_name="learner_profiles")
    columns = (
        "roster_metadata",
        "email",
        "subgroup_name",
        "group_name",
        "last_name",
        "first_name",
        "student_id",
    )
    if op.get_bind().dialect.name == "sqlite":
        for column in columns:
            op.drop_column("learner_profiles", column)
    else:
        with op.batch_alter_table("learner_profiles") as batch:
            for column in columns:
                batch.drop_column(column)
