from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event, insert, select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    Collection,
    Folder,
    Job,
    LibraryShare,
    PublicationGrant,
    ShareSlide,
    Slide,
    User,
)
from wsi_viewer.publication import INDIVIDUAL, SHARE, ensure_grant, remove_grant
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password
from wsi_viewer.storage import StorageLayout


def _client(tmp_path: Path, *, multi_share_enabled: bool = False) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        multi_share_enabled=multi_share_enabled,
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


def _login(client: TestClient) -> str:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return str(response.json()["csrfToken"])


def _headers(client: TestClient) -> dict[str, str]:
    return {"X-CSRF-Token": _login(client)}


def _create_folder(
    client: TestClient,
    headers: dict[str, str],
    name: str,
    parent_id: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v2/admin/folders",
        headers=headers,
        json={"name": name, "parentId": parent_id},
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


def _seed_slide(
    client: TestClient,
    *,
    slide_id: str,
    display_name: str,
    folder_id: str | None = None,
    state: SlideState = SlideState.READY_PRIVATE,
    case_id: str = "",
    organ_site: str = "",
    stain: str = "",
) -> None:
    settings = client.app.state.settings
    with session_factory(settings)() as database:
        database.add(
            Slide(
                id=slide_id,
                public_id=f"public-{slide_id}",
                display_name=display_name,
                original_filename=f"{slide_id}.ome.tiff",
                source_bytes=1024,
                folder_id=folder_id,
                state=state,
                case_id=case_id,
                organ_site=organ_site,
                stain=stain,
            )
        )
        database.commit()


def test_v2_navigation_requires_auth_and_returns_bounded_sections(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        assert client.get("/api/v2/admin/library/navigation").status_code == 401
        _login(client)
        response = client.get("/api/v2/admin/library/navigation")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"counts", "folders", "collections", "savedViews"}
    assert payload["counts"]["all"] == 0
    assert len(response.content) <= 256 * 1024


def test_folders_enforce_normalized_sibling_names_depth_and_cycles(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        root = _create_folder(client, headers, "  Breast  ")
        collision = client.post(
            "/api/v2/admin/folders",
            headers=headers,
            json={"name": "breast", "parentId": None},
        )
        assert collision.status_code == 409
        assert root["name"] == "Breast"

        parent = root
        for level in range(2, 9):
            parent = _create_folder(client, headers, f"Level {level}", parent["id"])
        too_deep = client.post(
            "/api/v2/admin/folders",
            headers=headers,
            json={"name": "Level 9", "parentId": parent["id"]},
        )
        assert too_deep.status_code == 409
        assert too_deep.json()["detail"]["code"] == "FOLDER_DEPTH_EXCEEDED"

        cycle = client.patch(
            f"/api/v2/admin/folders/{root['id']}",
            headers=headers,
            json={"parentId": parent["id"]},
        )
        assert cycle.status_code == 409
        assert cycle.json()["detail"]["code"] == "FOLDER_CYCLE"

        subtree = _create_folder(client, headers, "Subtree")
        subtree_child = _create_folder(client, headers, "Subtree child", subtree["id"])
        _create_folder(
            client, headers, "Subtree grandchild", subtree_child["id"]
        )
        destination = _create_folder(client, headers, "Destination")
        for level in range(2, 8):
            destination = _create_folder(
                client, headers, f"Destination {level}", destination["id"]
            )
        too_tall = client.patch(
            f"/api/v2/admin/folders/{subtree['id']}",
            headers=headers,
            json={"parentId": destination["id"]},
        )
        assert too_tall.status_code == 409
        assert too_tall.json()["detail"]["code"] == "FOLDER_DEPTH_EXCEEDED"


def test_folder_children_are_lazy_and_trash_restore_preserves_subtree(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        root = _create_folder(client, headers, "Organ systems")
        child = _create_folder(client, headers, "Lung", root["id"])
        _seed_slide(client, slide_id="slide-lung", display_name="Lung H&E", folder_id=child["id"])

        navigation = client.get("/api/v2/admin/library/navigation").json()
        assert [folder["id"] for folder in navigation["folders"]] == [root["id"]]
        children = client.get(f"/api/v2/admin/folders/{root['id']}/children").json()
        assert [folder["id"] for folder in children] == [child["id"]]

        trashed = client.post(
            f"/api/v2/admin/folders/{root['id']}/trash", headers=headers
        )
        assert trashed.status_code == 200
        assert client.get(
            "/api/v2/admin/library/items", params={"location": f"folder:{child['id']}"}
        ).json()["items"] == []

        restored = client.post(
            f"/api/v2/admin/folders/{root['id']}/restore", headers=headers
        )
        assert restored.status_code == 200
        items = client.get(
            "/api/v2/admin/library/items", params={"location": f"folder:{child['id']}"}
        ).json()["items"]
        assert [item["id"] for item in items] == ["slide-lung"]


def test_permanent_folder_delete_never_flattens_or_orphans_content(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        occupied = _create_folder(client, headers, "Occupied")
        child = _create_folder(client, headers, "Child", occupied["id"])
        _seed_slide(
            client,
            slide_id="slide-occupied",
            display_name="Occupied",
            folder_id=child["id"],
        )
        client.post(
            f"/api/v2/admin/folders/{occupied['id']}/trash", headers=headers
        )
        blocked = client.delete(
            f"/api/v2/admin/folders/{occupied['id']}", headers=headers
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "FOLDER_NOT_EMPTY"

        empty = _create_folder(client, headers, "Empty")
        empty_child = _create_folder(client, headers, "Nested empty", empty["id"])
        client.post(f"/api/v2/admin/folders/{empty['id']}/trash", headers=headers)
        deleted = client.delete(
            f"/api/v2/admin/folders/{empty['id']}", headers=headers
        )
        assert deleted.status_code == 204
        with session_factory(client.app.state.settings)() as database:
            assert database.get(Folder, empty["id"]) is None
            assert database.get(Folder, empty_child["id"]) is None


def test_collections_are_many_to_many_and_keep_manual_order(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        _seed_slide(client, slide_id="slide-a", display_name="A")
        _seed_slide(client, slide_id="slide-b", display_name="B")
        created = client.post(
            "/api/v2/admin/collections",
            headers=headers,
            json={"name": "Week 5", "description": "Teaching set"},
        )
        assert created.status_code == 201
        collection_id = created.json()["id"]
        added = client.post(
            f"/api/v2/admin/collections/{collection_id}/items",
            headers=headers,
            json={"slideIds": ["slide-b", "slide-a"]},
        )
        assert added.status_code == 200
        assert added.json()["slideIds"] == ["slide-b", "slide-a"]

        items = client.get(
            "/api/v2/admin/library/items",
            params={"location": f"collection:{collection_id}", "sort": "manual"},
        ).json()["items"]
        assert [item["id"] for item in items] == ["slide-b", "slide-a"]


def test_saved_views_reject_unknown_filters_and_drive_item_queries(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        rejected = client.post(
            "/api/v2/admin/saved-views",
            headers=headers,
            json={
                "name": "Unsafe",
                "definition": {"version": 1, "filters": {"rawSql": "DROP TABLE slides"}},
                "sort": "updated_desc",
            },
        )
        assert rejected.status_code == 422

        created = client.post(
            "/api/v2/admin/saved-views",
            headers=headers,
            json={
                "name": "Lung H&E",
                "definition": {
                    "version": 1,
                    "filters": {"organ": ["lung"], "stain": ["H&E"]},
                },
                "sort": "updated_desc",
            },
        )
        assert created.status_code == 201


def test_items_search_filters_cursor_and_payload_are_bounded(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        _login(client)
        for index in range(60):
            _seed_slide(
                client,
                slide_id=f"slide-{index:03}",
                display_name=f"Lung adenocarcinoma {index:03}",
                case_id=f"CASE-{index:03}",
                organ_site="Lung",
                stain="H&E",
            )
        first = client.get(
            "/api/v2/admin/library/items",
            params={"q": "adenocarcinoma", "organ": "Lung", "limit": 48},
        )
        assert first.status_code == 200
        assert len(first.json()["items"]) == 48
        assert first.json()["nextCursor"]
        assert len(first.content) <= 512 * 1024
        assert all(
            "filename" not in item and "adminNotes" not in item
            for item in first.json()["items"]
        )

        second = client.get(
            "/api/v2/admin/library/items",
            params={"q": "adenocarcinoma", "limit": 48, "cursor": first.json()["nextCursor"]},
        )
        assert second.status_code == 200
        assert len(second.json()["items"]) == 12
        assert {
            item["id"] for item in first.json()["items"]
        }.isdisjoint(item["id"] for item in second.json()["items"])

        invalid_limit = client.get("/api/v2/admin/library/items", params={"limit": 101})
        assert invalid_limit.status_code == 422


def test_batch_mutations_are_limited_and_patch_changed_slides(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "GI")
        for index in range(3):
            _seed_slide(client, slide_id=f"slide-{index}", display_name=f"Slide {index}")
        moved = client.post(
            "/api/v2/admin/slides/batch-move",
            headers=headers,
            json={"slideIds": ["slide-0", "slide-1"], "folderId": folder["id"]},
        )
        assert moved.status_code == 200
        assert {item["folderId"] for item in moved.json()["items"]} == {folder["id"]}

        rejected = client.post(
            "/api/v2/admin/slides/batch-move",
            headers=headers,
            json={"slideIds": [f"slide-{index}" for index in range(51)], "folderId": None},
        )
        assert rejected.status_code == 422


def test_slide_trash_restore_and_targeted_status(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Breast")
        _seed_slide(
            client,
            slide_id="slide-processing",
            display_name="Processing",
            folder_id=folder["id"],
            state=SlideState.CONVERTING,
        )
        trashed = client.post(
            "/api/v2/admin/slides/slide-processing/trash", headers=headers
        )
        assert trashed.status_code == 200
        assert trashed.json()["trashedAt"]
        restored = client.post(
            "/api/v2/admin/slides/slide-processing/restore", headers=headers
        )
        assert restored.status_code == 200
        assert restored.json()["folderId"] == folder["id"]

        statuses = client.get(
            "/api/v2/admin/slides/status", params={"ids": "slide-processing"}
        )
        assert statuses.status_code == 200
        assert statuses.json() == {
            "items": [{"id": "slide-processing", "state": "converting", "errorCode": None}]
        }
        too_many = client.get(
            "/api/v2/admin/slides/status",
            params={"ids": ",".join(f"slide-{index}" for index in range(101))},
        )
        assert too_many.status_code == 422


def test_permanent_delete_is_explicit_and_uses_existing_worker(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        headers = _headers(client)
        _seed_slide(
            client,
            slide_id="slide-delete",
            display_name="Delete",
            state=SlideState.READY_PRIVATE,
        )
        trashed = client.post(
            "/api/v2/admin/slides/slide-delete/trash", headers=headers
        )
        assert trashed.status_code == 200
        deleted = client.delete(
            "/api/v2/admin/slides/slide-delete", headers=headers
        )
        assert deleted.status_code == 202
        assert deleted.json()["state"] == "deleting"
        with session_factory(client.app.state.settings)() as database:
            assert database.scalar(
                database.query(Job).filter(
                    Job.slide_id == "slide-delete", Job.kind == "delete"
                ).statement
            )


def test_multi_share_activation_is_blocked_without_privacy_scanner(tmp_path: Path) -> None:
    with _client(tmp_path, multi_share_enabled=False) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Teaching")
        response = client.post(
            "/api/v2/admin/shares",
            headers=headers,
            json={"targetType": "folder", "targetId": folder["id"]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "PRIVACY_SCANNER_REQUIRED"


def _seed_share_ready_slide(
    client: TestClient,
    *,
    slide_id: str,
    folder_id: str | None = None,
) -> None:
    settings = client.app.state.settings
    with session_factory(settings)() as database:
        slide = Slide(
            id=slide_id,
            public_id=f"public-{slide_id}",
            display_name=f"Safe {slide_id}",
            original_filename=f"private-{slide_id}.ome.tiff",
            source_bytes=1024,
            folder_id=folder_id,
            state=SlideState.READY_PRIVATE,
            organ_site="Colon",
            stain="H&E",
            diagnosis="Adenocarcinoma",
            teaching_note="Safe teaching note",
            admin_notes="must stay private",
            privacy_status="passed",
            privacy_scanned_at=datetime.now(UTC).replace(tzinfo=None),
            thumbnail_filename="thumbnail.jpg",
        )
        database.add(slide)
        database.commit()
        derivative = StorageLayout(settings.data_root).for_slide(slide.id).private_derivative
        (derivative / "slide_files" / "0").mkdir(parents=True)
        (derivative / "slide.dzi").write_text("<Image />", encoding="utf-8")
        (derivative / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"tile")
        (derivative / "thumbnail.jpg").write_bytes(b"thumbnail")


def test_share_preview_scopes_folders_and_creation_requires_reviewed_slides(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        root = _create_folder(client, headers, "GI")
        child = _create_folder(client, headers, "Colon", root["id"])
        _seed_share_ready_slide(client, slide_id="direct", folder_id=root["id"])
        _seed_share_ready_slide(client, slide_id="descendant", folder_id=child["id"])

        direct = client.get(
            "/api/v2/admin/shares/preview",
            params={
                "targetType": "folder",
                "targetId": root["id"],
                "includeDescendants": False,
            },
        )
        assert direct.status_code == 200
        assert [item["displayName"] for item in direct.json()["included"]] == ["Safe direct"]

        descendant = client.get(
            "/api/v2/admin/shares/preview",
            params={
                "targetType": "folder",
                "targetId": root["id"],
                "includeDescendants": True,
            },
        )
        assert {item["displayName"] for item in descendant.json()["included"]} == {
            "Safe direct",
            "Safe descendant",
        }

        unconfirmed = client.post(
            "/api/v2/admin/shares",
            headers=headers,
            json={
                "targetType": "folder",
                "targetId": root["id"],
                "includeDescendants": True,
                "deidentifiedConfirmed": False,
            },
        )
        assert unconfirmed.status_code == 422

        created = client.post(
            "/api/v2/admin/shares",
            headers=headers,
            json={
                "targetType": "folder",
                "targetId": root["id"],
                "includeDescendants": True,
                "autoIncludeNew": False,
                "deidentifiedConfirmed": True,
                "slideIds": ["descendant", "direct"],
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["autoIncludeNew"] is False
        assert created.json()["includedCount"] == 2

        manifest = client.get(f"/api/v2/public/folders/{created.json()['publicId']}")
        assert manifest.status_code == 200
        payload = manifest.json()
        assert [item["displayName"] for item in payload["slides"]] == [
            "Safe descendant",
            "Safe direct",
        ]
        assert all(
            set(item)
            == {
                "position",
                "displayName",
                "organSite",
                "stain",
                "diagnosis",
                "tags",
                "teachingNote",
                "thumbnailUrl",
                "tileSource",
                "scale",
            }
            for item in payload["slides"]
        )
        public_thumbnail = client.get(payload["slides"][0]["thumbnailUrl"])
        assert public_thumbnail.status_code == 200
        assert public_thumbnail.content == b"thumbnail"
        assert public_thumbnail.headers["cache-control"] == "private, no-store"
        serialized = manifest.text
        for private_value in [
            "private-descendant.ome.tiff",
            "must stay private",
            "sourceBytes",
            "adminNotes",
        ]:
            assert private_value not in serialized


def test_collection_share_rotation_expiration_and_revoke_use_generic_failures(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        _seed_share_ready_slide(client, slide_id="collection-slide")
        created_collection = client.post(
            "/api/v2/admin/collections",
            headers=headers,
            json={"name": "Core set"},
        ).json()
        client.post(
            f"/api/v2/admin/collections/{created_collection['id']}/items",
            headers=headers,
            json={"slideIds": ["collection-slide"]},
        )
        created = client.post(
            "/api/v2/admin/shares",
            headers=headers,
            json={
                "targetType": "collection",
                "targetId": created_collection["id"],
                "deidentifiedConfirmed": True,
            },
        )
        assert created.status_code == 201
        share_id = created.json()["id"]
        old_public_id = created.json()["publicId"]

        rotated = client.post(
            f"/api/v2/admin/shares/{share_id}/rotate",
            headers=headers,
        )
        assert rotated.status_code == 200
        assert rotated.json()["publicId"] != old_public_id
        assert client.get(f"/api/v2/public/collections/{old_public_id}").status_code == 404
        new_manifest = client.get(
            f"/api/v2/public/collections/{rotated.json()['publicId']}"
        )
        assert new_manifest.status_code == 200
        new_tile_source = new_manifest.json()["slides"][0]["tileSource"]
        old_tile_source = new_tile_source.replace(rotated.json()["publicId"], old_public_id)
        assert client.get(old_tile_source).status_code == 404
        assert client.get(new_tile_source).status_code == 200

        revoked = client.delete(
            f"/api/v2/admin/shares/{share_id}",
            headers=headers,
        )
        assert revoked.status_code == 204
        missing = client.get(
            f"/api/v2/public/collections/{rotated.json()['publicId']}"
        )
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "SHARE_NOT_FOUND"
        assert client.get("/api/v2/public/collections/not-a-share").json() == missing.json()
        assert client.get(new_tile_source).status_code == 404

        settings = client.app.state.settings
        with session_factory(settings)() as database:
            assert database.query(ShareSlide).count() == 1
            assert database.query(PublicationGrant).count() == 0
            expired = LibraryShare(
                target_type="collection",
                target_id=created_collection["id"],
                privacy_status="passed",
                confirmed_at=datetime.now(UTC).replace(tzinfo=None),
                expires_at=(datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None),
            )
            database.add(expired)
            database.commit()
            expired_public_id = expired.public_id
        assert client.get(
            f"/api/v2/public/collections/{expired_public_id}"
        ).status_code == 404


def test_routine_move_never_auto_publishes_into_shared_folder(tmp_path: Path) -> None:
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Auto scope")
        _seed_share_ready_slide(client, slide_id="already-reviewed", folder_id=folder["id"])
        created = client.post(
            "/api/v2/admin/shares",
            headers=headers,
            json={
                "targetType": "folder",
                "targetId": folder["id"],
                "autoIncludeNew": True,
                "deidentifiedConfirmed": True,
            },
        )
        assert created.status_code == 201
        _seed_share_ready_slide(client, slide_id="routine-move")

        moved = client.post(
            "/api/v2/admin/slides/batch-move",
            headers=headers,
            json={"slideIds": ["routine-move"], "folderId": folder["id"]},
        )
        assert moved.status_code == 200

        with session_factory(client.app.state.settings)() as database:
            grants = database.scalars(
                select(PublicationGrant).where(
                    PublicationGrant.slide_id == "routine-move",
                    PublicationGrant.source_type == SHARE,
                )
            ).all()
            assert grants == []
            share = database.get(LibraryShare, created.json()["id"])
            assert share is not None
            memberships = database.scalars(
                select(ShareSlide).where(ShareSlide.share_id == share.id)
            ).all()
            assert [membership.slide_id for membership in memberships] == [
                "already-reviewed"
            ]


def test_publication_alias_and_thumbnail_remain_until_final_grant_is_removed(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'grants.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    storage = StorageLayout(settings.data_root)
    with session_factory(settings)() as database:
        slide = Slide(
            id="slide-grants",
            public_id="stable-public-grants",
            display_name="Safe title",
            original_filename="private.ome.tiff",
            source_bytes=10,
            state=SlideState.READY_PRIVATE,
            thumbnail_filename="thumbnail.jpg",
        )
        database.add(slide)
        database.commit()
        derivative = storage.for_slide(slide.id).private_derivative
        (derivative / "slide_files" / "0").mkdir(parents=True)
        (derivative / "slide.dzi").write_text("<Image />", encoding="utf-8")
        (derivative / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"tile")
        (derivative / "thumbnail.jpg").write_bytes(b"thumbnail")

        ensure_grant(database, storage, slide, INDIVIDUAL, slide.id)
        ensure_grant(database, storage, slide, SHARE, "share-1")
        database.commit()
        public = storage.public_for(slide.public_id)
        assert (public / "thumbnail.jpg").read_bytes() == b"thumbnail"
        assert database.query(PublicationGrant).count() == 2

        remove_grant(database, storage, slide, INDIVIDUAL, slide.id)
        database.commit()
        assert public.exists()
        assert slide.state is SlideState.PUBLISHED

        remove_grant(database, storage, slide, SHARE, "share-1")
        database.commit()
        assert not public.exists()
        assert slide.state is SlideState.READY_PRIVATE


def test_authenticated_thumbnail_uses_private_cache_and_etag(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        settings = client.app.state.settings
        _seed_slide(client, slide_id="slide-thumb", display_name="Thumbnail")
        with session_factory(settings)() as database:
            slide = database.get(Slide, "slide-thumb")
            assert slide is not None
            slide.thumbnail_filename = "thumbnail.jpg"
            database.commit()
        thumbnail = settings.data_root / "private" / "slide-thumb" / "thumbnail.jpg"
        thumbnail.parent.mkdir(parents=True)
        thumbnail.write_bytes(b"thumbnail")

        assert (
            client.get("/api/v2/admin/slides/slide-thumb/thumbnail").status_code
            == 401
        )
        _login(client)
        response = client.get("/api/v2/admin/slides/slide-thumb/thumbnail")

        assert response.status_code == 200
        assert response.content == b"thumbnail"
        assert response.headers["cache-control"] == "private, max-age=3600"
        assert response.headers["etag"].startswith('"')


def test_synthetic_library_contract_is_query_payload_and_filesystem_bounded(
    tmp_path: Path, monkeypatch
) -> None:
    with _client(tmp_path) as client:
        settings = client.app.state.settings
        roots = [
            {
                "id": f"folder-{index:04}",
                "name": f"Root {index:02}",
                "normalized_name": f"root {index:02}",
                "parent_id": None,
            }
            for index in range(20)
        ]
        children = [
            {
                "id": f"folder-{index:04}",
                "name": f"Child {index:04}",
                "normalized_name": f"child {index:04}",
                "parent_id": f"folder-{index % 20:04}",
            }
            for index in range(20, 2000)
        ]
        collections = [
            {
                "id": f"collection-{index:04}",
                "name": f"Collection {index:04}",
                "normalized_name": f"collection {index:04}",
            }
            for index in range(500)
        ]
        slides = [
            {
                "id": f"scale-slide-{index:05}",
                "public_id": f"scale-public-{index:05}",
                "display_name": f"Lung teaching slide {index:05}",
                "original_filename": f"private-{index:05}.ome.tiff",
                "source_bytes": 1024,
                "folder_id": f"folder-{20 + index % 1980:04}",
                "state": SlideState.READY_PRIVATE,
                "organ_site": "Lung",
                "stain": "H&E",
            }
            for index in range(10_000)
        ]
        with session_factory(settings)() as database:
            database.execute(insert(Folder), roots + children)
            database.execute(insert(Collection), collections)
            database.execute(insert(Slide), slides)
            database.commit()
        _login(client)

        executed: list[str] = []

        def count_statement(
            _connection: object,
            _cursor: object,
            statement: str,
            _parameters: object,
            _context: object,
            _many: object,
        ) -> None:
            executed.append(statement)

        engine = engine_for(settings)
        event.listen(engine, "before_cursor_execute", count_statement)
        monkeypatch.setattr(
            Path,
            "rglob",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("library request walked filesystem")
            ),
        )
        try:
            navigation = client.get("/api/v2/admin/library/navigation")
            navigation_queries = len(executed)
            executed.clear()
            items = client.get(
                "/api/v2/admin/library/items",
                params={"q": "teaching", "organ": "Lung", "limit": 48},
            )
            item_queries = len(executed)
        finally:
            event.remove(engine, "before_cursor_execute", count_statement)

        assert navigation.status_code == 200
        assert len(navigation.content) <= 256 * 1024
        assert navigation_queries <= 10
        assert items.status_code == 200
        assert len(items.json()["items"]) == 48
        assert len(items.content) <= 512 * 1024
        assert item_queries <= 7
