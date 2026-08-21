"""Add durable background jobs and the Classroom runtime guard."""

import sqlalchemy as sa
from alembic import op

revision = "20260822_0024"
down_revision = "20260821_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch:
        batch.alter_column("slide_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("organization_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("actor_type", sa.String(20), nullable=True))
        batch.add_column(sa.Column("actor_id", sa.String(100), nullable=True))
        batch.add_column(
            sa.Column(
                "resource_class",
                sa.String(20),
                nullable=False,
                server_default="background",
            )
        )
        batch.add_column(sa.Column("idempotency_key_hash", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("input_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("lease_expires_at", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("checkpoint", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("cancellation_requested_at", sa.DateTime(timezone=True)))
        batch.add_column(
            sa.Column("resource_limits", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("output_manifest", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("evidence_location", sa.String(500), nullable=True))
        batch.add_column(sa.Column("failure_code", sa.String(100), nullable=True))
        batch.add_column(sa.Column("audit_event_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            )
        )
        batch.create_foreign_key(
            "fk_jobs_audit_event_id", "audit_events", ["audit_event_id"], ["id"],
            ondelete="SET NULL"
        )

    op.execute(sa.text("UPDATE jobs SET status = 'succeeded' WHERE status = 'complete'"))
    op.execute(sa.text("UPDATE jobs SET status = 'failed_terminal' WHERE status = 'failed'"))

    with op.batch_alter_table("jobs") as batch:
        batch.create_check_constraint(
            "ck_jobs_status",
            "status IN ('queued', 'blocked_classroom', 'running', 'checkpointing', "
            "'retry_wait', 'succeeded', 'failed_terminal', 'cancelled')",
        )
        batch.create_check_constraint(
            "ck_jobs_resource_class",
            "resource_class IN ('live_critical', 'interactive', 'background', 'isolated')",
        )
        batch.create_index(
            "ix_jobs_claim", ["status", "next_attempt_at", "created_at"], unique=False
        )
        batch.create_index("ix_jobs_organization_id", ["organization_id"], unique=False)
        batch.create_index(
            "uq_jobs_idempotency",
            ["organization_id", "kind", "idempotency_key_hash"],
            unique=True,
            sqlite_where=sa.text("idempotency_key_hash IS NOT NULL"),
            postgresql_where=sa.text("idempotency_key_hash IS NOT NULL"),
        )

    op.create_table(
        "runtime_guards",
        sa.Column("id", sa.String(40), primary_key=True),
        sa.Column("mode", sa.String(30), nullable=False, server_default="idle"),
        sa.Column("classroom_session_id", sa.String(36), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "mode IN ('idle', 'draining_for_classroom', 'classroom_live', "
            "'classroom_cooldown')",
            name="ck_runtime_guards_mode",
        ),
    )
def downgrade() -> None:
    op.drop_table("runtime_guards")
    with op.batch_alter_table("jobs") as batch:
        batch.drop_index("uq_jobs_idempotency")
        batch.drop_index("ix_jobs_organization_id")
        batch.drop_index("ix_jobs_claim")
        batch.drop_constraint("ck_jobs_resource_class", type_="check")
        batch.drop_constraint("ck_jobs_status", type_="check")
    op.execute(
        sa.text(
            "UPDATE jobs SET status = 'queued' "
            "WHERE status IN ('blocked_classroom', 'checkpointing', 'retry_wait')"
        )
    )
    op.execute(sa.text("UPDATE jobs SET status = 'complete' WHERE status = 'succeeded'"))
    op.execute(sa.text("UPDATE jobs SET status = 'failed' WHERE status = 'failed_terminal'"))
    with op.batch_alter_table("jobs") as batch:
        batch.drop_constraint("fk_jobs_audit_event_id", type_="foreignkey")
        for column in (
            "updated_at",
            "audit_event_id",
            "failure_code",
            "evidence_location",
            "output_manifest",
            "resource_limits",
            "cancellation_requested_at",
            "checkpoint",
            "lease_expires_at",
            "next_attempt_at",
            "policy_version",
            "input_version",
            "idempotency_key_hash",
            "resource_class",
            "actor_id",
            "actor_type",
            "organization_id",
        ):
            batch.drop_column(column)
        batch.alter_column("slide_id", existing_type=sa.String(36), nullable=False)
