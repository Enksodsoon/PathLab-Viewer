"""Add a curated icon choice to assessment courses."""

import sqlalchemy as sa
from alembic import op

revision = "20260825_0032"
down_revision = "20260825_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assessment_courses",
        sa.Column("icon_key", sa.String(length=24), nullable=False, server_default="general"),
    )


def downgrade() -> None:
    op.drop_column("assessment_courses", "icon_key")
