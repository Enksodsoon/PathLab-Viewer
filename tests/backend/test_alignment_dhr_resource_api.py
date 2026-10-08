"""Real API admission binds configured research resources without importing models."""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_alignment_api import _client, _headers
from test_alignment_frame_routes import _candidate, _stack
from wsi_viewer.alignment_engines import (
    ENGINE_VERSIONS,
    engine_resource_availability,
    settings_digest,
)
from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.main import create_app
from wsi_viewer.models import ComparisonRegistrationCandidate, ComparisonSet, Job

ENGINE = "deeperhistreg-learned"


def _research_client(
    tmp_path: Path, *, resources: bool = True, enabled: bool = True
) -> tuple[TestClient, dict]:
    seeded = _client(tmp_path, enabled=True)
    values = seeded.app.state.settings.model_dump()
    values["alignment_deeperhistreg_enabled"] = enabled
    declared = {}
    if resources:
        for name in ("superpoint", "superglue"):
            path = tmp_path / f"private-{name}-research-weights.pth"
            path.write_bytes(f"{name}-fixture-research-resource".encode())
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            values[f"alignment_deeperhistreg_{name}_weights_path"] = path
            values[f"alignment_deeperhistreg_{name}_weights_sha256"] = sha
            declared[f"{name}WeightsPath"] = str(path)
            declared[f"{name}WeightsSha256"] = sha
    return TestClient(create_app(Settings(**values))), declared


def test_real_route_configured_learned_weights_bind_queue_and_idempotency(tmp_path):
    client, declared = _research_client(tmp_path)
    assert engine_resource_availability(ENGINE, declared) == (True, None)
    with client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        for ordinal in range(2):
            response = client.post(
                url + "/benchmark",
                headers=headers,
                json={"version": stack["version"], "engines": [ENGINE]},
            )
            assert response.status_code == 202, response.text
            assert response.json()["queuedCandidates"] == (1 if ordinal == 0 else 0)
        with session_factory(client.app.state.settings)() as database:
            job = database.query(Job).filter_by(kind="align_benchmark").one()
            assert job.checkpoint["engineSettings"] == declared
            assert job.checkpoint["requestedSettingsDigest"] == settings_digest(ENGINE, declared)
            assert job.resource_limits["timeoutSeconds"] == 600
            assert job.resource_limits["memoryBytes"] == 7 * 1024**3


@pytest.mark.parametrize("failure", ["missing-config", "missing-file", "bad-hash", "changed-bytes"])
def test_real_route_missing_or_invalid_research_resource_never_queues(tmp_path, failure):
    client, declared = _research_client(tmp_path, resources=failure != "missing-config")
    settings = client.app.state.settings
    if failure == "missing-file":
        Path(declared["superpointWeightsPath"]).unlink()
    elif failure == "bad-hash":
        settings.alignment_deeperhistreg_superpoint_weights_sha256 = "0" * 64
    elif failure == "changed-bytes":
        Path(declared["superglueWeightsPath"]).write_bytes(b"changed-after-declaration")
    with client:
        headers = _headers(client)
        stack = _stack(client, headers)
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": [ENGINE]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_ENGINE_RESOURCE_UNAVAILABLE"
        with session_factory(settings)() as database:
            assert database.query(Job).filter_by(kind="align_benchmark").count() == 0


def test_configured_research_paths_stay_private_in_real_candidate_and_active_get(tmp_path):
    client, declared = _research_client(tmp_path)
    with client:
        headers = _headers(client)
        stack = _stack(client, headers)
        url = f"/api/v1/admin/comparison-sets/{stack['id']}"
        candidate_id = _candidate(client, stack, declared)
        with session_factory(client.app.state.settings)() as database:
            candidate = database.get(ComparisonRegistrationCandidate, candidate_id)
            candidate.engine = ENGINE
            candidate.engine_version = ENGINE_VERSIONS[ENGINE]
            candidate.settings_digest = settings_digest(ENGINE, declared)
            candidate.registration = {
                **candidate.registration,
                "engine": ENGINE,
                "engineSettings": declared,
                "settingsDigest": candidate.settings_digest,
            }
            comparison = database.get(ComparisonSet, stack["id"])
            comparison.registrations = {"slide-2": candidate.registration}
            database.commit()
        for response in (client.get(url), client.get(url + "/candidates")):
            assert response.status_code == 200
            public = json.dumps(response.json())
            for name in ("superpoint", "superglue"):
                assert declared[f"{name}WeightsPath"] not in public
                assert f"private-{name}-research" not in public
                assert declared[f"{name}WeightsSha256"] in public


def test_configured_research_resources_do_not_activate_disabled_engine(tmp_path):
    client, declared = _research_client(tmp_path, enabled=False)
    assert engine_resource_availability(ENGINE, declared) == (True, None)
    with client:
        headers = _headers(client)
        stack = _stack(client, headers)
        response = client.post(
            f"/api/v1/admin/comparison-sets/{stack['id']}/benchmark",
            headers=headers,
            json={"version": stack["version"], "engines": [ENGINE]},
        )
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "ALIGNMENT_ENGINE_DISABLED"
        with session_factory(client.app.state.settings)() as database:
            assert database.query(Job).filter_by(kind="align_benchmark").count() == 0


def test_resource_environment_fields_are_optional_and_separate_from_flag(monkeypatch, tmp_path):
    for name in ("superpoint", "superglue"):
        for suffix in ("PATH", "SHA256"):
            monkeypatch.delenv(
                f"PATHLAB_ALIGNMENT_DEEPERHISTREG_{name.upper()}_WEIGHTS_{suffix}", raising=False
            )
    monkeypatch.delenv("PATHLAB_ALIGNMENT_DEEPERHISTREG_ENABLED", raising=False)
    defaults = Settings(_env_file=None)
    assert defaults.alignment_deeperhistreg_enabled is False
    for name in ("superpoint", "superglue"):
        assert getattr(defaults, f"alignment_deeperhistreg_{name}_weights_path") is None
        assert getattr(defaults, f"alignment_deeperhistreg_{name}_weights_sha256") is None
        monkeypatch.setenv(
            f"PATHLAB_ALIGNMENT_DEEPERHISTREG_{name.upper()}_WEIGHTS_PATH",
            str(tmp_path / f"{name}.pth"),
        )
        monkeypatch.setenv(
            f"PATHLAB_ALIGNMENT_DEEPERHISTREG_{name.upper()}_WEIGHTS_SHA256", "a" * 64
        )
    configured = Settings(_env_file=None)
    assert configured.alignment_deeperhistreg_enabled is False
    assert configured.alignment_deeperhistreg_superpoint_weights_path == tmp_path / "superpoint.pth"
    assert configured.alignment_deeperhistreg_superglue_weights_sha256 == "a" * 64
