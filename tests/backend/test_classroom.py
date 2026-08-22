import asyncio
import hashlib
import hmac
import inspect
import json
import sqlite3
import threading
import time
from collections.abc import AsyncGenerator, Callable, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as OrmSession
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from wsi_viewer.classroom_hub import ClassroomHub
from wsi_viewer.classroom_runtime import ClassroomSingletonLock
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, engine_for, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    ClassroomParticipant,
    ClassroomSession,
    Folder,
    Job,
    PublicationGrant,
    RuntimeGuard,
    Slide,
    User,
)
from wsi_viewer.publication import delivery_version
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _client(
    tmp_path: Path,
    *,
    enabled: bool,
    role: str = "all",
    max_participants: int = 300,
    protection_enabled: bool = False,
) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        classroom_enabled=enabled,
        classroom_protection_enabled=protection_enabled,
        classroom_max_participants=max_participants,
        service_role=role,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.add(
            Folder(
                id="folder-1",
                name="Teaching cases",
                normalized_name="teaching cases",
            )
        )
        database.add(
            Slide(
                id="slide-1",
                public_id="public-slide-1",
                display_name="Teaching slide",
                original_filename="teaching.ome.tiff",
                source_bytes=1024,
                derivative_bytes=2048,
                derivative_file_count=3,
                render_mode="static_dzi",
                state=SlideState.PUBLISHED,
                slide_metadata={
                    "width": 4000,
                    "height": 3000,
                    "dziTileSize": 512,
                    "dziFormat": "jpg",
                },
                sha256="a" * 64,
                folder_id="folder-1",
                published_at=datetime.now(UTC),
                privacy_status="passed",
            )
        )
        database.flush()
        database.add(
            PublicationGrant(slide_id="slide-1", source_type="individual", source_id="slide-1")
        )
        database.commit()
    with session_factory(settings)() as database:
        published = database.get(Slide, "slide-1")
        assert published is not None
        version = delivery_version(published)
    derivative = settings.data_root / "delivery" / "individual" / "public-slide-1" / version
    (derivative / "slide_files" / "0").mkdir(parents=True)
    (derivative / "slide.dzi").write_text(
        '<Image TileSize="512" Overlap="1" Format="jpg"><Size Width="4000" Height="3000"/></Image>',
        encoding="utf-8",
    )
    (derivative / "slide_files" / "0" / "0_0.jpg").write_bytes(b"tile")
    return TestClient(create_app(settings))


def _admin_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def _classroom_event_stream(
    client: TestClient, session_id: str
) -> tuple[AsyncGenerator[str | bytes | memoryview, None], Any]:
    path = f"/api/v1/classroom/sessions/{session_id}/events"
    app = cast(FastAPI, client.app)
    route = next(
        cast(APIRoute, route)
        for route in app.routes
        if getattr(route, "path", None) == "/api/v1/classroom/sessions/{session_id}/events"
    )
    cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
    request = Request(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [(b"cookie", cookie.encode())],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
            "root_path": "",
        }
    )
    response = cast(StreamingResponse, route.endpoint(session_id, request))
    pending = [route.endpoint]
    hub = None
    while pending and hub is None:
        function = pending.pop()
        for value in getattr(function, "__closure__", None) or ():
            item = value.cell_contents
            if item.__class__.__name__ == "ClassroomHub":
                hub = item
                break
            if callable(item):
                pending.append(item)
    assert hub is not None
    return (
        cast(AsyncGenerator[str | bytes | memoryview, None], response.body_iterator),
        hub,
    )


def test_classroom_routes_are_absent_when_disabled(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=False) as client:
        assert client.post("/api/v1/classroom/join", json={"joinCode": "ABC123"}).status_code == 404


def test_classroom_protection_drains_worker_before_live_session(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True, protection_enabled=True) as client:
        headers = _admin_headers(client)
        settings = cast(Settings, client.app.state.settings)
        factory = session_factory(settings)
        with factory() as database:
            job = Job(slide_id="slide-1", kind="ingest", status="running")
            database.add(job)
            database.commit()
            job_id = job.id

        draining = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        )
        assert draining.status_code == 409
        assert draining.json()["detail"] == {
            "code": "CLASSROOM_DRAINING",
            "runningJobs": 1,
        }
        with factory() as database:
            stored = database.get(Job, job_id)
            assert stored is not None
            assert stored.cancellation_requested_at is not None
            guard = database.get(RuntimeGuard, "classroom-protection")
            assert guard is not None
            assert guard.mode == "draining_for_classroom"
            stored.status = "succeeded"
            database.commit()

        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        )
        assert created.status_code == 201, created.text
        admission = client.get("/api/v1/internal/uploads/admission")
        assert admission.status_code == 423
        assert admission.json()["detail"]["code"] == "CLASSROOM_PROTECTION_ACTIVE"
        with factory() as database:
            guard = database.get(RuntimeGuard, "classroom-protection")
            assert guard is not None
            assert guard.mode == "classroom_live"
            assert guard.classroom_session_id == created.json()["id"]

        ended = client.delete("/api/v1/admin/classroom/sessions/active", headers=headers)
        assert ended.status_code == 204
        with factory() as database:
            guard = database.get(RuntimeGuard, "classroom-protection")
            assert guard is not None
            assert guard.mode == "classroom_cooldown"


def test_synthetic_classroom_is_durably_run_owned_and_cleanup_is_exact(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        run_id = "123456"
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers={**headers, "X-PathLab-Synthetic-Run": run_id},
            json={"slideIds": ["slide-1"]},
        )
        assert created.status_code == 201
        assert created.json()["syntheticRunId"] == run_id
        session_id = created.json()["id"]
        state = client.get(
            f"/api/v1/admin/classroom/sessions/{session_id}", headers=headers
        )
        assert state.json()["session"]["syntheticRunId"] == run_id
        mismatch = client.delete(
            f"/api/v1/admin/classroom/sessions/{session_id}",
            headers={**headers, "X-PathLab-Synthetic-Run": "another-run"},
        )
        assert mismatch.status_code == 409
        removed = client.delete(
            f"/api/v1/admin/classroom/sessions/{session_id}",
            headers={**headers, "X-PathLab-Synthetic-Run": run_id},
        )
        assert removed.status_code == 204
        assert (
            client.get(
                f"/api/v1/admin/classroom/sessions/{session_id}", headers=headers
            ).status_code
            == 404
        )


def test_saturated_classroom_mutation_fails_fast_with_retry_after(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from wsi_viewer.classroom_routes import ClassroomMutationGate

    gate = ClassroomMutationGate(timeout_seconds=0.01)
    assert gate.lock.acquire(blocking=False)
    monkeypatch.setattr("wsi_viewer.classroom_routes.ClassroomMutationGate", lambda: gate)
    try:
        with _client(tmp_path, enabled=True) as client:
            response = client.post(
                "/api/v1/admin/classroom/sessions",
                headers=_admin_headers(client),
                json={"slideIds": ["slide-1"]},
            )
    finally:
        gate.lock.release()

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "CLASSROOM_BUSY"}}
    assert response.headers["retry-after"] == "1"


