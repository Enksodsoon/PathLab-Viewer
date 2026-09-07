import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import UTC, datetime, timedelta, timezone

import pytest
import wsi_viewer.sharing as sharing
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from wsi_viewer.config import Settings
from wsi_viewer.domain import SlideState
from wsi_viewer.library_routes import register_library_routes
from wsi_viewer.models import (
    Base,
    Collection,
    CollectionSlide,
    Folder,
    LibraryShare,
    PublicationGrant,
    ShareSlide,
    Slide,
)
from wsi_viewer.storage import StorageLayout
from wsi_viewer.tile_routes import TileRouteService


@pytest.fixture(params=["sqlite", "postgresql"])
def sharing_database(request, tmp_path):
    url = os.getenv("PATHLAB_POSTGRES_TEST_URL")
    schema = "sharing_" + uuid.uuid4().hex
    if request.param == "postgresql":
        if not url:
            pytest.skip("isolated PostgreSQL URL required")
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-c search_path={schema}"})
    else:
        engine = create_engine(
            f"sqlite:///{tmp_path / 'race.sqlite'}",
            connect_args={"timeout": 5, "check_same_thread": False},
        )
    try:
        Base.metadata.create_all(engine)
        factory = sessionmaker(engine, expire_on_commit=False)
        storage = StorageLayout(tmp_path / "data")
        with factory() as database:
            database.add(Folder(id="folder", name="Folder", normalized_name="folder"))
            database.flush()
            database.add(
                Slide(
                    id="slide",
                    public_id="public-slide",
                    display_name="Slide",
                    original_filename="slide.ome.tiff",
                    source_bytes=10,
                    folder_id="folder",
                    state=SlideState.READY_PRIVATE,
                )
            )
            database.commit()
        derivative = storage.for_slide("slide").private_derivative
        (derivative / "slide_files" / "0").mkdir(parents=True)
        (derivative / "slide.dzi").write_text("<Image />")
        (derivative / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"tile")
        yield factory, storage
    finally:
        engine.dispose()
        if request.param == "postgresql":
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


def _activate(factory, storage, expires_at=None, *, target_type="folder", target_id="folder"):
    with factory() as database:
        try:
            share = sharing.activate_share(
                database,
                storage,
                target_type=target_type,
                target_id=target_id,
                include_descendants=False,
                auto_include_new=False,
                expires_at=expires_at,
                slide_ids=None,
            )
            return share.public_id
        except sharing.ShareConflict as error:
            return error.code


def test_activation_serializes_before_eligibility_check(sharing_database, monkeypatch):
    factory, storage = sharing_database
    first_ready = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    original_grant = sharing.ensure_grant
    original_preview = sharing.preview_share
    first_thread = None

    def grant(*args, **kwargs):
        nonlocal first_thread
        if first_thread is None:
            first_thread = threading.get_ident()
            first_ready.set()
            assert release_first.wait(5)
        return original_grant(*args, **kwargs)

    def preview(*args, **kwargs):
        if first_thread is not None and threading.get_ident() != first_thread:
            second_entered.set()
        return original_preview(*args, **kwargs)

    monkeypatch.setattr(sharing, "ensure_grant", grant)
    monkeypatch.setattr(sharing, "preview_share", preview)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_activate, factory, storage)
        assert first_ready.wait(5)
        second = executor.submit(_activate, factory, storage)
        try:
            with pytest.raises(TimeoutError):
                second.result(timeout=0.25)
            assert not second_entered.is_set(), "eligibility read ran before target lock"
        finally:
            release_first.set()
        first_id = first.result(timeout=5)
        assert second.result(timeout=5) == "SHARE_ALREADY_ACTIVE"
    with factory() as database:
        assert len(database.scalars(select(LibraryShare)).all()) == 1
        assert len(database.scalars(select(PublicationGrant)).all()) == 1
    assert (
        sharing.share_delivery_public_id(
            storage, public_id=first_id, target_type="folder", position=0
        )
        == "public-slide"
    )


