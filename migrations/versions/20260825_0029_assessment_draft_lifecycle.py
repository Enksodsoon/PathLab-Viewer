"""Allow a published assessment administration to return to draft state."""

from alembic import op

revision = "20260825_0029"
down_revision = "20260824_0028"
branch_labels = None
depends_on = None

OLD_STATUSES = "'preparing', 'open', 'closed', 'purged'"
NEW_STATUSES = "'draft', 'preparing', 'open', 'closed', 'purged'"


def upgrade() -> None:
    with op.batch_alter_table("assessment_administrations") as batch:
        batch.drop_constraint("ck_assessment_administration_status", type_="check")
        batch.create_check_constraint(
            "ck_assessment_administration_status", f"status IN ({NEW_STATUSES})"
        )


def downgrade() -> None:
    op.execute(
        "UPDATE assessment_administrations SET status = 'closed' WHERE status = 'draft'"
    )
    with op.batch_alter_table("assessment_administrations") as batch:
        batch.drop_constraint("ck_assessment_administration_status", type_="check")
        batch.create_check_constraint(
            "ck_assessment_administration_status", f"status IN ({OLD_STATUSES})"
        )
