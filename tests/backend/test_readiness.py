from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect as sqlalchemy_inspect
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
    [
        "20260719_0001",
        "20260719_0003",
        "20260719_0004",
        "20260724_0008",
        "20260726_0009",
    ],
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


def test_readiness_validates_schema_once_at_startup_then_uses_cached_lightweight_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, "cached-readiness.sqlite3")
    _upgrade(settings, "head", monkeypatch)
    inspections = 0

    def recording_inspect(bind: object):
        nonlocal inspections
        inspections += 1
        return sqlalchemy_inspect(bind)

    monkeypatch.setattr("wsi_viewer.readiness.inspect", recording_inspect)
    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").json() == {"status": "ready"}
        assert client.get("/readyz").json() == {"status": "ready"}

    assert inspections == 1


def test_production_readiness_requires_bounded_internal_tile_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _settings(tmp_path, "tile-service.sqlite3").model_dump()
    values["internal_file_redirects"] = True
    settings = Settings(**values)
    _upgrade(settings, "head", monkeypatch)
    monkeypatch.setattr("wsi_viewer.main.tile_service_is_ready", lambda _: False)
    with TestClient(create_app(settings)) as client:
        unavailable = client.get("/readyz")
        assert unavailable.status_code == 503
        assert unavailable.json() == {
            "detail": {"code": "TILE_SERVICE_NOT_READY"}
        }

    monkeypatch.setattr("wsi_viewer.main.tile_service_is_ready", lambda _: True)
    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").json() == {"status": "ready"}


def test_classroom_readiness_does_not_depend_on_the_general_tile_service(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _settings(tmp_path, "classroom-role.sqlite3").model_dump()
    values.update(
        service_role="classroom",
        classroom_enabled=True,
        classroom_singleton=True,
        internal_file_redirects=True,
    )
    settings = Settings(**values)
    _upgrade(settings, "head", monkeypatch)
    monkeypatch.setattr("wsi_viewer.main.tile_service_is_ready", lambda _: False)

    with TestClient(create_app(settings)) as client:
        assert client.get("/readyz").json() == {"status": "ready"}


def test_general_readiness_does_not_own_the_classroom_singleton(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _settings(tmp_path, "general-role.sqlite3").model_dump()
    values.update(
        service_role="general",
        classroom_enabled=True,
        classroom_singleton=False,
    )
    settings = Settings(**values)
    _upgrade(settings, "head", monkeypatch)
    monkeypatch.setattr(
        "wsi_viewer.main.ClassroomSingletonLock.acquire", lambda _: False
    )

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


def test_annotation_query_index_is_required_for_readiness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = _settings(tmp_path, "missing-annotation-index.sqlite3")
    _upgrade(settings, "head", monkeypatch)
    with session_factory(settings)() as database:
        database.execute(text("DROP INDEX ix_annotations_slide_active"))
        database.commit()
    _assert_not_ready(settings)