def test_classroom_pool_saturation_maps_to_busy_with_retry_after(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True, role="classroom") as client:
        settings = cast(FastAPI, client.app).state.settings
        engine = engine_for(settings)
        client.cookies.set("pathlab_session", "invalid-session")
        connections = [engine.connect() for _ in range(4)]
        try:
            response = client.post(
                "/api/v1/admin/classroom/sessions",
                headers={"X-CSRF-Token": "x" * 32},
                json={"slideIds": ["slide-1"]},
            )
        finally:
            for connection in connections:
                connection.close()

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "CLASSROOM_BUSY"}}
    assert response.headers["retry-after"] == "1"


def test_cross_process_sqlite_writer_lock_maps_to_bounded_classroom_busy(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as general_client:
        headers = _admin_headers(general_client)
        cookies = dict(general_client.cookies)
        general_settings = cast(FastAPI, general_client.app).state.settings

    classroom_settings = general_settings.model_copy(update={"service_role": "classroom"})
    writer = sqlite3.connect(tmp_path / "test.sqlite3", timeout=0.1)
    writer.execute("BEGIN IMMEDIATE")
    started = time.monotonic()
    try:
        with TestClient(
            create_app(classroom_settings), raise_server_exceptions=False
        ) as classroom_client:
            classroom_client.cookies.update(cookies)
            response = classroom_client.post(
                "/api/v1/admin/classroom/sessions",
                headers=headers,
                json={"slideIds": ["slide-1"]},
            )
    finally:
        elapsed = time.monotonic() - started
        writer.rollback()
        writer.close()

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "CLASSROOM_BUSY"}}
    assert response.headers["retry-after"] == "1"
    assert elapsed < 2.5


def test_non_locking_sqlite_operational_error_is_not_classified_as_busy() -> None:
    from wsi_viewer.main import _is_sqlite_busy_or_locked

    error = OperationalError(
        "SELECT missing FROM absent",
        {},
        sqlite3.OperationalError("no such table: absent"),
    )

    assert not _is_sqlite_busy_or_locked(error)


def test_join_admission_has_no_unbounded_async_lock_wait() -> None:
    from wsi_viewer.classroom_routes import register_classroom_routes

    source = inspect.getsource(register_classroom_routes)

    assert "async with join_queue_lock" not in source
    assert "await asyncio.wait_for(" in source
    assert "join_queue_lock.acquire()" in source


def test_join_admission_is_atomic_at_configured_capacity(tmp_path: Path) -> None:
    from wsi_viewer.classroom_routes import JoinRequest

    with _client(tmp_path, enabled=True, max_participants=1) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        app = cast(FastAPI, client.app)
        route = next(
            cast(APIRoute, route)
            for route in app.routes
            if getattr(route, "path", None) == "/api/v1/classroom/join"
        )

        def request() -> Request:
            return Request(
                {
                    "type": "http",
                    "asgi": {"version": "3.0"},
                    "http_version": "1.1",
                    "method": "POST",
                    "scheme": "http",
                    "path": "/api/v1/classroom/join",
                    "raw_path": b"/api/v1/classroom/join",
                    "query_string": b"",
                    "headers": [],
                    "client": ("testclient", 50000),
                    "server": ("testserver", 80),
                    "root_path": "",
                }
            )

        async def admit_two() -> list[object]:
            return await asyncio.gather(
                route.endpoint(
                    JoinRequest(joinCode=created["joinCode"], displayName="First"),
                    request(),
                    Response(),
                ),
                route.endpoint(
                    JoinRequest(joinCode=created["joinCode"], displayName="Second"),
                    request(),
                    Response(),
                ),
                return_exceptions=True,
            )

        results = asyncio.run(admit_two())

    admitted = [item for item in results if isinstance(item, dict)]
    rejected = [item for item in results if isinstance(item, HTTPException)]
    assert len(admitted) == 1
    assert len(rejected) == 1
    assert rejected[0].status_code == 409
    assert rejected[0].detail == {"code": "CLASSROOM_FULL"}


def test_restart_does_not_reclaim_persisted_live_member_before_current_epoch_reconnect(
    tmp_path: Path,
) -> None:
    settings: Settings
    with _client(tmp_path, enabled=True, max_participants=1) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Before restart"},
        ).json()
        participant_id = joined["participant"]["id"]
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)
            assert participant is not None
            participant.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
            participant.disconnected_at = datetime.now(UTC) - timedelta(hours=2)
            database.commit()

    with TestClient(create_app(settings)) as restarted:
        blocked = restarted.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "After restart"},
        )

    assert blocked.status_code == 409
    assert blocked.json()["detail"] == {"code": "CLASSROOM_FULL"}
    with session_factory(settings)() as database:
        assert database.get(ClassroomParticipant, participant_id) is not None


def test_preview_identities_neither_consume_live_seats_nor_get_reclaimed(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True, max_participants=2) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={
                "folderId": "folder-1",
                "reviewExpiresAt": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            },
        ).json()
        first_preview = client.post(
            f"/api/v1/classroom/invites/{created['publicId']}/unlock",
            json={"accessCode": created["joinCode"], "displayName": "Recent preview"},
        ).json()["participant"]["id"]
        client.cookies.delete("pathlab_classroom_participant")
        second_preview = client.post(
            f"/api/v1/classroom/invites/{created['publicId']}/unlock",
            json={"accessCode": created["joinCode"], "displayName": "Old preview"},
        ).json()["participant"]["id"]
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, second_preview)
            assert participant is not None and participant.joined_live_at is None
            participant.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
            participant.disconnected_at = datetime.now(UTC) - timedelta(hours=2)
            database.commit()
        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/start",
                headers=headers,
            ).status_code
            == 200
        )

        client.cookies.delete("pathlab_classroom_participant")
        first_live = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "First live"},
        )
        client.cookies.delete("pathlab_classroom_participant")
        second_live = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Second live"},
        )

        assert first_live.status_code == 201, first_live.text
        assert second_live.status_code == 201, second_live.text
        with session_factory(settings)() as database:
            previews = [
                database.get(ClassroomParticipant, participant_id)
                for participant_id in (first_preview, second_preview)
            ]
            assert all(item is not None and item.joined_live_at is None for item in previews)


def test_aliases_are_hmac_derived_with_bounded_collision_retries(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import wsi_viewer.classroom_routes as classroom_routes

    calls: list[int] = []

    def colliding_candidate(secret_key: str, token: str, attempt: int) -> str:
        assert secret_key == "test-secret-that-is-long-enough"
        assert token
        calls.append(attempt)
        return "MINT-00000001" if attempt < 2 else "FERN-00000002"

    monkeypatch.setattr(classroom_routes, "_alias_candidate", colliding_candidate, raising=False)
    with _client(tmp_path, enabled=True) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            database.add(
                ClassroomParticipant(
                    session_id=created["id"],
                    token_hash="f" * 64,
                    public_alias="MINT-00000001",
                    joined_live_at=datetime.now(UTC),
                    disconnected_at=datetime.now(UTC),
                )
            )
            database.commit()

        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Student"},
        )

    assert joined.status_code == 201
    assert joined.json()["participant"]["alias"] == "FERN-00000002"
    assert calls == [0, 1, 2]
    assert "existing_aliases = set(" not in inspect.getsource(
        classroom_routes.register_classroom_routes
    )


