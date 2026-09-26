from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session
from test_classroom import _admin_headers, _client
from wsi_viewer.classroom_hub import ClassroomHub
from wsi_viewer.database import session_factory
from wsi_viewer.models import ClassroomSession


def test_teaching_mutations_advance_durable_snapshot_version(tmp_path: Path, monkeypatch) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions", headers=headers, json={"slideIds": ["slide-1"]}
        ).json()
        sid = created["id"]
        route = f"/api/v1/admin/classroom/sessions/{sid}/annotations"
        annotation = {
            "id": "teaching-mark",
            "slideId": "slide-1",
            "tool": "pen",
            "color": "#42b883",
            "width": 4,
            "points": [{"x": 0.2, "y": 0.3}, {"x": 0.25, "y": 0.35}],
        }
        settings = client.app.state.settings

        def snapshot():
            return client.get(f"/api/v1/admin/classroom/sessions/{sid}", headers=headers).json()

        version = snapshot()["stateVersion"]
        published = []
        original = ClassroomHub.publish

        def publish(hub, session, name, payload, **kwargs):
            if name.startswith("teaching-annotation"):
                with session_factory(settings)() as database:
                    assert (
                        payload["stateVersion"] == database.get(ClassroomSession, sid).state_version
                    )
                published.append(payload["stateVersion"])
            return original(hub, session, name, payload, **kwargs)

        monkeypatch.setattr(ClassroomHub, "publish", publish)
        for method, url, payload in [
            ("post", route, annotation),
            ("delete", route + "/teaching-mark", None),
            ("post", route, annotation),
            ("delete", route, None),
        ]:
            kwargs = {"json": payload} if payload else {}
            response = getattr(client, method)(url, headers=headers, **kwargs)
            assert response.status_code == 204
            version += 1
            assert snapshot()["stateVersion"] == version
        assert published == list(range(version - 3, version + 1))
        assert snapshot()["teachingAnnotations"] == []
        assert client.delete(route, headers=headers).status_code == 204
        assert snapshot()["stateVersion"] == version

        def reject_commit(_database):
            raise RuntimeError("synthetic annotation commit failure")

        event.listen(Session, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic annotation commit failure"):
                client.post(route, headers=headers, json=annotation)
        finally:
            event.remove(Session, "before_commit", reject_commit)
        assert snapshot()["stateVersion"] == version
        assert snapshot()["teachingAnnotations"] == []
        assert len(published) == 4


@pytest.mark.parametrize("operation", ["remove", "clear"])
def test_failed_teaching_removal_keeps_transient_snapshot(tmp_path: Path, operation: str) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _admin_headers(client)
        sid = client.post(
            "/api/v1/admin/classroom/sessions", headers=headers, json={"slideIds": ["slide-1"]}
        ).json()["id"]
        route = f"/api/v1/admin/classroom/sessions/{sid}/annotations"
        annotation = {
            "id": "teaching-mark",
            "slideId": "slide-1",
            "tool": "pen",
            "color": "#42b883",
            "width": 4,
            "points": [{"x": 0.2, "y": 0.3}, {"x": 0.25, "y": 0.35}],
        }
        assert client.post(route, headers=headers, json=annotation).status_code == 204
        before = client.get(f"/api/v1/admin/classroom/sessions/{sid}", headers=headers).json()

        def reject_commit(_database):
            raise RuntimeError("synthetic removal commit failure")

        event.listen(Session, "before_commit", reject_commit)
        try:
            with pytest.raises(RuntimeError, match="synthetic removal commit failure"):
                client.delete(
                    route + ("/teaching-mark" if operation == "remove" else ""), headers=headers
                )
        finally:
            event.remove(Session, "before_commit", reject_commit)
        after = client.get(f"/api/v1/admin/classroom/sessions/{sid}", headers=headers).json()
        assert after["stateVersion"] == before["stateVersion"]
        assert after["teachingAnnotations"] == [annotation]
