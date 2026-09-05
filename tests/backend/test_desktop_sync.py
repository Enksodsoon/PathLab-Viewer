import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.identity import ensure_default_owner_membership
from wsi_viewer.main import create_app
from wsi_viewer.models import DesktopCredential, DesktopSyncEvent, Folder, Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password
from wsi_viewer.storage import StorageLayout


def test_desktop_sync_contract_fixtures_are_valid_and_bounded() -> None:
    root = Path(__file__).parents[1] / "fixtures" / "desktop_sync_v1"
    library = json.loads((root / "library-page.json").read_text(encoding="utf-8"))
    changes = json.loads((root / "change-page.json").read_text(encoding="utf-8"))
    assert library["schema"] == "desktop-sync/v1"
    assert len(library["items"]) <= 100
    assert changes["schema"] == "desktop-sync/v1"
    assert len(changes["changes"]) <= 500


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
        admin = User(username="admin", password_hash=hash_password("correct horse battery"))
        database.add(admin)
        database.flush()
        ensure_default_owner_membership(database, admin)
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


def _ready_slide_with_content(client: TestClient, payload: bytes) -> Slide:
    slide = _ready_slide(client, name="Offline slide")
    settings = client.app.state.settings
    digest = hashlib.sha256(payload).hexdigest()
    with session_factory(settings)() as database:
        stored = database.get(Slide, slide.id)
        assert stored is not None
        stored.source_bytes = len(payload)
        stored.sha256 = digest
        database.commit()
        database.refresh(stored)
        database.expunge(stored)
        slide = stored
    target = StorageLayout(settings.data_root).for_slide(slide.id).original
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
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


def test_offline_download_resumes_exact_range_with_persisted_digest(tmp_path: Path) -> None:
    payload = b"0123456789"
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide_with_content(client, payload)
        response = client.get(
            f"/api/v2/desktop/slides/{slide.id}/content",
            headers={**_authorization(exchanged), "Range": "bytes=4-"},
        )

    assert response.status_code == 206
    assert response.content == payload[4:]
    assert response.headers["content-range"] == "bytes 4-9/10"
    assert response.headers["x-pathlab-sha256"] == hashlib.sha256(payload).hexdigest()


def test_desktop_patch_rejects_stale_revision_without_mutating_slide(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide(client)
        response = client.patch(
            f"/api/v2/desktop/slides/{slide.id}",
            headers=_authorization(exchanged),
            json={
                "expectedMetadataRevision": 1,
                "expectedFolderRevision": 1,
                "displayName": "Local edit",
            },
        )
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            stored = database.get(Slide, slide.id)
            assert stored is not None
            stored_name = stored.display_name

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "DESKTOP_SYNC_CONFLICT"
    assert stored_name == "Remote slide"


def test_desktop_patch_updates_private_metadata_at_expected_revision(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide(client)
        listed = client.get(
            "/api/v2/desktop/library/items",
            headers=_authorization(exchanged),
        ).json()["items"][0]
        response = client.patch(
            f"/api/v2/desktop/slides/{slide.id}",
            headers=_authorization(exchanged),
            json={
                "expectedMetadataRevision": listed["metadataRevision"],
                "expectedFolderRevision": listed["folderRevision"],
                "displayName": "Local edit",
                "caseId": "CASE-42",
            },
        )

    assert response.status_code == 200
    assert response.json()["displayName"] == "Local edit"
    assert response.json()["caseId"] == "CASE-42"
    assert response.json()["metadataRevision"] > listed["metadataRevision"]


def test_offline_head_exposes_exact_length_digest_and_private_cache_policy(
    tmp_path: Path,
) -> None:
    payload = b"verified-offline-content"
    with _client(tmp_path) as client:
        exchanged = _pair(client)
        slide = _ready_slide_with_content(client, payload)
        response = client.head(
            f"/api/v2/desktop/slides/{slide.id}/content",
            headers=_authorization(exchanged),
        )

    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(payload))
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["cache-control"] == "private, no-store"
