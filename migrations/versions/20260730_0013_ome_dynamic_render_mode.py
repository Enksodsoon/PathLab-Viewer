"""Add OME-only dynamic render mode."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260730_0013"
down_revision: str | None = "20260730_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE slides ADD COLUMN render_mode VARCHAR(20) "
        "NOT NULL DEFAULT 'static_dzi' "
        "CONSTRAINT ck_slides_render_mode "
        "CHECK (render_mode IN ('static_dzi', 'ome_dynamic'))"
    )
    op.create_index("ix_slides_render_mode", "slides", ["render_mode"])


def downgrade() -> None:
    op.drop_index("ix_slides_render_mode", table_name="slides")
    op.execute("ALTER TABLE slides DROP COLUMN render_mode")
