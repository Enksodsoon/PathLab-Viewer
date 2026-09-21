from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.identity import ensure_default_owner_membership
from wsi_viewer.main import create_app
from wsi_viewer.models import (
    ComparisonRegistrationCandidate,
    ComparisonRegistrationRevision,
    ComparisonSet,
    ComparisonSetMember,
    Job,
    LibraryShare,
    ShareSlide,
    Slide,
    User,
)
from wsi_viewer.readiness import ALEMBIC_HEAD
from wsi_viewer.security import hash_password
from wsi_viewer.stack_service import activate_ready_slide_memberships, remove_slide_from_stacks


def _client(
    tmp_path: Path, *, enabled: bool, hisalign: bool = False, valis: bool = False
) -> TestClient:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'test.sqlite3'}",
        data_root=tmp_path / "data",
        secret_key="alignment-test-secret-that-is-long-enough",
        secure_cookies=False,
        tus_internal_upload_dir=tmp_path / "tus",
        alignment_enabled=enabled,
        alignment_hisalign_enabled=hisalign,
        alignment_valis_enabled=valis,
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
        assert payload["status"] == "queued"

        first = client.post(
            f"/api/v1/admin/comparison-sets/{payload['id']}/register", headers=headers
        )
        second = client.post(
            f"/api/v1/admin/comparison-sets/{payload['id']}/register", headers=headers
        )
        assert first.status_code == second.status_code == 202
        assert first.json()["queuedPairs"] == 0
        assert second.json()["queuedPairs"] == 0
        with session_factory(client.app.state.settings)() as database:
            assert database.query(Job).filter(Job.kind == "align").count() == 2
        jobs = client.get(f"/api/v1/admin/comparison-sets/{payload['id']}/jobs").json()
        assert {job["kind"] for job in jobs} == {"align"}
        assert {job["setVersion"] for job in jobs} == {payload["version"]}
        assert all(job["createdAt"] for job in jobs)


def test_slide_stack_membership_lifecycle_and_suggestions(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Case stack",
                "slideIds": ["slide-1"],
                "referenceSlideId": "slide-1",
            },
        )
        assert created.status_code == 201, created.text
        stack = created.json()
        assert stack["status"] == "draft"
        assert stack["members"][0]["anchorSlideId"] is None

        summaries = client.get("/api/v1/admin/slides/slide-1/stacks")
        assert summaries.status_code == 200
        assert summaries.json()[0]["role"] == "reference"
        suggestions = client.get("/api/v1/admin/slides/slide-1/stack-suggestions")
        assert {item["slideId"] for item in suggestions.json()} == {"slide-2", "slide-3"}

        linked = client.patch(
            f"/api/v1/admin/comparison-sets/{stack['id']}/members",
            headers=headers,
            json={
                "version": stack["version"],
                "add": [{"slideId": "slide-2", "anchorSlideId": "slide-1"}],
                "order": ["slide-2", "slide-1"],
            },
        )
        assert linked.status_code == 200, linked.text
        payload = linked.json()
        assert payload["version"] == stack["version"] + 1
        assert [member["slideId"] for member in payload["members"]] == [
            "slide-2",
            "slide-1",
        ]
        assert payload["members"][0]["anchorSlideId"] == "slide-1"

        stale = client.patch(
            f"/api/v1/admin/comparison-sets/{stack['id']}/members",
            headers=headers,
            json={"version": stack["version"], "add": []},
        )
        assert stale.status_code == 409
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.query(ComparisonSetMember).filter_by(comparison_set_id=stack["id"]).count()
                == 2
            )
            assert database.query(Job).filter(Job.kind == "align").count() == 1


def test_stack_upload_reservation_is_atomic_and_queues_when_ready(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Upload stack",
                "slideIds": ["slide-1"],
                "referenceSlideId": "slide-1",
            },
        ).json()
        endpoint = f"/api/v1/admin/comparison-sets/{stack['id']}/upload-reservations"
        base = {
            "version": stack["version"],
            "displayName": "HER2 serial section",
            "length": 4096,
            "stain": "HER2",
            "anchorSlideId": "slide-1",
            "folderId": None,
            "caseId": "case-a",
            "organSite": "breast",
        }
        rejected = client.post(endpoint, headers=headers, json={**base, "filename": "her2.svs"})
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["code"] == "OME_TIFF_REQUIRED"

        reserved = client.post(
            endpoint, headers=headers, json={**base, "filename": "her2.ome.tiff"}
        )
        assert reserved.status_code == 201, reserved.text
        slide_id = reserved.json()["slide"]["id"]
        manifest = client.get(f"/api/v1/admin/comparison-sets/{stack['id']}").json()
        pending = next(member for member in manifest["members"] if member["slideId"] == slide_id)
        assert pending["state"] == "uploading"
        assert pending["tileSource"] is None
        assert pending["anchorSlideId"] == "slide-1"

        with session_factory(client.app.state.settings)() as database:
            slide = database.get(Slide, slide_id)
            assert slide is not None
            slide.state = SlideState.READY_PRIVATE
            slide.sha256 = "uploaded-sha"
            assert activate_ready_slide_memberships(database, slide) == 1
            database.commit()
            job = database.scalar(select(Job).where(Job.slide_id == slide_id, Job.kind == "align"))
            assert job is not None
            assert job.checkpoint["anchorSlideId"] == "slide-1"
            remove_slide_from_stacks(database, slide_id)
            database.delete(slide)
            database.commit()
            remaining = database.get(ComparisonSet, stack["id"])
            assert remaining is not None
            assert remaining.member_slide_ids == ["slide-1"]

            reference = database.get(Slide, "slide-1")
            assert reference is not None
            remove_slide_from_stacks(database, reference.id)
            database.delete(reference)
            database.commit()
            assert database.get(ComparisonSet, stack["id"]) is None