@pytest.mark.parametrize("offset", [0, 7])
def test_expiry_roundtrip_and_reactivation(sharing_database, offset):
    factory, storage = sharing_database
    future = (datetime.now(UTC) + timedelta(hours=1)).astimezone(timezone(timedelta(hours=offset)))
    public_id = _activate(factory, storage, future)
    with factory() as database:
        share = sharing.active_public_share(database, target_type="folder", public_id=public_id)
        assert sharing.public_manifest(database, share, storage)["slides"][0]["position"] == 0
    assert (
        sharing.share_delivery_public_id(
            storage, public_id=public_id, target_type="folder", position=0
        )
        == "public-slide"
    )
    with factory() as database:
        share = database.scalar(select(LibraryShare))
        share.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
    replacement = _activate(factory, storage, future)
    assert replacement != "SHARE_ALREADY_ACTIVE"
    with factory() as database:
        assert database.scalar(sharing.shared_slide_statement(public_id, "folder")) is None
        assert database.scalar(sharing.shared_slide_statement(replacement, "folder")) is not None


@pytest.mark.parametrize("sharing_database", ["postgresql"], indirect=True)
def test_failed_activation_preserves_different_target_committed_delivery(
    sharing_database,
    monkeypatch,
):
    factory, storage = sharing_database
    with factory() as database:
        database.add(Collection(id="collection", name="Collection", normalized_name="collection"))
        database.flush()
        database.add(CollectionSlide(collection_id="collection", slide_id="slide"))
        database.commit()
    (storage.for_slide("slide").private_derivative / "thumbnail.jpg").write_bytes(b"thumbnail")
    a_ready = threading.Event()
    release_a = threading.Event()
    original_grant = sharing.ensure_grant
    original_write = sharing.write_share_delivery_manifest
    a_thread_id = None
    a_public_id = None

    def grant(*args, **kwargs):
        if threading.get_ident() == a_thread_id:
            a_ready.set()
            assert release_a.wait(10)
        return original_grant(*args, **kwargs)

    def write(layout, share, slides):
        nonlocal a_public_id
        if threading.get_ident() == a_thread_id:
            a_public_id = share.public_id
            raise OSError("injected A manifest failure")
        return original_write(layout, share, slides)

    def activate_a():
        nonlocal a_thread_id
        a_thread_id = threading.get_ident()
        return _activate(factory, storage)

    monkeypatch.setattr(sharing, "ensure_grant", grant)
    monkeypatch.setattr(sharing, "write_share_delivery_manifest", write)
    with ThreadPoolExecutor(max_workers=1) as executor:
        pending_a = executor.submit(activate_a)
        assert a_ready.wait(10)
        try:
            b_public_id = _activate(
                factory, storage, target_type="collection", target_id="collection"
            )
            root = storage.public_for("public-slide")
            names = ["slide.dzi", "slide_files/0/0_0.jpeg", "thumbnail.jpg"]
            before = {
                name: ((root / name).stat().st_ino, (root / name).read_bytes()) for name in names
            }
        finally:
            release_a.set()
        with pytest.raises(OSError, match="injected A"):
            pending_a.result(timeout=10)
    # No reconciliation or retry may intervene before these assertions.
    assert all((root / name).is_file() for name in names), "A removed B's shared alias"
    assert {
        name: ((root / name).stat().st_ino, (root / name).read_bytes()) for name in names
    } == before
    with factory() as database:
        shares = database.scalars(select(LibraryShare)).all()
        assert len(shares) == 1 and shares[0].public_id == b_public_id
        grants = database.scalars(select(PublicationGrant)).all()
        assert len(grants) == 1 and grants[0].source_id == shares[0].id
        assert len(database.scalars(select(ShareSlide)).all()) == 1
    assert not (storage.root / "delivery" / "shares" / f"{a_public_id}.json").exists()

    def database_dependency():
        with factory() as database:
            yield database

    app = FastAPI()
    app.state.settings = Settings(data_root=storage.root, internal_file_redirects=False)
    register_library_routes(
        app,
        factory=factory,
        storage=storage,
        database_dependency=database_dependency,
        admin_dependency=lambda: None,
        csrf_dependency=lambda: None,
        tile_routes=lambda: TileRouteService(storage, None, internal_redirects=True),
    )
    with TestClient(app) as client:
        b_url = f"/api/v2/public/collections/{b_public_id}"
        assert client.get(b_url).status_code == 200
        for suffix, expected in [
            ("tiles/slide.dzi", b"<Image />"),
            ("tiles/slide_files/0/0_0.jpeg", b"tile"),
            ("thumbnail", b"thumbnail"),
        ]:
            response = client.get(f"{b_url}/slides/0/{suffix}")
            assert response.status_code == 200 and response.content == expected
            assert (
                client.get(f"/api/v2/public/folders/{a_public_id}/slides/0/{suffix}").status_code
                == 404
            )
