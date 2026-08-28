from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from test_assessment_admin import _client, _document
from wsi_viewer.database import session_factory
from wsi_viewer.models import AssessmentAdministration, AssessmentAttempt, AssessmentParticipant
from wsi_viewer.time_support import utc_now


def test_practice_public_bundle_is_explicitly_answer_bearing_while_metadata_is_not(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "practice", "durationSeconds": 3600, "maxAttempts": 1},
    )
    assert published.status_code == 201
    public_id = published.json()["publicId"]

    metadata = client.get(f"/api/v2/assessment/administrations/{public_id}")
    assert metadata.status_code == 200
    assert "answerKey" not in metadata.text
    practice = client.get(f"/api/v2/assessment/practice/{public_id}")
    assert practice.status_code == 200
    assert "answerKey" in practice.text
    assert practice.json()["storage"] == "browser-local"


def test_non_practice_bundle_fails_closed(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    published_response = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    )
    assert published_response.status_code == 201, published_response.text
    published = published_response.json()

    response = client.get(f"/api/v2/assessment/practice/{published['publicId']}")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "ASSESSMENT_NOT_FOUND"


def test_recorded_administrations_are_singleton_and_close_with_cooldown(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    first = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    )
    assert first.status_code == 201
    listed = client.get("/api/v2/admin/assessment/administrations")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["draftId"] == draft["id"]
    assert listed.json()["items"][0]["version"] == 1
    second = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    )
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "ASSESSMENT_RUNTIME_BUSY"
    closed = client.post(
        f"/api/v2/admin/assessment/administrations/{first.json()['administrationId']}/close"
    )
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert closed.json()["cooldownSeconds"] == 120


def test_practice_administration_can_toggle_draft_open_and_closed(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Practice lifecycle", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "practice", "durationSeconds": 3600, "maxAttempts": 1},
    )
    assert published.status_code == 201
    administration_id = published.json()["administrationId"]
    path = f"/api/v2/admin/assessment/administrations/{administration_id}/status"

    returned_to_draft = client.patch(path, json={"status": "draft"})
    assert returned_to_draft.status_code == 200
    assert returned_to_draft.json()["status"] == "draft"
    reopened = client.patch(path, json={"status": "open"})
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "open"
    closed = client.patch(path, json={"status": "closed"})
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"


def test_anonymous_formative_attempt_saves_latest_responses_and_scores(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    ).json()
    client.post(f"/api/v2/admin/assessment/administrations/{published['administrationId']}/open")
    access = client.post(
        "/api/v2/assessment/access",
        json={"kind": "anonymous", "publicId": published["publicId"]},
    )
    assert access.status_code == 201
    replayed_access = client.post(
        "/api/v2/assessment/access",
        json={"kind": "anonymous", "publicId": published["publicId"]},
    )
    assert replayed_access.status_code == 201
    assert replayed_access.json() == access.json()
    csrf = access.json()["csrfToken"]
    attempt = client.post(
        "/api/v2/assessment/attempts",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "start-1"},
    )
    assert attempt.status_code == 201
    attempt_id = attempt.json()["id"]
    replayed_attempt = client.post(
        "/api/v2/assessment/attempts",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "start-1"},
    )
    assert replayed_attempt.status_code == 201
    assert replayed_attempt.json()["id"] == attempt_id
    saved = client.patch(
        f"/api/v2/assessment/attempts/{attempt_id}/responses",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "save-1"},
        json={
            "responses": [{"itemId": "item-1", "revision": 1, "response": {"optionId": "option-a"}}]
        },
    )
    assert saved.status_code == 200
    reused_key = client.patch(
        f"/api/v2/assessment/attempts/{attempt_id}/responses",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "save-1"},
        json={
            "responses": [{"itemId": "item-1", "revision": 2, "response": {"optionId": "option-b"}}]
        },
    )
    assert reused_key.status_code == 409
    assert reused_key.json()["detail"]["code"] == "ASSESSMENT_IDEMPOTENCY_CONFLICT"
    submitted = client.post(
        f"/api/v2/assessment/attempts/{attempt_id}/submit",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "submit-1"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["score"]["points"] == "1.000"
    assert submitted.json()["anonymousAggregateOnly"] is True
    replayed_submit = client.post(
        f"/api/v2/assessment/attempts/{attempt_id}/submit",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "submit-1"},
    )
    assert replayed_submit.status_code == 200
    assert replayed_submit.json() == submitted.json()
    results = client.get(
        f"/api/v2/admin/assessment/administrations/{published['administrationId']}/results"
    )
    assert results.status_code == 200
    assert results.json()["summary"]["responses"] == 1
    assert results.json()["summary"]["averagePoints"] == "1.000"


