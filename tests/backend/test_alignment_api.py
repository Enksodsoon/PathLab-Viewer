from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.identity import ensure_default_owner_membership
from wsi_viewer.main import create_app
from wsi_viewer.models import Job, Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _client(tmp_path: Path, *, enabled: bool) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="alignment-test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        alignment_enabled=enabled,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": ALEMBIC_HEAD})
        admin = User(username="admin", password_hash=hash_password("correct horse battery"))
        database.add(admin)
        database.flush()
        ensure_default_owner_membership(database, admin)
        for index, stain in enumerate(("H&E", "PAS", "CD3"), start=1):
            database.add(
                Slide(
                    id=f"slide-{index}",
                    public_id=f"public-{index}",
                    display_name=stain,
                    original_filename=f"{stain}.ome.tiff",
                    source_bytes=1024,
                    state=SlideState.READY_PRIVATE,
                    stain=stain,
                    sha256=f"sha-{index}",
                    slide_metadata={
                        "width": 1000,
                        "height": 800,
                        "physicalSizeX": 0.25,
                        "physicalSizeY": 0.25,
                    },
                )
            )
        database.commit()
    return TestClient(create_app(settings))


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "username": "admin",
            "password": "correct horse battery",
        },
    )
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_alignment_api_is_hidden_when_disabled(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=False) as client:
        assert client.get("/api/v1/admin/comparison-sets").status_code == 404


def test_admin_creates_set_and_queues_idempotent_pair_jobs(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Any tissue stains",
                "slideIds": ["slide-1", "slide-2", "slide-3"],
                "referenceSlideId": "slide-1",
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["referenceSlideId"] == "slide-1"
        assert [member["stain"] for member in payload["members"]] == ["H&E", "PAS", "CD3"]

        first = client.post(
            f"/api/v1/admin/comparison-sets/{payload['id']}/register", headers=headers
        )
        second = client.post(
            f"/api/v1/admin/comparison-sets/{payload['id']}/register", headers=headers
        )
        assert first.status_code == second.status_code == 202
        assert first.json()["queuedPairs"] == 2
        assert second.json()["queuedPairs"] == 0
        with session_factory(client.app.state.settings)() as database:
            assert database.query(Job).filter(Job.kind == "align").count() == 2


def test_set_rejects_unready_or_missing_reference_members(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        missing = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Bad set",
                "slideIds": ["slide-1", "slide-2"],
                "referenceSlideId": "slide-3",
            },
        )
        assert missing.status_code == 422
        assert missing.json()["detail"]["code"] == "REFERENCE_NOT_MEMBER"
