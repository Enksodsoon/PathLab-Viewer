"""Add revocable desktop device pairing credentials."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260729_0011"
down_revision: str | None = "20260728_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "desktop_pairings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("device_code_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("device_secret_hash", sa.String(64), nullable=False),
        sa.Column("user_code", sa.String(12), nullable=False, unique=True),
        sa.Column("device_name", sa.String(120), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("exchanged_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_desktop_pairings_user_code", "desktop_pairings", ["user_code"])
    op.create_index("ix_desktop_pairings_user_id", "desktop_pairings", ["user_id"])
    op.create_table(
        "desktop_credentials",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.String(36),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("device_name", sa.String(120), nullable=False),
        sa.Column("scopes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_desktop_credentials_user_id", "desktop_credentials", ["user_id"]
    )
    op.create_table(
        "desktop_ingests",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "credential_id",
            sa.String(64),
            sa.ForeignKey("desktop_credentials.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "slide_id",
            sa.String(36),
            sa.ForeignKey("slides.id", ondelete="SET NULL"),
        ),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("artifact_revision_id", sa.String(100), nullable=False),
        sa.Column("package_length", sa.Integer(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("package_sha256", sa.String(64), nullable=False),
        sa.Column("manifest_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="uploading"),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "package_length > 0", name="ck_desktop_ingests_length_positive"
        ),
        sa.CheckConstraint(
            "received_bytes >= 0 AND received_bytes <= package_length",
            name="ck_desktop_ingests_received_range",
        ),
    )
    op.create_index(
        "ix_desktop_ingests_credential_status",
        "desktop_ingests",
        ["credential_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_desktop_ingests_credential_status", table_name="desktop_ingests"
    )
    op.drop_table("desktop_ingests")
    op.drop_index("ix_desktop_credentials_user_id", table_name="desktop_credentials")
    op.drop_table("desktop_credentials")
    op.drop_index("ix_desktop_pairings_user_id", table_name="desktop_pairings")
    op.drop_index("ix_desktop_pairings_user_code", table_name="desktop_pairings")
    op.drop_table("desktop_pairings")
