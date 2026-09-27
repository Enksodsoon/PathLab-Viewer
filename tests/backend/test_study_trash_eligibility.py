import csv
import io
from pathlib import Path

from sqlalchemy import select
from test_study_coach import _admin, _client, _publish_pack, _slide
from wsi_viewer.database import session_factory
from wsi_viewer.models import Slide, StudyCourse, StudyLearnerSession, StudyPack
from wsi_viewer.storage import StorageLayout


def test_trashed_study_slide_denied_without_removing_pack_or_learner(tmp_path: Path) -> None:
    with _client(tmp_path) as client:
        admin = _admin(client)
        slide = _slide(client)
        derivative = (
            StorageLayout(client.app.state.settings.data_root)
            .for_slide(slide.id)
            .private_derivative
        )
        derivative.mkdir(parents=True)
        descriptor = derivative / "slide.dzi"
        descriptor.write_text(
            '<Image TileSize="256" Overlap="0" Format="jpg" '
            'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
            '<Size Width="256" Height="256"/></Image>',
            encoding="utf-8",
        )
        pack = _publish_pack(client, admin, slide)
        created = client.post(
            "/api/v1/admin/study/courses",
            headers=admin,
            json={
                "packId": pack["id"],
                "title": "Synthetic trash eligibility",
                "learnerLimit": 1,
            },
        )
        assert created.status_code == 201
        course_id = created.json()["id"]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/prepare", headers=admin
            ).status_code
            == 200
        )
        invitations = client.post(
            f"/api/v1/admin/study/courses/{course_id}/invitations",
            headers=admin,
            json={"count": 1},
        )
        assert invitations.status_code == 200
        code = next(csv.DictReader(io.StringIO(invitations.text)))["invitation_code"]
        assert (
            client.post(
                f"/api/v1/admin/study/courses/{course_id}/activate", headers=admin
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/v1/study/redeem", json={"code": code, "noticeAccepted": True}
            ).status_code
            == 201
        )
        tile_url = f"/api/v1/study/slides/{slide.id}/tiles/slide.dzi"
        assert client.get(tile_url).status_code == 200
        assert (
            client.post(f"/api/v2/admin/slides/{slide.id}/trash", headers=admin).status_code == 200
        )
        denied = client.get(tile_url)
        assert denied.status_code == 404
        assert denied.json()["detail"]["code"] == "STUDY_SLIDE_NOT_FOUND"
        assert client.get("/api/v1/study/session").status_code == 200
        with session_factory(client.app.state.settings)() as database:
            assert database.get(Slide, slide.id).trashed_at is not None
            assert (
                database.get(StudyPack, pack["id"]).definition["slides"][0]["viewerSlideId"]
                == slide.id
            )
            assert database.get(StudyCourse, course_id).status == "active"
            assert database.scalar(select(StudyLearnerSession.id)) is not None
        assert descriptor.is_file()
        assert (
            client.post(f"/api/v2/admin/slides/{slide.id}/restore", headers=admin).status_code
            == 200
        )
        assert client.get(tile_url).status_code == 200
