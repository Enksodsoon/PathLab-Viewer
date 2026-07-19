from pathlib import Path

from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.models import AuditEvent, Job, Session, Slide, User


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
