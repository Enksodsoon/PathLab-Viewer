import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from wsi_viewer import library_routes
from wsi_viewer.library import utcnow
from wsi_viewer.models import Base, Folder
from wsi_viewer.storage import StorageLayout


@pytest.fixture
def folder_app(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'folders.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine)
    with factory() as database:
        database.add_all([
            Folder(id="a", name="A", normalized_name="a"),
            Folder(id="b", name="B", normalized_name="b"),
        ])
        database.commit()

    def dependency():
        with factory() as database:
            yield database

    app = FastAPI()
    library_routes.register_library_routes(
        app, factory=factory, storage=StorageLayout(tmp_path / "data"),
        database_dependency=dependency, admin_dependency=lambda: None,
        csrf_dependency=lambda: None, tile_routes=lambda: None,
    )
    try:
        yield app, factory
    finally:
        engine.dispose()


def endpoint(app: FastAPI, path: str, method: str):
    return next(route.endpoint for route in app.routes if
                getattr(route, "path", "") == path and method in route.methods)


def test_opposing_folder_moves_cannot_commit_a_cycle(folder_app, monkeypatch):
    app, factory = folder_app
    move_endpoint = endpoint(app, "/api/v2/admin/folders/{folder_id}", "PATCH")
    original = library_routes.validate_folder_parent
    checked = threading.Barrier(2)
    start = threading.Barrier(2)

    def validate(*args, **kwargs):
        original(*args, **kwargs)
        # Force overlapping completed ancestry reads before the fix. A serialized
        # first mover continues after the bounded wait while its peer waits on SQL.
        with suppress(threading.BrokenBarrierError):
            checked.wait(0.25)

    monkeypatch.setattr(library_routes, "validate_folder_parent", validate)

    def move(pair):
        start.wait(2)
        with factory() as database:
            try:
                move_endpoint(
                    pair[0], library_routes.FolderUpdate(parentId=pair[1]), None, database,
                )
                return "moved"
            except HTTPException as error:
                return error.detail["code"]

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(move, [("a", "b"), ("b", "a")]))
    with factory() as database:
        parents = dict(database.execute(select(Folder.id, Folder.parent_id)).all())
    assert sorted(results) == ["FOLDER_CYCLE", "moved"], (results, parents)
    assert parents == {"a": "b", "b": None} or parents == {"a": None, "b": "a"}


@pytest.mark.parametrize("action", ["create", "move", "trash", "restore", "delete"])
def test_every_folder_mutation_locks_before_target_and_ancestry_reads(
    folder_app, monkeypatch, action,
):
    app, factory = folder_app
    with factory() as database:
        if action in {"restore", "delete"}:
            database.get(Folder, "a").trashed_at = utcnow()
            database.commit()
    acquired = []
    original_lock = library_routes.lock_admission
    original_get = Session.get
    original_target = library_routes.lock_share_target

    def lock(database, namespace):
        original_lock(database, namespace)
        acquired.append(namespace)

    def get(database, entity, *args, **kwargs):
        if entity is Folder:
            assert acquired == ["folder-topology"]
        return original_get(database, entity, *args, **kwargs)

    def target(database, *args, **kwargs):
        assert acquired == ["folder-topology"]
        return original_target(database, *args, **kwargs)

    monkeypatch.setattr(library_routes, "lock_admission", lock)
    monkeypatch.setattr(library_routes, "lock_share_target", target)
    monkeypatch.setattr(Session, "get", get)
    with factory() as database:
        # Match authentication's existing request Session read transaction.
        database.execute(select(Folder.id))
        if action == "create":
            endpoint(app, "/api/v2/admin/folders", "POST")(
                library_routes.FolderCreate(name="Child", parentId="a"), None, database,
            )
        elif action == "move":
            endpoint(app, "/api/v2/admin/folders/{folder_id}", "PATCH")(
                "a", library_routes.FolderUpdate(parentId="b"), None, database,
            )
        else:
            path = "/api/v2/admin/folders/{folder_id}"
            if action != "delete":
                path += f"/{action}"
            endpoint(app, path, "DELETE" if action == "delete" else "POST")(
                "a", None, database,
            )
    assert acquired == ["folder-topology"]


def test_folder_lock_failure_rolls_back_without_mutation(folder_app, monkeypatch):
    app, factory = folder_app

    def denied(database, _namespace):
        database.execute(text("BEGIN IMMEDIATE"))
        raise OperationalError("lock", {}, sqlite3.OperationalError("database is locked"))

    monkeypatch.setattr(library_routes, "lock_admission", denied)
    with factory() as database:
        with pytest.raises(OperationalError):
            endpoint(app, "/api/v2/admin/folders/{folder_id}", "PATCH")(
                "a", library_routes.FolderUpdate(parentId="b"), None, database,
            )
        assert not database.in_transaction()
        assert database.get(Folder, "a").parent_id is None


def test_restore_revalidates_previous_parent_depth_without_partial_restore(folder_app):
    app, factory = folder_app
    with factory() as database:
        # The former parent moved deeper while its child subtree remained trashed.
        chain = [Folder(id=f"d{index}", name=f"D{index}", normalized_name=f"d{index}",
                        parent_id=f"d{index - 1}" if index else None) for index in range(7)]
        database.add_all(chain)
        database.flush()
        database.get(Folder, "a").parent_id = "d6"
        child = database.get(Folder, "b")
        child.parent_id = "a"
        child.previous_parent_id = "a"
        child.trashed_at = utcnow()
        database.commit()
    with factory() as database:
        with pytest.raises(HTTPException) as caught:
            endpoint(app, "/api/v2/admin/folders/{folder_id}/restore", "POST")(
                "b", None, database,
            )
        assert caught.value.detail["code"] == "FOLDER_DEPTH_EXCEEDED"
        assert not database.in_transaction()
        assert database.get(Folder, "b").trashed_at is not None
