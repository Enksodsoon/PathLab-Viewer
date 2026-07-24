"""Index bounded library pagination and case-insensitive filters."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260724_0008"
down_revision: str | None = "20260723_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_slides_display_name_id",
        "slides",
        ["display_name", "id"],
    )
    op.execute("CREATE INDEX ix_slides_organ_site_ci ON slides (lower(organ_site))")
    op.execute("CREATE INDEX ix_slides_stain_ci ON slides (lower(stain))")
    op.execute("CREATE INDEX ix_slides_diagnosis_ci ON slides (lower(diagnosis))")
    op.execute("CREATE INDEX ix_slides_course_ci ON slides (lower(course))")


def downgrade() -> None:
    op.execute("DROP INDEX ix_slides_course_ci")
    op.execute("DROP INDEX ix_slides_diagnosis_ci")
    op.execute("DROP INDEX ix_slides_stain_ci")
    op.execute("DROP INDEX ix_slides_organ_site_ci")
    op.drop_index("ix_slides_display_name_id", table_name="slides")
