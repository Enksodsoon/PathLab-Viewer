import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session
from test_classroom import _admin_headers, _client
from wsi_viewer.classroom_hub import ClassroomHub
from wsi_viewer.config import Settings
from wsi_viewer.database import engine_for, session_factory
from wsi_viewer.models import Base, ClassroomSession
from wsi_viewer.time_support import utc_now


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_stale_student_snapshot_cannot_expire_a_new_teacher_control_grant(
    tmp_path: Path, monkeypatch, backend: str,
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
    with _client(tmp_path, enabled=True, database_url=database_url) as client:
        admin = _admin_headers(client)
        created = client.post(
            "/api/v1/admin/classroom/sessions", headers=admin,
            json={"slideIds": ["slide-1"]},
        )
        assert created.status_code == 201
        classroom = created.json()
        joined = client.post(
            "/api/v1/classroom/join", json={"joinCode": classroom["joinCode"]},
        )
        assert joined.status_code == 201
        participant_id = joined.json()["participant"]["id"]
        url = f"/api/v1/admin/classroom/sessions/{classroom['id']}/control"
        payload = {"participantId": participant_id, "seconds": 60}
        assert client.post(url, headers=admin, json=payload).status_code == 200
        factory = session_factory(client.app.state.settings)
        with factory() as database:
            stored = database.get(ClassroomSession, classroom["id"])
            stored.controller_expires_at = utc_now() - timedelta(seconds=1)
            database.commit()

        observed = threading.Event()
        release = threading.Event()
        guard = threading.Lock()
        armed = [True]
        native_get = Session.get
        native_publish = ClassroomHub.publish
        control_events = []

        def observed_publish(hub, session_id, event_type, payload, **kwargs):
            if event_type == "control":
                control_events.append(dict(payload))
            return native_publish(hub, session_id, event_type, payload, **kwargs)

        def paused_get(database, entity, identity, *args, **kwargs):
            row = native_get(database, entity, identity, *args, **kwargs)
            pause = False
            if entity is ClassroomSession:
                with guard:
                    if armed[0]:
                        armed[0] = False
                        pause = True
            if pause:
                observed.set()
                assert release.wait(5), "Student read was not released"
            return row

        monkeypatch.setattr(Session, "get", paused_get)
        monkeypatch.setattr(ClassroomHub, "publish", observed_publish)
        with ThreadPoolExecutor(1) as executor:
            pending = executor.submit(
                client.get, f"/api/v1/classroom/sessions/{classroom['id']}",
            )
            try:
                assert observed.wait(5), "Student did not read the expired native row"
                grant = client.post(url, headers=admin, json=payload)
                assert grant.status_code == 200
                with factory() as database:
                    fresh = database.get(ClassroomSession, classroom["id"])
                    lease = fresh.controller_lease_id
                    epoch = fresh.control_epoch
                    version = fresh.state_version
                acknowledged_events = len(control_events)
            finally:
                release.set()
            assert pending.result(5).status_code == 200
        assert len(control_events) == acknowledged_events
        with factory() as database:
            latest = database.get(ClassroomSession, classroom["id"])
            assert lease is not None
            assert latest.controller_lease_id == lease
            assert latest.control_epoch == epoch
            assert latest.state_version == version
