"""Allow multiple immutable registration attempts per slide version."""

from alembic import op

revision = "20260920_0041"
down_revision = "20260920_0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("comparison_registration_revisions") as batch:
        batch.drop_constraint("uq_registration_revision", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("comparison_registration_revisions") as batch:
        batch.create_unique_constraint(
            "uq_registration_revision", ["comparison_set_id", "slide_id", "set_version"]
        )
