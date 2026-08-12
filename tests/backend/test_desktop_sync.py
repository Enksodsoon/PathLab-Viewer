from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import DesktopCredential, DesktopSyncEvent, Folder, Slide, User
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


def _authorization(exchanged: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {exchanged['accessToken']}"}


def _ready_slide(client: TestClient, *, name: str = "Remote slide") -> Slide:
    settings = client.app.state.settings
    with session_factory(settings)() as database:
        folder = Folder(name="Remote folder", normalized_name="remote folder")
        slide = Slide(
            display_name=name,
            original_filename="private-source.ome.tif",
            source_bytes=1024,
            state=SlideState.READY_PRIVATE,
            render_mode="ome_dynamic",
            folder_id=None,
            sha256="a" * 64,
            annotation_version=3,
        )
        database.add_all([folder, slide])
        database.flush()
        slide.folder_id = folder.id
        database.commit()
        database.refresh(slide)
        database.expunge(slide)
        return slide


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


def test_desktop_library_is_bounded_private_and_omits_original_filename(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide(client)
        response = client.get(
            "/api/v2/desktop/library/items?limit=1",
            headers=_authorization(exchanged),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == "desktop-sync/v1"
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == slide.id
    assert "originalFilename" not in body["items"][0]
    assert body["items"][0]["annotationRevision"] == 3
    assert len(body["folders"]) == 1


def test_desktop_library_rejects_legacy_credential_without_sync_scope(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            credential = database.query(DesktopCredential).one()
            credential.scopes = ["desktop:ingest", "slides:private:read"]
            database.commit()
        response = client.get(
            "/api/v2/desktop/library/items",
            headers=_authorization(exchanged),
        )

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "DESKTOP_SCOPE_REQUIRED"


def test_changes_resume_after_durable_cursor(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide(client)
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            database.add_all(
                [
                    DesktopSyncEvent(
                        entity_type="slide",
                        entity_id=slide.id,
                        operation="upsert",
                        revision=11,
                    ),
                    DesktopSyncEvent(
                        entity_type="annotation",
                        entity_id=slide.id,
                        operation="upsert",
                        revision=12,
                    ),
                ]
            )
            database.commit()
        first = client.get(
            "/api/v2/desktop/library/changes?after=0&limit=1",
            headers=_authorization(exchanged),
        )
        second = client.get(
            f"/api/v2/desktop/library/changes?after={first.json().get('nextCursor', 0)}",
            headers=_authorization(exchanged),
        )

    assert first.status_code == 200
    assert len(first.json()["changes"]) == 1
    assert second.status_code == 200
    assert all(
        change["sequence"] > int(first.json()["nextCursor"])
        for change in second.json()["changes"]
    )


def test_admin_metadata_change_records_desktop_change_event(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide(client)
        login = client.post(
            "/api/v1/auth/session",
            json={"username": "admin", "password": "correct horse battery"},
        )
        changed = client.post(
            "/api/v2/admin/slides/batch-metadata",
            headers={"X-CSRF-Token": login.json()["csrfToken"]},
            json={"slideIds": [slide.id], "displayName": "Changed remotely"},
        )
        changes = client.get(
            "/api/v2/desktop/library/changes?after=0",
            headers=_authorization(exchanged),
        )

    assert changed.status_code == 200
    assert any(
        event["entityType"] == "slide"
        and event["entityId"] == slide.id
        and event["operation"] == "upsert"
        for event in changes.json()["changes"]
    )