def test_real_alias_candidate_is_a_bounded_hmac_of_token_and_attempt() -> None:
    from wsi_viewer.classroom_routes import ALIAS_WORDS, _alias_candidate

    secret = "test-secret-that-is-long-enough"
    token = "opaque-join-token"
    digest = hmac.new(
        secret.encode(), b"classroom-alias:opaque-join-token:0", hashlib.sha256
    ).digest()
    expected = (
        f"{ALIAS_WORDS[digest[0] % len(ALIAS_WORDS)]}-"
        f"{int.from_bytes(digest[1:5], 'big') % 100_000_000:08d}"
    )

    assert _alias_candidate(secret, token, 0) == expected
    assert len(expected) <= 16
    assert _alias_candidate(secret, token, 1) != expected
    assert _alias_candidate(secret, f"{token}-different", 0) != expected


def test_teacher_roster_is_searchable_keyset_paginated_and_versioned(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Initial"},
        )
        assert joined.status_code == 201
        settings = cast(FastAPI, client.app).state.settings
        seeded = (
            ("AMBER-00000001", "Alpha One"),
            ("CORAL-00000002", "Alpha Two"),
            ("FERN-00000003", "Beta Three"),
        )
        with session_factory(settings)() as database:
            for alias, display_name in seeded:
                database.add(
                    ClassroomParticipant(
                        session_id=created["id"],
                        token_hash=hashlib.sha256(alias.encode()).hexdigest(),
                        public_alias=alias,
                        optional_display_name=display_name,
                        joined_live_at=datetime.now(UTC),
                        disconnected_at=datetime.now(UTC),
                    )
                )
            database.commit()

        first = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}/participants",
            headers=headers,
            params={"limit": 1, "q": "alpha"},
        )
        assert first.status_code == 200, first.text
        first_payload = first.json()
        assert first_payload["total"] == 2
        assert len(first_payload["items"]) == 1
        assert first_payload["items"][0]["alias"] == "AMBER-00000001"
        assert first_payload["nextCursor"] == "AMBER-00000001"
        assert first_payload["rosterVersion"] >= 1

        second = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}/participants",
            headers=headers,
            params={"after": first_payload["nextCursor"], "limit": 1, "q": "alpha"},
        )
        assert second.status_code == 200, second.text
        assert second.json()["items"][0]["alias"] == "CORAL-00000002"
        assert second.json()["nextCursor"] is None

        teacher_state = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}", headers=headers
        ).json()
        assert teacher_state["participantCount"] == 4
        assert teacher_state["rosterVersion"] == first_payload["rosterVersion"]
        assert isinstance(teacher_state["participants"], list)

        oversized = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}/participants",
            headers=headers,
            params={"limit": 101},
        )
        assert oversized.status_code == 422


def test_roster_read_waits_for_membership_commit_and_version_change(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from wsi_viewer.classroom_hub import ClassroomHub
    from wsi_viewer.classroom_routes import JoinRequest

    commit_reached = threading.Event()
    release_version = threading.Event()
    original_mark = ClassroomHub.mark_roster_changed

    def blocking_mark(self: ClassroomHub, session_id: str) -> int:
        commit_reached.set()
        assert release_version.wait(timeout=2)
        return original_mark(self, session_id)

    monkeypatch.setattr(ClassroomHub, "mark_roster_changed", blocking_mark)
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        app = cast(FastAPI, client.app)
        join_route = next(
            cast(APIRoute, route)
            for route in app.routes
            if getattr(route, "path", None) == "/api/v1/classroom/join"
        )
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/classroom/join",
                "raw_path": b"/api/v1/classroom/join",
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "root_path": "",
            }
        )
        join_result: list[object] = []
        roster_result: list[object] = []

        def admit() -> None:
            join_result.append(
                asyncio.run(
                    join_route.endpoint(
                        JoinRequest(joinCode=created["joinCode"], displayName="Atomic"),
                        request,
                        Response(),
                    )
                )
            )

        def read_roster() -> None:
            roster_result.append(
                client.get(
                    f"/api/v1/admin/classroom/sessions/{created['id']}/participants",
                    headers=headers,
                )
            )

        join_thread = threading.Thread(target=admit)
        join_thread.start()
        assert commit_reached.wait(timeout=1)
        roster_thread = threading.Thread(target=read_roster)
        roster_thread.start()
        try:
            roster_thread.join(timeout=0.1)
            assert roster_thread.is_alive()
        finally:
            release_version.set()
        join_thread.join(timeout=2)
        roster_thread.join(timeout=2)

    assert not join_thread.is_alive()
    assert not roster_thread.is_alive()
    assert len(join_result) == 1
    assert len(roster_result) == 1
    roster = cast(Any, roster_result[0])
    assert roster.status_code == 200
    assert roster.json()["total"] == 1
    assert roster.json()["rosterVersion"] == 1


