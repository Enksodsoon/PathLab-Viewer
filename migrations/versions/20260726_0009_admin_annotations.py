"""Add bounded private administrator annotations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0009"
down_revision: str | None = "20260724_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "slides",
        sa.Column(
            "annotation_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        )
    )

    op.create_table(
        "annotation_layers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("visible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("locked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("opacity", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_annotation_layers_sort_order"),
        sa.CheckConstraint(
            "opacity >= 0 AND opacity <= 1",
            name="ck_annotation_layers_opacity",
        ),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_annotation_layers_slide_order",
        "annotation_layers",
        ["slide_id", "sort_order", "created_at"],
    )

    op.create_table(
        "annotations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("layer_id", sa.String(length=36), nullable=False),
        sa.Column("geometry_type", sa.String(length=30), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("annotation_metadata", sa.JSON(), nullable=False),
        sa.Column("bbox_min_x", sa.Float(), nullable=False),
        sa.Column("bbox_min_y", sa.Float(), nullable=False),
        sa.Column("bbox_max_x", sa.Float(), nullable=False),
        sa.Column("bbox_max_y", sa.Float(), nullable=False),
        sa.Column("vertex_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("mutation_id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_annotations_version"),
        sa.CheckConstraint("vertex_count >= 1", name="ck_annotations_vertex_count"),
        sa.CheckConstraint(
            "bbox_min_x <= bbox_max_x AND bbox_min_y <= bbox_max_y",
            name="ck_annotations_bbox_order",
        ),
        sa.ForeignKeyConstraint(["layer_id"], ["annotation_layers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_annotations_slide_active",
        "annotations",
        ["slide_id", "deleted_at", "created_at", "id"],
    )
    op.create_index(
        "ix_annotations_slide_layer_active",
        "annotations",
        ["slide_id", "layer_id", "deleted_at"],
    )
    op.create_index(
        "ix_annotations_slide_bbox",
        "annotations",
        [
            "slide_id",
            "bbox_min_x",
            "bbox_max_x",
            "bbox_min_y",
            "bbox_max_y",
        ],
    )
    op.create_index("ix_annotations_purge_after", "annotations", ["purge_after"])

    op.create_table(
        "annotation_revisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("annotation_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("layer_id", sa.String(length=36), nullable=False),
        sa.Column("geometry_type", sa.String(length=30), nullable=False),
        sa.Column("geometry", sa.JSON(), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("annotation_metadata", sa.JSON(), nullable=False),
        sa.Column("bbox_min_x", sa.Float(), nullable=False),
        sa.Column("bbox_min_y", sa.Float(), nullable=False),
        sa.Column("bbox_max_x", sa.Float(), nullable=False),
        sa.Column("bbox_max_y", sa.Float(), nullable=False),
        sa.Column("vertex_count", sa.Integer(), nullable=False),
        sa.Column("mutation_id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_after", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["annotation_id"], ["annotations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "annotation_id",
            "version",
            name="uq_annotation_revisions_annotation_version",
        ),
    )
    op.create_index(
        "ix_annotation_revisions_annotation_created",
        "annotation_revisions",
        ["annotation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_annotation_revisions_annotation_created",
        table_name="annotation_revisions",
    )
    op.drop_table("annotation_revisions")
    op.drop_index("ix_annotations_purge_after", table_name="annotations")
    op.drop_index("ix_annotations_slide_bbox", table_name="annotations")
    op.drop_index("ix_annotations_slide_layer_active", table_name="annotations")
    op.drop_index("ix_annotations_slide_active", table_name="annotations")
    op.drop_table("annotations")
    op.drop_index(
        "ix_annotation_layers_slide_order",
        table_name="annotation_layers",
    )
    op.drop_table("annotation_layers")

    op.drop_column("slides", "annotation_version")
