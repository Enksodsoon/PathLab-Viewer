import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.main import create_app
from wsi_viewer.models import Organization, OrganizationMembership, Session, User


def _client(tmp_path: Path) -> tuple[TestClient, str]:
    settings = Settings(
        _env_file=None,
        service_role="assessment",
        assessment_enabled=True,
        identity_governance_enabled=True,
        database_url=f"sqlite:///{tmp_path / 'assessment-admin.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="assessment-test-secret-that-is-long-enough",
        secure_cookies=False,
    )
    create_schema(settings)
    token = "assessment-admin-session"
    with session_factory(settings)() as database:
        user = User(username="instructor", password_hash="unused")
        database.add(user)
        database.flush()
        organization = Organization(slug="pathology", display_name="Pathology")
        database.add(organization)
        database.flush()
        database.add(
            OrganizationMembership(
                organization_id=organization.id,
                user_id=user.id,
                role="owner",
                created_by_user_id=user.id,
            )
        )
        database.add(
            Session(
                id=hashlib.sha256(token.encode()).hexdigest(),
                user_id=user.id,
                csrf_token="csrf-assessment",
                expires_at=datetime(2027, 8, 24, tzinfo=UTC),
            )
        )
        database.commit()
        organization_id = organization.id
    client = TestClient(create_app(settings))
    client.cookies.set("pathlab_session", token)
    client.headers.update(
        {"X-CSRF-Token": "csrf-assessment", "X-PathLab-Organization": organization_id}
    )
    return client, organization_id


def _document() -> dict[str, object]:
    return {
        "title": "Lung pathology",
        "items": [
            {
                "id": "item-1",
                "type": "multiple-choice",
                "prompt": "Diagnosis?",
                "points": "1",
                "required": True,
                "options": [
                    {"id": "option-a", "label": "Adenocarcinoma"},
                    {"id": "option-b", "label": "Reactive change"},
                ],
                "answerKey": {"optionIds": ["option-a"]},
            }
        ],
        "settings": {},
    }


def test_draft_autosave_conflict_preview_and_immutable_publish(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    created = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Lung pathology", "document": _document()},
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["revision"] == 1

    saved = client.patch(
        f"/api/v2/admin/assessment/drafts/{draft['id']}",
        headers={"If-Match": "1"},
        json={"document": {**_document(), "title": "Updated"}},
    )
    assert saved.status_code == 200
    assert saved.json()["revision"] == 2
    conflict = client.patch(
        f"/api/v2/admin/assessment/drafts/{draft['id']}",
        headers={"If-Match": "1"},
        json={"document": _document()},
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["code"] == "ASSESSMENT_DRAFT_CONFLICT"

    preview = client.post(f"/api/v2/admin/assessment/drafts/{draft['id']}/preview")
    assert preview.status_code == 200
    assert "answerKey" not in repr(preview.json()["learnerManifest"])
    published = client.post(f"/api/v2/admin/assessment/drafts/{draft['id']}/publish")
    assert published.status_code == 201
    assert published.json()["schema"] == "pathlab.assessment/1"


def test_class_import_is_preview_then_explicit_bounded_commit(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    created = client.post("/api/v2/admin/assessment/classes", json={"name": "Year 3"})
    assert created.status_code == 201
    cohort_id = created.json()["id"]
    classes = client.get("/api/v2/admin/assessment/classes")
    assert classes.status_code == 200
    assert classes.json()["items"][0]["name"] == "Year 3"
    preview = client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/preview",
        json={"rows": "s001,Somchai P.\ns002,Malee T."},
    )
    assert preview.status_code == 200
    assert preview.json()["validCount"] == 2
    checksum = preview.json()["checksum"]
    committed = client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/commit",
        json={"rows": "s001,Somchai P.\ns002,Malee T.", "checksum": checksum},
    )
    assert committed.status_code == 201
    assert committed.json()["created"] == 2
    students = client.get(f"/api/v2/admin/assessment/classes/{cohort_id}/students?limit=50")
    assert students.status_code == 200
    assert students.json()["total"] == 2
    assert "s001" not in students.text

    learner_id = students.json()["items"][0]["id"]
    withdrawn = client.patch(
        f"/api/v2/admin/assessment/classes/{cohort_id}/students/{learner_id}",
        json={"status": "withdrawn"},
    )
    assert withdrawn.status_code == 200
    recommitted = client.post(
        f"/api/v2/admin/assessment/classes/{cohort_id}/import/commit",
        json={"rows": "s001,Somchai P.\ns002,Malee T.", "checksum": checksum},
    )
    assert recommitted.status_code == 201
    assert recommitted.json()["created"] == 1
    archived = client.patch(
        f"/api/v2/admin/assessment/classes/{cohort_id}",
        json={"status": "archived"},
    )
    assert archived.json()["status"] == "archived"


def test_duplicate_import_and_archive_generate_fresh_ids(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    source = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Source", "document": _document()},
    ).json()
    duplicate = client.post(
        f"/api/v2/admin/assessment/drafts/{source['id']}/duplicate",
        json={"title": "Duplicate"},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["document"]["items"][0]["id"] != "item-1"
    assert duplicate.json()["document"]["items"][0]["options"][0]["id"] != "option-a"
    destination = client.post(
        "/api/v2/admin/assessment/drafts",
        json={
            "title": "Destination",
            "document": {"title": "Destination", "items": [], "settings": {}},
        },
    ).json()
    imported = client.post(
        f"/api/v2/admin/assessment/drafts/{destination['id']}/import-questions",
        json={"sourceDraftId": source["id"], "itemIds": ["item-1"], "expectedRevision": 1},
    )
    assert imported.status_code == 200
    assert imported.json()["revision"] == 2
    assert imported.json()["document"]["items"][0]["id"] != "item-1"
    archived = client.post(f"/api/v2/admin/assessment/drafts/{source['id']}/archive")
    assert archived.status_code == 200
    assert archived.json()["status"] == "archived"
