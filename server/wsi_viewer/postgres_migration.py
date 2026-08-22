from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, Table, create_engine, inspect, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.engine import URL, Connection, Engine, make_url

from .config import Settings
from .database import database_target_for

MIGRATION_SCHEMA_VERSION = 1
EXCLUDED_SQLITE_TABLE_PREFIXES = ("sqlite_", "slide_search")
RELEASE_SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
MIGRATION_ADVISORY_LOCK = 22607181910319426


class PostgresMigrationError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalize(value: Any) -> Any:
    if isinstance(value, datetime):
        aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        return aware.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, bytes):
        return {"bytesSha256": hashlib.sha256(value).hexdigest(), "length": len(value)}
    if isinstance(value, Mapping):
        return {str(key): _normalize(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        _normalize(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _row_digest(rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256()
    for row in rows:
        digest.update(_canonical_json(dict(row)))
        digest.update(b"\n")
    return digest.hexdigest()


def _primary_key_value(row: Mapping[str, Any], primary_keys: Sequence[str]) -> str:
    return _canonical_json([row[key] for key in primary_keys]).decode("utf-8")


def _source_engine(source: Path) -> Engine:
    uri = f"file:{source.as_posix()}?mode=ro&immutable=1"

    def connect() -> sqlite3.Connection:
        return sqlite3.connect(
            uri,
            uri=True,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )

    return create_engine("sqlite+pysqlite://", creator=connect)


def _validate_source(source: Path) -> str:
    resolved = source.resolve(strict=True)
    if not resolved.is_file():
        raise PostgresMigrationError("SQLite source must be a regular file")
    sidecars = [Path(f"{resolved}-wal"), Path(f"{resolved}-shm")]
    present = [path.name for path in sidecars if path.exists()]
    if present:
        raise PostgresMigrationError(
            "SQLite source is not immutable; stop writers, checkpoint it, and remove sidecars: "
            + ", ".join(present)
        )
    with resolved.open("rb") as handle:
        if handle.read(16) != b"SQLite format 3\x00":
            raise PostgresMigrationError("Source is not a SQLite 3 database")
    return _sha256_file(resolved)


def _validate_target(target_url: str) -> URL:
    target = make_url(target_url)
    if target.get_backend_name() != "postgresql":
        raise PostgresMigrationError("Migration target must be PostgreSQL")
    if not target.drivername.startswith("postgresql+psycopg"):
        raise PostgresMigrationError("Migration target must use the Psycopg 3 SQLAlchemy driver")
    return target


def _upgrade_target(target_engine: Engine) -> None:
    with target_engine.connect() as connection:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


def _release_sha() -> str:
    configured = os.getenv("PATHLAB_RELEASE_SHA", "").strip().lower()
    if RELEASE_SHA_PATTERN.fullmatch(configured):
        return configured
    try:
        discovered = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip().lower()
    except (FileNotFoundError, subprocess.SubprocessError) as error:
        raise PostgresMigrationError(
            "PATHLAB_RELEASE_SHA must contain the exact 40-character release SHA"
        ) from error
    if RELEASE_SHA_PATTERN.fullmatch(discovered) is None:
        raise PostgresMigrationError("Could not determine an exact release SHA")
    return discovered


def _copyable_table_names(connection: Connection) -> list[str]:
    return sorted(
        name
        for name in inspect(connection).get_table_names()
        if name != "alembic_version"
        and not name.startswith(EXCLUDED_SQLITE_TABLE_PREFIXES)
    )


def _ordered_tables(metadata: MetaData, names: set[str]) -> list[Table]:
    ordered = [table for table in metadata.sorted_tables if table.name in names]
    if {table.name for table in ordered} != names:
        raise PostgresMigrationError("Could not derive a complete foreign-key table order")
    return ordered


def _ordered_rows(connection: Connection, table: Table) -> list[Mapping[str, Any]]:
    primary_keys = list(table.primary_key.columns)
    if not primary_keys:
        raise PostgresMigrationError(f"Table {table.name} has no primary key")
    return [
        dict(row)
        for row in connection.execute(select(table).order_by(*primary_keys)).mappings()
    ]


def _matching_target_rows(
    connection: Connection,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    primary_keys = list(table.primary_key.columns)
    key_values = [tuple(row[column.name] for column in primary_keys) for row in rows]
    if not key_values:
        return []
    if len(primary_keys) == 1:
        predicate = primary_keys[0].in_([key[0] for key in key_values])
    else:
        predicate = tuple_(*primary_keys).in_(key_values)
    return [
        dict(row)
        for row in connection.execute(
            select(table).where(predicate).order_by(*primary_keys)
        ).mappings()
    ]


def _copy_table(
    source: Connection,
    target: Connection,
    source_table: Table,
    target_table: Table,
    batch_size: int,
) -> None:
    source_rows = _ordered_rows(source, source_table)
    source_columns = [column.name for column in source_table.columns]
    target_columns = [column.name for column in target_table.columns]
    if source_columns != target_columns:
        raise PostgresMigrationError(
            f"Schema mismatch for {source_table.name}: source and target columns differ"
        )
    primary_keys = [column.name for column in source_table.primary_key.columns]
    for offset in range(0, len(source_rows), batch_size):
        batch = source_rows[offset : offset + batch_size]
        target.execute(
            postgresql_insert(target_table)
            .values([dict(row) for row in batch])
            .on_conflict_do_nothing(
                index_elements=[target_table.c[name] for name in primary_keys]
            )
        )
        copied = _matching_target_rows(target, target_table, batch)
        expected = sorted(
            (_primary_key_value(row, primary_keys), _canonical_json(dict(row)))
            for row in batch
        )
        actual = sorted(
            (_primary_key_value(row, primary_keys), _canonical_json(dict(row)))
            for row in copied
        )
        if actual != expected:
            raise PostgresMigrationError(
                f"Conflicting or missing rows detected in target table {source_table.name}"
            )
        target.commit()


def _foreign_key_results(connection: Connection, metadata: MetaData) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for table in sorted(metadata.tables.values(), key=lambda item: item.name):
        for constraint in sorted(
            table.foreign_key_constraints,
            key=lambda item: str(item.name) if item.name is not None else "",
        ):
            local = list(constraint.columns)
            remote = [element.column for element in constraint.elements]
            parent = remote[0].table
            join = text(" AND ".join(
                f'child."{left.name}" = parent."{right.name}"'
                for left, right in zip(local, remote, strict=True)
            ))
            non_null = text(" AND ".join(
                f'child."{column.name}" IS NOT NULL' for column in local
            ))
            missing = text(f'parent."{remote[0].name}" IS NULL')
            statement = (
                select(text("count(*)"))
                .select_from(table.alias("child").outerjoin(parent.alias("parent"), join))
                .where(non_null, missing)
            )
            orphan_count = int(connection.scalar(statement) or 0)
            results.append(
                {
                    "constraint": constraint.name,
                    "table": table.name,
                    "referencedTable": parent.name,
                    "orphanCount": orphan_count,
                    "passed": orphan_count == 0,
                }
            )
    return results


def _table_evidence(
    source: Connection,
    target: Connection,
    source_table: Table,
    target_table: Table,
) -> dict[str, Any]:
    source_rows = _ordered_rows(source, source_table)
    target_rows = _ordered_rows(target, target_table)
    primary_keys = [column.name for column in source_table.primary_key.columns]
    source_keys = [_primary_key_value(row, primary_keys) for row in source_rows]
    target_keys = [_primary_key_value(row, primary_keys) for row in target_rows]
    source_hash = _row_digest(source_rows)
    target_hash = _row_digest(target_rows)
    passed = (
        len(source_rows) == len(target_rows)
        and source_keys == target_keys
        and hmac.compare_digest(source_hash, target_hash)
    )
    return {
        "table": source_table.name,
        "sourceCount": len(source_rows),
        "targetCount": len(target_rows),
        "primaryKeyColumns": primary_keys,
        "primaryKeys": source_keys,
        "sourceContentSha256": source_hash,
        "targetContentSha256": target_hash,
        "passed": passed,
    }


def _redacted_target(target: URL) -> str:
    return target.set(password=None).render_as_string(hide_password=True)


def migrate_sqlite_to_postgres(
    *,
    source_path: Path,
    target_url: str,
    target_password_file: Path | None = None,
    manifest_path: Path,
    signing_key: str,
    verify: bool,
    batch_size: int = 500,
) -> dict[str, Any]:
    if not verify:
        raise PostgresMigrationError("--verify is required; unverified migration is prohibited")
    if len(signing_key.encode("utf-8")) < 32:
        raise PostgresMigrationError("Migration manifest signing key must be at least 32 bytes")
    if batch_size < 1 or batch_size > 5000:
        raise PostgresMigrationError("Migration batch size must be between 1 and 5000")
    if manifest_path.exists():
        raise PostgresMigrationError("Refusing to overwrite an existing migration manifest")

    source_path = source_path.resolve(strict=True)
    source_hash_before = _validate_source(source_path)
    target = _validate_target(target_url)
    release_sha = _release_sha()

    source_engine = _source_engine(source_path)
    target_settings = Settings(
        database_url=target_url,
        database_password_file=target_password_file,
    )
    target_engine = create_engine(database_target_for(target_settings), pool_pre_ping=True)
    lock_connection = target_engine.connect()
    try:
        locked = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK},
        )
        if locked is not True:
            raise PostgresMigrationError("Another SQLite migration is already running")
        _upgrade_target(target_engine)
        with source_engine.connect() as source, target_engine.connect() as destination:
            source_revision = source.scalar(text("SELECT version_num FROM alembic_version"))
            target_revision = destination.scalar(text("SELECT version_num FROM alembic_version"))
            if source_revision != target_revision:
                raise PostgresMigrationError(
                    "Source and target schema revisions differ: "
                    f"source={source_revision}, target={target_revision}"
                )
            source_names = set(_copyable_table_names(source))
            target_names = set(_copyable_table_names(destination))
            if source_names != target_names:
                raise PostgresMigrationError(
                    "Source and target table sets differ: "
                    f"source-only={sorted(source_names - target_names)}, "
                    f"target-only={sorted(target_names - source_names)}"
                )
            source_metadata = MetaData()
            source_metadata.reflect(bind=source, only=sorted(source_names))
            target_metadata = MetaData()
            target_metadata.reflect(bind=destination, only=sorted(target_names))
            destination.commit()
            ordered = _ordered_tables(source_metadata, source_names)
            for source_table in ordered:
                _copy_table(
                    source,
                    destination,
                    source_table,
                    target_metadata.tables[source_table.name],
                    batch_size,
                )

        with source_engine.connect() as source, target_engine.connect() as destination:
            source_metadata = MetaData()
            source_metadata.reflect(bind=source, only=sorted(source_names))
            target_metadata = MetaData()
            target_metadata.reflect(bind=destination, only=sorted(target_names))
            tables = [
                _table_evidence(
                    source,
                    destination,
                    source_metadata.tables[name],
                    target_metadata.tables[name],
                )
                for name in sorted(source_names)
            ]
            foreign_keys = _foreign_key_results(destination, target_metadata)
    finally:
        if not lock_connection.closed:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": MIGRATION_ADVISORY_LOCK},
            )
            lock_connection.close()
        source_engine.dispose()
        target_engine.dispose()

    source_hash_after = _sha256_file(source_path)
    passed = (
        hmac.compare_digest(source_hash_before, source_hash_after)
        and all(table["passed"] for table in tables)
        and all(result["passed"] for result in foreign_keys)
    )
    if not passed:
        raise PostgresMigrationError("Migration verification failed; manifest was not written")

    payload: dict[str, Any] = {
        "schemaVersion": MIGRATION_SCHEMA_VERSION,
        "kind": "pathlab-sqlite-to-postgres",
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "releaseSha": release_sha,
        "schemaRevision": target_revision,
        "sourceSchemaRevision": source_revision,
        "source": {
            "fileName": source_path.name,
            "sha256Before": source_hash_before,
            "sha256After": source_hash_after,
            "unchanged": True,
        },
        "target": {"database": _redacted_target(target)},
        "tables": tables,
        "foreignKeys": foreign_keys,
        "verified": True,
        "claimRestrictions": [
            "synthetic or staging migration evidence only",
            "not a production migration certificate",
            "not a backup restore certificate",
        ],
    }
    signature = hmac.new(signing_key.encode("utf-8"), _canonical_json(payload), hashlib.sha256)
    manifest = {
        **payload,
        "signature": {"algorithm": "HMAC-SHA256", "value": signature.hexdigest()},
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest
