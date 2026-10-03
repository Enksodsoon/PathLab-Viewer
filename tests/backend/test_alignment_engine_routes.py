from pathlib import Path

import pytest
from sqlalchemy import select
from test_alignment_api import _client, _headers
from wsi_viewer.alignment_engines import ENGINE_VERSIONS, RECIPE_STAGES, settings_digest
from wsi_viewer.database import session_factory
from wsi_viewer.models import ComparisonRegistrationCandidate, ComparisonSet, Job


def _stack(client, headers):
    return client.post(
        "/api/v1/admin/comparison-sets",
        headers=headers,
        json={
            "name": "Engine admission",
            "slideIds": ["slide-1", "slide-2"],
            "referenceSlideId": "slide-1",
        },
    ).json()


@pytest.mark.parametrize(
    "engine",
    [
        "wsireg-0.3.10",
        "deeperhistreg-classical",
        "deeperhistreg-learned",
        "native-wsireg",
        "valis-rigid-wsireg",
        "native-valis",
    ],
)
def test_optional_recipes_require_enabled_stages(tmp_path: Path, engine: str):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": [engine]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_ENGINE_DISABLED"


def test_benchmark_api_uses_total_ten_minute_ceiling(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": ["native-v12"]},
        )
        assert response.status_code == 202
        with session_factory(client.app.state.settings)() as database:
            job = database.scalar(select(Job).where(Job.kind == "align_benchmark"))
            assert job is not None
            assert job.resource_limits["timeoutSeconds"] == 600


def test_native_overview_available_and_aliases_queue_distinct_from_legacy(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        availability = client.get(url + "/candidates").json()["engineAvailability"]
        assert availability.get("native-overview-v6", {}).get("available") is True
        assert availability["native-v12"]["available"] is True
        response = client.post(
            url + "/benchmark",
            headers=headers,
            json={
                "version": stack["version"],
                "engines": ["native", "native-overview", "native-overview-v6", "native-v12"],
            },
        )
        assert response.status_code == 202, response.json()
        assert response.json()["engines"] == ["native-overview-v6", "native-v12"]
        assert response.json()["queuedCandidates"] == 2
        repeated = client.post(
            url + "/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": ["native", "native-v12"]},
        )
        assert repeated.status_code == 202, repeated.json()
        assert repeated.json()["queuedCandidates"] == 0
        with session_factory(client.app.state.settings)() as database:
            jobs = list(database.scalars(select(Job).where(Job.kind == "align_benchmark")))
            assert {job.checkpoint["engine"] for job in jobs} == {
                "native-overview-v6",
                "native-v12",
            }
            assert len(jobs) == 2
            assert all(job.resource_limits["timeoutSeconds"] == 600 for job in jobs)


