import os
from datetime import UTC, datetime
from pathlib import Path

from test_assessment_admin import _client, _document
from wsi_viewer.assessment_assets import assessment_assets_ready, definition_slide_ids
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import AssessmentCourse, Cohort, Folder, PublicationGrant, Slide
from wsi_viewer.publication import delivery_version
from wsi_viewer.storage import StorageLayout


def test_definition_slide_ids_includes_all_question_media() -> None:
    assert definition_slide_ids(
        {
            "sections": [
                {
                    "items": [
                        {
                            "slideId": "diagnostic-slide",
                            "media": {"kind": "slide-thumbnail", "slideId": "media-one"},
                            "mediaItems": [
                                {"kind": "slide-thumbnail", "slideId": "media-two"},
                                {
                                    "kind": "uploaded-image",
                                    "assetPath": "data:image/png;base64,aA==",
                                },
                            ],
                        }
                    ]
                }
            ]
        }
    ) == ["diagnostic-slide", "media-one", "media-two"]


def _seed_static_slide(client, slide_id: str = "assessment-slide") -> tuple[Path, str]:
    settings = client.app.state.settings
    slide = Slide(
        id=slide_id,
        public_id="assessment-public-slide",
        display_name="Eligible teaching slide",
        original_filename="teaching.ome.tiff",
        source_bytes=1024,
        derivative_bytes=2048,
        derivative_file_count=2,
        render_mode="static_dzi",
        state=SlideState.PUBLISHED,
        slide_metadata={"width": 1024, "height": 768},
        sha256="a" * 64,
        published_at=datetime.now(UTC),
        privacy_status="passed",
    )
    with session_factory(settings)() as database:
        database.add(slide)
        database.flush()
        database.add(
            PublicationGrant(slide_id=slide.id, source_type="individual", source_id=slide.id)
        )
        database.commit()
        version = delivery_version(slide)
    derivative = settings.data_root / "private" / slide.id
    (derivative / "slide_files" / "0").mkdir(parents=True)
    (derivative / "slide.dzi").write_text(
        '<Image TileSize="256" Overlap="1" Format="jpg"><Size Width="1024" Height="768"/></Image>',
        encoding="utf-8",
    )
    (derivative / "slide_files" / "0" / "0_0.jpg").write_bytes(b"real-static-tile")
    return derivative, version


def test_eligible_slides_only_exposes_existing_thumbnails(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    derivative, version = _seed_static_slide(client, "thumbnail-check-slide")
    with session_factory(client.app.state.settings)() as database:
        slide = database.get(Slide, "thumbnail-check-slide")
        assert slide is not None
        slide.thumbnail_filename = "thumbnail.jpg"
        database.commit()

    missing = client.get("/api/v2/admin/assessment/slides?query=Eligible")
    assert missing.status_code == 200
    assert missing.json()["items"][0]["thumbnail"] is None

    (derivative / "thumbnail.jpg").write_bytes(b"jpeg-thumbnail")
    available = client.get("/api/v2/admin/assessment/slides?query=Eligible")
    assert available.status_code == 200
    assert available.json()["items"][0]["thumbnail"].endswith(
        f"/{version}/thumbnail.jpg"
    )


def test_eligible_slides_are_scoped_to_the_draft_class_folder(tmp_path: Path) -> None:
    client, organization_id = _client(tmp_path)
    _seed_static_slide(client, "class-slide")
    with session_factory(client.app.state.settings)() as database:
        folder = Folder(name="Class slides", normalized_name="class slides")
        database.add(folder)
        database.flush()
        course = AssessmentCourse(
            organization_id=organization_id,
            name="Thoracic pathology",
            course_code="THOR-101",
            semester="2026-1",
        )
        database.add(course)
        database.flush()
        cohort = Cohort(
            organization_id=organization_id,
            name="Thoracic pathology A",
            assessment_course_id=course.id,
            folder_id=folder.id,
        )
        database.add(cohort)
        slide = database.get(Slide, "class-slide")
        assert slide is not None
        slide.folder_id = folder.id
        database.commit()
        cohort_id = cohort.id
        course_id = course.id

    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={
            "title": "Class assessment",
            "document": _document(),
            "courseId": course_id,
            "classId": cohort_id,
        },
    )
    assert draft.status_code == 201, draft.text
    draft = draft.json()
    scoped = client.get(f"/api/v2/admin/assessment/slides?draft_id={draft['id']}")
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["scopeLabel"] == "Thoracic pathology A"
    assert [item["id"] for item in scoped.json()["items"]] == ["class-slide"]

    unrelated = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Unscoped assessment", "document": _document()},
    ).json()
    empty = client.get(f"/api/v2/admin/assessment/slides?draft_id={unrelated['id']}")
    assert empty.status_code == 200
    assert empty.json()["items"] == []


def test_prepare_creates_scoped_hardlink_grants_and_open_requires_them(tmp_path: Path) -> None:
    client, _ = _client(tmp_path)
    source, version = _seed_static_slide(client)
    eligible = client.get("/api/v2/admin/assessment/slides?query=Eligible")
    assert eligible.status_code == 200
    assert eligible.json()["items"][0]["id"] == "assessment-slide"

    document = _document()
    document["items"][0]["slideId"] = "assessment-slide"
    draft = client.post(
        "/api/v2/admin/assessment/drafts",
        json={"title": "Slide assessment", "document": document},
    ).json()
    published = client.post(
        f"/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        json={
            "mode": "formative",
            "durationSeconds": 3600,
            "maxAttempts": 2,
            "syntheticFixture": True,
        },
    ).json()
    administration_id = published["administrationId"]
    public_id = published["publicId"]
    unopened = client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/open")
    assert unopened.status_code == 409
    assert unopened.json()["detail"]["code"] == "ASSESSMENT_ASSETS_NOT_PREPARED"

    prepared = client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/prepare")
    assert prepared.status_code == 200, prepared.text
    assert prepared.json()["slidesPrepared"] == 1
    target = (
        client.app.state.settings.data_root
        / "delivery"
        / "assessment"
        / public_id
        / "assessment-public-slide"
        / version
    )
    assert os.path.samefile(source / "slide.dzi", target / "slide.dzi")
    assert os.path.samefile(
        source / "slide_files" / "0" / "0_0.jpg",
        target / "slide_files" / "0" / "0_0.jpg",
    )
    opened = client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/open")
    assert opened.status_code == 200
    metadata = client.get(f"/api/v2/assessment/administrations/{public_id}")
    assert metadata.json()["assets"]["assessment-slide"].endswith("/slide.dzi")
    with session_factory(client.app.state.settings)() as database:
        assert assessment_assets_ready(database, StorageLayout(client.app.state.settings.data_root))
    (target / "slide.dzi").unlink()
    with session_factory(client.app.state.settings)() as database:
        assert not assessment_assets_ready(
            database, StorageLayout(client.app.state.settings.data_root)
        )
    os.link(source / "slide.dzi", target / "slide.dzi")

    client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/close")
    purged = client.post(f"/api/v2/admin/assessment/administrations/{administration_id}/purge")
    assert purged.status_code == 200
    assert not target.exists()
