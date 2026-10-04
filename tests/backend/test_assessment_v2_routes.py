from pathlib import Path

import pytest
from test_assessment_admin import _client, _document
from test_assessment_contract_v2 import v2_document


@pytest.mark.parametrize(
    ("shape", "code"),
    [
        ("sections-null", "ASSESSMENT_SECTIONS_REQUIRED"),
        ("section-null", "ASSESSMENT_INVALID_SECTION"),
        ("items-null", "ASSESSMENT_ITEMS_REQUIRED"),
        ("item-null", "ASSESSMENT_INVALID_ITEM"),
        ("options-null", "ASSESSMENT_OPTIONS_INVALID"),
        ("release-null", None),
    ],
)
def test_v2_preflight_handles_saved_incomplete_shapes_without_crashing(
    tmp_path: Path, shape: str, code: str | None
) -> None:
    client, _ = _client(tmp_path)
    document = v2_document()
    if shape == "sections-null":
        document["sections"] = None
    elif shape == "section-null":
        document["sections"][0] = None  # type: ignore[index]
    elif shape == "items-null":
        document["sections"][0]["items"] = None  # type: ignore[index]
    elif shape == "item-null":
        document["sections"][0]["items"][0] = None  # type: ignore[index]
    elif shape == "options-null":
        document["sections"][0]["items"][0]["options"] = None  # type: ignore[index]
    else:
        document["release"] = None
    created = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Synthetic incomplete", "document": document},
    )
    assert created.status_code == 201
    path = f"/api/v2/admin/assessment/drafts/{created.json()['id']}"
    preflight = client.post(f"{path}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["valid"] is (code is None)
    if code:
        assert preflight.json()["errors"][0]["code"] == code
    else:
        assert preflight.json()["errors"] == []
    assert preflight.json()["effectiveRelease"] == "manual"
    retained = client.get(path).json()
    assert retained["document"] == document
    assert retained["revision"] == 1


@pytest.mark.parametrize("points", ["invalid", "NaN", "Infinity", "1e999999999", "1000000000"])
def test_v2_invalid_points_preflight_and_publication_preserve_editable_draft(
    tmp_path: Path, points: str
) -> None:
    client, _ = _client(tmp_path)
    document = v2_document()
    document["sections"][0]["items"][0]["points"] = points  # type: ignore[index]
    created = client.post(
        "/api/v2/admin/assessment/drafts", json={"title": "Synthetic invalid", "document": document}
    )
    assert created.status_code == 201
    path = f"/api/v2/admin/assessment/drafts/{created.json()['id']}"
    preflight = client.post(f"{path}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["valid"] is False
    assert preflight.json()["errors"][0]["code"] == "ASSESSMENT_POINTS_INVALID"
    assert preflight.json()["metrics"]["points"] is None
    for action in ("preview", "publish"):
        rejected = client.post(f"{path}/{action}")
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "ASSESSMENT_POINTS_INVALID"
    retained = client.get(path).json()
    assert retained["document"] == document
    assert retained["revision"] == 1
    assert (
        client.patch(path, headers={"If-Match": "1"}, json={"document": v2_document()}).status_code
        == 200
    )
    published = client.post(f"{path}/publish")
    assert published.status_code == 201
    assert published.json()["version"] == 1


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


def test_v2_preflight_supports_the_same_decimal_spelling_as_scoring(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    document = v2_document()
    document["sections"][0]["items"][0]["points"] = "1__0"  # type: ignore[index]
    draft = client.post(
        "/api/v2/admin/assessment/drafts", json={"title": "Synthetic decimal", "document": document}
    ).json()
    path = f"/api/v2/admin/assessment/drafts/{draft['id']}"
    preflight = client.post(f"{path}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["valid"] is True
    assert preflight.json()["metrics"]["points"] == "10"
    assert client.post(f"{path}/preview").status_code == 200
    assert client.post(f"{path}/publish").status_code == 201


@pytest.mark.parametrize("invalid", [[], {}], ids=["list", "object"])
@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("item-type", "ASSESSMENT_ITEM_TYPE_INVALID"),
        ("rating-style", "ASSESSMENT_RATING_INVALID"),
        ("route-option", "ASSESSMENT_ROUTE_INVALID"),
        ("route-target", "ASSESSMENT_ROUTE_INVALID"),
        ("answer-key", "ASSESSMENT_ANSWER_KEY_INVALID"),
        ("media-kind", "ASSESSMENT_MEDIA_INVALID"),
        ("additional-media-kind", "ASSESSMENT_MEDIA_INVALID"),
        ("option-media-kind", "ASSESSMENT_MEDIA_INVALID"),
        ("media-mark-kind", "ASSESSMENT_MEDIA_INVALID"),
        ("additional-media-mark-kind", "ASSESSMENT_MEDIA_INVALID"),
    ],
)
def test_v2_validation_rejects_unhashable_contract_fields(
    tmp_path: Path, field: str, code: str, invalid: object
) -> None:
    client, _ = _client(tmp_path)
    document = v2_document()
    item = document["sections"][0]["items"][0]  # type: ignore[index]
    if field == "item-type":
        item["type"] = invalid
    elif field == "rating-style":
        document["sections"][2]["items"][0]["rating"]["style"] = invalid  # type: ignore[index]
    elif field == "route-option":
        item["routing"]["rules"][0]["when"]["optionId"] = invalid
    elif field == "route-target":
        item["routing"]["defaultSectionId"] = invalid
    elif field == "answer-key":
        item["answerKey"]["optionIds"] = [invalid]
    elif field == "option-media-kind":
        item["options"][0]["media"] = {"kind": invalid}
    else:
        media = {"kind": invalid}
        if "mark" in field:
            media = {
                "kind": "slide-thumbnail",
                "slideId": "synthetic",
                "marks": [{"kind": invalid}],
            }
        if field.startswith("additional"):
            item["media"] = {"kind": "slide-thumbnail", "slideId": "synthetic"}
            item["mediaItems"] = [media]
        else:
            item["media"] = media
    created = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Synthetic malformed field", "document": document},
    )
    assert created.status_code == 201
    path = f"/api/v2/admin/assessment/drafts/{created.json()['id']}"
    preflight = client.post(f"{path}/preflight")
    assert preflight.status_code == 200
    assert preflight.json()["valid"] is False
    assert preflight.json()["errors"][0]["code"] == code
    for action in ("preview", "publish"):
        rejected = client.post(f"{path}/{action}")
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == code
    retained = client.get(path).json()
    assert retained["document"] == document
    assert retained["revision"] == 1


@pytest.mark.parametrize("schema", [[], {}, "unsupported"], ids=["list", "object", "unknown"])
@pytest.mark.parametrize(
    "action", ["preflight", "preview", "publish", "duplicate", "migrate-v2", "import-questions"]
)
def test_saved_invalid_schema_returns_structured_errors_without_mutation(
    tmp_path: Path, schema: object, action: str
) -> None:
    client, _ = _client(tmp_path)
    document = v2_document()
    document["schema"] = schema
    created = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Synthetic invalid schema", "document": document},
    )
    assert created.status_code == 201
    source = created.json()
    path = f"/api/v2/admin/assessment/drafts/{source['id']}"
    if action == "import-questions":
        destination = client.post(
            "/api/v2/admin/assessment/drafts",
            json={"title": "Synthetic destination", "document": v2_document()},
        ).json()
        destination_path = f"/api/v2/admin/assessment/drafts/{destination['id']}"
        response = client.post(
            f"{destination_path}/import-questions",
            json={
                "sourceDraftId": source["id"],
                "itemIds": ["item-pattern"],
                "expectedRevision": 1,
            },
        )
        retained_destination = client.get(destination_path).json()
        assert retained_destination["document"] == destination["document"]
        assert retained_destination["revision"] == 1
    elif action == "duplicate":
        response = client.post(f"{path}/{action}", json={"title": "Synthetic copy"})
    elif action == "migrate-v2":
        response = client.post(f"{path}/{action}", json={"expectedRevision": 1})
    else:
        response = client.post(f"{path}/{action}")
    if action == "preflight":
        assert response.status_code == 200
        assert response.json()["valid"] is False
        assert response.json()["errors"][0]["code"] == "ASSESSMENT_SCHEMA_INVALID"
    elif action == "import-questions":
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "ASSESSMENT_ITEM_NOT_FOUND"
    else:
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "ASSESSMENT_SCHEMA_INVALID"
    retained = client.get(path).json()
    assert retained["document"] == document
    assert retained["revision"] == 1
    assert len(client.get("/api/v2/admin/assessment/drafts").json()["items"]) == (
        2 if action == "import-questions" else 1
    )