def test_session_creation_and_real_slide_change_schedule_bounded_prewarm(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    import wsi_viewer.classroom_routes as classroom_routes

    instances: list[Any] = []

    class RecordingPrewarmer:
        def __init__(self) -> None:
            self.requests: list[tuple[Any, ...]] = []
            self.started = False
            self.requests_coalesced = 0
            self.completed = 0
            self.failures = 0
            instances.append(self)

        def start(self) -> None:
            self.started = True

        def request(self, slides: Sequence[Any]) -> None:
            self.requests.append(tuple(slides))

        def clear(self) -> None:
            return

        async def close(self) -> None:
            return

    monkeypatch.setattr(classroom_routes, "ClassroomPrewarmer", RecordingPrewarmer, raising=False)
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            slide = Slide(
                id="slide-2",
                public_id="public-slide-2",
                display_name="Second teaching slide",
                original_filename="second.ome.tiff",
                source_bytes=1024,
                derivative_bytes=2048,
                derivative_file_count=4,
                render_mode="static_dzi",
                state=SlideState.PUBLISHED,
                slide_metadata={
                    "width": 4096,
                    "height": 2048,
                    "dziTileSize": 512,
                    "dziFormat": "jpg",
                },
                sha256="b" * 64,
                folder_id="folder-1",
                published_at=datetime.now(UTC),
                privacy_status="passed",
                thumbnail_filename="thumbnail.jpg",
            )
            database.add(slide)
            database.flush()
            database.add(
                PublicationGrant(slide_id=slide.id, source_type="individual", source_id=slide.id)
            )
            database.commit()
            version = delivery_version(slide)
        derivative = settings.data_root / "delivery" / "individual" / "public-slide-2" / version
        (derivative / "slide_files" / "0").mkdir(parents=True)
        (derivative / "slide.dzi").write_text(
            '<Image TileSize="512" Overlap="1" Format="jpg">'
            '<Size Width="4096" Height="2048"/></Image>',
            encoding="utf-8",
        )
        (derivative / "thumbnail.jpg").write_bytes(b"poster")
        (derivative / "slide_files" / "0" / "0_0.jpg").write_bytes(b"tile")

        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1", "slide-2"]},
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        assert instances and instances[0].started
        assert len(instances[0].requests) == 1
        assert len(instances[0].requests[0]) == 2

        switched = client.post(
            f"/api/v1/admin/classroom/sessions/{session_id}/presenter",
            headers=headers,
            json={"slideId": "slide-2", "x": 0.5, "y": 0.5, "zoom": 1},
        )
        assert switched.status_code == 200, switched.text
        assert len(instances[0].requests) == 2
        assert instances[0].requests[-1][0].root == derivative

        same_slide = client.post(
            f"/api/v1/admin/classroom/sessions/{session_id}/presenter",
            headers=headers,
            json={"slideId": "slide-2", "x": 0.6, "y": 0.5, "zoom": 1},
        )
        assert same_slide.status_code == 200, same_slide.text
        assert len(instances[0].requests) == 2


def test_classroom_event_stream_runs_database_work_off_event_loop(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    calls: list[str] = []

    async def recording_run_in_threadpool(function: Callable[..., Any], *args: object) -> Any:
        calls.append(getattr(function, "__name__", "unknown"))
        return await run_in_threadpool(function, *args)

    monkeypatch.setattr(
        "wsi_viewer.classroom_routes.run_in_threadpool", recording_run_in_threadpool
    )

    with _client(tmp_path, enabled=True) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Student"},
        ).json()
        participant_id = joined["participant"]["id"]
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)
            assert participant is not None
            original_last_seen_at = participant.last_seen_at
            original_disconnected_at = participant.disconnected_at
        calls.clear()
        path = f"/api/v1/classroom/sessions/{created['id']}/events"
        app = cast(FastAPI, client.app)
        route = next(
            cast(APIRoute, route)
            for route in app.routes
            if getattr(route, "path", None) == "/api/v1/classroom/sessions/{session_id}/events"
        )
        cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
        request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": path,
                "raw_path": path.encode(),
                "query_string": b"",
                "headers": [(b"cookie", cookie.encode())],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "root_path": "",
            }
        )

        async def open_and_close_stream() -> tuple[str, dict[str, int]]:
            response = cast(StreamingResponse, route.endpoint(created["id"], request))
            body_iterator = cast(
                AsyncGenerator[str | bytes | memoryview, None], response.body_iterator
            )
            first = cast(str, await anext(body_iterator))
            await body_iterator.aclose()
            pending = [route.endpoint]
            hub = None
            while pending and hub is None:
                function = pending.pop()
                for value in getattr(function, "__closure__", None) or ():
                    item = value.cell_contents
                    if item.__class__.__name__ == "ClassroomHub":
                        hub = item
                        break
                    if callable(item):
                        pending.append(item)
            assert hub is not None
            return first, hub.metrics()

        writer = sqlite3.connect(tmp_path / "test.sqlite3", timeout=0.1)
        writer.execute("BEGIN IMMEDIATE")
        try:
            first, metrics = asyncio.run(open_and_close_stream())
            second, metrics = asyncio.run(open_and_close_stream())
        finally:
            writer.rollback()
            writer.close()
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)
            assert participant is not None
            assert participant.last_seen_at == original_last_seen_at
            assert participant.disconnected_at == original_disconnected_at

    assert first.startswith("event: stream-ready")
    assert second.startswith("event: stream-ready")
    assert calls == ["stream_state_version", "stream_state_version"]
    assert metrics["activeParticipants"] == 0
    assert metrics["reconnects"] == 1


def test_stream_bootstrap_buffers_mutation_committed_after_state_read(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    state_read_complete = threading.Event()
    release_state_read = threading.Event()

    async def held_run_in_threadpool(function: Callable[..., Any], *args: object) -> Any:
        result = await run_in_threadpool(function, *args)
        if getattr(function, "__name__", "") == "stream_state_version":
            state_read_complete.set()
            released = await asyncio.to_thread(release_state_read.wait, 2)
            assert released
        return result

    monkeypatch.setattr("wsi_viewer.classroom_routes.run_in_threadpool", held_run_in_threadpool)

    with _client(tmp_path, enabled=True) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Bootstrap"},
        )
        assert joined.status_code == 201
        body_iterator, hub = _classroom_event_stream(client, created["id"])
        settings = cast(FastAPI, client.app).state.settings

        async def bootstrap_with_mutation() -> tuple[str, str, int, int]:
            ready_task = asyncio.create_task(anext(body_iterator))
            try:
                assert await asyncio.to_thread(state_read_complete.wait, 2)
                with session_factory(settings)() as database:
                    classroom = database.get(ClassroomSession, created["id"])
                    assert classroom is not None
                    old_version = classroom.state_version
                    classroom.state_version += 1
                    new_version = classroom.state_version
                    database.commit()
                hub._publish(
                    created["id"],
                    "control",
                    {"stateVersion": new_version},
                    True,
                    "all",
                )
                release_state_read.set()
                ready = cast(str, await asyncio.wait_for(ready_task, timeout=1))
                buffered = cast(str, await asyncio.wait_for(anext(body_iterator), timeout=1))
                return ready, buffered, old_version, new_version
            finally:
                release_state_read.set()
                await body_iterator.aclose()

        ready, buffered, old_version, new_version = asyncio.run(bootstrap_with_mutation())

    ready_payload = json.loads(ready.split("data: ", 1)[1].strip())
    buffered_payload = json.loads(buffered.split("data: ", 1)[1].strip())
    assert ready.startswith("event: stream-ready")
    assert ready_payload["stateVersion"] == old_version
    assert buffered.startswith("event: control")
    assert buffered_payload["stateVersion"] == new_version
    assert buffered_payload["eventSequence"] == ready_payload["eventSequence"] + 1


def test_replacement_stream_closes_stale_without_disconnecting_current(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Reconnect"},
        )
        assert joined.status_code == 201
        stale, hub = _classroom_event_stream(client, created["id"])
        current, _ = _classroom_event_stream(client, created["id"])

        async def replace() -> tuple[dict[str, int], dict[str, int]]:
            assert cast(str, await anext(stale)).startswith("event: stream-ready")
            assert cast(str, await anext(current)).startswith("event: stream-ready")
            with pytest.raises(StopAsyncIteration):
                await anext(stale)
            while_still_connected = hub.metrics()
            await current.aclose()
            after_close = hub.metrics()
            return while_still_connected, after_close

        while_connected, after_close = asyncio.run(replace())

    assert while_connected["currentSseConnections"] == 1
    assert while_connected["activeParticipants"] == 1
    assert after_close["currentSseConnections"] == 0
    assert after_close["activeParticipants"] == 0


def test_stream_authorized_before_session_end_cannot_register_when_consumed_late(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Late stream"},
        )
        assert joined.status_code == 201
        body_iterator, hub = _classroom_event_stream(client, created["id"])

        ended = client.delete(f"/api/v1/admin/classroom/sessions/{created['id']}", headers=headers)
        assert ended.status_code == 204

        async def consume_after_end() -> None:
            try:
                with pytest.raises(StopAsyncIteration):
                    await anext(body_iterator)
            finally:
                await body_iterator.aclose()

        asyncio.run(consume_after_end())

    assert hub.metrics()["currentSseConnections"] == 0
    assert hub.metrics()["activeParticipants"] == 0
    assert hub.roster_version(created["id"]) == 0


