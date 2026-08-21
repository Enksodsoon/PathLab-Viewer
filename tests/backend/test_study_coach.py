import csv
import hashlib
import io
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    DesktopCredential,
    EvidenceBundle,
    ResultDelivery,
    Slide,
    StudyLearnerSession,
    StudyProgress,
    StudyReadinessAggregate,
    User,
)
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password
from wsi_viewer.study_pack_contract import canonical_json, content_checksum


def _client(
    tmp_path: Path,
    *,
    ai_enabled: bool = False,
    pilot_enabled: bool = False,
    study_enabled: bool = True,
) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'study.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="study-test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        study_mode_enabled=study_enabled,
        study_coach_ai_enabled=ai_enabled,
        study_coach_ai_pilot_enabled=pilot_enabled,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:head)"),
            {"head": ALEMBIC_HEAD},
        )
        database.add(User(username="admin", password_hash=hash_password("correct horse battery")))
        database.commit()
    return TestClient(create_app(settings))


def _admin(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={"username": "admin", "password": "correct horse battery"},
    )
    assert response.status_code == 201
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def _slide(client: TestClient) -> Slide:
    with session_factory(client.app.state.settings)() as database:
        slide = Slide(
            display_name="Approved teaching slide",
            original_filename="deidentified.ome.tif",
            source_bytes=1024,
            derivative_bytes=2048,
            derivative_file_count=2,
            render_mode="static_dzi",
            privacy_status="passed",
            privacy_scanned_at=None,
            sha256="a" * 64,
            state=SlideState.READY_PRIVATE,
        )
        database.add(slide)
        database.commit()
        database.refresh(slide)
        database.expunge(slide)
        return slide


def _pack(slide: Slide, *, version: int = 1) -> dict[str, object]:
    core: dict[str, object] = {
        "schema": "pathlab.study-pack/1",
        "packKey": "histology-basics",
        "version": version,
        "title": "Histology basics",
        "author": "Faculty",
        "license": "CC-BY-4.0",
        "provenance": "Faculty-authored from deidentified teaching material",
        "revision": "2026-08-21",
        "languages": ["en", "th"],
        "slides": [
            {
                "viewerSlideId": slide.id,
                "sha256": slide.sha256,
                "displayName": slide.display_name,
            }
        ],
        "tasks": [
            {
                "id": "task-1",
                "type": "multiple-choice",
                "slideId": slide.id,
                "prompt": "Which option is faculty approved?",
                "options": ["Approved", "Not approved"],
                "answerKey": "Approved",
                "hints": ["Use the faculty source."],
                "explanation": "Approved is the explicit answer.",
                "sources": [{"title": "Faculty source", "url": "https://example.edu/source"}],
            }
        ],
    }
    checksum = content_checksum(core)
    return {
        **core,
        "checksum": checksum,
        "facultyPreview": {
            "packChecksum": checksum,
            "previewVersion": "pathlab.study-preview/1",
            "reviewedAt": "2026-08-21T00:00:00Z",
        },
    }


def _publish_pack(
    client: TestClient, admin_headers: dict[str, str], slide: Slide
) -> dict[str, object]:
    response = client.post("/api/v1/admin/study/packs", headers=admin_headers, json=_pack(slide))
    assert response.status_code == 201, response.text
    return response.json()