def test_retention_hold_blocks_purge_until_explicitly_released(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    ).json()
    administration_id = published["administrationId"]
    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/close")
    held = client.patch(
        f"/api/v2/admin/assessment/administrations/{administration_id}/retention",
        json={"retentionDays": 30, "hold": True},
    )
    assert held.status_code == 200
    blocked = client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/purge")
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "ASSESSMENT_HOLD_ACTIVE"
    client.patch(
        f"/api/v2/admin/assessment/administrations/{administration_id}/retention",
        json={"retentionDays": 30, "hold": False},
    )
    retained = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/purge"
    )
    assert retained.status_code == 409
    assert retained.json()["detail"]["code"] == "ASSESSMENT_RETENTION_ACTIVE"
    with session_factory(client.app.state.settings)() as database:
        administration = database.get(AssessmentAdministration, administration_id)
        assert administration is not None
        administration.closes_at = utc_now() - timedelta(days=31)
        database.add_all(
            [
                AssessmentParticipant(
                    administration_id=administration_id,
                    kind="anonymous",
                    receipt_hash="a" * 64,
                ),
                AssessmentParticipant(
                    administration_id=administration_id,
                    kind="anonymous",
                    receipt_hash="b" * 64,
                ),
            ]
        )
        database.commit()
    first_batch = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/purge?batchSize=1"
    )
    assert first_batch.status_code == 200
    assert first_batch.json()["status"] == "closed"
    assert first_batch.json()["remaining"] == 1
    purged = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/purge?batchSize=1"
    )
    assert purged.status_code == 200
    assert purged.json()["status"] == "purged"
    preserved = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/aggregates/reconcile"
    )
    assert preserved.status_code == 200
    assert preserved.json()["source"] == "preserved"
    assert preserved.json()["aggregate"]["responses"] == 0


def test_synthetic_fixture_can_be_purged_and_removed_immediately(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Synthetic fixture", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={
            "mode": "practice",
            "durationSeconds": 3600,
            "maxAttempts": 1,
            "syntheticFixture": True,
        },
    ).json()
    administration_id = published["administrationId"]
    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/close")
    purged = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/purge"
    )
    assert purged.json()["status"] == "purged"
    cleaned = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/synthetic-fixture/cleanup"
    )
    assert cleaned.status_code == 200
    assert all(cleaned.json().values())
    assert client.get(f"/api/v2/admin/assessment/drafts/{draft['id']}").status_code == 404