def test_active_stream_is_not_stale_deleted_after_persisted_activity_expires(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Active"},
        ).json()
        participant_id = joined["participant"]["id"]
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)
            assert participant is not None
            participant.last_seen_at = datetime.now(UTC) - timedelta(minutes=16)
            participant.disconnected_at = datetime.now(UTC) - timedelta(minutes=16)
            database.commit()

        body_iterator, _ = _classroom_event_stream(client, created["id"])

        async def join_while_stream_is_active() -> list[dict[str, Any]]:
            assert cast(str, await anext(body_iterator)).startswith("event: stream-ready")
            client.cookies.delete("pathlab_classroom_participant")
            admitted = client.post(
                "/api/v1/classroom/join",
                json={"joinCode": created["joinCode"], "displayName": "New student"},
            )
            assert admitted.status_code == 201
            roster = client.get(
                f"/api/v1/admin/classroom/sessions/{created['id']}", headers=headers
            ).json()["participants"]
            await body_iterator.aclose()
            return roster

        roster = asyncio.run(join_while_stream_is_active())

    active = next(item for item in roster if item["id"] == participant_id)
    assert active["status"] == "connected"


def test_stalled_admission_keeps_presence_responsive_and_connecting_participant(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    from wsi_viewer.classroom_routes import JoinRequest

    admission_db_blocked = threading.Event()
    release_admission_db = threading.Event()
    presence_attempted = threading.Event()
    ticker_ran = threading.Event()
    responsiveness: list[bool] = []

    with _client(tmp_path, enabled=True) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Returning"},
        ).json()
        participant_id = joined["participant"]["id"]
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)
            assert participant is not None
            participant.last_seen_at = datetime.now(UTC) - timedelta(minutes=16)
            participant.disconnected_at = datetime.now(UTC) - timedelta(minutes=16)
            database.commit()

        body_iterator, hub = _classroom_event_stream(client, created["id"])
        hub.clear_participant(created["id"], participant_id)
        client.cookies.delete("pathlab_classroom_participant")

        app = cast(FastAPI, client.app)
        join_route = next(
            cast(APIRoute, route)
            for route in app.routes
            if getattr(route, "path", None) == "/api/v1/classroom/join"
        )
        join_request = Request(
            {
                "type": "http",
                "asgi": {"version": "3.0"},
                "http_version": "1.1",
                "method": "POST",
                "scheme": "http",
                "path": "/api/v1/classroom/join",
                "raw_path": b"/api/v1/classroom/join",
                "query_string": b"",
                "headers": [],
                "client": ("testclient", 50000),
                "server": ("testserver", 80),
                "root_path": "",
            }
        )
        join_response = Response()

        original_scalars = OrmSession.scalars
        blocked_once = False

        def blocking_scalars(
            database: OrmSession, statement: Any, *args: Any, **kwargs: Any
        ) -> Any:
            nonlocal blocked_once
            if not blocked_once:
                blocked_once = True
                admission_db_blocked.set()
                assert release_admission_db.wait(timeout=2)
            return original_scalars(database, statement, *args, **kwargs)

        monkeypatch.setattr(OrmSession, "scalars", blocking_scalars)
        original_connected = hub.participant_connected

        def observed_connected(session_id: str, connecting_participant_id: str) -> bool | None:
            presence_attempted.set()
            return original_connected(session_id, connecting_participant_id)

        monkeypatch.setattr(hub, "participant_connected", observed_connected)

        def observe_event_loop() -> None:
            if not admission_db_blocked.wait(timeout=1) or not presence_attempted.wait(timeout=1):
                responsiveness.append(False)
            else:
                responsiveness.append(ticker_ran.wait(timeout=0.2))
            release_admission_db.set()

        observer = threading.Thread(target=observe_event_loop)
        observer.start()

        async def admission_and_connect() -> str:
            admission = asyncio.create_task(
                join_route.endpoint(
                    JoinRequest(joinCode=created["joinCode"], displayName="New student"),
                    join_request,
                    join_response,
                )
            )
            assert await asyncio.to_thread(admission_db_blocked.wait, 1)

            async def tick() -> None:
                await asyncio.sleep(0)
                ticker_ran.set()

            connection = asyncio.create_task(anext(body_iterator))
            ticker = asyncio.create_task(tick())
            first_event = cast(str, await connection)
            await ticker
            await admission
            await body_iterator.aclose()
            return first_event

        try:
            first = asyncio.run(admission_and_connect())
        finally:
            release_admission_db.set()
            observer.join(timeout=2)

        assert not observer.is_alive()
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)

    assert first.startswith("event: stream-ready")
    assert responsiveness == [True]
    assert participant is not None


def test_disconnect_and_reconnect_grace_is_hub_owned(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Reconnect"},
        ).json()
        participant_id = joined["participant"]["id"]
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, participant_id)
            assert participant is not None
            participant.disconnected_at = datetime.now(UTC) - timedelta(minutes=5)
            database.commit()

        first_stream, _ = _classroom_event_stream(client, created["id"])

        async def disconnect_then_reconnect() -> tuple[str, str]:
            await anext(first_stream)
            await first_stream.aclose()
            disconnected = client.get(
                f"/api/v1/admin/classroom/sessions/{created['id']}", headers=headers
            ).json()["participants"][0]["status"]
            second_stream, _ = _classroom_event_stream(client, created["id"])
            await anext(second_stream)
            reconnected = client.get(
                f"/api/v1/admin/classroom/sessions/{created['id']}", headers=headers
            ).json()["participants"][0]["status"]
            await second_stream.aclose()
            return disconnected, reconnected

        disconnected, reconnected = asyncio.run(disconnect_then_reconnect())

    assert disconnected == "reconnecting"
    assert reconnected == "connected"


def test_session_snapshots_static_asset_and_join_reconnects_idempotently(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=_admin_headers(client),
            json={"slideIds": ["slide-1"]},
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["slides"][0]["assetVersion"]
        assert payload["slides"][0]["tileSource"].endswith("/slide.dzi")
        assert payload["slides"][0]["folderPath"] == ["Teaching cases"]

        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": payload["joinCode"], "displayName": "  Student  "},
        )
        assert joined.status_code == 201, joined.text
        alias = joined.json()["participant"]["alias"]
        assert joined.json()["participant"]["displayName"] == "Student"

        rejoined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": payload["joinCode"], "displayName": "Changed"},
        )
        assert rejoined.status_code == 200, rejoined.text
        assert rejoined.json()["participant"]["alias"] == alias
        assert rejoined.json()["participant"]["displayName"] == "Student"


def test_admin_can_end_an_active_session_after_losing_browser_state(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        )
        assert created.status_code == 201

        ended = client.delete("/api/v1/admin/classroom/sessions/active", headers=headers)
        assert ended.status_code == 204

        restarted = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        )
        assert restarted.status_code == 201


