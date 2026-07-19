"""Index recovery audit retention queries and advance the runtime schema contract."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260719_0004"
down_revision: str | None = "20260719_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_audit_events_action_created_at",
        "audit_events",
        ["action", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_audit_events_action_created_at", table_name="audit_events")
