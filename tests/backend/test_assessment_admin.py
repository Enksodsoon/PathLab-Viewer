import hashlib
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from wsi_viewer.assessment_routes import _parse_rows
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
        {
            "X-CSRF-Token": "csrf-assessment",
            "X-PathLab-Organization": organization_id,
            "Idempotency-Key": "assessment-test-default",
        }
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


def test_class_draft_context_is_persisted_listed_and_named(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    course = client.post(
        "/api/v2/admin/assessment/courses",
        json={
            "name": "Thoracic Pathology",
            "courseCode": "PATH-301",
            "semester": "Semester 1",
            "academicYear": "2027",
        },
    ).json()
    cohort = client.post(
        f"/api/v2/admin/assessment/courses/{course['id']}/classes",
        json={
            "name": "Demo Cohort",
            "sectionCode": "DEMO-A",
            "description": "",
            "location": "Lab 2",
            "opensAt": None,
            "closesAt": None,
            "rosterRule": {"mode": "all", "filters": []},
        },
    ).json()
    created = client.post(
        "/api/v2/admin/assessment/drafts",
        json={
            "title": "Class quiz",
            "document": {**_document(), "title": "Class quiz"},
            "courseId": course["id"],
            "classId": cohort["id"],
        },
    )
    assert created.status_code == 201
    assert created.json()["courseId"] == course["id"]
    assert created.json()["classId"] == cohort["id"]
    listing = client.get(
        f"/api/v2/admin/assessment/drafts?cohort_id={cohort['id']}"
    ).json()
    assert listing["total"] == 1
    assert listing["items"][0]["courseName"] == "Thoracic Pathology"
    assert listing["items"][0]["className"] == "Demo Cohort"


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


def test_course_requires_academic_year_and_keeps_availability_optional(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    base = {"name": "Surgical Pathology", "courseCode": "PATH-301", "semester": "Semester 1"}

    assert client.post("/api/v2/admin/assessment/courses", json=base).status_code == 422
    assert client.post(
        "/api/v2/admin/assessment/courses",
        json={**base, "academicYear": "   "},
    ).status_code == 422

    created = client.post(
        "/api/v2/admin/assessment/courses",
        json={**base, "academicYear": "2026-2027"},
    )
    assert created.status_code == 201
    assert created.json()["opensAt"] is None
    assert created.json()["closesAt"] is None
    assert created.json()["iconKey"] == "general"
    assert created.json()["scoringMethod"] == "percentage"


def test_course_roster_is_shared_and_classes_select_a_subset(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    course = client.post(
        "/api/v2/admin/assessment/courses",
        json={
            "name": "Surgical Pathology",
            "courseCode": "PATH-301",
            "semester": "Semester 1",
            "academicYear": "2026",
            "iconKey": "microscope",
            "scoringMethod": "percentage",
            "description": "Diagnostic pathology course",
            "opensAt": "2026-08-01T08:00:00Z",
            "closesAt": "2026-12-01T17:00:00Z",
            "status": "active",
        },
    )
    assert course.status_code == 201
    assert course.json()["iconKey"] == "microscope"
    assert datetime.fromisoformat(course.json()["opensAt"]).tzinfo is not None
    assert datetime.fromisoformat(course.json()["closesAt"]).tzinfo is not None
    course_id = course.json()["id"]
    assert client.patch(
        f"/api/v2/admin/assessment/courses/{course_id}",
        json={"iconKey": "anything-at-all"},
    ).status_code == 422
    updated_icon = client.patch(
        f"/api/v2/admin/assessment/courses/{course_id}",
        json={"iconKey": "respiratory"},
    )
    assert updated_icon.status_code == 200
    assert updated_icon.json()["iconKey"] == "respiratory"
    roster_rows = (
        "student_id,first_name,last_name,group,subgroup,email,advisor,national_id\n"
        "s001,Somchai,Prasert,Year 3,A,s001@example.edu,Dr Arun,N001\n"
        "s002,มาลี,ทองชัย,Year 3,B,s002@example.edu,Dr Mali,N002"
    )
    preview_response = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/preview",
        json={"rows": roster_rows},
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()
    committed = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/commit",
        json={"rows": roster_rows, "checksum": preview["checksum"]},
    )
    assert committed.status_code == 201
    roster = client.get(f"/api/v2/admin/assessment/courses/{course_id}/roster").json()
    assert roster["total"] == 2
    assert [column["key"] for column in roster["columns"]] == [
        "student_id", "name", "group", "subgroup", "email", "metadata:advisor", "metadata:national_id", "status",
    ]
    assert {item["studentId"] for item in roster["items"]} == {"s001", "s002"}
    assert any(item["firstName"] == "มาลี" and item["lastName"] == "ทองชัย" for item in roster["items"])
    sorted_roster = client.get(
        f"/api/v2/admin/assessment/courses/{course_id}/roster",
        params={"sort_by": "student_id", "sort_direction": "desc"},
    ).json()
    assert [item["studentId"] for item in sorted_roster["items"]] == ["s002", "s001"]
    section = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/classes",
        json={
            "name": "PATH 301 — Lab A",
            "sectionCode": "LAB-A",
            "location": "Pathology Lab 2",
            "rosterRule": {
                "mode": "filters",
                "filters": [{"field": "subgroup", "values": ["A"]}],
            },
        },
    )
    assert section.status_code == 201
    assert section.json()["studentCount"] == 1
    detail = client.get(f"/api/v2/admin/assessment/courses/{course_id}").json()
    assert detail["rosterCount"] == 2
    assert detail["classCount"] == 1
    assert detail["classes"][0]["studentCount"] == 1
    assert detail["classes"][0]["rosterRule"]["filters"][0]["field"] == "subgroup"
    exported = client.get(f"/api/v2/admin/assessment/courses/{course_id}/roster/export")
    assert exported.status_code == 200
    assert exported.content.startswith(b"\xef\xbb\xbf")
    assert "มาลี" in exported.text
    assert "advisor" in exported.text

    possible_duplicates = (
        "student_id,first_name,last_name,group,national_id\n"
        "s001,Somchai,Prasert,Year 3,N001\n"
        "s003,Somchai,Prasert,Year 3,N003\n"
        "s004,Arthit,Saelim,Year 3,N002"
    )
    duplicate_preview = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/preview",
        json={"rows": possible_duplicates},
    ).json()
    assert duplicate_preview["warningCount"] == 3
    assert {warning["code"] for warning in duplicate_preview["warnings"]} == {
        "existing_student_id", "matching_full_name", "matching_identifier",
    }
    blocked = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/commit",
        json={"rows": possible_duplicates, "checksum": duplicate_preview["checksum"]},
    )
    assert blocked.status_code == 409
    confirmed = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/commit",
        json={"rows": possible_duplicates, "checksum": duplicate_preview["checksum"], "confirmWarnings": True},
    )
    assert confirmed.status_code == 201
    assert confirmed.json() == {"created": 2, "skipped": 1}

    current_roster = client.get(f"/api/v2/admin/assessment/courses/{course_id}/roster").json()
    editable = next(item for item in current_roster["items"] if item["studentId"] == "s002")
    edited = client.patch(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/{editable['id']}/profile",
        json={
            "studentId": "s002-edited",
            "firstName": "มาลี",
            "lastName": "",
            "group": "Year 4",
            "subgroup": "C",
            "email": "malee.updated@example.edu",
            "metadata": {"advisor": "Dr New", "campus": "North"},
        },
    )
    assert edited.status_code == 200
    assert edited.json()["studentId"] == "s002-edited"
    assert edited.json()["lastName"] is None
    assert edited.json()["metadata"] == {"advisor": "Dr New", "campus": "North"}
    collision = client.patch(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/{editable['id']}/profile",
        json={
            "studentId": "s001",
            "firstName": "มาลี",
            "lastName": "",
            "group": "Year 4",
            "subgroup": "C",
            "email": "",
            "metadata": {},
        },
    )
    assert collision.status_code == 409
    assert collision.json()["detail"]["code"] == "ASSESSMENT_STUDENT_ID_EXISTS"

    removed = client.delete(f"/api/v2/admin/assessment/courses/{course_id}/roster")
    assert removed.status_code == 200
    assert removed.json() == {"removed": 4}
    assert client.get(f"/api/v2/admin/assessment/courses/{course_id}/roster").json()["total"] == 0
    detail_after_removal = client.get(f"/api/v2/admin/assessment/courses/{course_id}").json()
    assert detail_after_removal["rosterCount"] == 0
    assert detail_after_removal["classes"][0]["studentCount"] == 0

    restored_rows = "student_id,first_name,group\ns002-edited,มาลี,Year 4"
    restored_preview = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/preview",
        json={"rows": restored_rows},
    ).json()
    restored = client.post(
        f"/api/v2/admin/assessment/courses/{course_id}/roster/import/commit",
        json={"rows": restored_rows, "checksum": restored_preview["checksum"], "confirmWarnings": True},
    )
    assert restored.status_code == 201
    assert restored.json()["created"] == 1


