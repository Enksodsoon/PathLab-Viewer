"""Widen admitted WSI byte counters without rebuilding SQLite parent tables."""

import sqlalchemy as sa
from alembic import op

revision = "20260907_0037"
down_revision = "20260905_0036"
branch_labels = None
depends_on = None

BYTE_COLUMNS = {
    "slides": ("source_bytes", "reserved_bytes", "derivative_bytes"),
    "desktop_ingests": ("package_length", "received_bytes", "derivative_bytes"),
}


def upgrade() -> None:
    # SQLite INTEGER is already signed 64-bit; keeping it avoids rebuilding slides
    # while foreign keys refer to it. Models use the same SQLite INTEGER variant.
    if op.get_bind().dialect.name == "sqlite":
        return
    for table, columns in BYTE_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.Integer(), type_=sa.BigInteger())


def downgrade() -> None:
    connection = op.get_bind()
    # SQLite had the same signed 64-bit INTEGER columns before this revision.
    # Rollback changes only the revision marker; do not impose PostgreSQL limits.
    if connection.dialect.name == "sqlite":
        return
    # Freeze writers before checking every column. No column changes if any value
    # cannot fit the prior PostgreSQL schema.
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE slides, desktop_ingests IN ACCESS EXCLUSIVE MODE"))
    for table, columns in BYTE_COLUMNS.items():
        for column in columns:
            outside = connection.scalar(
                sa.text(
                    f"SELECT 1 FROM {table} WHERE {column} < -2147483648 "
                    f"OR {column} > 2147483647 LIMIT 1"
                )
            )
            if outside is not None:
                raise RuntimeError(f"Cannot downgrade: {table}.{column} exceeds int32 range")
    for table, columns in BYTE_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.BigInteger(), type_=sa.Integer())