def test_viewer_authoring_preview_checksum_and_immutable_version(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        admin = _admin(client)
        slide = _slide(client)
        authoring_slides = client.get("/api/v1/admin/study/authoring/slides").json()
        assert authoring_slides == [
            {"id": slide.id, "displayName": slide.display_name, "sha256": slide.sha256}
        ]
        core = _pack(slide)
        core.pop("checksum")
        core.pop("facultyPreview")
        preview = client.post("/api/v1/admin/study/packs/validate", headers=admin, json=core)
        assert preview.status_code == 200
        assert preview.json()["checksum"] == content_checksum(core)
        first = _publish_pack(client, admin, slide)
        duplicate = client.post("/api/v1/admin/study/packs", headers=admin, json=_pack(slide))
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == first["id"]

        changed = _pack(slide)
        changed["title"] = "Changed after preview"
        rejected = client.post("/api/v1/admin/study/packs", headers=admin, json=changed)
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "STUDY_PACK_CHECKSUM_INVALID"


def test_study_course_redeem_score_minimal_progress_and_withdrawal(tmp_path: Path) -> None:
    with _client(tmp_path, ai_enabled=True) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Course A",
                "retentionDays": 30,
                "learnerLimit": 10,
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
        invitation_export = client.post(
            f"/api/v1/admin/study/courses/{course_id}/invitations",
            headers=admin,
            json={"count": 1},
        )
        assert invitation_export.status_code == 200
        invitation_code = list(csv.DictReader(io.StringIO(invitation_export.text)))[0][
            "invitation_code"
        ]
        assert invitation_code.startswith("SC-")
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin
            ).status_code
            == 200
        )

        redeem = client.post(
            "/api/v1/study/redeem",
            json={"code": invitation_code, "noticeAccepted": True},
        )
        assert redeem.status_code == 201, redeem.text
        document = redeem.json()
        assert document["pseudonym"].startswith("Learner-")
        assert "answerKey" not in str(document["pack"])
        assert document["pack"]["tasks"][0]["hints"] == ["Use the faculty source."]
        assert "explanation" not in document["pack"]["tasks"][0]
        assert document["ai"]["eligible"] is False
        assert client.get("/api/v1/study/assets/trace-sim.9ca7e812951712eb.onnx").status_code == 404
        csrf = {"X-Study-CSRF": document["csrfToken"]}
        restored = client.get("/api/v1/study/session")
        assert restored.status_code == 200
        assert restored.json()["csrfToken"] == document["csrfToken"]
        result = client.post(
            "/api/v1/study/tasks/task-1/submit",
            headers=csrf,
            json={"selectedOption": "Approved"},
        )
        assert result.status_code == 200
        assert result.json()["correct"] is True

        with session_factory(client.app.state.settings)() as database:
            progress = database.scalar(select(StudyProgress))
            stored_session = database.scalar(select(StudyLearnerSession))
            assert progress is not None and stored_session is not None
            assert progress.task_id == "task-1"
            assert progress.latest_correctness is True
            assert progress.attempt_count == 1
            assert not hasattr(progress, "selected_option")
            assert not hasattr(progress, "coordinates")

        withdrawn = client.post("/api/v1/study/withdraw", headers=csrf)
        assert withdrawn.status_code == 204
        with session_factory(client.app.state.settings)() as database:
            assert database.scalar(select(StudyLearnerSession)) is None
            assert database.scalar(select(StudyProgress)) is None


def test_closed_pilot_is_course_scoped_and_stores_only_aggregate_actions(tmp_path: Path) -> None:
    with _client(tmp_path, ai_enabled=True, pilot_enabled=True) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        course_response = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Private TRACE-SIM pilot",
                "learnerLimit": 1,
                "aiMode": "closed_pilot_trace_sim",
                "pilotAcknowledged": True,
            },
        )
        assert course_response.status_code == 201, course_response.text
        course = course_response.json()
        assert course["aiMode"] == "closed_pilot_trace_sim"
        assert course["pilotAcknowledgedAt"] is not None
        client.post(f"/api/v1/admin/study/courses/{course['id']}/prepare", headers=admin)
        invitation = client.post(
            f"/api/v1/admin/study/courses/{course['id']}/invitations",
            headers=admin,
            json={"count": 1},
        )
        code = list(csv.DictReader(io.StringIO(invitation.text)))[0]["invitation_code"]
        client.post(f"/api/v1/admin/study/courses/{course['id']}/activate", headers=admin)
        redeemed = client.post(
            "/api/v1/study/redeem", json={"code": code, "noticeAccepted": True}
        ).json()
        assert redeemed["ai"]["eligible"] is True
        assert redeemed["ai"]["authorizationMode"] == "closed_pilot"
        assert redeemed["ai"]["manifest"]["approvalStatus"].startswith("not_approved")
        csrf = {"X-Study-CSRF": redeemed["csrfToken"]}
        submitted = client.post(
            "/api/v1/study/tasks/task-1/submit",
            headers=csrf,
            json={"selectedOption": "Approved"},
        )
        assert submitted.status_code == 200
        reported = client.post(
            "/api/v1/study/ai-events",
            headers=csrf,
            json={"taskId": "task-1", "outcome": "continue"},
        )
        assert reported.status_code == 204
        with session_factory(client.app.state.settings)() as database:
            aggregate = database.scalar(select(StudyReadinessAggregate))
            assert aggregate is not None and aggregate.continue_count == 1
            assert not hasattr(aggregate, "task_id")
            assert not hasattr(aggregate, "session_id")
            assert not hasattr(aggregate, "probability")


