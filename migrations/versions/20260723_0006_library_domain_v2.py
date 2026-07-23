"""Add bounded library organization, search, trash, and generic grants."""

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
        sa.Column("previous_parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("normalized_name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_folders_sort_order_nonnegative"),
        sa.ForeignKeyConstraint(["parent_id"], ["folders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parent_id",
            "normalized_name",
            name="uq_folders_parent_normalized_name",
        ),
    )
    op.create_index("ix_folders_parent_id", "folders", ["parent_id"])
    op.create_index(
        "ix_folders_parent_order",
        "folders",
        ["parent_id", "sort_order", "normalized_name"],
    )
    op.create_index("ix_folders_trashed_at", "folders", ["trashed_at"])
    op.create_index(
        "uq_folders_root_normalized_name",
        "folders",
        ["normalized_name"],
        unique=True,
        sqlite_where=sa.text("parent_id IS NULL"),
    )

    with op.batch_alter_table("slides") as batch:
        batch.add_column(sa.Column("folder_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("previous_folder_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch.add_column(
            sa.Column("case_id", sa.String(length=120), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("organ_site", sa.String(length=120), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("stain", sa.String(length=80), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("diagnosis", sa.String(length=300), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column("course", sa.String(length=160), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "tags",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )
        batch.add_column(sa.Column("teaching_note", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("admin_notes", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("thumbnail_filename", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_slides_folder_id_folders",
            "folders",
            ["folder_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint("ck_slides_sort_order_nonnegative", "sort_order >= 0")
        batch.create_index("ix_slides_folder_id", ["folder_id"])
        batch.create_index("ix_slides_case_id", ["case_id"])
        batch.create_index("ix_slides_organ_site", ["organ_site"])
        batch.create_index("ix_slides_stain", ["stain"])
        batch.create_index("ix_slides_diagnosis", ["diagnosis"])
        batch.create_index("ix_slides_course", ["course"])
        batch.create_index("ix_slides_trashed_at", ["trashed_at"])
        batch.create_index("ix_slides_updated_id", ["updated_at", "id"])
        batch.create_index("ix_slides_created_id", ["created_at", "id"])

    op.create_table(
        "collections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_collections_sort_order_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )
    op.create_index(
        "ix_collections_order",
        "collections",
        ["sort_order", "normalized_name"],
    )
    op.create_table(
        "collection_slides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "sort_order >= 0",
            name="ck_collection_slides_sort_order_nonnegative",
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "slide_id",
            name="uq_collection_slides_membership",
        ),
    )
    op.create_index(
        "ix_collection_slides_order",
        "collection_slides",
        ["collection_id", "sort_order", "slide_id"],
    )
    op.create_index("ix_collection_slides_slide", "collection_slides", ["slide_id"])

    op.create_table(
        "saved_views",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("normalized_name", sa.String(length=160), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column("sort", sa.String(length=40), nullable=False, server_default="updated_desc"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("normalized_name"),
    )

    op.create_table(
        "library_shares",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("public_id", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "include_descendants",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "auto_include_new",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("privacy_status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_type IN ('folder', 'collection')",
            name="ck_library_shares_target_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id"),
    )
    op.create_index(
        "ix_library_shares_target",
        "library_shares",
        ["target_type", "target_id"],
    )
    op.create_index(
        "ix_library_shares_public_id",
        "library_shares",
        ["public_id"],
        unique=True,
    )
    op.create_table(
        "share_slides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("share_id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["share_id"], ["library_shares.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["slide_id"], ["slides.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("share_id", "slide_id", name="uq_share_slides_membership"),
    )
    op.create_index(
        "ix_share_slides_order",
        "share_slides",
        ["share_id", "sort_order", "slide_id"],
    )

    op.create_table(
        "publication_grants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("slide_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=20), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_type IN ('individual', 'share')",
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

    # Search remains optional at runtime: SQLite builds without FTS5 use the
    # bounded LIKE adapter. The migration skips only this accelerator.
    bind = op.get_bind()
    try:
        bind.exec_driver_sql(
            """
            CREATE VIRTUAL TABLE slide_search USING fts5(
                display_name,
                original_filename,
                case_id,
                organ_site,
                stain,
                diagnosis,
                course,
                tags,
                content='slides',
                content_rowid='rowid'
            )
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER slide_search_ai AFTER INSERT ON slides BEGIN
              INSERT INTO slide_search(
                rowid, display_name, original_filename, case_id, organ_site,
                stain, diagnosis, course, tags
              ) VALUES (
                new.rowid, new.display_name, new.original_filename, new.case_id,
                new.organ_site, new.stain, new.diagnosis, new.course, new.tags
              );
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER slide_search_ad AFTER DELETE ON slides BEGIN
              INSERT INTO slide_search(
                slide_search, rowid, display_name, original_filename, case_id,
                organ_site, stain, diagnosis, course, tags
              ) VALUES (
                'delete', old.rowid, old.display_name, old.original_filename,
                old.case_id, old.organ_site, old.stain, old.diagnosis,
                old.course, old.tags
              );
            END
            """
        )
        bind.exec_driver_sql(
            """
            CREATE TRIGGER slide_search_au AFTER UPDATE ON slides BEGIN
              INSERT INTO slide_search(
                slide_search, rowid, display_name, original_filename, case_id,
                organ_site, stain, diagnosis, course, tags
              ) VALUES (
                'delete', old.rowid, old.display_name, old.original_filename,
                old.case_id, old.organ_site, old.stain, old.diagnosis,
                old.course, old.tags
              );
              INSERT INTO slide_search(
                rowid, display_name, original_filename, case_id, organ_site,
                stain, diagnosis, course, tags
              ) VALUES (
                new.rowid, new.display_name, new.original_filename, new.case_id,
                new.organ_site, new.stain, new.diagnosis, new.course, new.tags
              );
            END
            """
        )
        bind.exec_driver_sql("INSERT INTO slide_search(slide_search) VALUES('rebuild')")
    except sa.exc.OperationalError as error:
        if "fts5" not in str(error).lower():
            raise


def downgrade() -> None:
    bind = op.get_bind()
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS slide_search_au")
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS slide_search_ad")
    bind.exec_driver_sql("DROP TRIGGER IF EXISTS slide_search_ai")
    bind.exec_driver_sql("DROP TABLE IF EXISTS slide_search")

    op.drop_index("ix_publication_grants_source", table_name="publication_grants")
    op.drop_index("ix_publication_grants_slide", table_name="publication_grants")
    op.drop_table("publication_grants")
    op.drop_index("ix_share_slides_order", table_name="share_slides")
    op.drop_table("share_slides")
    op.drop_index("ix_library_shares_public_id", table_name="library_shares")
    op.drop_index("ix_library_shares_target", table_name="library_shares")
    op.drop_table("library_shares")
    op.drop_table("saved_views")
    op.drop_index("ix_collection_slides_slide", table_name="collection_slides")
    op.drop_index("ix_collection_slides_order", table_name="collection_slides")
    op.drop_table("collection_slides")
    op.drop_index("ix_collections_order", table_name="collections")
    op.drop_table("collections")

    with op.batch_alter_table("slides") as batch:
        batch.drop_index("ix_slides_created_id")
        batch.drop_index("ix_slides_updated_id")
        batch.drop_index("ix_slides_trashed_at")
        batch.drop_index("ix_slides_course")
        batch.drop_index("ix_slides_diagnosis")
        batch.drop_index("ix_slides_stain")
        batch.drop_index("ix_slides_organ_site")
        batch.drop_index("ix_slides_case_id")
        batch.drop_index("ix_slides_folder_id")
        batch.drop_constraint("ck_slides_sort_order_nonnegative", type_="check")
        batch.drop_constraint("fk_slides_folder_id_folders", type_="foreignkey")
        batch.drop_column("trashed_at")
        batch.drop_column("sort_order")
        batch.drop_column("thumbnail_filename")
        batch.drop_column("admin_notes")
        batch.drop_column("teaching_note")
        batch.drop_column("tags")
        batch.drop_column("course")
        batch.drop_column("diagnosis")
        batch.drop_column("stain")
        batch.drop_column("organ_site")
        batch.drop_column("case_id")
        batch.drop_column("description")
        batch.drop_column("previous_folder_id")
        batch.drop_column("folder_id")

    op.drop_index("uq_folders_root_normalized_name", table_name="folders")
    op.drop_index("ix_folders_trashed_at", table_name="folders")
    op.drop_index("ix_folders_parent_order", table_name="folders")
    op.drop_index("ix_folders_parent_id", table_name="folders")
    op.drop_table("folders")
