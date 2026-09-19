from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.identity import ensure_default_owner_membership
from wsi_viewer.main import create_app
from wsi_viewer.models import ComparisonSet, Job, LibraryShare, ShareSlide, Slide, User
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password


def _client(tmp_path: Path, *, enabled: bool) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="alignment-test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        alignment_enabled=enabled,
    )
    create_schema(settings)
    with session_factory(settings)() as database:
        database.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        database.execute(text("INSERT INTO alembic_version VALUES (:head)"), {"head": ALEMBIC_HEAD})
        admin = User(username="admin", password_hash=hash_password("correct horse battery"))
        database.add(admin)
        database.flush()
        ensure_default_owner_membership(database, admin)
        for index, stain in enumerate(("H&E", "PAS", "CD3"), start=1):
            database.add(
                Slide(
                    id=f"slide-{index}",
                    public_id=f"public-{index}",
                    display_name=stain,
                    original_filename=f"{stain}.ome.tiff",
                    source_bytes=1024,
                    state=SlideState.READY_PRIVATE,
                    stain=stain,
                    sha256=f"sha-{index}",
                    slide_metadata={
                        "width": 1000,
                        "height": 800,
                        "physicalSizeX": 0.25,
                        "physicalSizeY": 0.25,
                    },
                )
            )
        database.commit()
    return TestClient(create_app(settings))


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/session",
        json={
            "username": "admin",
            "password": "correct horse battery",
        },
    )
    return {"X-CSRF-Token": response.json()["csrfToken"]}


def test_alignment_api_is_hidden_when_disabled(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=False) as client:
        assert client.get("/api/v1/admin/comparison-sets").status_code == 404


def test_admin_creates_set_and_queues_idempotent_pair_jobs(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Any tissue stains",
                "slideIds": ["slide-1", "slide-2", "slide-3"],
                "referenceSlideId": "slide-1",
            },
        )
        assert created.status_code == 201, created.text
        payload = created.json()
        assert payload["referenceSlideId"] == "slide-1"
        assert [member["stain"] for member in payload["members"]] == ["H&E", "PAS", "CD3"]

        first = client.post(
            f"/api/v1/admin/comparison-sets/{payload['id']}/register", headers=headers
        )
        second = client.post(
            f"/api/v1/admin/comparison-sets/{payload['id']}/register", headers=headers
        )
        assert first.status_code == second.status_code == 202
        assert first.json()["queuedPairs"] == 2
        assert second.json()["queuedPairs"] == 0
        with session_factory(client.app.state.settings)() as database:
            assert database.query(Job).filter(Job.kind == "align").count() == 2


def test_set_rejects_unready_or_missing_reference_members(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        missing = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Bad set",
                "slideIds": ["slide-1", "slide-2"],
                "referenceSlideId": "slide-3",
            },
        )
        assert missing.status_code == 422
        assert missing.json()["detail"]["code"] == "REFERENCE_NOT_MEMBER"


def test_numbered_sections_queue_against_their_matching_he_anchor(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        with session_factory(client.app.state.settings)() as database:
            first, second, stain = [database.get(Slide, f"slide-{index}") for index in range(1, 4)]
            assert first and second and stain
            first.display_name, first.original_filename = "H&E 1of2", "case_HE_1of2.svs"
            second.display_name, second.original_filename, second.stain = (
                "H&E 2of2",
                "case_HE_2of2.svs",
                "H&E",
            )
            stain.display_name, stain.original_filename, stain.stain = (
                "PAS 2of2",
                "case_PAS_2of2.svs",
                "PAS",
            )
            database.commit()
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Numbered serial sections",
                "slideIds": ["slide-1", "slide-2", "slide-3"],
                "referenceSlideId": "slide-1",
            },
        ).json()

        response = client.post(
            f"/api/v1/admin/comparison-sets/{created['id']}/register", headers=headers
        )

        assert response.status_code == 202
        with session_factory(client.app.state.settings)() as database:
            jobs = {job.slide_id: job for job in database.query(Job).all()}
            assert jobs["slide-2"].checkpoint["anchorSlideId"] == "slide-1"
            assert jobs["slide-3"].checkpoint["anchorSlideId"] == "slide-2"
            assert jobs["slide-2"].created_at <= jobs["slide-3"].created_at


def test_shared_collection_lists_only_fully_authorized_comparisons(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        with session_factory(client.app.state.settings)() as database:
            share = LibraryShare(
                public_id="shared-collection",
                target_type="collection",
                target_id="collection-id",
                privacy_status="passed",
            )
            database.add(share)
            database.flush()
            database.add_all(
                [
                    ShareSlide(share_id=share.id, slide_id="slide-1", sort_order=0),
                    ShareSlide(share_id=share.id, slide_id="slide-2", sort_order=1),
                ]
            )
            visible = ComparisonSet(
                name="Shared H&E and PAS",
                reference_slide_id="slide-1",
                member_slide_ids=["slide-1", "slide-2"],
                source_versions={"slide-1": "sha-1", "slide-2": "sha-2"},
                registrations={},
                status="partial",
            )
            hidden = ComparisonSet(
                name="Includes unshared IHC",
                reference_slide_id="slide-1",
                member_slide_ids=["slide-1", "slide-3"],
                source_versions={"slide-1": "sha-1", "slide-3": "sha-3"},
                registrations={},
                status="partial",
            )
            database.add_all([visible, hidden])
            database.commit()
            visible_id = visible.id

        response = client.get("/api/v2/public/collections/shared-collection/comparisons")
        assert response.status_code == 200
        assert response.json() == [
            {"id": visible_id, "name": "Shared H&E and PAS", "status": "partial"}
        ]

        with session_factory(client.app.state.settings)() as database:
            share = database.scalar(
                select(LibraryShare).where(LibraryShare.public_id == "shared-collection")
            )
            assert share is not None
            share.privacy_status = "pending"
            database.commit()
        assert (
            client.get(
                f"/api/v2/public/collections/shared-collection/comparisons/{visible_id}"
            ).status_code
            == 404
        )
