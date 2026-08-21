"""Add Viewer-native authoring pilot controls and aggregate AI actions."""

import sqlalchemy as sa
from alembic import op

revision = "20260821_0023"
down_revision = "20260821_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("study_courses") as batch:
        batch.add_column(
            sa.Column("ai_mode", sa.String(32), nullable=False, server_default="deterministic")
        )
        batch.add_column(sa.Column("pilot_acknowledged_at", sa.DateTime(timezone=True)))
        batch.create_check_constraint(
            "ck_study_courses_ai_mode",
            "ai_mode IN ('deterministic', 'closed_pilot_trace_sim')",
        )
    with op.batch_alter_table("study_readiness_aggregates") as batch:
        for name in (
            "continue_count",
            "offer_hint_count",
            "ask_confidence_count",
            "ask_source_check_count",
            "retrieve_count",
            "pause_count",
        ):
            batch.add_column(sa.Column(name, sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("study_readiness_aggregates") as batch:
        for name in (
            "pause_count",
            "retrieve_count",
            "ask_source_check_count",
            "ask_confidence_count",
            "offer_hint_count",
            "continue_count",
        ):
            batch.drop_column(name)
    with op.batch_alter_table("study_courses") as batch:
        batch.drop_constraint("ck_study_courses_ai_mode", type_="check")
        batch.drop_column("pilot_acknowledged_at")
        batch.drop_column("ai_mode")