def test_changing_stack_reference_invalidates_dependent_maps(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Editable anchors",
                "slideIds": ["slide-1", "slide-2"],
                "referenceSlideId": "slide-1",
            },
        ).json()
        with session_factory(client.app.state.settings)() as database:
            item = database.get(ComparisonSet, stack["id"])
            assert item is not None
            item.registrations = {"slide-2": {"status": "ready", "anchorSlideId": "slide-1"}}
            database.commit()

        updated = client.patch(
            f"/api/v1/admin/comparison-sets/{stack['id']}/members",
            headers=headers,
            json={
                "version": stack["version"],
                "add": [],
                "referenceSlideId": "slide-2",
            },
        )
        assert updated.status_code == 200, updated.text
        payload = updated.json()
        assert payload["referenceSlideId"] == "slide-2"
        assert all(member["registration"] is None for member in payload["members"])
        old_reference = next(
            member for member in payload["members"] if member["slideId"] == "slide-1"
        )
        assert old_reference["anchorSlideId"] == "slide-2"


def test_benchmark_queues_enabled_engines_and_promotes_candidate(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True, hisalign=True, valis=False) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Engine bakeoff",
                "slideIds": ["slide-1", "slide-2"],
                "referenceSlideId": "slide-1",
            },
        ).json()
        original_status = created["status"]
        url = f"/api/v1/admin/comparison-sets/{created['id']}"
        disabled = client.post(
            url + "/benchmark",
            headers=headers,
            json={"version": created["version"], "engines": ["valis-1.2.0"]},
        )
        assert disabled.status_code == 409
        queued = client.post(
            url + "/benchmark",
            headers=headers,
            json={
                "version": created["version"],
                "engines": ["native-v12", "hisalign-0.2.1"],
            },
        )
        assert queued.status_code == 202, queued.text
        assert queued.json()["queuedCandidates"] == 2
        assert client.get(url).json()["status"] == original_status
        rerun = client.post(
            url + "/benchmark",
            headers=headers,
            json={
                "version": created["version"],
                "engines": ["hisalign-0.2.1"],
                "rerun": True,
            },
        )
        assert rerun.status_code == 202
        assert rerun.json()["queuedCandidates"] == 1
        cancelled = client.delete(url + "/register", headers=headers)
        assert cancelled.status_code == 200
        assert cancelled.json()["cancelledJobs"] == 4
        with session_factory(client.app.state.settings)() as database:
            assert database.query(Job).filter(Job.kind == "align_benchmark").count() == 3
            assert (
                database.query(Job)
                .filter(Job.kind == "align_benchmark", Job.cancellation_requested_at.is_not(None))
                .count()
                == 3
            )
            candidate = ComparisonRegistrationCandidate(
                comparison_set_id=created["id"],
                slide_id="slide-2",
                set_version=created["version"],
                anchor_slide_id="slide-1",
                source_version="sha-2",
                anchor_version="sha-1",
                engine="hisalign-0.2.1",
                engine_version="commit",
                settings_digest="a" * 64,
                status="ready",
                validation_state="engineering_passed",
                registration={
                    "status": "ready",
                    "movingToReference": [[1, 0, 10], [0, 1, 5]],
                    "triangles": [
                        {
                            "moving": [[0, 0], [100, 0], [0, 100]],
                            "reference": [[10, 5], [110, 5], [10, 105]],
                        }
                    ],
                },
                evidence={"roundTripP95Pixels": 0.1},
            )
            database.add(candidate)
            database.add(
                ComparisonRegistrationRevision(
                    comparison_set_id=created["id"],
                    slide_id="slide-2",
                    set_version=created["version"],
                    source_version="sha-2",
                    anchor_slide_id="slide-1",
                    algorithm_version="native-v12",
                    provenance="automatic",
                    registration={"status": "approximate"},
                )
            )
            stale_candidate = ComparisonRegistrationCandidate(
                comparison_set_id=created["id"],
                slide_id="slide-2",
                set_version=created["version"],
                anchor_slide_id="slide-1",
                source_version="superseded-source",
                anchor_version="sha-1",
                engine="native-v12",
                engine_version="old-build",
                settings_digest="b" * 64,
                status="ready",
                validation_state="engineering_passed",
                registration={"status": "ready"},
                evidence={},
            )
            database.add(stale_candidate)
            database.commit()
            candidate_id = candidate.id
            stale_candidate_id = stale_candidate.id
        stale_promotion = client.post(
            url + f"/candidates/{stale_candidate_id}/promote",
            headers=headers,
            json={"version": created["version"]},
        )
        assert stale_promotion.status_code == 409
        assert stale_promotion.json()["detail"]["code"] == "ALIGNMENT_CANDIDATE_STALE"
        promoted = client.post(
            url + f"/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": created["version"]},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["members"][1]["registration"]["engine"] == "hisalign-0.2.1"
        with session_factory(client.app.state.settings)() as database:
            assert (
                database.query(ComparisonRegistrationRevision)
                .filter(
                    ComparisonRegistrationRevision.comparison_set_id == created["id"],
                    ComparisonRegistrationRevision.slide_id == "slide-2",
                    ComparisonRegistrationRevision.set_version == created["version"],
                )
                .count()
                == 2
            )
        manifest = client.get(url + "/candidates")
        assert manifest.status_code == 200
        assert manifest.json()["candidates"][0]["artifactSha256"] is None


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
            slide = database.get(Slide, "slide-2")
            assert slide is not None
            slide.state = SlideState.CONVERTING
            database.commit()
        assert client.get("/api/v2/public/collections/shared-collection/comparisons").json() == []
        assert (
            client.get(
                f"/api/v2/public/collections/shared-collection/comparisons/{visible_id}"
            ).status_code
            == 404
        )

        with session_factory(client.app.state.settings)() as database:
            share = database.scalar(
                select(LibraryShare).where(LibraryShare.public_id == "shared-collection")
            )
            assert share is not None
            slide = database.get(Slide, "slide-2")
            assert slide is not None
            slide.state = SlideState.READY_PRIVATE
            share.privacy_status = "pending"
            database.commit()
        assert (
            client.get(
                f"/api/v2/public/collections/shared-collection/comparisons/{visible_id}"
            ).status_code
            == 404
        )


