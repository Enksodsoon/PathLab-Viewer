import csv
import inspect
import io
from pathlib import Path
from types import SimpleNamespace

from test_study_coach import _admin, _client, _publish_pack, _slide
from wsi_viewer import study_routes


def test_completed_rate_windows_do_not_retain_previous_learner_keys(
    tmp_path: Path, monkeypatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr(study_routes, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    with _client(tmp_path, ai_enabled=True, pilot_enabled=True) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Synthetic throttle course",
                "learnerLimit": 3,
                "aiMode": "closed_pilot_trace_sim",
                "pilotAcknowledged": True,
            },
        )
        assert course.status_code == 201
        course_id = course.json()["id"]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/prepare", headers=admin
            ).status_code
            == 200
        )
        exported = client.post(
            f"/api/v1/admin/study/courses/{course_id}/invitations", headers=admin, json={"count": 3}
        )
        assert exported.status_code == 200
        codes = [row["invitation_code"] for row in csv.DictReader(io.StringIO(exported.text))]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin
            ).status_code
            == 200
        )
        submission_route = next(
            route
            for route in client.app.routes
            if getattr(route, "path", "") == "/api/v1/study/tasks/{task_id}/submit"
        )
        ai_route = next(
            route
            for route in client.app.routes
            if getattr(route, "path", "") == "/api/v1/study/ai-events"
        )
        submission_times = inspect.getclosurevars(submission_route.endpoint).nonlocals[
            "submission_times"
        ]
        ai_event_times = inspect.getclosurevars(ai_route.endpoint).nonlocals["ai_event_times"]
        for code in codes:
            clock[0] += study_routes.SUBMISSION_INTERVAL_SECONDS + 1
            client.cookies.delete("pathlab-study-session")
            learner = client.post(
                "/api/v1/study/redeem", json={"code": code, "noticeAccepted": True}
            )
            assert learner.status_code == 201, learner.text
            csrf = {"X-Study-CSRF": learner.json()["csrfToken"]}

            def submit(headers=csrf):
                return client.post(
                    "/api/v1/study/tasks/task-1/submit",
                    headers=headers,
                    json={"selectedOption": "Approved"},
                )

            def ai(headers=csrf):
                return client.post(
                    "/api/v1/study/ai-events",
                    headers=headers,
                    json={"taskId": "task-1", "outcome": "continue"},
                )

            assert submit().status_code == 200
            assert submit().status_code == 429
            assert ai().status_code == 204
            assert ai().status_code == 409
            assert len(submission_times) == 1
            assert len(ai_event_times) == 1
        courses = client.get("/api/v1/admin/study/courses").json()
        assert courses[0]["learnerLimit"] == 3
        assert courses[0]["invitations"] == 3
        assert courses[0]["redeemed"] == 3
