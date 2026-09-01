"""Add courses, shared rosters, and class section metadata."""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "20260825_0030"
down_revision = "20260825_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_courses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("course_code", sa.String(length=60), nullable=False),
        sa.Column("semester", sa.String(length=80), nullable=False),
        sa.Column("academic_year", sa.String(length=20)),
        sa.Column("scoring_method", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("opens_at", sa.DateTime(timezone=True)),
        sa.Column("closes_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')", name="ck_assessment_courses_status"
        ),
        sa.CheckConstraint(
            "scoring_method IN ('points', 'percentage', 'weighted', 'pass_fail')",
            name="ck_assessment_courses_scoring_method",
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "organization_id", "course_code", name="uq_assessment_courses_org_code"
        ),
    )
    op.create_index(
        "ix_assessment_courses_organization_id", "assessment_courses", ["organization_id"]
    )

    cohort_columns = (
        sa.Column("assessment_course_id", sa.String(length=36)),
        sa.Column("section_code", sa.String(length=60)),
        sa.Column("description", sa.Text()),
        sa.Column("meeting_schedule", sa.String(length=160)),
        sa.Column("location", sa.String(length=160)),
        sa.Column("opens_at", sa.DateTime(timezone=True)),
        sa.Column("closes_at", sa.DateTime(timezone=True)),
    )
    for column in cohort_columns:
        op.add_column("cohorts", column)
    op.create_index("ix_cohorts_assessment_course_id", "cohorts", ["assessment_course_id"])
    if op.get_bind().dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_cohorts_assessment_course_id",
            "cohorts",
            "assessment_courses",
            ["assessment_course_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "assessment_course_enrollments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("learner_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'withdrawn')", name="ck_course_enrollments_status"
        ),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["assessment_courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["learner_id"], ["learner_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("course_id", "learner_id", name="uq_course_enrollments_course_learner"),
    )
    op.create_index(
        "ix_assessment_course_enrollments_organization_id",
        "assessment_course_enrollments",
        ["organization_id"],
    )
    op.create_index(
        "ix_assessment_course_enrollments_course_id", "assessment_course_enrollments", ["course_id"]
    )

    connection = op.get_bind()
    cohorts = connection.execute(
        sa.text(
            "SELECT id, organization_id, name, status, created_by_user_id, created_at, updated_at "
            "FROM cohorts ORDER BY created_at, id"
        )
    ).mappings()
    for index, cohort in enumerate(cohorts, start=1):
        course_id = str(uuid.uuid4())
        course_code = f"LEGACY-{index}-{str(cohort['id'])[:8]}"
        connection.execute(
            sa.text(
                "INSERT INTO assessment_courses "
                "(id, organization_id, name, course_code, semester, academic_year, "
                "scoring_method, description, opens_at, closes_at, status, schema_version, "
                "created_by_user_id, created_at, updated_at) VALUES (:id, :organization_id, "
                ":name, :course_code, 'Imported', NULL, 'percentage', :description, NULL, "
                "NULL, :status, 1, :created_by_user_id, :created_at, :updated_at)"
            ),
            {
                "id": course_id,
                "organization_id": cohort["organization_id"],
                "name": cohort["name"],
                "course_code": course_code,
                "description": "Migrated from the existing class roster.",
                "status": "active" if cohort["status"] == "active" else "archived",
                "created_by_user_id": cohort["created_by_user_id"],
                "created_at": cohort["created_at"],
                "updated_at": cohort["updated_at"],
            },
        )
        connection.execute(
            sa.text(
                "UPDATE cohorts SET assessment_course_id = :course_id, "
                "section_code = :section_code "
                "WHERE id = :cohort_id"
            ),
            {"course_id": course_id, "section_code": "MAIN", "cohort_id": cohort["id"]},
        )
        enrollments = connection.execute(
            sa.text(
                "SELECT organization_id, learner_id, status, created_by_user_id, "
                "created_at, updated_at "
                "FROM cohort_enrollments WHERE cohort_id = :cohort_id"
            ),
            {"cohort_id": cohort["id"]},
        ).mappings()
        for enrollment in enrollments:
            connection.execute(
                sa.text(
                    "INSERT INTO assessment_course_enrollments "
                    "(id, organization_id, course_id, learner_id, status, created_by_user_id, "
                    "created_at, updated_at) VALUES (:id, :organization_id, :course_id, "
                    ":learner_id, :status, :created_by_user_id, :created_at, :updated_at)"
                ),
                {"id": str(uuid.uuid4()), "course_id": course_id, **enrollment},
            )


def downgrade() -> None:
    op.drop_table("assessment_course_enrollments")
    op.drop_index("ix_cohorts_assessment_course_id", table_name="cohorts")
    if op.get_bind().dialect.name != "sqlite":
        op.drop_constraint("fk_cohorts_assessment_course_id", "cohorts", type_="foreignkey")
    columns = (
        "closes_at",
        "opens_at",
        "location",
        "meeting_schedule",
        "description",
        "section_code",
        "assessment_course_id",
    )
    if op.get_bind().dialect.name == "sqlite":
        for column in columns:
            op.drop_column("cohorts", column)
    else:
        with op.batch_alter_table("cohorts") as batch:
            for column in columns:
                batch.drop_column(column)
    op.drop_table("assessment_courses")