def test_correction_preview_save_and_stale_write(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Correction test",
                "slideIds": ["slide-1", "slide-2", "slide-3"],
                "referenceSlideId": "slide-1",
            },
        ).json()
        url = f"/api/v1/admin/comparison-sets/{created['id']}"
        payload = {
            "version": created["version"],
            "referenceSlideId": "slide-2",
            "referencePoints": [[100, 100], [500, 100], [100, 500]],
            "movingPoints": [[120, 110], [520, 110], [120, 510]],
            "previewOnly": True,
        }
        preview = client.put(url + "/corrections/slide-3", headers=headers, json=payload)
        assert preview.status_code == 200, preview.text
        assert preview.json()["members"][2]["registration"]["coordinateReferenceId"] == "slide-2"
        assert client.get(url).json()["members"][2]["registration"] is None
        payload["previewOnly"] = False
        saved = client.put(url + "/corrections/slide-3", headers=headers, json=payload)
        assert saved.status_code == 200, saved.text
        assert saved.json()["version"] == created["version"] + 1
        assert client.get(url).json()["members"][2]["registration"]["provenance"] == "manual"
        assert (
            client.put(url + "/corrections/slide-3", headers=headers, json=payload).status_code
            == 409
        )
        assert len(client.get(url + "/revisions").json()) == 1
        # Updating anchors must not incorrectly require movingPoints.
        updated = client.patch(
            url,
            headers=headers,
            json={"version": saved.json()["version"], "anchors": {"slide-3": "slide-2"}},
        )
        assert updated.status_code == 200, updated.text


def test_correction_rejects_collinear_and_out_of_bounds_points(tmp_path: Path) -> None:
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        created = client.post(
            "/api/v1/admin/comparison-sets",
            headers=headers,
            json={
                "name": "Correction test",
                "slideIds": ["slide-1", "slide-2"],
                "referenceSlideId": "slide-1",
            },
        ).json()
        url = f"/api/v1/admin/comparison-sets/{created['id']}/corrections/slide-2"
        for points in ([[100, 100], [200, 200], [300, 300]], [[100, 100], [1200, 100], [100, 500]]):
            response = client.put(
                url,
                headers=headers,
                json={
                    "version": created["version"],
                    "referencePoints": points,
                    "movingPoints": points,
                },
            )
            assert response.status_code == 422
