import threading
import time
from collections.abc import Callable

import httpx
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .models import Base

ALEMBIC_HEAD = "20260905_0027"
AUDIT_RETENTION_INDEX = "ix_audit_events_action_created_at"
ANNOTATION_ACTIVE_INDEX = "ix_annotations_slide_active"
READINESS_CACHE_SECONDS = 1.0


class CachedReadiness:
    """Validate schema once, then cache a cheap connection probe."""

    def __init__(
        self,
        *,
        cache_seconds: float = READINESS_CACHE_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cache_seconds = cache_seconds
        self._clock = clock
        self._lock = threading.Lock()
        self._schema_ready = False
        self._database_ready = False
        self._checked_at = float("-inf")

    @property
    def schema_ready(self) -> bool:
        return self._schema_ready

    def validate_startup(self, factory: sessionmaker[OrmSession]) -> bool:
        try:
            with factory() as database:
                ready = schema_is_current(database)
        except SQLAlchemyError:
            ready = False
        with self._lock:
            self._schema_ready = ready
            self._database_ready = ready
            self._checked_at = self._clock()
        return ready

    def database_is_ready(self, factory: sessionmaker[OrmSession]) -> bool:
        if not self._schema_ready:
            return False
        now = self._clock()
        if now - self._checked_at < self._cache_seconds:
            return self._database_ready
        with self._lock:
            now = self._clock()
            if now - self._checked_at < self._cache_seconds:
                return self._database_ready
            try:
                with factory() as database:
                    ready = bool(database.execute(text("SELECT 1")).scalar_one() == 1)
            except SQLAlchemyError:
                ready = False
            self._database_ready = ready
            self._checked_at = now
            return ready


def tile_service_is_ready(url: str) -> bool:
    try:
        response = httpx.get(f"{url.rstrip('/')}/readyz", timeout=2.0)
        payload = response.json()
        return (
            response.status_code == 200
            and payload.get("status") == "ready"
            and int(payload.get("cacheBytes", -1))
            <= int(payload.get("cacheMaxBytes", -2))
        )
    except (httpx.HTTPError, TypeError, ValueError):
        return False


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
        annotation_indexes = {
            index["name"] for index in inspector.get_indexes("annotations")
        }
        return (
            AUDIT_RETENTION_INDEX in audit_indexes
            and ANNOTATION_ACTIVE_INDEX in annotation_indexes
        )
    except SQLAlchemyError:
        return False
