import csv
import io
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from test_study_coach import _admin, _client, _publish_pack, _slide
from wsi_viewer.database import session_factory
from wsi_viewer.models import StudyLearnerSession, StudyReadinessAggregate
from wsi_viewer.study_routes import AiEventReport, ReadinessReport


@pytest.fixture(params=["sqlite", "postgresql"])
def study_database_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path / 'study.sqlite3'}"
        return
    configured = os.getenv("PATHLAB_POSTGRES_TEST_URL")
    if not configured:
        pytest.skip("isolated PostgreSQL required")
    schema = "study_concurrency_" + uuid4().hex
    engine = create_engine(configured)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(configured).update_query_dict({"options": f"-c search_path={schema}"})
    try:
        yield url.render_as_string(hide_password=False)
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("writer", ["readiness", "ai", "mixed"])
def test_concurrent_reports_preserve_every_allowed_counter(
    tmp_path: Path, existing: bool, writer: str, study_database_url: str,
) -> None:
    with _client(
        tmp_path, ai_enabled=True, pilot_enabled=True, database_url=study_database_url,
    ) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Synthetic aggregate concurrency",
                "learnerLimit": 2,
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
            f"/api/v1/admin/study/courses/{course_id}/invitations", headers=admin, json={"count": 2}
        )
        assert exported.status_code == 200
        codes = [row["invitation_code"] for row in csv.DictReader(io.StringIO(exported.text))]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin
            ).status_code
            == 200
        )
        for code in codes:
            client.cookies.delete("pathlab-study-session")
            joined = client.post(
                "/api/v1/study/redeem", json={"code": code, "noticeAccepted": True}
            )
            assert joined.status_code == 201
            assert (
                client.post(
                    "/api/v1/study/tasks/task-1/submit",
                    headers={"X-Study-CSRF": joined.json()["csrfToken"]},
                    json={"selectedOption": "Approved"},
                ).status_code
                == 200
            )
        factory = session_factory(client.app.state.settings)
        with factory() as database:
            ids = list(database.scalars(select(StudyLearnerSession.id)))
            if existing:
                database.add(
                    StudyReadinessAggregate(
                        course_id=course_id, ready_count=1, fallback_count=1, continue_count=1
                    )
                )
                database.commit()
        endpoints = {
            route.path: route.endpoint
            for route in client.app.routes
            if getattr(route, "path", "") in {"/api/v1/study/readiness", "/api/v1/study/ai-events"}
            and "POST" in route.methods
        }
        start, aggregate_read = threading.Barrier(2), threading.Barrier(2)

        class PausedSession(Session):
            def scalar(self, statement, *args, **kwargs):
                result = super().scalar(statement, *args, **kwargs)
                if any(
                    item.get("entity") is StudyReadinessAggregate
                    for item in getattr(statement, "column_descriptions", [])
                ):
                    aggregate_read.wait(3)
                return result

        def report(index):
            with PausedSession(bind=factory.kw["bind"]) as database:
                stored = database.get(StudyLearnerSession, ids[index])
                start.wait(3)
                path = (
                    "/api/v1/study/readiness"
                    if writer == "readiness" or (writer == "mixed" and index == 0)
                    else "/api/v1/study/ai-events"
                )
                payload = (
                    ReadinessReport(outcome="ready")
                    if path.endswith("readiness")
                    else AiEventReport(taskId="task-1", outcome="continue")
                )
                endpoints[path](payload, stored, database)

        with ThreadPoolExecutor(2) as pool:
            list(pool.map(report, range(2)))
        with factory() as database:
            aggregate = database.scalar(select(StudyReadinessAggregate))
            initial = int(existing)
            assert aggregate.ready_count == initial + (
                2 if writer == "readiness" else 1 if writer == "mixed" else 0
            )
            assert aggregate.continue_count == initial + (
                2 if writer == "ai" else 1 if writer == "mixed" else 0
            )
            assert aggregate.fallback_count == initial
            assert len(list(database.scalars(select(StudyReadinessAggregate)))) == 1
