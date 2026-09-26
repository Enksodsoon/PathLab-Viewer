import csv
import hashlib
import io
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from threading import Barrier, BrokenBarrierError

from fastapi import HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from test_study_coach import _admin, _client, _publish_pack, _slide
from wsi_viewer.database import session_factory
from wsi_viewer.models import StudyInvitation, StudyLearnerSession
from wsi_viewer.study_routes import InvitationRequest, RedeemRequest


def test_expired_active_course_does_not_consume_invitation(tmp_path, monkeypatch):
    end = datetime.now(UTC) + timedelta(days=1)
    with _client(tmp_path) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Expiring course",
                "retentionDays": 30,
                "learnerLimit": 1,
                "endsAt": end.isoformat(),
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
        export = client.post(
            f"/api/v1/admin/study/courses/{course_id}/invitations",
            headers=admin,
            json={"count": 1},
        )
        assert export.status_code == 200
        code = next(csv.DictReader(io.StringIO(export.text)))["invitation_code"]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin
            ).status_code
            == 200
        )
        for now in (end, end + timedelta(seconds=1)):
            monkeypatch.setattr("wsi_viewer.study_routes._now", lambda now=now: now)
            response = client.post(
                "/api/v1/study/redeem", json={"code": code, "noticeAccepted": True}
            )
            assert response.status_code == 409
            assert response.json()["detail"]["code"] == "STUDY_COURSE_UNAVAILABLE"
            assert "set-cookie" not in response.headers
            with session_factory(client.app.state.settings)() as database:
                invitation = database.scalar(select(StudyInvitation))
                assert invitation.status == "issued"
                assert invitation.redeemed_at is None
                assert database.scalar(select(func.count()).select_from(StudyLearnerSession)) == 0


def test_concurrent_study_issuance_and_same_code_redemption_are_bounded(tmp_path, monkeypatch):
    with _client(tmp_path) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        response = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Concurrent course",
                "retentionDays": 30,
                "learnerLimit": 1,
            },
        )
        assert response.status_code == 201
        course_id = response.json()["id"]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/prepare", headers=admin
            ).status_code
            == 200
        )
        factory = session_factory(client.app.state.settings)
        issue = next(
            route.endpoint
            for route in client.app.routes
            if getattr(route, "path", "") == "/api/v1/admin/study/courses/{course_id}/invitations"
        )
        redeem = next(
            route.endpoint
            for route in client.app.routes
            if getattr(route, "path", "") == "/api/v1/study/redeem"
        )
        original_scalar = Session.scalar
        read_barrier = Barrier(2)

        def pause_empty_count(database, statement, *args, **kwargs):
            value = original_scalar(database, statement, *args, **kwargs)
            sql = str(statement)
            if (
                value == 0
                and "count(" in sql
                and ("study_invitations" in sql or "study_learner_sessions" in sql)
            ):
                # Force both unprotected requests past the actual capacity read.
                # A serialized request legitimately has no concurrent reader.
                with suppress(BrokenBarrierError):
                    read_barrier.wait(timeout=0.5)
            return value

        monkeypatch.setattr(Session, "scalar", pause_empty_count)

        def issue_once(_):
            with factory() as database:
                try:
                    issue(course_id, InvitationRequest(count=1), None, database)
                    return 200
                except HTTPException as error:
                    return error.status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(issue_once, range(2)))
        assert sorted(statuses) == [200, 409]
        with factory() as database:
            assert database.scalar(select(func.count()).select_from(StudyInvitation)) == 1
            invitation = database.scalar(select(StudyInvitation))
            # Set a known synthetic code without creating an extra invitation.
            invitation.code_hash = hashlib.sha256(b"concurrent-test-code-12345").hexdigest()
            database.commit()

        read_barrier = Barrier(2)

        def redeem_once(_):
            with factory() as database:
                try:
                    redeem(
                        RedeemRequest(code="concurrent-test-code-12345", noticeAccepted=True),
                        Response(),
                        database,
                    )
                    return 201
                except HTTPException as error:
                    return error.status_code
                except IntegrityError:
                    return 500

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(redeem_once, range(2)))
        assert sorted(statuses) == [201, 404]
        with factory() as database:
            assert database.scalar(select(func.count()).select_from(StudyLearnerSession)) == 1
