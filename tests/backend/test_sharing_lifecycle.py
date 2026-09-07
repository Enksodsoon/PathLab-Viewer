from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import wsi_viewer.sharing as sharing
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_library_v2 import (
    _client,
    _create_folder,
    _headers,
    _seed_share_ready_slide,
)
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import LibraryShare, PublicationGrant, Slide
from wsi_viewer.publication import INDIVIDUAL, ensure_grant
from wsi_viewer.storage import StorageLayout


def _share(client, headers, target_id, *, kind="folder", **extra):
    return client.post(
        "/api/v2/admin/shares",
        headers=headers,
        json={
            "targetType": kind,
            "targetId": target_id,
            "deidentifiedConfirmed": True,
            **extra,
        },
    )


@pytest.mark.parametrize("action", ["trash", "unpublish"])
def test_removed_member_never_rebinds_position_or_returns_after_restore(tmp_path, action):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Shared")
        for slide_id in ["first", "second"]:
            _seed_share_ready_slide(client, slide_id=slide_id, folder_id=folder["id"])
        created = _share(client, headers, folder["id"], slideIds=["first", "second"])
        assert created.status_code == 201
        url = f"/api/v2/public/folders/{created.json()['publicId']}"
        before = client.get(url).json()["slides"]
        endpoint = (
            "/api/v2/admin/slides/first/trash"
            if action == "trash"
            else "/api/v1/admin/slides/first/unpublish"
        )
        assert client.post(endpoint, headers=headers).status_code == 200
        after = client.get(url).json()["slides"]
        assert [(s["position"], s["displayName"]) for s in after] == [(1, "Safe second")]
        assert client.get(before[0]["tileSource"]).status_code == 404
        assert client.get(before[1]["tileSource"]).status_code == 200
        if action == "trash":
            assert (
                client.post("/api/v2/admin/slides/first/restore", headers=headers).status_code
                == 200
            )
        with session_factory(client.app.state.settings)() as database:
            slide = database.get(Slide, "first")
            assert slide.state == SlideState.READY_PRIVATE
            assert (
                database.scalars(
                    select(PublicationGrant).where(PublicationGrant.slide_id == slide.id)
                ).all()
                == []
            )
            ensure_grant(
                database,
                StorageLayout(client.app.state.settings.data_root),
                slide,
                INDIVIDUAL,
                slide.id,
            )
            database.commit()
        assert client.get(before[0]["tileSource"]).status_code == 404
        assert len(client.get(url).json()["slides"]) == 1
        # Startup reconciliation must preserve the same gap.
        from wsi_viewer.storage_accounting import reconcile_storage

        reconcile_storage(
            session_factory(client.app.state.settings),
            StorageLayout(client.app.state.settings.data_root),
        )
        assert client.get(before[0]["tileSource"]).status_code == 404
        assert client.get(before[1]["tileSource"]).status_code == 200


def test_delete_active_shared_collection_is_rejected(tmp_path):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        collection = client.post(
            "/api/v2/admin/collections", headers=headers, json={"name": "Shared"}
        ).json()
        _seed_share_ready_slide(client, slide_id="slide")
        client.post(
            f"/api/v2/admin/collections/{collection['id']}/items",
            headers=headers,
            json={"slideIds": ["slide"]},
        )
        created = _share(client, headers, collection["id"], kind="collection")
        assert created.status_code == 201
        response = client.delete(f"/api/v2/admin/collections/{collection['id']}", headers=headers)
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "SHARE_ACTIVE"
        assert (
            client.get(f"/api/v2/public/collections/{created.json()['publicId']}").status_code
            == 200
        )


def test_new_share_excludes_trashed_subtrees_but_existing_snapshot_survives_folder_trash(tmp_path):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        root = _create_folder(client, headers, "Root")
        child = _create_folder(client, headers, "Trash", root["id"])
        sibling = _create_folder(client, headers, "Live", root["id"])
        _create_folder(client, headers, "Empty", sibling["id"])
        _seed_share_ready_slide(client, slide_id="hidden", folder_id=child["id"])
        _seed_share_ready_slide(client, slide_id="live", folder_id=sibling["id"])
        assert (
            client.post(f"/api/v2/admin/folders/{child['id']}/trash", headers=headers).status_code
            == 200
        )
        created = _share(client, headers, root["id"], includeDescendants=True)
        assert created.status_code == 201, created.text
        url = f"/api/v2/public/folders/{created.json()['publicId']}"
        before = client.get(url).json()
        assert [s["displayName"] for s in before["slides"]] == ["Safe live"]
        assert before["folders"] == [["Live"], ["Live", "Empty"]]
        assert (
            client.post(f"/api/v2/admin/folders/{root['id']}/trash", headers=headers).status_code
            == 200
        )
        assert client.get(url).json() == before


