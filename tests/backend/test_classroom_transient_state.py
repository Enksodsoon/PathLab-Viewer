from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session
from test_classroom import _admin_headers, _client
from wsi_viewer.classroom_hub import ClassroomHub
from wsi_viewer.database import session_factory
from wsi_viewer.models import ClassroomQuestion, ClassroomSession


@pytest.mark.parametrize("mode", ["matching", "newer_pin", "commit_failed"])
def test_question_clears_only_matching_pin_after_durable_ack(
    tmp_path: Path, monkeypatch, mode: str
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions", headers=headers, json={"slideIds": ["slide-1"]}
        ).json()
        session_id = created["id"]
        first = client.post("/api/v1/classroom/join", json={"joinCode": created["joinCode"]}).json()
        first_cookies = dict(client.cookies)
        pin = {
            "csrfToken": first["csrfToken"],
            "slideId": "slide-1",
            "x": 0.3 if mode == "newer_pin" else 0.25,
            "y": 0.5,
            "zoom": 4,
        }
        assert (
            client.post(f"/api/v1/classroom/sessions/{session_id}/pin", json=pin).status_code == 204
        )
        client.cookies.clear()
        # A second participant's matching coordinates must never be cleared.
        second = client.post(
            "/api/v1/classroom/join", json={"joinCode": created["joinCode"]}
        ).json()
        assert (
            client.post(
                f"/api/v1/classroom/sessions/{session_id}/pin",
                json={**pin, "csrfToken": second["csrfToken"], "x": 0.25},
            ).status_code
            == 204
        )
        client.cookies.clear()
        client.cookies.update(first_cookies)
        settings = client.app.state.settings
        published = []
        original_publish = ClassroomHub.publish

        def publish(hub, session, name, payload, **kwargs):
            if name in {"question-added", "pin-removed"}:
                with session_factory(settings)() as database:
                    assert database.scalar(select(ClassroomQuestion.id)) is not None
                published.append(name)
            return original_publish(hub, session, name, payload, **kwargs)

        monkeypatch.setattr(ClassroomHub, "publish", publish)

        def reject_commit(database):
            raise RuntimeError("synthetic durable question failure")

        if mode == "commit_failed":
            event.listen(Session, "before_commit", reject_commit)
        try:
            question = {
                "csrfToken": first["csrfToken"],
                "idempotencyKey": "synthetic-key",
                "slideId": "slide-1",
                "text": "What is this?",
                "x": 0.25,
                "y": 0.5,
                "zoom": 4,
            }
            if mode == "commit_failed":
                with pytest.raises(RuntimeError, match="synthetic durable question failure"):
                    client.post(f"/api/v1/classroom/sessions/{session_id}/questions", json=question)
            else:
                assert (
                    client.post(
                        f"/api/v1/classroom/sessions/{session_id}/questions", json=question
                    ).status_code
                    == 201
                )
        finally:
            if mode == "commit_failed":
                event.remove(Session, "before_commit", reject_commit)
        state = client.get(f"/api/v1/admin/classroom/sessions/{session_id}", headers=headers).json()
        remaining = {pin["participantId"] for pin in state["activePins"]}
        assert second["participant"]["id"] in remaining
        assert (first["participant"]["id"] in remaining) == (mode != "matching")
        assert published == (
            []
            if mode == "commit_failed"
            else ["question-added", "pin-removed"]
            if mode == "matching"
            else ["question-added"]
        )


def test_teacher_snapshot_expires_controller_once_and_publishes_durable_state(
    tmp_path: Path, monkeypatch
) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions", headers=headers, json={"slideIds": ["slide-1"]}
        ).json()
        joined = client.post(
            "/api/v1/classroom/join", json={"joinCode": created["joinCode"]}
        ).json()
        session_id = created["id"]
        lease = client.post(
            f"/api/v1/admin/classroom/sessions/{session_id}/control",
            headers=headers,
            json={"participantId": joined["participant"]["id"], "seconds": 60},
        )
        assert lease.status_code == 200
        settings = client.app.state.settings
        with session_factory(settings)() as database:
            session = database.get(ClassroomSession, session_id)
            epoch, version = session.control_epoch, session.state_version
            session.controller_expires_at = datetime.now(UTC) - timedelta(seconds=1)
            database.commit()
        events = []
        original_publish = ClassroomHub.publish

        def publish(hub, session_id, name, payload, **kwargs):
            if name == "control":
                with session_factory(settings)() as database:
                    assert (
                        database.get(ClassroomSession, session_id).controller_participant_id is None
                    )
                events.append(payload)
            return original_publish(hub, session_id, name, payload, **kwargs)

        monkeypatch.setattr(ClassroomHub, "publish", publish)
        for _ in range(2):
            response = client.get(f"/api/v1/admin/classroom/sessions/{session_id}", headers=headers)
            assert response.status_code == 200
            assert response.json()["controller"] == {
                "participantId": None,
                "leaseId": None,
                "expiresAt": None,
                "controlEpoch": epoch + 1,
            }
            assert response.json()["stateVersion"] == version + 1
        assert len(events) == 1
