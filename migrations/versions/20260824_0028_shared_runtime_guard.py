"""Generalize the protected runtime guard for Assessment and Classroom."""

import sqlalchemy as sa
from alembic import op

revision = "20260824_0028"
down_revision = "20260824_0027"
branch_labels = None
depends_on = None

OLD_MODES = "'idle', 'draining_for_classroom', 'classroom_live', 'classroom_cooldown'"
NEW_MODES = (
    "'idle', 'draining_for_classroom', 'classroom_live', 'classroom_cooldown', "
    "'draining_for_assessment', 'assessment_live', 'assessment_cooldown'"
)


def upgrade() -> None:
    with op.batch_alter_table("runtime_guards") as batch:
        batch.drop_constraint("ck_runtime_guards_mode", type_="check")
        batch.add_column(sa.Column("assessment_administration_id", sa.String(36)))
        batch.create_check_constraint("ck_runtime_guards_mode", f"mode IN ({NEW_MODES})")


def downgrade() -> None:
    op.execute(
        "UPDATE runtime_guards SET mode = 'idle', cooldown_until = NULL "
        "WHERE mode IN ('draining_for_assessment', 'assessment_live', 'assessment_cooldown')"
    )
    with op.batch_alter_table("runtime_guards") as batch:
        batch.drop_constraint("ck_runtime_guards_mode", type_="check")
        batch.drop_column("assessment_administration_id")
        batch.create_check_constraint("ck_runtime_guards_mode", f"mode IN ({OLD_MODES})")