@pytest.mark.parametrize("engine", ["native-v12", "native-overview-v6"])
@pytest.mark.parametrize("status", ["ready", "approximate"])
def test_native_candidate_identity_preserves_promotion_status_boundary(
    tmp_path: Path, engine, status
):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        with session_factory(client.app.state.settings)() as database:
            candidate_id, saved = _hybrid_candidate(
                database, stack, engine=engine, map_status=status
            )
            row = database.get(ComparisonRegistrationCandidate, candidate_id)
            row.status = status
            database.commit()
        manifest = client.get(url + "/candidates").json()
        assert manifest["candidates"][0]["currentSettings"] is True
        response = client.post(
            url + f"/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert response.status_code == (200 if status == "ready" else 409), response.json()
        with session_factory(client.app.state.settings)() as database:
            registration = database.get(ComparisonSet, stack["id"]).registrations["slide-2"]
            if status == "ready":
                assert registration["engine"] == engine
                assert registration["settingsDigest"] == settings_digest(engine)
                assert registration["triangles"][0]["reference"][0] == [10, 5]
            else:
                assert registration == saved


def test_removed_engine_candidate_remains_reviewable_and_cannot_promote(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        with session_factory(client.app.state.settings)() as database:
            row = ComparisonRegistrationCandidate(
                comparison_set_id=stack["id"],
                slide_id="slide-2",
                set_version=stack["version"],
                anchor_slide_id="slide-1",
                source_version="sha-2",
                anchor_version="sha-1",
                engine="removed-engine",
                engine_version="old",
                settings_digest="x" * 64,
                status="ready",
                validation_state="engineering_passed",
                registration={},
                evidence={},
            )
            database.add(row)
            database.commit()
            candidate_id = row.id
        response = client.get(url + "/candidates")
        assert response.status_code == 200
        assert response.json()["candidates"][0]["currentSettings"] is False
        response = client.post(
            url + f"/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_CANDIDATE_SETTINGS_STALE"


def _hybrid_candidate(
    database,
    stack,
    *,
    engine="native-wsireg",
    measurements=None,
    validation_state="engineering_passed",
    map_status="ready",
):
    saved = {"status": "approximate", "provenance": "manual", "saved": True}
    database.get(ComparisonSet, stack["id"]).registrations = {"slide-2": saved}
    row = ComparisonRegistrationCandidate(
        comparison_set_id=stack["id"],
        slide_id="slide-2",
        set_version=stack["version"],
        anchor_slide_id="slide-1",
        source_version="sha-2",
        anchor_version="sha-1",
        engine=engine,
        engine_version=ENGINE_VERSIONS[engine],
        settings_digest=settings_digest(engine),
        status="ready",
        validation_state=validation_state,
        registration={
            "status": map_status,
            "movingToReference": [[1, 0, 10], [0, 1, 5]],
            "anchorSlideId": "slide-1",
            "coordinateReferenceId": "slide-1",
            "triangles": [
                {
                    "moving": [[0, 0], [100, 0], [0, 100]],
                    "reference": [[10, 5], [110, 5], [10, 105]],
                }
            ],
            "evidence": {"valisLocalEvidenceQualified": True},
        },
        evidence={} if measurements is None else {"benchmarkMeasurements": measurements},
    )
    database.add(row)
    database.commit()
    return row.id, saved


@pytest.mark.parametrize(
    "measurements,validation_state",
    [
        (None, "engineering_passed"),
        (None, "landmark_passed"),
        ({"qualified": True}, "engineering_passed"),
        (
            {
                "qualified": False,
                "improvesOnIndividualStages": True,
                "settingsDigest": settings_digest("native-wsireg"),
            },
            "landmark_passed",
        ),
        (
            {
                "qualified": True,
                "improvesOnIndividualStages": False,
                "settingsDigest": settings_digest("native-wsireg"),
            },
            "landmark_passed",
        ),
        ({"qualified": True, "improvesOnIndividualStages": True}, "landmark_passed"),
        (
            {"qualified": True, "improvesOnIndividualStages": True, "settingsDigest": "stale"},
            "landmark_passed",
        ),
        (
            {
                "qualified": True,
                "improvesOnIndividualStages": True,
                "settingsDigest": settings_digest("native-wsireg"),
            },
            "engineering_passed",
        ),
    ],
)
def test_hybrid_promotion_requires_bound_improvement_and_landmark_qualification(
    tmp_path: Path, measurements, validation_state
):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        with session_factory(client.app.state.settings)() as database:
            candidate_id, saved = _hybrid_candidate(
                database, stack, measurements=measurements, validation_state=validation_state
            )
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert response.status_code == 409, response.status_code
        assert response.json()["detail"]["code"] == "ALIGNMENT_CANDIDATE_NOT_PROMOTABLE"
        with session_factory(client.app.state.settings)() as database:
            assert database.get(ComparisonSet, stack["id"]).registrations == {"slide-2": saved}


@pytest.mark.parametrize("engine", list(RECIPE_STAGES))
def test_hybrid_promotion_accepts_current_independently_qualified_improvement(
    tmp_path: Path, engine
):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        measurements = {
            "qualified": True,
            "improvesOnIndividualStages": True,
            "settingsDigest": settings_digest(engine),
        }
        with session_factory(client.app.state.settings)() as database:
            candidate_id, _ = _hybrid_candidate(
                database,
                stack,
                engine=engine,
                measurements=measurements,
                validation_state="landmark_passed",
            )
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert response.status_code == 200, response.json()
        registration = response.json()["members"][1]["registration"]
        assert registration["status"] == "ready"
        assert registration["engine"] == engine
        assert registration["triangles"][0]["reference"][0] == [10, 5]


def test_hybrid_benchmark_qualification_does_not_bypass_existing_map_validation(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        measurements = {
            "qualified": True,
            "improvesOnIndividualStages": True,
            "settingsDigest": settings_digest("native-wsireg"),
        }
        with session_factory(client.app.state.settings)() as database:
            candidate_id, saved = _hybrid_candidate(
                database,
                stack,
                measurements=measurements,
                validation_state="landmark_passed",
                map_status="rejected",
            )
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/candidates/{candidate_id}/promote",
            headers=headers,
            json={"version": stack["version"]},
        )
        assert response.status_code == 409
        with session_factory(client.app.state.settings)() as database:
            assert database.get(ComparisonSet, stack["id"]).registrations == {"slide-2": saved}
