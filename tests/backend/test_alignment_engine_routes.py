from pathlib import Path

import pytest
from sqlalchemy import select
from test_alignment_api import _client, _headers
from wsi_viewer.database import session_factory
from wsi_viewer.models import ComparisonRegistrationCandidate, Job


def _stack(client, headers):
    return client.post("/api/v1/admin/comparison-sets", headers=headers, json={
        "name": "Engine admission", "slideIds": ["slide-1", "slide-2"],
        "referenceSlideId": "slide-1",
    }).json()


@pytest.mark.parametrize("engine", ["wsireg-0.3.10", "deeperhistreg-classical",
                                  "deeperhistreg-learned", "native-wsireg",
                                  "valis-rigid-wsireg", "native-valis"])
def test_optional_recipes_require_enabled_stages(tmp_path: Path, engine: str):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        response = client.post(f"/api/v1/admin/comparison-sets/{stack['id']}/benchmark",
                               headers=headers, json={"version": stack["version"],
                                                      "engines": [engine]})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_ENGINE_DISABLED"


def test_benchmark_api_uses_total_ten_minute_ceiling(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        response = client.post(f"/api/v1/admin/comparison-sets/{stack['id']}/benchmark",
                               headers=headers, json={"version": stack["version"],
                                                      "engines": ["native-v12"]})
        assert response.status_code == 202
        with session_factory(client.app.state.settings)() as database:
            job = database.scalar(select(Job).where(Job.kind == "align_benchmark"))
            assert job is not None
            assert job.resource_limits["timeoutSeconds"] == 600


def test_removed_engine_candidate_remains_reviewable_and_cannot_promote(tmp_path: Path):
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        with session_factory(client.app.state.settings)() as database:
            row = ComparisonRegistrationCandidate(
                comparison_set_id=stack["id"], slide_id="slide-2", set_version=stack["version"],
                anchor_slide_id="slide-1", source_version="sha-2", anchor_version="sha-1",
                engine="removed-engine", engine_version="old", settings_digest="x" * 64,
                status="ready", validation_state="engineering_passed", registration={}, evidence={},
            )
            database.add(row)
            database.commit()
            candidate_id = row.id
        response = client.get(url + "/candidates")
        assert response.status_code == 200
        assert response.json()["candidates"][0]["currentSettings"] is False
        response = client.post(url + f"/candidates/{candidate_id}/promote", headers=headers,
                               json={"version": stack["version"]})
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_CANDIDATE_SETTINGS_STALE"
