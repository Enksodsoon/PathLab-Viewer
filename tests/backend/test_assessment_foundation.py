from pathlib import Path

from fastapi.testclient import TestClient
from wsi_viewer.config import Settings
from wsi_viewer.main import create_app


def test_disabled_assessment_routes_are_not_registered(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            service_role="all",
            assessment_enabled=False,
            database_url=f"sqlite:///{tmp_path / 'disabled.sqlite3'}",
            data_root=tmp_path / "disabled",
        )
    )

    paths = {getattr(route, "path", "") for route in app.routes}

    assert not any(path.startswith("/api/v2/assessment") for path in paths)
    assert not any(path.startswith("/api/v2/admin/assessment") for path in paths)


def test_enabled_assessment_metadata_is_answer_free_and_no_store(tmp_path: Path) -> None:
    app = create_app(
        Settings(
            _env_file=None,
            service_role="assessment",
            assessment_enabled=True,
            database_url=f"sqlite:///{tmp_path / 'enabled.sqlite3'}",
            data_root=tmp_path / "enabled",
        )
    )

    with TestClient(app) as client:
        response = client.get("/api/v2/assessment/administrations/not-found")

    assert response.status_code == 404
    assert response.json() == {"detail": {"code": "ASSESSMENT_NOT_FOUND"}}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
