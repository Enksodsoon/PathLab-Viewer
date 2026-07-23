from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.main import create_app


def _settings(tmp_path: Path, name: str) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / name}",
        data_root=tmp_path / f"{name}-data",
    )


def _upgrade(settings: Settings, revision: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATHLAB_DATABASE_URL", settings.database_url)
    monkeypatch.setenv("PATHLAB_DATA_ROOT", str(settings.data_root))
    command.upgrade(Config("alembic.ini"), revision)


def _assert_not_ready(settings: Settings) -> None:
    with TestClient(create_app(settings)) as client:
        response = client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "DATABASE_NOT_READY"}}


def test_empty_database_is_not_ready_and_readiness_does_not_mutate_it(tmp_path: Path) -> None:
    settings = _settings(tmp_path, "empty.sqlite3")
    _assert_not_ready(settings)
    with session_factory(settings)() as database:
        tables = set(database.scalars(text("SELECT name FROM sqlite_master WHERE type='table'")))
    assert tables == set()


@pytest.mark.parametrize(
    "revision",
    ["20260719_0001", "20260719_0003", "20260719_0004"],
)
def test_stale_migration_is_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, revision: str
) -> None:
    settings = _settings(tmp_path, f"{revision}.sqlite3")
    _upgrade(settings, revision, monkeypatch)
    _assert_not_ready(settings)


def test_current_alembic_head_is_ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, "head.sqlite3")
    _upgrade(settings, "head", monkeypatch)
    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").json() == {"status": "ready"}


def test_falsely_stamped_incomplete_schema_is_not_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, "missing-schema.sqlite3")
    _upgrade(settings, "head", monkeypatch)
    with session_factory(settings)() as database:
        database.execute(text("DROP INDEX ix_audit_events_action_created_at"))
        database.commit()
    _assert_not_ready(settings)
