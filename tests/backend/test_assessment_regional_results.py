import copy
import importlib.util

import pytest

SPEC = importlib.util.spec_from_file_location(
    "assessment_regional_results", "scripts/assessment_regional_results.py",
)
assert SPEC is not None and SPEC.loader is not None
regional = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(regional)
EXPECTED = {
    "run_id": "34231730897", "release_sha": "a" * 40,
    "administration_id": "fixture-id", "start_epoch": 1000,
    "public_id": "public-id",
}


def bundle():
    return {
        "runId": EXPECTED["run_id"], "releaseSha": EXPECTED["release_sha"],
        "administrationId": EXPECTED["administration_id"], "startEpoch": 1000,
        "publicId": "public-id",
        "clientRegion": "southeast-asia",
        "artifacts": {
            **{f"shard-{index}.json": {
                "shard": index, "seats": 100, "autosavesPerSeat": 20,
                "reconnectPercent": 10, "holdSeconds": 3600, "exactRelease": "a" * 40,
                "publicId": "public-id", "startEpoch": 1000,
                "metrics": {"http_req_failed": {"values": {"rate": 0.5}}},
            } for index in range(1, 6)},
            "observer.json": {
                "releaseSha": "a" * 40, "errorCount": 10,
                "administrationId": "fixture-id", "startEpoch": 1000,
            },
        },
    }


def test_negative_measurements_survive_collection_for_normal_gate_evaluation():
    value = bundle()
    assert regional.validate_bundle(value, **EXPECTED) == value["artifacts"]
    assert value["artifacts"]["observer.json"]["errorCount"] == 10


@pytest.mark.parametrize("key", [
    "runId", "releaseSha", "administrationId", "publicId", "startEpoch", "clientRegion",
])
def test_other_run_release_fixture_barrier_or_region_is_rejected(key):
    value = bundle()
    value[key] = "wrong"
    with pytest.raises(ValueError, match="identity"):
        regional.validate_bundle(value, **EXPECTED)


@pytest.mark.parametrize("change", [
    {"seats": 99}, {"holdSeconds": 90}, {"autosavesPerSeat": 3},
    {"reconnectPercent": 0}, {"diagnosticOnly": True}, {"shard": 2},
    {"exactRelease": "b" * 40},
    {"publicId": "another-fixture"}, {"startEpoch": 900},
])
def test_shortened_or_misidentified_shards_cannot_be_certified(change):
    value = bundle()
    value["artifacts"]["shard-1.json"].update(change)
    with pytest.raises(ValueError, match="full-hour"):
        regional.validate_bundle(value, **EXPECTED)


def test_exact_artifact_inventory_rejects_missing_and_arbitrary_output_paths():
    value = bundle()
    for name in ["../secret.json", "shard-6.json"]:
        extra = copy.deepcopy(value)
        extra["artifacts"][name] = {}
        with pytest.raises(ValueError, match="exactly five"):
            regional.validate_bundle(extra, **EXPECTED)
    del value["artifacts"]["observer.json"]
    with pytest.raises(ValueError, match="exactly five"):
        regional.validate_bundle(value, **EXPECTED)


def test_redirect_cannot_forward_observer_authorization_to_another_origin():
    with pytest.raises(ValueError, match="must not redirect"):
        regional.NoRedirect().redirect_request(None, None, 302, "", {}, "https://foreign.test")
