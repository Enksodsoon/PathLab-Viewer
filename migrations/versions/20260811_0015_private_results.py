"""Add private result delivery metadata."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260811_0015"
down_revision: str | None = "20260730_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Keep the migration aligned with SQLAlchemy metadata while retaining support
    # for both SQLite test deployments and PostgreSQL production deployments.
    from wsi_viewer.models import (
        AnalysisRun,
        ManagedResultAttachment,
        PathObjectMeasurement,
        PathObjectMetadata,
        ResultDelivery,
    )

    bind = op.get_bind()
    for table in (
        ResultDelivery.__table__,
        AnalysisRun.__table__,
        PathObjectMetadata.__table__,
        PathObjectMeasurement.__table__,
        ManagedResultAttachment.__table__,
    ):
        table.create(bind, checkfirst=True)


def downgrade() -> None:
    for table in (
        "managed_result_attachments",
        "path_object_measurements",
        "path_object_metadata",
        "analysis_runs",
        "result_deliveries",
    ):
        op.drop_table(table)
