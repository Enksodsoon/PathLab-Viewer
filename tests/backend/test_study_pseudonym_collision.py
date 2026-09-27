import csv
import io
import os
from pathlib import Path

import pytest
from sqlalchemy import select, text
from test_study_coach import _admin, _client, _publish_pack, _slide
from wsi_viewer import study_routes
from wsi_viewer.config import Settings
from wsi_viewer.database import engine_for, session_factory
from wsi_viewer.models import Base, StudyInvitation, StudyLearnerSession


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
@pytest.mark.parametrize("exhausted", [False, True])
def test_pseudonym_collision_retries_without_consuming_invitation(
    tmp_path: Path, monkeypatch, exhausted: bool, backend: str,
):
    database_url = None
    if backend == "postgres":
        database_url = os.getenv("PATHLAB_POSTGRES_TEST_URL")
        if database_url is None:
            pytest.skip("PATHLAB_POSTGRES_TEST_URL is required for isolated PostgreSQL")
        settings = Settings(_env_file=None, database_url=database_url)
        engine = engine_for(settings)
        Base.metadata.drop_all(engine)
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    with _client(tmp_path, database_url=database_url) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        created = client.post(
            "/api/v1/admin/study/courses", headers=admin,
            json={"packId": pack["id"], "title": "Synthetic collision", "learnerLimit": 2},
        )
        assert created.status_code == 201
        course_id = created.json()["id"]
        assert client.post(
            f"/api/v1/admin/study/courses/{course_id}/prepare", headers=admin,
        ).status_code == 200
        invitations = client.post(
            f"/api/v1/admin/study/courses/{course_id}/invitations", headers=admin,
            json={"count": 2},
        )
        assert invitations.status_code == 200
        codes = [row["invitation_code"] for row in csv.DictReader(io.StringIO(invitations.text))]
        assert client.post(
            f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin,
        ).status_code == 200
        monkeypatch.setattr(study_routes.secrets, "token_hex", lambda size: "1234ABCD")
        assert client.post(
            "/api/v1/study/redeem", json={"code": codes[0], "noticeAccepted": True},
        ).status_code == 201
        attempts = []

        def candidate(size):
            attempts.append(size)
            return "1234ABCD" if exhausted or len(attempts) == 1 else "ABCD5678"

        monkeypatch.setattr(study_routes.secrets, "token_hex", candidate)
        response = client.post(
            "/api/v1/study/redeem", json={"code": codes[1], "noticeAccepted": True},
        )
        assert response.status_code == (503 if exhausted else 201)
        assert len(attempts) == (8 if exhausted else 2)
        factory = session_factory(client.app.state.settings)
        with factory() as database:
            assert len(list(database.scalars(select(StudyLearnerSession.id)))) == (
                1 if exhausted else 2
            )
            assert list(database.scalars(select(StudyInvitation.status))).count("issued") == int(
                exhausted
            )
        if exhausted:
            assert response.json()["detail"]["code"] == "STUDY_BUSY"
            assert response.headers["Retry-After"] == "1"
            monkeypatch.setattr(study_routes.secrets, "token_hex", lambda size: "ABCD5678")
            assert client.post(
                "/api/v1/study/redeem", json={"code": codes[1], "noticeAccepted": True},
            ).status_code == 201
        assert client.post(
            "/api/v1/study/redeem", json={"code": codes[1], "noticeAccepted": True},
        ).status_code == 404