def test_expired_share_can_be_replaced(tmp_path):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Shared")
        _seed_share_ready_slide(client, slide_id="slide", folder_id=folder["id"])
        first = _share(client, headers, folder["id"])
        with session_factory(client.app.state.settings)() as database:
            share = database.get(LibraryShare, first.json()["id"])
            share.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            database.commit()
        second = _share(client, headers, folder["id"])
        assert second.status_code == 201, second.text
        old_url = f"/api/v2/public/folders/{first.json()['publicId']}"
        assert client.get(old_url).status_code == 404
        assert client.get(f"{old_url}/slides/0/tiles/slide.dzi").status_code == 404


@pytest.mark.parametrize("operation", ["activate", "rotate"])
def test_manifest_write_failure_is_retryable_and_preserves_old_delivery(
    tmp_path, monkeypatch, operation
):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Shared")
        _seed_share_ready_slide(client, slide_id="slide", folder_id=folder["id"])
        if operation == "rotate":
            first = _share(client, headers, folder["id"]).json()
            old_url = f"/api/v2/public/folders/{first['publicId']}"
        original = sharing.os.replace

        def fail(source, target):
            if Path(target).suffix == ".json":
                raise OSError("injected manifest replacement failure")
            return original(source, target)

        monkeypatch.setattr(sharing.os, "replace", fail)
        with pytest.raises(OSError, match="injected"):
            if operation == "activate":
                _share(client, headers, folder["id"])
            else:
                client.post(f"/api/v2/admin/shares/{first['id']}/rotate", headers=headers)
        monkeypatch.setattr(sharing.os, "replace", original)
        if operation == "rotate":
            assert client.get(old_url).status_code == 200
            assert client.get(f"{old_url}/slides/0/tiles/slide.dzi").status_code == 200
            assert (
                client.post(
                    f"/api/v2/admin/shares/{first['id']}/rotate", headers=headers
                ).status_code
                == 200
            )
        else:
            with session_factory(client.app.state.settings)() as database:
                assert database.scalars(select(LibraryShare)).all() == []
                assert database.scalars(select(PublicationGrant)).all() == []
                assert database.get(Slide, "slide").state == SlideState.READY_PRIVATE
            assert (
                not StorageLayout(client.app.state.settings.data_root)
                .public_for("public-slide")
                .exists()
            )
            assert _share(client, headers, folder["id"]).status_code == 201


@pytest.mark.parametrize("operation", ["activate", "rotate"])
@pytest.mark.parametrize("already_published", [False, True])
def test_commit_failure_restores_database_and_old_manifest(
    tmp_path,
    monkeypatch,
    operation,
    already_published,
):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Shared")
        _seed_share_ready_slide(client, slide_id="slide", folder_id=folder["id"])
        storage = StorageLayout(client.app.state.settings.data_root)
        if already_published:
            with session_factory(client.app.state.settings)() as database:
                slide = database.get(Slide, "slide")
                ensure_grant(database, storage, slide, INDIVIDUAL, slide.id)
                database.commit()
        if operation == "rotate":
            first = _share(client, headers, folder["id"]).json()
            old_path = storage.root / "delivery" / "shares" / f"{first['publicId']}.json"
            old_bytes = old_path.read_bytes()
        original = Session.commit

        def fail(database):
            if any(isinstance(row, LibraryShare) for row in database.identity_map.values()):
                raise RuntimeError("injected commit failure")
            return original(database)

        monkeypatch.setattr(Session, "commit", fail)
        with pytest.raises(RuntimeError, match="injected commit"):
            if operation == "activate":
                _share(client, headers, folder["id"])
            else:
                client.post(f"/api/v2/admin/shares/{first['id']}/rotate", headers=headers)
        monkeypatch.setattr(Session, "commit", original)
        with session_factory(client.app.state.settings)() as database:
            grants = database.scalars(select(PublicationGrant)).all()
            assert len(grants) == int(already_published) + int(operation == "rotate")
            if operation == "rotate":
                assert database.get(LibraryShare, first["id"]).public_id == first["publicId"]
                assert old_path.read_bytes() == old_bytes
                url = f"/api/v2/public/folders/{first['publicId']}/slides/0/tiles/slide.dzi"
                assert client.get(url).status_code == 200
            else:
                assert database.scalars(select(LibraryShare)).all() == []
                assert storage.public_for("public-slide").exists() == already_published
        assert len(list((storage.root / "delivery" / "shares").glob("*.json"))) == int(
            operation == "rotate"
        )


