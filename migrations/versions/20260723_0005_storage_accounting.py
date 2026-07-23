"""Persist storage reservations and derivative measurements."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0005"
down_revision: str | None = "20260719_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("slides") as batch:
        batch.add_column(
            sa.Column(
                "reserved_bytes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(
            sa.Column(
                "derivative_bytes",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(
            sa.Column(
                "derivative_file_count",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.create_check_constraint(
            "ck_slides_reserved_bytes_nonnegative",
            "reserved_bytes >= 0",
        )
        batch.create_check_constraint(
            "ck_slides_derivative_bytes_nonnegative",
            "derivative_bytes >= 0",
        )
        batch.create_check_constraint(
            "ck_slides_derivative_file_count_nonnegative",
            "derivative_file_count >= 0",
        )


def downgrade() -> None:
    with op.batch_alter_table("slides") as batch:
        batch.drop_constraint(
            "ck_slides_derivative_file_count_nonnegative",
            type_="check",
        )
        batch.drop_constraint(
            "ck_slides_derivative_bytes_nonnegative",
            type_="check",
        )
        batch.drop_constraint(
            "ck_slides_reserved_bytes_nonnegative",
            type_="check",
        )
        batch.drop_column("derivative_file_count")
        batch.drop_column("derivative_bytes")
        batch.drop_column("reserved_bytes")
