import os
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session as OrmSession
from test_assessment_admin import _client, _document
from wsi_viewer import database as database_module
from wsi_viewer.database import session_factory
from wsi_viewer.models import AssessmentDraft


@pytest.fixture(params=["sqlite", "postgres"])
def draft_client(
    tmp_path: Path, request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[TestClient]:
    if request.param == "sqlite":
        client, _ = _client(tmp_path)
        try:
            yield client
        finally:
            client.close()
        return
    database_url = os.getenv("PATHLAB_POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("isolated PostgreSQL is required for actual draft revision admission")
    url = make_url(database_url)
    assert url.get_backend_name() == "postgresql"
    schema = f"assessment_revision_{uuid.uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated = url.update_query_dict({"options": f"-c search_path={schema}"})
    isolated_engines = []

    def isolated_create_engine(target, **kwargs):
        if make_url(target) != isolated:
            return create_engine(target, **kwargs)
        connect_args = dict(kwargs.pop("connect_args", {}))
        existing_options = connect_args.get("options", "")
        connect_args["options"] = f"{existing_options} -c search_path={schema}".strip()
        engine = create_engine(target, connect_args=connect_args, **kwargs)
        isolated_engines.append(engine)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT current_schema()")) == schema
        return engine

    monkeypatch.setattr(database_module, "create_engine", isolated_create_engine)
    client = None
    try:
        client, _ = _client(tmp_path, database_url=isolated.render_as_string(hide_password=False))
        yield client
    finally:
        if client is not None:
            client.close()
        for engine in isolated_engines:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


@pytest.mark.parametrize("methods", [("save", "save"), ("save", "import"), ("import", "import")])
def test_competing_draft_mutations_admit_only_one_revision(
    draft_client: TestClient, methods: tuple[str, str]
) -> None:
    client = draft_client
    payload = {"title": "Synthetic revision QA", "document": _document()}
    draft = client.post("/api/v2/admin/assessment/drafts", json=payload).json()
    source = client.post("/api/v2/admin/assessment/drafts", json=payload).json()
    path = f"/api/v2/admin/assessment/drafts/{draft['id']}"
    barrier = Barrier(2, timeout=10)

    def after_read(_database: OrmSession, target: object) -> None:
        if (
            isinstance(target, AssessmentDraft)
            and target.id == draft["id"]
            and target.revision == 1
        ):
            barrier.wait()

    def mutate(entry: tuple[int, str]) -> tuple[int, dict]:
        index, method = entry
        with TestClient(client.app) as other:
            other.cookies.update(client.cookies)
            other.headers.update(client.headers)
            if method == "save":
                response = other.patch(
                    path,
                    headers={"If-Match": "1"},
                    json={"document": {**_document(), "title": f"Synthetic writer {index}"}},
                )
            else:
                response = other.post(
                    f"{path}/import-questions",
                    json={
                        "sourceDraftId": source["id"],
                        "itemIds": ["item-1"],
                        "expectedRevision": 1,
                    },
                )
            return response.status_code, response.json()

    event.listen(OrmSession, "loaded_as_persistent", after_read)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(mutate, enumerate(methods)))
    finally:
        event.remove(OrmSession, "loaded_as_persistent", after_read)
    assert sorted(status for status, _ in results) == [200, 409]
    winner = next(body for status, body in results if status == 200)
    loser = next(body for status, body in results if status == 409)
    assert loser["detail"]["code"] == "ASSESSMENT_DRAFT_CONFLICT"
    assert loser["detail"]["revision"] == 2
    persisted = client.get(path).json()
    assert winner["revision"] == persisted["revision"] == 2
    assert persisted["document"] == winner["document"]


def test_archive_after_draft_read_prevents_late_document_save(draft_client: TestClient) -> None:
    client = draft_client
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Synthetic archive QA", "document": _document()},
    ).json()
    path = f"/api/v2/admin/assessment/drafts/{draft['id']}"
    loaded, resume = Event(), Event()

    def after_read(_database: OrmSession, target: object) -> None:
        if isinstance(target, AssessmentDraft) and target.id == draft["id"] and not loaded.is_set():
            loaded.set()
            assert resume.wait(10)

    event.listen(OrmSession, "loaded_as_persistent", after_read)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            saving = pool.submit(
                client.patch,
                path,
                headers={"If-Match": "1"},
                json={"document": {**_document(), "title": "Late synthetic edit"}},
            )
            try:
                assert loaded.wait(10)
                assert client.post(f"{path}/archive").status_code == 200
            finally:
                resume.set()
            assert saving.result(timeout=10).status_code == 409
    finally:
        event.remove(OrmSession, "loaded_as_persistent", after_read)
    assert client.get(path).status_code == 409
    with session_factory(client.app.state.settings)() as database:
        persisted = database.get(AssessmentDraft, draft["id"])
        assert persisted is not None
        assert persisted.status == "archived"
        assert persisted.revision == 1
        assert persisted.document == _document()
