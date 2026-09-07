"""Add saved slide folders and roster rules to assessment classes."""

import sqlalchemy as sa
from alembic import op

revision = "20260825_0033"
down_revision = "20260825_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cohorts", sa.Column("folder_id", sa.String(length=36)))
    op.add_column(
        "cohorts",
        sa.Column(
            "roster_rule",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{\"mode\":\"existing\",\"filters\":[]}'"),
        ),
    )
    op.create_index("ix_cohorts_folder_id", "cohorts", ["folder_id"])
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_cohorts_folder_id_folders",
            "cohorts",
            "folders",
            ["folder_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_cohorts_folder_id_folders", "cohorts", type_="foreignkey")
    op.drop_index("ix_cohorts_folder_id", table_name="cohorts")
    op.drop_column("cohorts", "roster_rule")
    op.drop_column("cohorts", "folder_id")