def test_retention_can_only_shorten_after_invites_and_disabled_mode_is_hidden(
    tmp_path: Path,
) -> None:
    with _client(tmp_path) as client:
        admin = _admin(client)
        pack = _publish_pack(client, admin, _slide(client))
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={"packId": pack["id"], "title": "Course", "retentionDays": 30},
        ).json()
        client.post(
            f"/api/v1/admin/study/courses/{course['id']}/invitations",
            headers=admin,
            json={"count": 1},
        )
        extended = client.patch(
            f"/api/v1/admin/study/courses/{course['id']}",
            headers=admin,
            json={"retentionDays": 31},
        )
        assert extended.status_code == 409
        shortened = client.patch(
            f"/api/v1/admin/study/courses/{course['id']}",
            headers=admin,
            json={"retentionDays": 0},
        )
        assert shortened.status_code == 200

    with _client(tmp_path / "disabled", study_enabled=False) as disabled:
        assert disabled.get("/api/v1/study/session").status_code == 404


def test_evidence_mentor_v2_is_review_bound_grounded_and_answer_hidden(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        admin = _admin(client)
        slide = _slide(client)
        with session_factory(client.app.state.settings)() as database:
            user = database.scalar(select(User).where(User.username == "admin"))
            assert user is not None
            credential = DesktopCredential(
                id="evidence-credential",
                user_id=user.id,
                device_name="Forge Evidence Mentor",
                scopes=["results:sync"],
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
            delivery = ResultDelivery(
                id="delivery-v2",
                credential_id=credential.id,
                slide_id=slide.id,
                artifact_revision_id="revision-1",
                slide_sha256=slide.sha256,
                payload_length=1,
                received_bytes=1,
                payload_sha256="b" * 64,
                schema="pathlab-private-results/v1",
                status="complete",
            )
            manifest_sha = "c" * 64
            evidence = EvidenceBundle(
                delivery_id=delivery.id,
                slide_id=slide.id,
                bundle_id="bundle-v2",
                manifest_sha256=manifest_sha,
                pack_id="ihc-descriptive-v1",
                pack_version="1",
                status="completed",
                validation_status="experimental",
                manifest={
                    "schema": "pathlab.ai-evidence/1",
                    "manifestSha256": manifest_sha,
                    "status": "completed",
                    "researchOnly": True,
                    "notDiagnostic": True,
                    "evidence": [],
                    "cellAggregates": [],
                    "ihcDescriptors": [],
                    "qc": {
                        "focus": 0.9,
                        "tissueFraction": 0.8,
                        "uncertainty": 0.2,
                        "abstentionReasons": [],
                    },
                },
            )
            database.add(credential)
            database.flush()
            database.add(delivery)
            database.flush()
            database.add(evidence)
            database.commit()
            evidence_id = evidence.id

        review = client.post(
            f"/api/v1/admin/study/evidence/{evidence_id}/review",
            headers=admin,
            json={"previewChecksum": manifest_sha},
        )
        assert review.status_code == 200, review.text

        knowledge_core: dict[str, object] = {
            "schema": "pathlab.knowledge-pack/1",
            "packId": "pathology-en",
            "version": "1",
            "language": "en",
            "claims": [
                {
                    "id": "nci.ki67.1",
                    "text": "Ki-67 is used as a marker of cell proliferation.",
                    "retrievalText": "ki-67 nuclear proliferation dividing cells",
                    "source": {
                        "title": "NCI Dictionary",
                        "url": "https://www.cancer.gov/example",
                        "revision": "2026-08-22",
                    },
                    "license": "US Government public-domain text; reuse reviewed",
                    "allowedUse": "private-research-education",
                    "reviewedAt": "2026-08-22T00:00:00Z",
                    "tags": ["ihc", "ki-67"],
                }
            ],
        }
        knowledge_core["checksum"] = hashlib.sha256(
            canonical_json(knowledge_core).encode()
        ).hexdigest()
        knowledge = client.post(
            "/api/v1/admin/study/knowledge-packs",
            headers=admin,
            json=knowledge_core,
        )
        assert knowledge.status_code == 201, knowledge.text
        knowledge_sha = knowledge.json()["checksum"]

        core: dict[str, object] = {
            "schema": "pathlab.study-pack/2",
            "packKey": "evidence-mentor",
            "version": 1,
            "title": "Evidence Mentor",
            "author": "Faculty",
            "license": "private education",
            "provenance": "Reviewed signed evidence and allowlisted claims",
            "revision": "2026-08-22",
            "languages": ["en"],
            "knowledgePackChecksum": knowledge_sha,
            "slides": [
                {
                    "viewerSlideId": slide.id,
                    "sha256": slide.sha256,
                    "displayName": slide.display_name,
                    "evidenceBundleSha256": manifest_sha,
                }
            ],
            "tasks": [
                {
                    "id": "task-v2",
                    "type": "multiple-choice",
                    "slideId": slide.id,
                    "prompt": "Which reviewed claim is supported?",
                    "options": ["Proliferation", "Diagnosis"],
                    "answerKey": "Proliferation",
                    "hints": ["Use the reviewed NCI claim."],
                    "explanation": "The reviewed claim describes proliferation, not diagnosis.",
                    "sources": [
                        {"title": "NCI Dictionary", "url": "https://www.cancer.gov/example"}
                    ],
                    "claimIds": ["nci.ki67.1"],
                }
            ],
        }
        preview = client.post("/api/v1/admin/study/packs/validate", headers=admin, json=core)
        assert preview.status_code == 200, preview.text
        checksum = preview.json()["checksum"]
        published = client.post(
            "/api/v1/admin/study/packs",
            headers=admin,
            json={
                **core,
                "checksum": checksum,
                "facultyPreview": {
                    "packChecksum": checksum,
                    "previewVersion": "pathlab.study-preview/1",
                    "reviewedAt": "2026-08-22T00:00:00Z",
                },
            },
        )
        assert published.status_code == 201, published.text
        course = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": published.json()["id"],
                "title": "Evidence Mentor staff",
                "learnerLimit": 1,
            },
        ).json()
        client.post(f"/api/v1/admin/study/courses/{course['id']}/prepare", headers=admin)
        invitation = client.post(
            f"/api/v1/admin/study/courses/{course['id']}/invitations",
            headers=admin,
            json={"count": 1},
        )
        code = list(csv.DictReader(io.StringIO(invitation.text)))[0]["invitation_code"]
        client.post(f"/api/v1/admin/study/courses/{course['id']}/activate", headers=admin)
        redeemed = client.post(
            "/api/v1/study/redeem",
            json={"code": code, "noticeAccepted": True},
        )
        assert redeemed.status_code == 201, redeemed.text
        learner = redeemed.json()
        assert "answerKey" not in str(learner["pack"])
        assert "explanation" not in learner["pack"]["tasks"][0]
        assert learner["pack"]["tasks"][0]["claimIds"] == ["nci.ki67.1"]
        assert client.get(learner["pack"]["knowledgePackUrl"]).status_code == 200
        assert client.get(learner["pack"]["slides"][0]["evidenceUrl"]).status_code == 200

        result = client.post(
            "/api/v1/study/tasks/task-v2/submit",
            headers={"X-Study-CSRF": learner["csrfToken"]},
            json={"selectedOption": "Proliferation"},
        )
        assert result.status_code == 200, result.text
        assert result.json()["claimIds"] == ["nci.ki67.1"]
        assert result.json()["evidence"]["manifestSha256"] == manifest_sha
        assert "diagnosis" in result.json()["explanation"]
