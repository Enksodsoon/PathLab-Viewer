"""Add virtual folders, metadata, shares, and publication grants."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260723_0006"
down_revision: str | None = "20260723_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "folders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_folders_sort_order_nonnegative"),
        sa.ForeignKeyConstraint(["parent_id"], ["folders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])
    op.create_index(
        "ix_folders_parent_order",
        "folders",
        ["parent_id", "sort_order", "normalized_name"],
    )
    op.create_index(
        "uq_folders_root_normalized_name",
        "folders",
        ["normalized_name"],
        unique=True,
        sqlite_where=sa.text("parent_id IS NULL"),
    )
    op.create_index(
        "uq_folders_child_normalized_name",
        "folders",
        ["parent_id", "normalized_name"],
        unique=True,
        sqlite_where=sa.text("parent_id IS NOT NULL"),
    )

    with op.batch_alter_table("slides") as batch:
        batch.add_column(sa.Column("folder_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("stain", sa.String(length=80), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("organ_site", sa.String(length=120), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("tags", sa.JSON(), nullable=False, server_default="'[]'"))
        batch.add_column(
            sa.Column("teaching_note", sa.Text(), nullable=False, server_default="")
        )
        batch.add_column(sa.Column("admin_notes", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
        batch.create_foreign_key(
            "fk_slides_folder_id_folders",
            "folders",
            ["folder_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_slides_sort_order_nonnegative",
            "sort_order >= 0",
        )
        batch.create_index("ix_slides_folder_id", ["folder_id"])

    op.create_table(
        "folder_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("folder_id", sa.String(length=36), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index("ix_folder_shares_folder_id", "folder_shares", ["folder_id"])
    op.create_index(
        "uq_folder_shares_active_folder",
        "folder_shares",
        ["folder_id"],
        unique=True,
        sqlite_where=sa.text("is_active = 1"),
    )

    op.create_table(
        "publication_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('individual', 'folder')",
            name="ck_publication_grants_source_type",
        ),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "slide_id",
            "source_type",
            "source_id",
            name="uq_publication_grants_source",
        ),
    )
    op.create_index("ix_publication_grants_slide", "publication_grants", ["slide_id"])
    op.create_index(
        "ix_publication_grants_source",
        "publication_grants",
        ["source_type", "source_id"],
    )
    op.execute(
        sa.text(
            """
            INSERT INTO publication_grants
                (id, slide_id, source_type, source_id, created_at)
            SELECT lower(hex(randomblob(4))) || '-' || lower(hex(randomblob(2))) || '-4' ||
                   substr(lower(hex(randomblob(2))), 2) || '-' ||
                   substr('89ab', abs(random()) % 4 + 1, 1) ||
                   substr(lower(hex(randomblob(2))), 2) || '-' ||
                   lower(hex(randomblob(6))),
                   id, 'individual', id, COALESCE(published_at, created_at)
            FROM slides
            WHERE state = 'published'
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_publication_grants_source", table_name="publication_grants")
    op.drop_index("ix_publication_grants_slide", table_name="publication_grants")
    op.drop_table("publication_grants")
    op.drop_index("uq_folder_shares_active_folder", table_name="folder_shares")
    op.drop_index("ix_folder_shares_folder_id", table_name="folder_shares")
    op.drop_table("folder_shares")
    with op.batch_alter_table("slides") as batch:
        batch.drop_index("ix_slides_folder_id")
        batch.drop_constraint("ck_slides_sort_order_nonnegative", type_="check")
        batch.drop_constraint("fk_slides_folder_id_folders", type_="foreignkey")
        batch.drop_column("sort_order")
        batch.drop_column("admin_notes")
        batch.drop_column("teaching_note")
        batch.drop_column("tags")
        batch.drop_column("organ_site")
        batch.drop_column("stain")
        batch.drop_column("description")
        batch.drop_column("folder_id")
    op.drop_index("uq_folders_child_normalized_name", table_name="folders")
    op.drop_index("uq_folders_root_normalized_name", table_name="folders")
    op.drop_index("ix_folders_parent_order", table_name="folders")
    op.drop_index("ix_folders_parent_id", table_name="folders")
    op.drop_table("folders")
