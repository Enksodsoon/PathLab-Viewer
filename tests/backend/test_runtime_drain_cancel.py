from datetime import UTC, datetime, timedelta

from test_classroom import _admin_headers, _client
from wsi_viewer.database import session_factory
from wsi_viewer.models import Job, RuntimeGuard
from wsi_viewer.runtime_protection import (
    CLASSROOM_GUARD_ID,
    COOLDOWN,
    DRAINING,
    IDLE,
    protection_snapshot,
)
from wsi_viewer.worker import background_work_is_allowed


def test_canceling_preview_drain_cools_down_then_resumes_background(tmp_path):
    with _client(tmp_path, enabled=True, protection_enabled=True) as client:
        headers = _admin_headers(client)
        factory = session_factory(client.app.state.settings)
        created = client.post(
            "/api/v1/admin/classroom/sessions",
            headers=headers,
            json={
                "folderId": "folder-1",
                "reviewExpiresAt": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
        assert created.status_code == 201
        session_id = created.json()["id"]
        with factory() as database:
            running = Job(slide_id="slide-1", kind="ingest", status="running")
            queued = Job(slide_id="slide-1", kind="ingest", status="queued")
            database.add_all([running, queued])
            database.commit()
            running_id, queued_id = running.id, queued.id
        start = client.post(f"/api/v1/admin/classroom/sessions/{session_id}/start", headers=headers)
        assert start.status_code == 409
        assert start.json()["detail"]["code"] == "CLASSROOM_DRAINING"
        with factory() as database:
            database.get(Job, running_id).status = "succeeded"
            database.commit()
        # Completing the worker drain must not release a still-active preview.
        assert not background_work_is_allowed(factory, enabled=True)
        with factory() as database:
            guard = database.get(RuntimeGuard, CLASSROOM_GUARD_ID)
            assert guard.mode == DRAINING
            assert guard.classroom_session_id == session_id
            assert database.get(Job, queued_id).status == "blocked_classroom"
        assert (
            client.delete(
                f"/api/v1/admin/classroom/sessions/{session_id}", headers=headers
            ).status_code
            == 204
        )
        assert not background_work_is_allowed(factory, enabled=True)
        with factory() as database:
            guard = database.get(RuntimeGuard, CLASSROOM_GUARD_ID)
            assert guard.mode == COOLDOWN
            assert guard.classroom_session_id is None
            until = guard.cooldown_until
            assert until is not None
        with factory() as database:
            assert (
                protection_snapshot(database, now=until - timedelta(microseconds=1)).mode
                == COOLDOWN
            )
            database.commit()
        with factory() as database:
            assert protection_snapshot(database, now=until).mode == IDLE
            database.commit()
            assert database.get(Job, queued_id).status == "queued"
