from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
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
        assert database.execute(
            text("SELECT credential_generation FROM users")
        ).scalar_one() == 1
        assert database.execute(
            text("SELECT credential_generation FROM sessions")
        ).scalar_one() == 1


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
