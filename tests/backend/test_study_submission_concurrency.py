import csv
import io
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_study_aggregate_concurrency import study_database_url  # noqa: F401
from test_study_coach import _admin, _client, _publish_pack, _slide
from wsi_viewer.database import session_factory
from wsi_viewer.models import StudyLearnerSession, StudyProgress
from wsi_viewer.study_routes import TaskSubmission


@pytest.mark.parametrize("seeded", [False, True])
def test_competing_task_submissions_preserve_progress_and_throttle(
    tmp_path, seeded, study_database_url,  # noqa: F811
):
    with _client(tmp_path, database_url=study_database_url) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        created = client.post(
            "/api/v1/admin/study/courses", headers=admin,
            json={"packId": pack["id"], "title": "Synthetic concurrency", "learnerLimit": 1},
        )
        assert created.status_code == 201
        course_id = created.json()["id"]
        assert client.post(
            f"/api/v1/admin/study/courses/{course_id}/prepare", headers=admin,
        ).status_code == 200
        exported = client.post(
            f"/api/v1/admin/study/courses/{course_id}/invitations", headers=admin,
            json={"count": 1},
        )
        assert exported.status_code == 200
        code = next(csv.DictReader(io.StringIO(exported.text)))["invitation_code"]
        assert client.post(
            f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin,
        ).status_code == 200
        assert client.post(
            "/api/v1/study/redeem", json={"code": code, "noticeAccepted": True},
        ).status_code == 201
        factory = session_factory(client.app.state.settings)
        endpoint = next(
            route.endpoint for route in client.app.routes
            if getattr(route, "path", "") == "/api/v1/study/tasks/{task_id}/submit"
        )
        with factory() as database:
            session_id = database.scalar(select(StudyLearnerSession.id))
            if seeded:
                database.add(StudyProgress(
                    session_id=session_id, task_id="task-1", status="attempted",
                    latest_correctness=False, attempt_count=1,
                ))
                database.commit()
        start = threading.Barrier(2)

        class PausedSession(Session):
            def scalar(self, statement, *args, **kwargs):
                result = super().scalar(statement, *args, **kwargs)
                if any(
                    item.get("entity") is StudyProgress
                    for item in getattr(statement, "column_descriptions", [])
                ):
                    time.sleep(0.1)
                return result

        def submit(_):
            with PausedSession(bind=factory.kw["bind"]) as database:
                stored = database.get(StudyLearnerSession, session_id)
                start.wait(3)
                try:
                    result = endpoint(
                        "task-1", TaskSubmission(selected_option="Approved"), stored, database,
                    )
                    assert result["attemptCount"] == 1 + int(seeded)
                    return 200
                except HTTPException as error:
                    assert error.detail["code"] == "STUDY_SUBMISSION_THROTTLED"
                    return error.status_code

        with ThreadPoolExecutor(2) as pool:
            assert sorted(pool.map(submit, range(2))) == [200, 429]
        with factory() as database:
            progress = database.scalar(select(StudyProgress))
            assert progress.attempt_count == 1 + int(seeded)
            assert progress.latest_correctness is True
