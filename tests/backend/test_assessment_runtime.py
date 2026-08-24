from pathlib import Path

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
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative", "durationSeconds": 3600, "maxAttempts": 2},
    ).json()

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
    saved = client.patch(
        f"/api/v2/assessment/attempts/{attempt_id}/responses",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "save-1"},
        json={
            "responses": [{"itemId": "item-1", "revision": 1, "response": {"optionId": "option-a"}}]
        },
    )
    assert saved.status_code == 200
    submitted = client.post(
        f"/api/v2/assessment/attempts/{attempt_id}/submit",
        headers={"X-CSRF-Token": csrf, "Idempotency-Key": "submit-1"},
    )
    assert submitted.status_code == 200
    assert submitted.json()["score"]["points"] == "1.000"
    assert submitted.json()["anonymousAggregateOnly"] is True
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
