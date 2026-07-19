from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
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
