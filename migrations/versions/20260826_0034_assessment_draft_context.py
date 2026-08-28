"""Persist course and class ownership on assessment drafts."""

import sqlalchemy as sa
from alembic import op

revision = "20260826_0034"
down_revision = "20260825_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assessment_drafts", sa.Column("course_id", sa.String(length=36)))
    op.add_column("assessment_drafts", sa.Column("cohort_id", sa.String(length=36)))
    op.create_index("ix_assessment_drafts_course_id", "assessment_drafts", ["course_id"])
    op.create_index("ix_assessment_drafts_cohort_id", "assessment_drafts", ["cohort_id"])
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_assessment_drafts_course_id_courses",
            "assessment_drafts",
            "assessment_courses",
            ["course_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_foreign_key(
            "fk_assessment_drafts_cohort_id_cohorts",
            "assessment_drafts",
            "cohorts",
            ["cohort_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute(sa.text("""
        UPDATE assessment_drafts
        SET cohort_id = (
            SELECT assessment_administrations.cohort_id
            FROM assessment_versions
            JOIN assessment_administrations
              ON assessment_administrations.version_id = assessment_versions.id
            WHERE assessment_versions.draft_id = assessment_drafts.id
              AND assessment_administrations.cohort_id IS NOT NULL
            ORDER BY assessment_administrations.created_at DESC
            LIMIT 1
        )
        WHERE cohort_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM assessment_versions
            JOIN assessment_administrations
              ON assessment_administrations.version_id = assessment_versions.id
            WHERE assessment_versions.draft_id = assessment_drafts.id
              AND assessment_administrations.cohort_id IS NOT NULL
          )
    """))
    op.execute(sa.text("""
        UPDATE assessment_drafts
        SET course_id = (
            SELECT cohorts.assessment_course_id
            FROM cohorts
            WHERE cohorts.id = assessment_drafts.cohort_id
        )
        WHERE course_id IS NULL AND cohort_id IS NOT NULL
    """))


def downgrade() -> None:
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_assessment_drafts_cohort_id_cohorts", "assessment_drafts", type_="foreignkey")
        op.drop_constraint("fk_assessment_drafts_course_id_courses", "assessment_drafts", type_="foreignkey")
    op.drop_index("ix_assessment_drafts_cohort_id", table_name="assessment_drafts")
    op.drop_index("ix_assessment_drafts_course_id", table_name="assessment_drafts")
    op.drop_column("assessment_drafts", "cohort_id")
    op.drop_column("assessment_drafts", "course_id")
