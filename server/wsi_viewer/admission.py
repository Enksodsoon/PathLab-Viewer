"""Small, database-shared admission windows for anonymous credential endpoints."""

import hashlib
import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.orm import Session, sessionmaker

from .models import AdmissionAttempt
from .time_support import as_utc

# A global ceiling also bounds retained rows when clients rotate addresses/names.
POLICIES = {
    "login": (timedelta(minutes=5), 5, 5, 1000),
    "password": (timedelta(minutes=5), 5, 5, 1000),
    "pairing": (timedelta(minutes=10), 5, 5, 100),
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class _AdmissionPressure(HTTPException):
    """Recognized transient database pressure, distinct from quota rejection."""


def lock_admission(database: Session, namespace: str) -> None:
    """Call before reads in a fresh transaction; held until commit/rollback."""
    dialect = database.get_bind().dialect.name
    if dialect == "sqlite":
        database.execute(text("BEGIN IMMEDIATE"))
    elif dialect == "postgresql":
        lock_id = int.from_bytes(
            hashlib.sha256(f"pathlab-admission:{namespace}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        database.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    else:
        raise RuntimeError("Shared admission requires SQLite or PostgreSQL")


class SharedAdmission:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory

    @contextmanager
    def _transaction(self, namespace: str) -> Iterator[Session]:
        try:
            with self.factory() as database:
                lock_admission(database, namespace)
                yield database
        except (OperationalError, PoolTimeout) as error:
            original = error.orig if isinstance(error, OperationalError) else None
            sqlite_busy = isinstance(original, sqlite3.OperationalError) and any(
                message in str(original).lower()
                for message in (
                    "database is locked",
                    "database table is locked",
                    "database is busy",
                )
            )
            postgres_busy = getattr(original, "sqlstate", None) in {"55P03", "40P01", "40001"}
            if not isinstance(error, PoolTimeout) and not sqlite_busy and not postgres_busy:
                raise
            raise _AdmissionPressure(
                status_code=429,
                detail={
                    "code": "PAIRING_THROTTLED" if namespace == "pairing" else "AUTH_THROTTLED"
                },
                headers={"Retry-After": "1"},
            ) from error

    def check(self, namespace: str, client: str, now: datetime, subject: str | None = None) -> None:
        window, client_limit, subject_limit, global_limit = POLICIES[namespace]
        client_hash = _hash(client)
        subject_hash = _hash(subject) if subject is not None else None
        with self._transaction(namespace) as database:
            # Expiry is opportunistic on every admission, including denied attempts.
            # Never retain more than the sum of the fixed global window ceilings.
            database.execute(
                delete(AdmissionAttempt).where(
                    AdmissionAttempt.namespace == namespace,
                    AdmissionAttempt.attempted_at <= now - window,
                )
            )
            base = (
                AdmissionAttempt.namespace == namespace,
                AdmissionAttempt.attempted_at > now - window,
            )
            scopes = [
                ((), global_limit),
                ((AdmissionAttempt.client_key_hash == client_hash,), client_limit),
            ]
            if subject_hash is not None:
                scopes.append(((AdmissionAttempt.subject_key_hash == subject_hash,), subject_limit))
            retry_after = 0
            for conditions, limit in scopes:
                count, oldest = database.execute(
                    select(func.count(), func.min(AdmissionAttempt.attempted_at)).where(
                        *base, *conditions
                    )
                ).one()
                if count >= limit and oldest is not None:
                    retry_after = max(
                        retry_after,
                        max(1, math.ceil((as_utc(oldest) + window - now).total_seconds())),
                    )
            if retry_after:
                database.commit()
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "PAIRING_THROTTLED" if namespace == "pairing" else "AUTH_THROTTLED"
                    },
                    headers={"Retry-After": str(retry_after)},
                )
            database.add(
                AdmissionAttempt(
                    namespace=namespace,
                    client_key_hash=client_hash,
                    subject_key_hash=subject_hash,
                    attempted_at=now,
                )
            )
            database.commit()

    def clear(self, namespace: str, client: str, now: datetime, subject: str | None = None) -> None:
        # The caller has already committed authentication/credential rotation.
        # A failed cleanup must retain the conservative counters without turning
        # that durable success into a retryable authentication failure.
        try:
            with self._transaction(namespace) as database:
                base = (
                    AdmissionAttempt.namespace == namespace,
                    AdmissionAttempt.attempted_at <= now,
                )
                database.execute(
                    update(AdmissionAttempt)
                    .where(*base, AdmissionAttempt.client_key_hash == _hash(client))
                    .values(client_key_hash=None)
                )
                if subject is not None:
                    database.execute(
                        update(AdmissionAttempt)
                        .where(*base, AdmissionAttempt.subject_key_hash == _hash(subject))
                        .values(subject_key_hash=None)
                    )
                # Keep the global accounting even after success so rotating identities
                # cannot create an unbounded number of rows in one window.
                database.commit()
        except _AdmissionPressure:
            return
