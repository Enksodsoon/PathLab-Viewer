"""Add durable desktop synchronization events."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260812_0016"
down_revision: str | None = "20260811_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    from wsi_viewer.models import DesktopSyncEvent

    DesktopSyncEvent.__table__.create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    op.drop_table("desktop_sync_events")
