from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    AuditEvent,
    Job,
    PasswordRecoveryAttempt,
    PasswordRecoveryCode,
    Session,
    Slide,
    User,
)


def test_sqlite_schema_has_contract_tables_and_wal(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
        mode = database.execute(text("PRAGMA journal_mode")).scalar_one().lower()
    assert {
        User.__tablename__,
        Session.__tablename__,
        Slide.__tablename__,
        Job.__tablename__,
        AuditEvent.__tablename__,
    } <= tables
    assert mode == "wal"


def test_runtime_app_startup_does_not_create_or_stamp_schema(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'runtime.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_app(settings)
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert tables == set()


def test_sqlite_schema_contains_password_recovery_tables(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'recovery.sqlite3'}", data_root=tmp_path
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert PasswordRecoveryCode.__tablename__ in tables
    assert PasswordRecoveryAttempt.__tablename__ in tables


def test_alembic_upgrade_adds_password_recovery_tables(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "migrated.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    with database_path.open("rb"):
        pass
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        }
    assert {"password_recovery_codes", "password_recovery_attempts"} <= tables


def test_alembic_upgrade_from_0001_preserves_users_and_sessions(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "upgrade-from-0001.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260719_0001")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO users (id, username, password_hash, created_at) "
                "VALUES ('user-1', 'admin', 'hash', '2026-07-19 08:00:00')"
            )
        )
        database.execute(
            text(
                "INSERT INTO sessions (id, user_id, csrf_token, expires_at, created_at) "
                "VALUES ('session-1', 'user-1', 'csrf', "
                "'2026-07-20 08:00:00', '2026-07-19 08:00:00')"
            )
        )
        database.commit()

    command.upgrade(config, "head")

    with session_factory(settings)() as database:
        assert database.execute(text("SELECT username FROM users")).scalar_one() == "admin"
        assert database.execute(text("SELECT user_id FROM sessions")).scalar_one() == "user-1"
        assert database.execute(text("SELECT credential_generation FROM users")).scalar_one() == 1
        assert (
            database.execute(text("SELECT credential_generation FROM sessions")).scalar_one() == 1
        )


def test_current_migration_indexes_recovery_audit_retention_queries(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "audit-index.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        indexes = inspect(database.connection()).get_indexes("audit_events")

    assert any(index["column_names"] == ["action", "created_at"] for index in indexes)


def test_storage_accounting_migration_upgrades_and_downgrades(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "storage-accounting.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")

    command.upgrade(config, "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        columns = {
            column["name"] for column in inspect(database.connection()).get_columns("slides")
        }
    assert {"reserved_bytes", "derivative_bytes", "derivative_file_count"} <= columns

    command.downgrade(config, "20260719_0004")
    with session_factory(settings)() as database:
        downgraded = {
            column["name"] for column in inspect(database.connection()).get_columns("slides")
        }
    assert (
        not {
            "reserved_bytes",
            "derivative_bytes",
            "derivative_file_count",
        }
        & downgraded
    )


def test_library_v2_migration_preserves_public_ids_and_round_trips(
    tmp_path: Path, monkeypatch
) -> None:
    database_path = tmp_path / "library-v2.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    config = Config("alembic.ini")
    command.upgrade(config, "20260723_0005")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")
    with session_factory(settings)() as database:
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, created_at, "
                "updated_at, published_at) VALUES "
                "('slide-1', 'stable-public-id', 'Published', 'source.ome.tiff', 10, "
                "'published', 0, 20, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
        database.commit()

    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        tables = {
            row[0]
            for row in database.execute(
                text("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
            )
        }
        assert {
            "folders",
            "collections",
            "collection_slides",
            "saved_views",
            "library_shares",
            "share_slides",
            "publication_grants",
        } <= tables
        assert (
            database.execute(text("SELECT public_id FROM slides WHERE id = 'slide-1'")).scalar_one()
            == "stable-public-id"
        )
        assert (
            database.execute(
                text(
                    "SELECT source_type || ':' || source_id FROM publication_grants "
                    "WHERE slide_id = 'slide-1'"
                )
            ).scalar_one()
            == "individual:slide-1"
        )
        migrated_slide = database.get(Slide, "slide-1")
        assert migrated_slide is not None
        assert migrated_slide.tags == []

    command.downgrade(config, "20260723_0005")
    command.upgrade(config, "head")
    with session_factory(settings)() as database:
        assert (
            database.execute(text("SELECT public_id FROM slides WHERE id = 'slide-1'")).scalar_one()
            == "stable-public-id"
        )
        migrated_slide = database.get(Slide, "slide-1")
        assert migrated_slide is not None
        assert migrated_slide.tags == []


def test_storage_accounting_columns_reject_negative_values(tmp_path: Path, monkeypatch) -> None:
    database_path = tmp_path / "storage-accounting-negative.sqlite3"
    monkeypatch.setenv("PATHLAB_DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(tmp_path / "data"))
    command.upgrade(Config("alembic.ini"), "head")
    settings = Settings(database_url=f"sqlite:///{database_path}", data_root=tmp_path / "data")

    with (
        session_factory(settings)() as database,
        pytest.raises(IntegrityError),
    ):
        database.execute(
            text(
                "INSERT INTO slides "
                "(id, public_id, display_name, original_filename, source_bytes, state, "
                "reserved_bytes, derivative_bytes, derivative_file_count, created_at, "
                "updated_at) VALUES ('slide-1', 'public-1', 'Test', 'test.ome.tif', 1, "
                "'uploading', -1, 0, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        database.commit()