def test_student_session_restore_logout_and_stale_save_reconciliation(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    ).json()
    client.post(f"/api/v2/admin/assessment/administrations/{published['administrationId']}/open")
    access = client.post(
        "/api/v2/assessment/access",
        json={"kind": "anonymous", "publicId": published["publicId"]},
    ).json()
    student_headers = {"X-CSRF-Token": access["csrfToken"]}

    restored = client.get("/api/v2/assessment/session", headers=student_headers)
    assert restored.status_code == 200
    assert restored.json()["publicId"] == published["publicId"]
    attempt = client.post(
        "/api/v2/assessment/attempts",
        headers={**student_headers, "Idempotency-Key": "restore-start"},
    ).json()
    attempt_id = attempt["id"]
    saved = client.patch(
        f"/api/v2/assessment/attempts/{attempt_id}/responses",
        headers={**student_headers, "Idempotency-Key": "newer-save"},
        json={
            "responses": [{"itemId": "item-1", "revision": 2, "response": {"optionId": "option-a"}}]
        },
    )
    assert saved.status_code == 200
    stale = client.patch(
        f"/api/v2/assessment/attempts/{attempt_id}/responses",
        headers={**student_headers, "Idempotency-Key": "stale-save"},
        json={
            "responses": [{"itemId": "item-1", "revision": 1, "response": {"optionId": "option-b"}}]
        },
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "ASSESSMENT_RESPONSE_CONFLICT"
    assert stale.json()["detail"]["authoritative"][0]["revision"] == 2

    logged_out = client.post("/api/v2/assessment/session/logout", headers=student_headers)
    assert logged_out.status_code == 204
    assert client.get("/api/v2/assessment/session", headers=student_headers).status_code == 401


def test_rostered_access_requires_explicit_device_takeover(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    cohort_id = client.post("/api/v2/admin/assessment/classes", json={"name": "Year 3"}).json()[
        "id"
    ]
    preview = client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/preview",
        json={"rows": "s001,Somchai P."},
    ).json()
    client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/commit",
        json={"rows": "s001,Somchai P.", "checksum": preview["checksum"]},
    )
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={
            "mode": "quiz",
            "cohortId": cohort_id,
            "accessCode": "quiz-code",
            "durationSeconds": 3600,
            "maxAttempts": 1,
        },
    ).json()
    client.post(f"/api/v2/admin/assessment/administrations/{published['administrationId']}/open")
    credentials = {
        "kind": "roster",
        "publicId": published["publicId"],
        "studentIdentifier": "s001",
        "accessCode": "quiz-code",
    }
    first = client.post("/api/v2/assessment/access", json=credentials)
    assert first.status_code == 201
    first_csrf = first.json()["csrfToken"]

    second = TestClient(client.app)
    second.headers.update({"Idempotency-Key": "second-device"})
    conflict = second.post("/api/v2/assessment/access", json=credentials)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ASSESSMENT_DEVICE_ACTIVE"
    takeover = second.post(
        "/api/v2/assessment/access",
        headers={"Idempotency-Key": "takeover-device"},
        json={**credentials, "takeover": True},
    )
    assert takeover.status_code == 201
    assert (
        client.get("/api/v2/assessment/session", headers={"X-CSRF-Token": first_csrf}).status_code
        == 403
    )


