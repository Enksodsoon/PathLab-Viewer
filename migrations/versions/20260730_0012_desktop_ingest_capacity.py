"""Add prepared-ingest derivative capacity declarations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260730_0012"
down_revision: str | None = "20260729_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("desktop_ingests") as batch:
        batch.add_column(sa.Column("derivative_bytes", sa.Integer()))
        batch.add_column(sa.Column("derivative_file_count", sa.Integer()))
        batch.create_check_constraint(
            "ck_desktop_ingests_derivative_bytes_positive",
            "derivative_bytes IS NULL OR derivative_bytes > 0",
        )
        batch.create_check_constraint(
            "ck_desktop_ingests_derivative_files_positive",
            "derivative_file_count IS NULL OR derivative_file_count > 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("desktop_ingests") as batch:
        batch.drop_constraint(
            "ck_desktop_ingests_derivative_files_positive", type_="check"
        )
        batch.drop_constraint(
            "ck_desktop_ingests_derivative_bytes_positive", type_="check"
        )
        batch.drop_column("derivative_file_count")
        batch.drop_column("derivative_bytes")