def test_legacy_compacted_manifest_keeps_issued_positions_through_reconciliation(tmp_path):
    import json

    from wsi_viewer.models import ShareSlide
    from wsi_viewer.storage_accounting import reconcile_storage

    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Legacy")
        for slide_id in ["gone", "first", "second"]:
            _seed_share_ready_slide(client, slide_id=slide_id, folder_id=folder["id"])
        created = _share(client, headers, folder["id"], slideIds=["gone", "first", "second"])
        share = created.json()
        storage = StorageLayout(client.app.state.settings.data_root)
        path = storage.root / "delivery" / "shares" / f"{share['publicId']}.json"
        with session_factory(client.app.state.settings)() as database:
            membership = database.scalar(select(ShareSlide).where(ShareSlide.slide_id == "gone"))
            grant = database.scalar(
                select(PublicationGrant).where(PublicationGrant.slide_id == "gone")
            )
            database.delete(membership)
            database.delete(grant)
            database.commit()
        raw = json.loads(path.read_text())
        raw["slides"] = ["public-first", "public-second"]
        path.write_text(json.dumps(raw))
        url = f"/api/v2/public/folders/{share['publicId']}"
        for _ in range(2):
            reconcile_storage(session_factory(client.app.state.settings), storage)
            manifest = client.get(url).json()["slides"]
            assert [(s["position"], s["displayName"]) for s in manifest] == [
                (0, "Safe first"),
                (1, "Safe second"),
            ]
            assert client.get(f"{url}/slides/0/tiles/slide.dzi").status_code == 200
            assert client.get(f"{url}/slides/1/tiles/slide.dzi").status_code == 200
        client.post("/api/v1/admin/slides/first/unpublish", headers=headers)
        reconcile_storage(session_factory(client.app.state.settings), storage)
        assert client.get(f"{url}/slides/0/tiles/slide.dzi").status_code == 404
        assert client.get(f"{url}/slides/1/tiles/slide.dzi").status_code == 200
        assert client.get(url).json()["slides"][0]["position"] == 1


@pytest.mark.parametrize("slots", [["public-slide", "public-slide"], [12], {}, "public-slide"])
def test_ambiguous_or_malformed_delivery_mapping_fails_closed(tmp_path, slots):
    import json

    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Invalid")
        _seed_share_ready_slide(client, slide_id="slide", folder_id=folder["id"])
        created = _share(client, headers, folder["id"]).json()
        storage = StorageLayout(client.app.state.settings.data_root)
        path = storage.root / "delivery" / "shares" / f"{created['publicId']}.json"
        path.write_text(json.dumps({"targetType": "folder", "slides": slots}))
        before = path.read_bytes()
        url = f"/api/v2/public/folders/{created['publicId']}"
        assert client.get(url).status_code == 404
        assert client.get(f"{url}/slides/0/tiles/slide.dzi").status_code == 404
        with (
            session_factory(client.app.state.settings)() as database,
            pytest.raises(sharing.ShareConflict),
        ):
            sharing.write_share_delivery_manifest(
                storage,
                database.get(LibraryShare, created["id"]),
                [database.get(Slide, "slide")],
            )
        assert path.read_bytes() == before


def test_expired_replacement_commit_failure_restores_previous_derivatives(tmp_path, monkeypatch):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Shared")
        for slide_id in ["old", "new"]:
            _seed_share_ready_slide(client, slide_id=slide_id, folder_id=folder["id"])
        first = _share(client, headers, folder["id"], slideIds=["old"]).json()
        factory = session_factory(client.app.state.settings)
        storage = StorageLayout(client.app.state.settings.data_root)
        with factory() as database:
            database.get(LibraryShare, first["id"]).expires_at = datetime.now(UTC) - timedelta(
                seconds=1
            )
            database.commit()
        original = Session.commit

        def fail(database):
            if any(isinstance(row, LibraryShare) for row in database.identity_map.values()):
                raise RuntimeError("injected expired replacement commit failure")
            return original(database)

        monkeypatch.setattr(Session, "commit", fail)
        with pytest.raises(RuntimeError, match="injected expired"):
            _share(client, headers, folder["id"], slideIds=["new"])
        monkeypatch.setattr(Session, "commit", original)
        with factory() as database:
            assert database.get(LibraryShare, first["id"]).is_active
            assert [g.slide_id for g in database.scalars(select(PublicationGrant))] == ["old"]
        assert storage.public_for("public-old").is_dir()
        assert not storage.public_for("public-new").exists()
        assert _share(client, headers, folder["id"], slideIds=["new"]).status_code == 201


def test_rotation_cleanup_failure_leaves_old_file_unauthorized(tmp_path, monkeypatch):
    with _client(tmp_path, multi_share_enabled=True) as client:
        headers = _headers(client)
        folder = _create_folder(client, headers, "Shared")
        _seed_share_ready_slide(client, slide_id="slide", folder_id=folder["id"])
        first = _share(client, headers, folder["id"]).json()
        old_url = f"/api/v2/public/folders/{first['publicId']}"
        original = sharing.remove_share_delivery_manifest

        def fail(storage, public_id):
            if public_id == first["publicId"]:
                raise OSError("injected old file unlink failure")
            return original(storage, public_id)

        monkeypatch.setattr(sharing, "remove_share_delivery_manifest", fail)
        response = client.post(f"/api/v2/admin/shares/{first['id']}/rotate", headers=headers)
        assert response.status_code == 200
        assert client.get(old_url).status_code == 404
        assert client.get(f"{old_url}/slides/0/tiles/slide.dzi").status_code == 404
        new_url = f"/api/v2/public/folders/{response.json()['publicId']}"
        assert client.get(new_url).status_code == 200
        assert client.get(f"{new_url}/slides/0/tiles/slide.dzi").status_code == 200
