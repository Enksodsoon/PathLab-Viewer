from pathlib import Path

from test_assessment_admin import _client, _document
from test_assessment_contract_v2 import v2_document


def test_explicit_v1_migration_clones_source_and_preserves_item_identity(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    source = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Legacy", "document": _document()},
    ).json()

    migrated = client.post(
        f"/api/v2/admin/assessment/drafts/{source['id']}/migrate-v2",
        json={"expectedRevision": source["revision"]},
    )

    assert migrated.status_code == 201, migrated.text
    clone = migrated.json()
    assert clone["id"] != source["id"]
    assert clone["document"]["schema"] == "pathlab.assessment/2"
    assert clone["document"]["sections"][0]["items"][0]["id"] == "item-1"
    original = client.get(f"/api/v2/admin/assessment/drafts/{source['id']}").json()
    assert "schema" not in original["document"]
    assert original["revision"] == source["revision"]


def test_v1_migration_is_revision_checked_and_v2_cannot_be_migrated(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    source = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Legacy", "document": _document()},
    ).json()
    conflict = client.post(
        f"/api/v2/admin/assessment/drafts/{source['id']}/migrate-v2",
        json={"expectedRevision": 99},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ASSESSMENT_DRAFT_CONFLICT"

    v2 = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "V2", "document": v2_document()},
    ).json()
    rejected = client.post(
        f"/api/v2/admin/assessment/drafts/{v2['id']}/migrate-v2",
        json={"expectedRevision": 1},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"]["code"] == "ASSESSMENT_ALREADY_V2"


def test_preflight_and_publish_share_the_v2_contract(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "V2", "document": v2_document()},
    ).json()

    preflight = client.post(f"/api/v2/admin/assessment/drafts/{draft['id']}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["valid"] is True
    published = client.post(f"/api/v2/admin/assessment/drafts/{draft['id']}/publish")
    assert published.status_code == 201, published.text
    assert published.json()["schema"] == "pathlab.assessment/2"
    assert "answerKey" not in repr(published.json()["learnerManifest"])


def test_preflight_returns_focusable_issues_without_publishing(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    document = v2_document()
    document["sections"][0]["items"][0]["options"] = []  # type: ignore[index]
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Invalid", "document": document},
    ).json()

    preflight = client.post(f"/api/v2/admin/assessment/drafts/{draft['id']}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["valid"] is False
    assert preflight.json()["errors"][0]["path"] == "/"
    published = client.post(f"/api/v2/admin/assessment/drafts/{draft['id']}/publish")
    assert published.status_code == 422
    assert published.json()["detail"]["code"] == "ASSESSMENT_OPTIONS_REQUIRED"


def test_v2_question_library_imports_into_first_section_without_routes(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    source = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Source", "document": v2_document()},
    ).json()
    destination_document = v2_document()
    destination_document["title"] = "Destination"
    destination_document["sections"][0]["items"] = []  # type: ignore[index]
    destination = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Destination", "document": destination_document},
    ).json()

    imported = client.post(
        f"/api/v2/admin/assessment/drafts/{destination['id']}/import-questions",
        json={
            "sourceDraftId": source["id"],
            "itemIds": ["item-pattern"],
            "expectedRevision": destination["revision"],
        },
    )

    assert imported.status_code == 200, imported.text
    item = imported.json()["document"]["sections"][0]["items"][0]
    assert item["id"] != "item-pattern"
    assert "routing" not in item
