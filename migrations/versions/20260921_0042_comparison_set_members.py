"""Add canonical slide stack membership."""

import json
import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260921_0042"
down_revision = "20260920_0041"
branch_labels = None
depends_on = None


def _json(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


def upgrade() -> None:
    op.create_table(
        "comparison_set_members",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("comparison_set_id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("anchor_slide_id", sa.String(length=36), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("position >= 0", name="ck_comparison_set_members_position"),
        sa.ForeignKeyConstraint(["anchor_slide_id"], ["slides.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["comparison_set_id"], ["comparison_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("comparison_set_id", "slide_id", name="uq_comparison_set_member"),
    )
    op.create_index(
        "ix_comparison_set_members_comparison_set_id",
        "comparison_set_members",
        ["comparison_set_id"],
    )
    op.create_index(
        "ix_comparison_set_members_slide",
        "comparison_set_members",
        ["slide_id", "comparison_set_id"],
    )

    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, reference_slide_id, member_slide_ids, alignment_config FROM comparison_sets"
        )
    ).mappings()
    for row in rows:
        member_ids = list(_json(row["member_slide_ids"]) or [])
        config = _json(row["alignment_config"]) or {}
        anchors = config.get("anchors", {}) if isinstance(config, dict) else {}
        for position, slide_id in enumerate(member_ids):
            connection.execute(
                sa.text(
                    "INSERT INTO comparison_set_members "
                    "(id, comparison_set_id, slide_id, anchor_slide_id, position, created_at) "
                    "VALUES (:id, :set_id, :slide_id, :anchor_id, :position, CURRENT_TIMESTAMP)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "set_id": row["id"],
                    "slide_id": slide_id,
                    "anchor_id": None
                    if slide_id == row["reference_slide_id"]
                    else anchors.get(slide_id, row["reference_slide_id"]),
                    "position": position,
                },
            )


def downgrade() -> None:
    op.drop_index("ix_comparison_set_members_slide", table_name="comparison_set_members")
    op.drop_index(
        "ix_comparison_set_members_comparison_set_id", table_name="comparison_set_members"
    )
    op.drop_table("comparison_set_members")
