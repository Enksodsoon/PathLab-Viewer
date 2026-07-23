from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession

from .models import Base

ALEMBIC_HEAD = "20260723_0007"
AUDIT_RETENTION_INDEX = "ix_audit_events_action_created_at"


def schema_is_current(database: OrmSession) -> bool:
    """Check migration identity and required schema using reads only."""

    try:
        connection = database.connection()
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        required_tables = set(Base.metadata.tables)
        if "alembic_version" not in tables or not required_tables <= tables:
            return False
        versions = set(database.scalars(text("SELECT version_num FROM alembic_version")))
        if versions != {ALEMBIC_HEAD}:
            return False
        for table_name, table in Base.metadata.tables.items():
            actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
            if not {column.name for column in table.columns} <= actual_columns:
                return False
        audit_indexes = {index["name"] for index in inspector.get_indexes("audit_events")}
        return AUDIT_RETENTION_INDEX in audit_indexes
    except SQLAlchemyError:
        return False