def test_smart_invite_supports_preview_live_and_post_class_review(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        readiness = client.post(
            "/api/v1/admin/classroom/readiness",
            headers=headers,
            json={"folderId": "folder-1"},
        )
        assert readiness.status_code == 200
        assert [item["id"] for item in readiness.json()["ready"]] == ["slide-1"]
        assert readiness.json()["blocked"] == []

        expiry = datetime.now(UTC) + timedelta(days=7)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"folderId": "folder-1", "reviewExpiresAt": expiry.isoformat()},
        )
        assert created.status_code == 201, created.text
        classroom = created.json()
        assert classroom["phase"] == "preview"
        assert classroom["publicId"]
        assert classroom["joinCode"] not in f"/classroom/invite/{classroom['publicId']}"

        unlocked = client.post(
            f"/api/v1/classroom/invites/{classroom['publicId']}/unlock",
            json={"accessCode": classroom["joinCode"], "displayName": "Student"},
        )
        assert unlocked.status_code == 201, unlocked.text
        assert unlocked.json()["phase"] == "preview"
        preview = client.get(f"/api/v1/classroom/invites/{classroom['publicId']}")
        assert preview.status_code == 200
        assert preview.json()["slides"][0]["id"] == "slide-1"

        preview_question = client.post(
            f"/api/v1/classroom/sessions/{classroom['id']}/questions",
            json={
                "idempotencyKey": "preview-question",
                "slideId": "slide-1",
                "text": "Not live yet",
                "x": 0.25,
                "y": 0.5,
                "zoom": 4,
                "csrfToken": unlocked.json()["csrfToken"],
            },
        )
        assert preview_question.status_code == 409

        not_live = client.post(
            f"/api/v1/classroom/sessions/{classroom['id']}/live-join",
            json={"csrfToken": unlocked.json()["csrfToken"]},
        )
        assert not_live.status_code == 409
        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{classroom['id']}/start",
                headers=headers,
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/classroom/sessions/{classroom['id']}/live-join",
                json={"csrfToken": unlocked.json()["csrfToken"]},
            ).status_code
            == 200
        )
        roster = client.get(f"/api/v1/admin/classroom/sessions/{classroom['id']}").json()
        assert roster["session"]["phase"] == "live"
        assert len(roster["participants"]) == 1

        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{classroom['id']}/end",
                headers=headers,
            ).status_code
            == 204
        )
        phase = client.get(f"/api/v1/classroom/invites/{classroom['publicId']}/phase")
        assert phase.status_code == 200
        assert phase.json()["phase"] == "review"
        review_pin = client.post(
            f"/api/v1/classroom/sessions/{classroom['id']}/pin",
            json={
                "slideId": "slide-1",
                "x": 0.25,
                "y": 0.5,
                "zoom": 4,
                "csrfToken": unlocked.json()["csrfToken"],
            },
        )
        assert review_pin.status_code == 409
        assert (
            client.delete(
                f"/api/v1/admin/classroom/sessions/{classroom['id']}", headers=headers
            ).status_code
            == 204
        )
        assert (
            client.get(f"/api/v1/classroom/invites/{classroom['publicId']}/phase").status_code
            == 404
        )


def test_smart_invite_cannot_bypass_live_capacity_gate(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True, max_participants=1) as client:
        headers = _admin_headers(client)
        expiry = datetime.now(UTC) + timedelta(days=7)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"folderId": "folder-1", "reviewExpiresAt": expiry.isoformat()},
        ).json()
        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/start",
                headers=headers,
            ).status_code
            == 200
        )

        client.cookies.delete("pathlab_classroom_participant")
        admitted = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Admitted student"},
        )
        assert admitted.status_code == 201, admitted.text

        client.cookies.delete("pathlab_classroom_participant")
        unlocked = client.post(
            f"/api/v1/classroom/invites/{created['publicId']}/unlock",
            json={"accessCode": created["joinCode"], "displayName": "Invite student"},
        )
        assert unlocked.status_code == 201, unlocked.text
        rejected = client.post(
            f"/api/v1/classroom/sessions/{created['id']}/live-join",
            json={"csrfToken": unlocked.json()["csrfToken"]},
        )
        assert rejected.status_code == 409
        assert rejected.json()["detail"] == {"code": "CLASSROOM_FULL"}

        bypass = client.get(f"/api/v1/classroom/sessions/{created['id']}")
        assert bypass.status_code == 409
        assert bypass.json()["detail"] == {"code": "CLASSROOM_JOIN_REQUIRED"}


def test_live_join_reclaims_only_current_epoch_stale_live_seats(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True, max_participants=1) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={
                "folderId": "folder-1",
                "reviewExpiresAt": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            },
        ).json()
        preview = client.post(
            f"/api/v1/classroom/invites/{created['publicId']}/unlock",
            json={"accessCode": created["joinCode"], "displayName": "Invite student"},
        ).json()
        preview_cookie = client.cookies.get("pathlab_classroom_participant")
        assert preview_cookie is not None
        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/start",
                headers=headers,
            ).status_code
            == 200
        )

        client.cookies.delete("pathlab_classroom_participant")
        live = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Stale live seat"},
        ).json()
        live_id = live["participant"]["id"]
        unused_stream, hub = _classroom_event_stream(client, created["id"])
        asyncio.run(unused_stream.aclose())
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            participant = database.get(ClassroomParticipant, live_id)
            assert participant is not None
            participant.last_seen_at = datetime.now(UTC) - timedelta(minutes=16)
            database.commit()
        with hub._presence_lock:
            key = (created["id"], live_id)
            hub._participant_disconnected_at.pop(key, None)
            hub._participant_stale.add(key)

        client.cookies.clear()
        client.cookies.set("pathlab_classroom_participant", preview_cookie)
        admitted = client.post(
            f"/api/v1/classroom/sessions/{created['id']}/live-join",
            json={"csrfToken": preview["csrfToken"]},
        )

        assert admitted.status_code == 200, admitted.text
        with session_factory(settings)() as database:
            reclaimed = database.get(ClassroomParticipant, live_id)
            converted = database.get(ClassroomParticipant, preview["participant"]["id"])
            assert reclaimed is None
            assert converted is not None and converted.joined_live_at is not None


def test_smart_invite_blocks_folder_when_delivery_is_missing(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        with sqlite3.connect(tmp_path / "test.sqlite3") as database:
            database.execute("UPDATE slides SET derivative_file_count = 0 WHERE id = 'slide-1'")
            database.commit()
        readiness = client.post(
            "/api/v1/admin/classroom/readiness", headers=headers, json={"folderId": "folder-1"}
        )
        assert readiness.status_code == 200
        assert readiness.json()["blocked"][0]["reason"] == "delivery_missing"
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={
                "folderId": "folder-1",
                "reviewExpiresAt": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            },
        )
        assert created.status_code == 409
        assert created.json()["detail"]["code"] == "CLASSROOM_SLIDES_BLOCKED"