def test_structured_roster_accepts_more_than_two_thousand_unicode_learners() -> None:
    rows = ["student_id,first_name,last_name,group,subgroup,email"]
    rows.extend(f"TH-{index:04d},นักศึกษา{index},ทดสอบ,Year 3,Lab {index % 8},student{index}@example.edu" for index in range(2001))
    parsed = _parse_rows("\n".join(rows), require_structured=True)
    assert len(parsed) == 2001
    assert parsed[-1].first_name == "นักศึกษา2000"


def test_structured_roster_allows_a_single_name() -> None:
    parsed = _parse_rows("student_id,first_name,group\nS-1,มานี,Year 3", require_structured=True)
    assert parsed[0].first_name == "มานี"
    assert parsed[0].last_name is None
    assert parsed[0].display_name == "มานี"


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
    assert client.get(f"/api/v2/admin/assessment/drafts/{source['id']}").status_code == 409
    locked_save = client.patch(
        f"/api/v2/admin/assessment/drafts/{source['id']}",
        headers={"If-Match": str(source["revision"])},
        json={"document": source["document"]},
    )
    assert locked_save.status_code == 409
    assert locked_save.json()["detail"]["code"] == "ASSESSMENT_DRAFT_ARCHIVED"
    restored = client.post(f"/api/v2/admin/assessment/drafts/{source['id']}/restore")
    assert restored.status_code == 200
    assert restored.json()["status"] == "draft"
    assert client.get(f"/api/v2/admin/assessment/drafts/{source['id']}").status_code == 200
