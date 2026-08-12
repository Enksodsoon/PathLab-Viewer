from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.main import create_app
from wsi_viewer.models import DesktopSyncEvent, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _client(tmp_path: Path) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'sync.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="desktop-sync-test-secret-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        annotations_enabled=True,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.commit()
    return TestClient(create_app(settings))


def _pair(client: TestClient) -> dict[str, str]:
    login = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": "correct horse battery"},
    )
    csrf = login.json()["csrfToken"]
    pairing = client.post(
        "/api/v1/desktop/pairings",
        json={"deviceName": "PathLab Forge sync test"},
    ).json()
    approved = client.post(
        "/api/v1/desktop/pairings/approve",
        headers={"X-CSRF-Token": csrf},
        json={"userCode": pairing["userCode"]},
    )
    assert approved.status_code == 204
    exchanged = client.post(
        "/api/v1/desktop/pairings/exchange",
        json={
            "deviceCode": pairing["deviceCode"],
            "deviceSecret": pairing["deviceSecret"],
        },
    )
    assert exchanged.status_code == 200
    return exchanged.json()


def test_new_pairing_receives_private_sync_scopes(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)

    assert {
        "library:read",
        "slides:offline:read",
        "library:sync",
    } <= set(exchanged["scopes"])


def test_sync_event_sequence_is_monotonic(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'events.sqlite3'}",
        data_root=tmp_path / "events-data",
        secret_key="desktop-sync-event-test-long-enough",
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        first = DesktopSyncEvent(
            entity_type="slide", entity_id="a", operation="upsert", revision=1
        )
        second = DesktopSyncEvent(
            entity_type="slide", entity_id="b", operation="upsert", revision=1
        )
        database.add_all([first, second])
        database.commit()

        assert first.sequence is not None
        assert second.sequence > first.sequence