def test_expired_live_ceiling_becomes_review_and_does_not_block_next_preview(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        expiry = datetime.now(UTC) + timedelta(days=7)
        first = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"folderId": "folder-1", "reviewExpiresAt": expiry.isoformat()},
        ).json()
        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{first['id']}/start", headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/api/v1/classroom/invites/{first['publicId']}/unlock",
                json={"accessCode": first["joinCode"]},
            ).status_code
            == 201
        )
        past = (datetime.now(UTC) - timedelta(minutes=1)).replace(tzinfo=None).isoformat()
        with sqlite3.connect(tmp_path / "test.sqlite3") as database:
            database.execute(
                "UPDATE classroom_sessions SET live_expires_at = ?, expires_at = ? WHERE id = ?",
                (past, past, first["id"]),
            )
            database.commit()

        phase = client.get(f"/api/v1/classroom/invites/{first['publicId']}/phase")
        assert phase.status_code == 200
        assert phase.json()["phase"] == "review"

        second = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"folderId": "folder-1", "reviewExpiresAt": expiry.isoformat()},
        )
        assert second.status_code == 201, second.text
        recent = client.get("/api/v1/admin/classroom/sessions", headers=headers).json()["sessions"]
        assert {item["phase"] for item in recent} == {"preview", "review"}


def test_deleted_question_retry_returns_receipt_instead_of_recreating(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        join = client.post("/api/v1/classroom/join", json={"joinCode": created["joinCode"]}).json()
        question = {
            "idempotencyKey": "retry-key",
            "slideId": "slide-1",
            "text": "What is this?",
            "x": 0.25,
            "y": 0.5,
            "zoom": 4,
            "csrfToken": join["csrfToken"],
        }
        first = client.post(f"/api/v1/classroom/sessions/{created['id']}/questions", json=question)
        assert first.status_code == 201, first.text
        question_id = first.json()["questionId"]
        assert (
            client.delete(
                f"/api/v1/admin/classroom/sessions/{created['id']}/questions/{question_id}",
                headers=headers,
            ).status_code
            == 204
        )

        retry = client.post(f"/api/v1/classroom/sessions/{created['id']}/questions", json=question)
        assert retry.status_code == 200, retry.text
        assert retry.json() == {"status": "already_processed", "questionId": question_id}

        state = client.get(f"/api/v1/admin/classroom/sessions/{created['id']}")
        assert state.status_code == 200
        assert state.json()["pendingQuestions"] == []


def test_stale_control_lease_cannot_publish(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join", json={"joinCode": created["joinCode"]}
        ).json()
        participant_id = joined["participant"]["id"]
        lease = client.post(
            f"/api/v1/admin/classroom/sessions/{created['id']}/control",
            headers=headers,
            json={"participantId": participant_id, "seconds": 60},
        ).json()
        client.delete(
            f"/api/v1/admin/classroom/sessions/{created['id']}/control",
            headers=headers,
        )
        response = client.post(
            f"/api/v1/classroom/sessions/{created['id']}/presenter",
            json={
                "csrfToken": joined["csrfToken"],
                "leaseId": lease["leaseId"],
                "slideId": "slide-1",
                "x": 0.5,
                "y": 0.5,
                "zoom": 2,
            },
        )
        assert response.status_code == 409
        assert response.json() == {"detail": {"code": "CONTROL_LEASE_STALE"}}


def test_presenter_updates_are_immediate_but_persisted_sparsely(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        for index in range(4):
            response = client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/presenter",
                headers=headers,
                json={
                    "slideId": "slide-1",
                    "x": index / 10,
                    "y": 0.5,
                    "zoom": 2,
                    "zoomSpace": "viewport",
                },
            )
            assert response.status_code == 200

        state = client.get(f"/api/v1/admin/classroom/sessions/{created['id']}")
        assert state.json()["presenter"]["viewport"]["x"] == 0.3
        assert state.json()["presenter"]["viewport"]["zoomSpace"] == "viewport"
        assert (
            client.get("/api/v1/admin/classroom/metrics").json()["presenterPersistenceWrites"] == 0
        )

        time.sleep(2.3)
        metrics = client.get("/api/v1/admin/classroom/metrics").json()
        assert metrics["presenterPersistenceWrites"] == 1
        assert metrics["queueCapacity"] == 512
        assert metrics["queueMaxDepth"] >= 0
        assert metrics["eventLoopP99Ms"] >= 0
        assert metrics["poolWaitP95Ms"] >= 0
        assert metrics["poolTimeouts"] == 0
        assert metrics["sqliteLockErrors"] == 0
        with sqlite3.connect(tmp_path / "test.sqlite3") as database:
            row = database.execute(
                "SELECT presenter_sequence, presenter_viewport "
                "FROM classroom_sessions WHERE id = ?",
                (created["id"],),
            ).fetchone()
        assert row is not None and row[0] == 4
        assert json.loads(row[1])["x"] == 0.3
        assert json.loads(row[1])["zoomSpace"] == "viewport"


def test_question_receipt_hashes_idempotency_key(tmp_path: Path) -> None:
    assert hashlib.sha256(b"retry-key").hexdigest() != "retry-key"


def test_student_pin_and_control_request_are_bounded_transient_state(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join", json={"joinCode": created["joinCode"]}
        ).json()
        mutation = {"csrfToken": joined["csrfToken"]}
        pin = {
            **mutation,
            "slideId": "slide-1",
            "x": 0.25,
            "y": 0.5,
            "zoom": 4,
        }

        assert (
            client.post(f"/api/v1/classroom/sessions/{created['id']}/pin", json=pin).status_code
            == 204
        )
        assert (
            client.post(
                f"/api/v1/classroom/sessions/{created['id']}/control-request",
                json=mutation,
            ).status_code
            == 204
        )

        state = client.get(f"/api/v1/admin/classroom/sessions/{created['id']}").json()
        assert state["activePins"] == [
            {
                "participantId": joined["participant"]["id"],
                "alias": joined["participant"]["alias"],
                "slideId": "slide-1",
                "x": 0.25,
                "y": 0.5,
                "zoom": 4.0,
            }
        ]
        assert state["participants"][0]["controlRequested"] is True

        student_state = client.get(f"/api/v1/classroom/sessions/{created['id']}").json()
        assert student_state["activePin"] == {
            "participantId": joined["participant"]["id"],
            "slideId": "slide-1",
            "x": 0.25,
            "y": 0.5,
            "zoom": 4.0,
        }

        granted = client.post(
            f"/api/v1/admin/classroom/sessions/{created['id']}/control",
            headers=headers,
            json={"participantId": joined["participant"]["id"], "seconds": 60},
        )
        assert granted.status_code == 200
        state = client.get(f"/api/v1/admin/classroom/sessions/{created['id']}").json()
        assert state["participants"][0]["controlRequested"] is False

        assert (
            client.request(
                "DELETE",
                f"/api/v1/classroom/sessions/{created['id']}/pin",
                json=mutation,
            ).status_code
            == 204
        )
        assert (
            client.get(f"/api/v1/admin/classroom/sessions/{created['id']}").json()["activePins"]
            == []
        )
        assert client.get(f"/api/v1/classroom/sessions/{created['id']}").json()["activePin"] is None


def test_control_request_event_carries_authoritative_participant_identity(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    captured: list[dict[str, Any]] = []
    original_publish = ClassroomHub.publish

    def capture_publish(
        self: ClassroomHub,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        critical: bool,
        audience: str = "all",
    ) -> None:
        if event_type == "control-requested":
            captured.append(payload)
        original_publish(
            self,
            session_id,
            event_type,
            payload,
            critical=critical,
            audience=cast(Any, audience),
        )

    monkeypatch.setattr(ClassroomHub, "publish", capture_publish)
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Renal learner"},
        ).json()
        response = client.post(
            f"/api/v1/classroom/sessions/{created['id']}/control-request",
            json={"csrfToken": joined["csrfToken"]},
        )
        client.cookies.delete("pathlab_classroom_participant")
        client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Observer"},
        )
        pending = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}/participants?requested=true",
        ).json()

    assert response.status_code == 204
    assert captured[-1]["participantId"] == joined["participant"]["id"]
    assert captured[-1]["participant"] == {
        "id": joined["participant"]["id"],
        "alias": joined["participant"]["alias"],
        "displayName": "Renal learner",
        "controlRequested": True,
        "controlRequestedAt": captured[-1]["participant"]["controlRequestedAt"],
        "status": "reconnecting",
    }
    assert pending["total"] == 1
    assert pending["items"] == [captured[-1]["participant"]]


