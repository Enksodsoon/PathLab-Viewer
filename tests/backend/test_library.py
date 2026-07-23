import os
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import Folder, PublicationGrant, Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _client(tmp_path: Path) -> tuple[TestClient, Settings]:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
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
    return TestClient(create_app(settings)), settings


def _login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def _folder(client: TestClient, headers: dict[str, str], name: str, parent_id: str | None = None):
    response = client.post(
        "/api/v1/admin/folders",
        headers=headers,
        json={"name": name, "parentId": parent_id},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _ready_slide(settings: Settings, folder_id: str, name: str = "Teaching slide") -> Slide:
    with session_factory(settings)() as database:
        slide = Slide(
            display_name=name,
            original_filename="private.ome.tif",
            source_bytes=100,
            derivative_bytes=20,
            derivative_file_count=2,
            state=SlideState.READY_PRIVATE,
            folder_id=folder_id,
            slide_metadata={"width": 1000, "height": 500, "physicalSizeX": 0.5},
        )
        database.add(slide)
        database.commit()
        slide_id = slide.id
    derivative = settings.data_root / "private" / slide_id
    (derivative / "slide_files" / "0").mkdir(parents=True)
    (derivative / "slide.dzi").write_text("<Image />", encoding="utf-8")
    (derivative / "slide_files" / "0" / "0_0.jpg").write_bytes(b"jpeg")
    with session_factory(settings)() as database:
        return database.get(Slide, slide_id)  # type: ignore[return-value]


def test_folder_depth_duplicate_and_cycle_validation(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    with client:
        headers = _login(client)
        root = _folder(client, headers, " Histology ")
        assert root["name"] == "Histology"
        assert client.post(
            "/api/v1/admin/folders", headers=headers, json={"name": "HISTOLOGY"}
        ).status_code == 409
        level_two = _folder(client, headers, "Level two", root["id"])
        level_three = _folder(client, headers, "Level three", level_two["id"])
        too_deep = client.post(
            "/api/v1/admin/folders",
            headers=headers,
            json={"name": "Level four", "parentId": level_three["id"]},
        )
        assert too_deep.status_code == 409
        cycle = client.patch(
            f"/api/v1/admin/folders/{root['id']}",
            headers=headers,
            json={"parentId": level_three["id"]},
        )
        assert cycle.status_code == 409


def test_library_metadata_and_storage_summary_are_set_based(tmp_path: Path) -> None:
    client, settings = _client(tmp_path)
    with client:
        headers = _login(client)
        folder = _folder(client, headers, "Cases")
        slide = _ready_slide(settings, folder["id"])
        response = client.patch(
            f"/api/v1/admin/slides/{slide.id}",
            headers=headers,
            json={
                "displayName": "  Colon H&E  ",
                "description": "Teaching description",
                "stain": "H&E",
                "organSite": "Colon",
                "tags": [" GI ", "gi", "normal"],
                "teachingNote": "Look at crypts",
                "adminNotes": "private",
                "sortOrder": 2,
            },
        )
        assert response.status_code == 200, response.text
        library = client.get("/api/v1/admin/library").json()
        stored = next(item for item in library["slides"] if item["id"] == slide.id)
        assert stored["displayName"] == "Colon H&E"
        assert stored["tags"] == ["GI", "normal"]
        assert stored["adminNotes"] == "private"
        assert library["storage"]["accountedBytes"] == 120
        assert library["storage"]["derivativeBytes"] == 20


def test_folder_share_uses_hardlinks_and_public_manifest_is_private_safe(
    tmp_path: Path,
) -> None:
    client, settings = _client(tmp_path)
    with client:
        headers = _login(client)
        folder = _folder(client, headers, "GI", None)
        slide = _ready_slide(settings, folder["id"])
        response = client.post(
            f"/api/v1/admin/folders/{folder['id']}/share", headers=headers
        )
        assert response.status_code == 200, response.text
        share = response.json()
        manifest = client.get(f"/api/v1/public/folders/{share['publicId']}")
        assert manifest.status_code == 200
        body = manifest.json()
        assert body["folderPublicId"] == share["publicId"]
        assert body["slides"][0]["publicId"] == slide.public_id
        serialized = str(body)
        assert slide.id not in serialized
        assert "private.ome.tif" not in serialized
        assert "adminNotes" not in serialized
        private_tile = settings.data_root / "private" / slide.id / "slide_files" / "0" / "0_0.jpg"
        public_tile = (
            settings.data_root
            / "public"
            / slide.public_id
            / "slide_files"
            / "0"
            / "0_0.jpg"
        )
        assert os.stat(private_tile).st_ino == os.stat(public_tile).st_ino


def test_grants_preserve_individual_link_until_last_grant_removed(tmp_path: Path) -> None:
    client, settings = _client(tmp_path)
    with client:
        headers = _login(client)
        folder = _folder(client, headers, "Shared")
        slide = _ready_slide(settings, folder["id"])
        assert client.post(
            f"/api/v1/admin/slides/{slide.id}/publish", headers=headers
        ).status_code == 200
        share = client.post(
            f"/api/v1/admin/folders/{folder['id']}/share", headers=headers
        ).json()
        assert client.post(
            f"/api/v1/admin/slides/{slide.id}/unpublish", headers=headers
        ).json()["state"] == "published"
        assert client.get(f"/api/v1/public/slides/{slide.public_id}").status_code == 200
        assert client.delete(
            f"/api/v1/admin/folders/{folder['id']}/share", headers=headers
        ).status_code == 204
        assert client.get(f"/api/v1/public/folders/{share['publicId']}").status_code == 404
        assert client.get(f"/api/v1/public/slides/{slide.public_id}").status_code == 404


def test_folder_delete_is_non_destructive_and_reparents_children(tmp_path: Path) -> None:
    client, settings = _client(tmp_path)
    with client:
        headers = _login(client)
        root = _folder(client, headers, "Root")
        child = _folder(client, headers, "Child", root["id"])
        slide = _ready_slide(settings, root["id"])
        original = settings.data_root / "originals" / slide.id / "source.ome.tif"
        original.parent.mkdir(parents=True)
        original.write_bytes(b"original")
        assert client.delete(
            f"/api/v1/admin/folders/{root['id']}", headers=headers
        ).status_code == 204
        with session_factory(settings)() as database:
            stored_slide = database.get(Slide, slide.id)
            stored_child = database.get(Folder, child["id"])
            assert stored_slide is not None and stored_slide.folder_id is None
            assert stored_child is not None and stored_child.parent_id is None
            assert database.scalars(
                select(PublicationGrant).where(PublicationGrant.slide_id == slide.id)
            ).all() == []
        assert original.exists()
        assert (settings.data_root / "private" / slide.id / "slide.dzi").exists()
