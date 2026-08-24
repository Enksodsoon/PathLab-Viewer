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