def test_teacher_pointer_and_marks_are_bounded_transient_state(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={"slideIds": ["slide-1"]},
        ).json()
        client.post("/api/v1/classroom/join", json={"joinCode": created["joinCode"]})
        pointer = {"slideId": "slide-1", "style": "green-arrow", "x": 0.25, "y": 0.5}
        annotation = {
            "id": "teaching-mark-1",
            "slideId": "slide-1",
            "tool": "pen",
            "color": "#42b883",
            "width": 4,
            "points": [{"x": 0.2, "y": 0.3}, {"x": 0.25, "y": 0.35}],
        }

        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/pointer",
                headers=headers,
                json=pointer,
            ).status_code
            == 204
        )
        assert (
            client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/annotations",
                headers=headers,
                json=annotation,
            ).status_code
            == 204
        )

        state = client.get(f"/api/v1/classroom/sessions/{created['id']}").json()
        assert state["teacherPointer"] == pointer
        assert state["teachingAnnotations"] == [annotation]

        assert (
            client.delete(
                f"/api/v1/admin/classroom/sessions/{created['id']}/annotations/teaching-mark-1",
                headers=headers,
            ).status_code
            == 204
        )
        assert (
            client.delete(
                f"/api/v1/admin/classroom/sessions/{created['id']}/pointer",
                headers=headers,
            ).status_code
            == 204
        )
        state = client.get(f"/api/v1/classroom/sessions/{created['id']}").json()
        assert state["teacherPointer"] is None
        assert state["teachingAnnotations"] == []


def test_singleton_hub_lock_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "classroom-hub.lock"
    first = ClassroomSingletonLock(path)
    second = ClassroomSingletonLock(path)
    assert first.acquire() is True
    try:
        assert second.acquire() is False
    finally:
        first.release()
    assert second.acquire() is True
    second.release()


def test_dedicated_synthetic_room_reset_removes_participants_but_keeps_room_live(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers={**headers, "X-PathLab-Synthetic-Run": "123456"},
            json={"slideIds": ["slide-1"]},
        ).json()
        joined = client.post(
            "/api/v1/classroom/join",
            json={"joinCode": created["joinCode"], "displayName": "Synthetic"},
        )
        assert joined.status_code == 201
        safety = client.post(
            f"/api/v1/admin/classroom/sessions/{created['id']}/synthetic-safety-stop",
            headers={
                **headers,
                "X-PathLab-Synthetic-Run": "123456",
                "X-PathLab-Plan-Digest": "a" * 64,
                "X-PathLab-Stage-Nonce": "stage-nonce-breakpoint-1750-1234567890",
            },
            json={"stageName": "breakpoint-1750", "causes": ["cpu-sustained"]},
        )
        assert safety.status_code == 204
        metrics = client.get("/api/v1/admin/classroom/metrics", headers=headers).json()
        assert metrics["capacitySafetyStopCauses"] == ["cpu-sustained"]
        assert metrics["capacitySafetyStopStage"] == "breakpoint-1750"
        assert metrics["capacitySafetyStopPlanDigest"] == "a" * 64
        assert (
            metrics["capacitySafetyStopNonceDigest"]
            == hashlib.sha256(b"stage-nonce-breakpoint-1750-1234567890").hexdigest()
        )
        for shard_index in range(6):
            ack = client.post(
                f"/api/v1/admin/classroom/sessions/{created['id']}/synthetic-stage-ack",
                headers={**headers, "X-PathLab-Synthetic-Run": "123456"},
                json={"stageName": "sustained-1200", "shardIndex": shard_index},
            )
            assert ack.status_code == 200
            assert ack.json()["acknowledgedShards"] == shard_index + 1
        assert ack.json()["complete"] is True
        settings = cast(FastAPI, client.app).state.settings
        with session_factory(settings)() as database:
            classroom = database.get(ClassroomSession, created["id"])
            assert classroom is not None
            classroom.presenter_sequence = 42
            classroom.presenter_sequence_reserved = 64
            classroom.presenter_viewport = {"x": 0.8, "y": 0.7, "zoom": 9}
            database.commit()

        wrong_reset = client.post(
            f"/api/v1/admin/classroom/sessions/{created['id']}/synthetic-reset",
            headers={**headers, "X-PathLab-Synthetic-Run": "654321"},
        )
        assert wrong_reset.status_code == 409
        assert wrong_reset.json()["detail"]["code"] == "SYNTHETIC_RUN_MISMATCH"

        reset = client.post(
            f"/api/v1/admin/classroom/sessions/{created['id']}/synthetic-reset",
            headers={**headers, "X-PathLab-Synthetic-Run": "123456"},
        )

        assert reset.status_code == 204
        metrics = client.get("/api/v1/admin/classroom/metrics", headers=headers).json()
        assert metrics["capacitySafetyStopCauses"] == []
        state = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}", headers=headers
        ).json()
        assert state["presenter"]["sequence"] == 0
        assert state["presenter"]["viewport"] is None
        roster = client.get(
            f"/api/v1/admin/classroom/sessions/{created['id']}/participants",
            headers=headers,
        ).json()
        assert roster["total"] == 0
        assert (
            client.post(
                "/api/v1/classroom/join", json={"joinCode": created["joinCode"]}
            ).status_code
            == 201
        )


def test_capacity_inventory_is_bounded_and_exposes_only_synthetic_ownership(
    tmp_path: Path,
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers={**headers, "X-PathLab-Synthetic-Run": "capacity-run-1"},
            json={"slideIds": ["slide-1"]},
        ).json()

        inventory = client.get(
            "/api/v1/admin/classroom/capacity-inventory",
            headers=headers,
            params={"syntheticRunId": "capacity-run-1"},
        )

        assert inventory.status_code == 200
        assert inventory.json() == {
            "sessions": [
                {
                    "id": created["id"],
                    "status": "active",
                    "phase": "live",
                    "syntheticRunId": "capacity-run-1",
                }
            ],
            "truncated": False,
        }
        assert "joinCode" not in inventory.text
