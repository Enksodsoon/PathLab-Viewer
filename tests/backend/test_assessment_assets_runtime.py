import os
from datetime import UTC, datetime
from pathlib import Path

from test_assessment_admin import _client, _document
from wsi_viewer.assessment_assets import assessment_assets_ready
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import PublicationGrant, Slide
from wsi_viewer.publication import delivery_version
from wsi_viewer.storage import StorageLayout


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
