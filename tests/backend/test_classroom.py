import hashlib
import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import text
from wsi_viewer.classroom_runtime import ClassroomSingletonLock
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import Folder, PublicationGrant, Slide, User
from wsi_viewer.publication import delivery_version
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _client(tmp_path: Path, *, enabled: bool) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        classroom_enabled=enabled,
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


def test_classroom_routes_are_absent_when_disabled(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=False) as client:
        assert client.post("/api/v1/classroom/join", json={"joinCode": "ABC123"}).status_code == 404


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
