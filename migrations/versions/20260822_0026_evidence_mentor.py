"""Add signed Evidence Mentor bundles and reviewed knowledge packs."""

import sqlalchemy as sa
from alembic import op

revision = "20260822_0026"
down_revision = "20260822_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_bundles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "delivery_id",
            sa.String(36),
            sa.ForeignKey("result_deliveries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "slide_id",
            sa.String(36),
            sa.ForeignKey("slides.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bundle_id", sa.String(120), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("pack_id", sa.String(120), nullable=False),
        sa.Column("pack_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("validation_status", sa.String(24), nullable=False),
        sa.Column("manifest", sa.JSON(), nullable=False),
        sa.Column(
            "reviewed_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("delivery_id", name="uq_evidence_bundles_delivery_id"),
        sa.UniqueConstraint("manifest_sha256", name="uq_evidence_bundles_manifest"),
        sa.UniqueConstraint("slide_id", "bundle_id", name="uq_evidence_bundles_slide_bundle"),
        sa.CheckConstraint(
            "status IN ('completed', 'partial', 'abstained', 'unsupported', 'failed')",
            name="ck_evidence_bundles_status",
        ),
        sa.CheckConstraint(
            "validation_status IN ('experimental', 'qualified')",
            name="ck_evidence_bundles_validation",
        ),
    )
    op.create_index("ix_evidence_bundles_slide_id", "evidence_bundles", ["slide_id"])
    op.create_table(
        "knowledge_packs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("pack_key", sa.String(120), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("definition", sa.JSON(), nullable=False),
        sa.Column(
            "created_by_user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("pack_key", "version", name="uq_knowledge_packs_key_version"),
        sa.UniqueConstraint("checksum", name="uq_knowledge_packs_checksum"),
    )


def downgrade() -> None:
    op.drop_table("knowledge_packs")
    op.drop_index("ix_evidence_bundles_slide_id", table_name="evidence_bundles")
    op.drop_table("evidence_bundles")
