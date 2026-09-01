"""Persist immutable assessment manual feedback and grader identity."""

import sqlalchemy as sa
from alembic import op

revision = "20260828_0035"
down_revision = "20260826_0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_score_versions",
        sa.Column(
            "manual_feedback",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "assessment_score_versions",
        sa.Column("graded_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_assessment_score_versions_graded_by_user_id",
        "assessment_score_versions",
        ["graded_by_user_id"],
    )
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_assessment_score_versions_graded_by_user_id_users",
            "assessment_score_versions",
            "users",
            ["graded_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint(
            "fk_assessment_score_versions_graded_by_user_id_users",
            "assessment_score_versions",
            type_="foreignkey",
        )
    op.drop_index(
        "ix_assessment_score_versions_graded_by_user_id",
        table_name="assessment_score_versions",
    )
    op.drop_column("assessment_score_versions", "graded_by_user_id")
    op.drop_column("assessment_score_versions", "manual_feedback")
