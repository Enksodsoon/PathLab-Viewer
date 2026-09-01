from datetime import UTC, datetime, timedelta
from pathlib import Path

from test_assessment_admin import _client
from test_assessment_contract_v2 import v2_document


def _draft(client):
    return client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Sectioned assessment", "document": v2_document()},
    ).json()


def test_v2_publish_creates_atomic_class_administrations_and_one_time_codes(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    first = client.post("/api/v2/admin/assessment/classes", json={"name": "Class A"}).json()
    second = client.post("/api/v2/admin/assessment/classes", json={"name": "Class B"}).json()
    draft = _draft(client)

    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "quiz", "classIds": [first["id"], second["id"]]},
    )

    assert published.status_code == 201, published.text
    result = published.json()
    assert result["administrationId"] is None
    assert {item["classId"] for item in result["administrations"]} == {
        first["id"],
        second["id"],
    }
    assert all(len(item["accessCode"]) >= 8 for item in result["administrations"])
    assert len({item["accessCode"] for item in result["administrations"]}) == 2
    listed = client.get("/api/v2/admin/assessment/administrations").json()["items"]
    assert len(listed) == 2
    assert "accessCode" not in repr(listed)


def test_collection_controls_block_only_new_attempts_and_expiry_auto_submits(
    tmp_path: Path,
) -> None:
    client, _ = _client(tmp_path)
    draft = _draft(client)
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={"mode": "formative"},
    ).json()
    administration_id = published["administrationId"]
    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/open")
    access = client.post(
        "/api/v2/assessment/access",
        headers={"Idempotency-Key": "collection-access"},
        json={"kind": "anonymous", "publicId": published["publicId"]},
    ).json()
    student_headers = {
        "X-CSRF-Token": access["csrfToken"],
        "Idempotency-Key": "collection-start",
    }

    paused = client.patch(
        f"/api/v2/admin/assessment/administrations/{administration_id}/collection",
        json={"manualAcceptance": False, "closedMessage": "Review in progress"},
    )
    assert paused.status_code == 200
    blocked = client.post("/api/v2/assessment/attempts", headers=student_headers)
    assert blocked.status_code == 409
    assert blocked.json()["detail"]["code"] == "ASSESSMENT_NOT_ACCEPTING"

    client.patch(
        f"/api/v2/admin/assessment/administrations/{administration_id}/collection",
        json={"manualAcceptance": True, "responseLimit": 1},
    )
    attempt = client.post("/api/v2/assessment/attempts", headers=student_headers).json()
    expired_at = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
    client.patch(
        f"/api/v2/admin/assessment/administrations/{administration_id}/collection",
        json={"manualAcceptance": True, "closesAt": expired_at},
    )
    expired = client.patch(
        f"/api/v2/assessment/attempts/{attempt['id']}/responses",
        headers={
            "X-CSRF-Token": access["csrfToken"],
            "Idempotency-Key": "collection-expired-save",
        },
        json={
            "responses": [
                {
                    "itemId": "q-choice",
                    "revision": 1,
                    "response": {"optionId": "q-choice-a"},
                }
            ]
        },
    )
    assert expired.status_code == 409
    assert expired.json()["detail"]["code"] == "ASSESSMENT_COLLECTION_EXPIRED"
    monitor = client.get(
        f"/api/v2/admin/assessment/administrations/{administration_id}/monitor"
    ).json()
    assert monitor["autoSubmitted"] == 1
