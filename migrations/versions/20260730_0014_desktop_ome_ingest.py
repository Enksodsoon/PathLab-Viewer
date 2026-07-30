"""Add direct OME desktop ingest declarations."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260730_0014"
down_revision: str | None = "20260730_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE desktop_ingests ADD COLUMN ingest_mode VARCHAR(24) "
        "NOT NULL DEFAULT 'prepared_v2' "
        "CONSTRAINT ck_desktop_ingests_mode "
        "CHECK (ingest_mode IN ('prepared_v2', 'ome_dynamic_v1'))"
    )
    op.execute("ALTER TABLE desktop_ingests ADD COLUMN ome_profile VARCHAR(40)")
    op.execute("ALTER TABLE desktop_ingests ADD COLUMN ome_width INTEGER")
    op.execute("ALTER TABLE desktop_ingests ADD COLUMN ome_height INTEGER")
    op.execute("ALTER TABLE desktop_ingests ADD COLUMN ome_downsample FLOAT")


def downgrade() -> None:
    op.execute("ALTER TABLE desktop_ingests DROP COLUMN ome_downsample")
    op.execute("ALTER TABLE desktop_ingests DROP COLUMN ome_height")
    op.execute("ALTER TABLE desktop_ingests DROP COLUMN ome_width")
    op.execute("ALTER TABLE desktop_ingests DROP COLUMN ome_profile")
    op.execute("ALTER TABLE desktop_ingests DROP COLUMN ingest_mode")
