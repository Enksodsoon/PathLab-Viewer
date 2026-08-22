import hashlib
import hmac
import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from wsi_viewer.postgres_migration import (
    MIGRATION_ADVISORY_LOCK,
    PostgresMigrationError,
    _canonical_json,
    migrate_sqlite_to_postgres,
)

POSTGRES_TEST_URL = os.getenv("PATHLAB_POSTGRES_TEST_URL")
SIGNING_KEY = "synthetic-migration-manifest-key-32-bytes"


def _upgrade(url: str, revision: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATHLAB_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), revision)


def _downgrade(url: str, revision: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATHLAB_DATABASE_URL", url)
    command.downgrade(Config("alembic.ini"), revision)


def _seed_source(source: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source_url = f"sqlite:///{source}"
    _upgrade(source_url, "head", monkeypatch)
    engine = create_engine(source_url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, username, password_hash, credential_generation, "
                "created_at) VALUES ('migration-user', 'admin', 'hash', 1, "
                "'2026-08-21 10:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, description, "
                "case_id, organ_site, stain, diagnosis, course, tags, teaching_note, "
                "admin_notes, sort_order, render_mode, created_at, updated_at) VALUES "
                "('migration-slide', 'migration-public', 'Synthetic slide', "
                "'synthetic.ome.tiff', 10, 'ready_private', 0, 20, 2, '', '', 'skin', "
                "'H&E', '', 'course', '[\"synthetic\"]', '', '', 0, 'static_dzi', "
                "'2026-08-21 10:00:00', '2026-08-21 10:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, actor_user_id, action, target_id, detail, created_at) VALUES "
                "('migration-audit', 'migration-user', 'synthetic.migration', "
                "'migration-slide', :detail, '2026-08-21 10:00:00')"
            ),
            {"detail": '{"fixture":true}'},
        )
    engine.dispose()


@pytest.mark.skipif(
    POSTGRES_TEST_URL is None,
    reason="PATHLAB_POSTGRES_TEST_URL is required for the isolated PostgreSQL test",
)
def test_verified_migration_is_signed_read_only_and_resumable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert POSTGRES_TEST_URL is not None
    source = tmp_path / "source.sqlite3"
    manifest_path = tmp_path / "migration-manifest.json"
    _seed_source(source, monkeypatch)
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    _downgrade(POSTGRES_TEST_URL, "base", monkeypatch)

    manifest = migrate_sqlite_to_postgres(
        source_path=source,
        target_url=POSTGRES_TEST_URL,
        manifest_path=manifest_path,
        signing_key=SIGNING_KEY,
        verify=True,
        batch_size=2,
    )

    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    assert manifest["verified"] is True
    assert manifest["schemaRevision"] == "20260822_0024"
    assert all(table["passed"] for table in manifest["tables"])
    assert all(item["passed"] for item in manifest["foreignKeys"])
    evidence = {item["table"]: item for item in manifest["tables"]}
    assert evidence["users"]["primaryKeys"] == ['["migration-user"]']
    assert evidence["slides"]["sourceCount"] == 1
    assert evidence["audit_events"]["targetCount"] == 1
    signature = manifest.pop("signature")
    expected = hmac.new(
        SIGNING_KEY.encode(), _canonical_json(manifest), hashlib.sha256
    ).hexdigest()
    assert hmac.compare_digest(signature["value"], expected)
    assert ":pathlab_test@" not in json.dumps(manifest["target"])

    manifest_path.unlink()
    resumed = migrate_sqlite_to_postgres(
        source_path=source,
        target_url=POSTGRES_TEST_URL,
        manifest_path=manifest_path,
        signing_key=SIGNING_KEY,
        verify=True,
        batch_size=2,
    )
    assert all(table["passed"] for table in resumed["tables"])

    target_engine = create_engine(POSTGRES_TEST_URL)
    with target_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE users SET username = 'conflicting-admin' "
                "WHERE id = 'migration-user'"
            )
        )
    target_engine.dispose()
    manifest_path.unlink()
    with pytest.raises(PostgresMigrationError, match="Conflicting or missing rows"):
        migrate_sqlite_to_postgres(
            source_path=source,
            target_url=POSTGRES_TEST_URL,
            manifest_path=manifest_path,
            signing_key=SIGNING_KEY,
            verify=True,
            batch_size=2,
        )
    assert not manifest_path.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash

    lock_engine = create_engine(POSTGRES_TEST_URL)
    with lock_engine.connect() as lock_connection:
        lock_connection.execute(
            text("SELECT pg_advisory_lock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK},
        )
        with pytest.raises(PostgresMigrationError, match="already running"):
            migrate_sqlite_to_postgres(
                source_path=source,
                target_url=POSTGRES_TEST_URL,
                manifest_path=manifest_path,
                signing_key=SIGNING_KEY,
                verify=True,
                batch_size=2,
            )
        lock_connection.execute(
            text("SELECT pg_advisory_unlock(:lock_id)"),
            {"lock_id": MIGRATION_ADVISORY_LOCK},
        )
    lock_engine.dispose()


def test_migration_requires_verification_and_a_strong_key(tmp_path: Path) -> None:
    source = tmp_path / "not-opened.sqlite3"
    source.write_bytes(b"SQLite format 3\x00")
    with pytest.raises(PostgresMigrationError, match="--verify is required"):
        migrate_sqlite_to_postgres(
            source_path=source,
            target_url="postgresql+psycopg://example.invalid/pathlab",
            manifest_path=tmp_path / "manifest.json",
            signing_key=SIGNING_KEY,
            verify=False,
        )
    with pytest.raises(PostgresMigrationError, match="at least 32 bytes"):
        migrate_sqlite_to_postgres(
            source_path=source,
            target_url="postgresql+psycopg://example.invalid/pathlab",
            manifest_path=tmp_path / "manifest.json",
            signing_key="weak",
            verify=True,
        )


def test_migration_rejects_a_live_sqlite_sidecar(tmp_path: Path) -> None:
    source = tmp_path / "live.sqlite3"
    source.write_bytes(b"SQLite format 3\x00")
    Path(f"{source}-wal").write_bytes(b"active writer evidence")
    with pytest.raises(PostgresMigrationError, match="not immutable"):
        migrate_sqlite_to_postgres(
            source_path=source,
            target_url="postgresql+psycopg://example.invalid/pathlab",
            manifest_path=tmp_path / "manifest.json",
            signing_key=SIGNING_KEY,
            verify=True,
        )
