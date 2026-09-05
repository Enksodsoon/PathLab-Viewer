"""Transaction-scoped serialization for organization membership mutations."""

from __future__ import annotations

import sqlite3
from contextlib import suppress

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session

LOCK_TIMEOUT_MS = 1_000
LOCK_CONFLICT_CODE = "ORGANIZATION_MUTATION_BUSY"
_SQLITE_BUSY_MESSAGES = (
    "database is locked",
    "database table is locked",
    "database is busy",
    "database snapshot is locked",
)
_POSTGRES_LOCK_SQLSTATES = {"55P03", "40P01", "40001"}


def _is_lock_pressure(error: OperationalError | PoolTimeout) -> bool:
    if isinstance(error, PoolTimeout):
        return True
    original = error.orig
    if isinstance(original, sqlite3.OperationalError):
        message = str(original).casefold()
        return any(value in message for value in _SQLITE_BUSY_MESSAGES)
    return getattr(original, "sqlstate", None) in _POSTGRES_LOCK_SQLSTATES


def lock_organization_mutation(database: Session, organization_id: str) -> None:
    """Lock one organization row until the caller commits or rolls back.

    The caller must invoke this inside its existing request transaction, then
    re-read the actor, organization context, and mutation target before making
    any authorization decision. Acquiring this lock grants no authority.
    """

    dialect = database.get_bind().dialect.name
    connection: Connection | None = None
    sqlite_timeout: int | None = None
    try:
        connection = database.connection()
        if dialect == "sqlite":
            sqlite_timeout = int(connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one())
            connection.exec_driver_sql(f"PRAGMA busy_timeout = {LOCK_TIMEOUT_MS}")
        elif dialect == "postgresql":
            database.execute(text(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT_MS}ms'"))
        else:
            raise RuntimeError("Organization mutation locking requires SQLite or PostgreSQL")
        database.execute(
            text("UPDATE organizations SET id = id WHERE id = :organization_id"),
            {"organization_id": organization_id},
        )
    except (OperationalError, PoolTimeout) as error:
        if sqlite_timeout is not None and connection is not None:
            with suppress(SQLAlchemyError):
                connection.exec_driver_sql(f"PRAGMA busy_timeout = {sqlite_timeout}")
        if not _is_lock_pressure(error):
            raise
        database.rollback()
        raise HTTPException(
            status_code=409,
            detail={"code": LOCK_CONFLICT_CODE},
            headers={"Retry-After": "1"},
        ) from error
    else:
        if sqlite_timeout is not None and connection is not None:
            connection.exec_driver_sql(f"PRAGMA busy_timeout = {sqlite_timeout}")