def test_manual_grading_release_monitor_and_formula_safe_export(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    cohort_id = client.post("/api/v2/admin/assessment/classes", json={"name": "Year 3"}).json()[
        "id"
    ]
    roster_rows = "student_id,first_name\ns001,=Somchai"
    preview = client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/preview",
        json={"rows": roster_rows},
    ).json()
    client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/commit",
        json={"rows": roster_rows, "checksum": preview["checksum"]},
    )
    document = _document()
    document["items"].append(
        {
            "id": "item-manual",
            "type": "paragraph",
            "prompt": "Describe the morphology",
            "points": "2",
            "required": False,
        }
    )
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": document},
    ).json()
    published_response = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={
            "mode": "quiz",
            "cohortId": cohort_id,
            "accessCode": "quiz-code",
            "durationSeconds": 3600,
            "maxAttempts": 1,
        },
    )
    assert published_response.status_code == 201, published_response.text
    published = published_response.json()
    administration_id = published["administrationId"]
    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/open")
    access = client.post(
        "/api/v2/assessment/access",
        json={
            "kind": "roster",
            "publicId": published["publicId"],
            "studentIdentifier": "s001",
            "accessCode": "quiz-code",
        },
    ).json()
    headers = {"X-CSRF-Token": access["csrfToken"]}
    attempt_id = client.post(
        "/api/v2/assessment/attempts",
        headers={**headers, "Idempotency-Key": "manual-start"},
    ).json()["id"]
    client.patch(
        f"/api/v2/assessment/attempts/{attempt_id}/responses",
        headers={**headers, "Idempotency-Key": "manual-save"},
        json={
            "responses": [
                {"itemId": "item-1", "revision": 1, "response": {"optionId": "option-a"}},
                {
                    "itemId": "item-manual",
                    "revision": 1,
                    "response": {"text": "Irregular glands"},
                },
            ]
        },
    )
    submitted = client.post(
        f"/api/v2/assessment/attempts/{attempt_id}/submit",
        headers={**headers, "Idempotency-Key": "manual-submit"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["needsGrading"] is True
    assert "score" not in submitted.json()
    listed = client.get("/api/v2/admin/assessment/administrations").json()["items"][0]
    assert listed["cohortId"] == cohort_id
    assert listed["expectedParticipants"] == 1
    assert listed["completedParticipants"] == 1
    filtered = client.get(
        "/api/v2/admin/assessment/administrations",
        params={"cohort_id": cohort_id},
    )
    assert filtered.status_code == 200
    assert [item["id"] for item in filtered.json()["items"]] == [administration_id]
    unreleased = client.get(f"/api/v2/assessment/attempts/{attempt_id}/result", headers=headers)
    assert unreleased.status_code == 404

    monitor = client.get(f"/api/v2/admin/assessment/administrations/{administration_id}/monitor")
    assert monitor.status_code == 200
    assert set(monitor.json()) == {
        "expected",
        "entered",
        "active",
        "submitted",
        "autoSubmitted",
        "stale",
        "needsGrading",
        "activeSessions",
        "activeAttempts",
    }
    graded = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/manual-grades",
        json={
            "grades": [
                {
                    "attemptId": attempt_id,
                    "itemId": "item-manual",
                    "points": "2",
                    "feedback": "Clear and appropriately concise.",
                    "expectedScoreVersion": 1,
                }
            ]
        },
    )
    assert graded.status_code == 200
    assert graded.json()["items"][0]["scoreVersion"] == 2
    assert graded.json()["items"][0]["points"] == "3.000"
    conflict = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/manual-grade",
        json={
            "attemptId": attempt_id,
            "itemId": "item-manual",
            "points": "1",
            "expectedScoreVersion": 1,
        },
    )
    assert conflict.status_code == 409
    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/close")
    released = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/release",
        json={
            "showScore": True,
            "showAnswers": False,
            "showFeedback": False,
            "showManualFeedback": True,
        },
    )
    assert released.status_code == 201
    result = client.get(f"/api/v2/assessment/attempts/{attempt_id}/result", headers=headers)
    assert result.status_code == 200
    assert result.json()["score"]["points"] == "3.000"
    assert "breakdown" not in result.json()
    manual_item = next(
        item for item in result.json()["review"]["items"] if item["itemId"] == "item-manual"
    )
    assert manual_item["manualFeedback"] == "Clear and appropriately concise."

    exported = client.get(
        f"/api/v2/admin/assessment/administrations/{administration_id}/export.csv"
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert exported.text.splitlines()[0].startswith(
        "student_id,first_name,last_name,display_name,group,subgroup,email"
    )
    assert "s001" in exported.text
    assert "'=Somchai" in exported.text
    admin_results = client.get(
        f"/api/v2/admin/assessment/administrations/{administration_id}/results"
    ).json()
    learner = admin_results["individuals"]["items"][0]
    assert learner["studentId"] == "s001"
    assert set(("firstName", "lastName", "group", "subgroup", "email", "metadata")) <= set(learner)


def test_deadline_sweeper_auto_submits_incomplete_attempts(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Timed quiz", "document": _document()},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 1, "maxAttempts": 1},
    ).json()
    administration_id = published["administrationId"]
    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/open")
    access = client.post(
        "/api/v2/assessment/access",
        json={"kind": "anonymous", "publicId": published["publicId"]},
    ).json()
    headers = {"X-CSRF-Token": access["csrfToken"]}
    attempt_id = client.post(
        "/api/v2/assessment/attempts",
        headers={**headers, "Idempotency-Key": "deadline-start"},
    ).json()["id"]
    with session_factory(client.app.state.settings)() as database:
        attempt = database.get(AssessmentAttempt, attempt_id)
        assert attempt is not None
        attempt.started_at = utc_now() - timedelta(seconds=2)
        database.commit()

    swept = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/deadlines/sweep"
    )
    assert swept.status_code == 200
    assert swept.json() == {"scanned": 1, "autoSubmitted": 1}
    result = client.get(f"/api/v2/assessment/attempts/{attempt_id}/result", headers=headers)
    assert result.status_code == 200
    assert result.json()["status"] == "auto_submitted"
    assert result.json()["score"]["points"] == "0.000"
