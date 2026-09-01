from pathlib import Path

from fastapi.testclient import TestClient
from test_assessment_admin import _client, _document


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
    purged = client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/purge")
    assert purged.status_code == 200
    assert purged.json()["status"] == "purged"


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
    conflict = second.post("/api/v2/assessment/access", json=credentials)
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ASSESSMENT_DEVICE_ACTIVE"
    takeover = second.post(
        "/api/v2/assessment/access",
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
    preview = client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/preview",
        json={"rows": "s001,=Somchai"},
    ).json()
    client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/commit",
        json={"rows": "s001,=Somchai", "checksum": preview["checksum"]},
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
    unreleased = client.get(f"/api/v2/assessment/attempts/{attempt_id}/result", headers=headers)
    assert unreleased.status_code == 404

    monitor = client.get(f"/api/v2/admin/assessment/administrations/{administration_id}/monitor")
    assert monitor.status_code == 200
    assert set(monitor.json()) == {"activeSessions", "activeAttempts", "submitted", "needsGrading"}
    graded = client.post(
        f"/api/v2/admin/assessment/administrations/{administration_id}/manual-grade",
        json={
            "attemptId": attempt_id,
            "itemId": "item-manual",
            "points": "2",
            "expectedScoreVersion": 1,
        },
    )
    assert graded.status_code == 200
    assert graded.json()["scoreVersion"] == 2
    assert graded.json()["points"] == "3.000"
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
        json={"showScore": True, "showAnswers": False, "showFeedback": False},
    )
    assert released.status_code == 201
    result = client.get(f"/api/v2/assessment/attempts/{attempt_id}/result", headers=headers)
    assert result.status_code == 200
    assert result.json()["score"]["points"] == "3.000"
    assert "breakdown" not in result.json()

    exported = client.get(
        f"/api/v2/admin/assessment/administrations/{administration_id}/export.csv"
    )
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "'=Somchai" in exported.text
