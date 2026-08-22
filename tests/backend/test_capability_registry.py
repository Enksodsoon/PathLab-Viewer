import json
import subprocess
import sys
from pathlib import Path

REGISTRY = Path("docs/evidence/capability-registry.json")
VALIDATOR = Path("scripts/validate_capability_registry.py")


def test_capability_registry_validator_accepts_the_repository_registry() -> None:
    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(REGISTRY)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "Capability registry valid: 6 entries\n"


def test_existing_capabilities_remain_built_without_inflated_claims() -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    capabilities = {item["id"]: item for item in registry["capabilities"]}

    assert registry["schemaVersion"] == 1
    assert registry["baselineReleaseSha"] == "b9d56022dea04940ffa8d262460a15b51074a37b"
    assert set(capabilities) == {
        "admin-annotations",
        "calibrated-measurements",
        "classroom",
        "classroom-background-protection",
        "postgres-runtime-cutover",
        "qupath-geojson",
    }
    assert {item["evidenceState"] for item in capabilities.values()} == {
        "BUILT",
        "SYNTHETICALLY_VERIFIED",
    }
    existing = {
        key: value
        for key, value in capabilities.items()
        if key not in {"classroom-background-protection", "postgres-runtime-cutover"}
    }
    assert {item["releaseSha"] for item in existing.values()} == {
        registry["baselineReleaseSha"]
    }
    protection = capabilities["classroom-background-protection"]
    assert protection["releaseSha"] == "b331171fa15a8ad4d08c62fa8a5e9c0af94c0f79"
    assert "disabled by default and not production-activated" in protection[
        "claimRestrictions"
    ]
    postgres = capabilities["postgres-runtime-cutover"]
    assert postgres["evidenceState"] == "SYNTHETICALLY_VERIFIED"
    assert postgres["releaseSha"] == "6a97058cc8cbfe27bedb9ff039908199f4496aeb"
    assert "staging and synthetic evidence only" in postgres["claimRestrictions"]
    assert "production remains on its current database engine" in postgres[
        "claimRestrictions"
    ]
    assert "not production-certified" in capabilities["classroom"]["claimRestrictions"]
    assert "not collaborative" in capabilities["admin-annotations"]["claimRestrictions"]
    assert "requires valid slide calibration" in capabilities["calibrated-measurements"][
        "claimRestrictions"
    ]
    assert "not a complete QuPath project exchange" in capabilities["qupath-geojson"][
        "claimRestrictions"
    ]


def test_validator_rejects_duplicate_capability_ids(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry["capabilities"].append(registry["capabilities"][0])
    invalid = tmp_path / "duplicate.json"
    invalid.write_text(json.dumps(registry), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(invalid)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "duplicate capability id: classroom" in result.stderr


def test_validator_rejects_unearned_state_and_missing_evidence(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry["capabilities"][0]["evidenceState"] = "MARKETING_COMPLETE"
    registry["capabilities"][0]["supportingEvidence"] = ["docs/evidence/missing.json"]
    invalid = tmp_path / "invalid-state.json"
    invalid.write_text(json.dumps(registry), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(invalid)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "unknown evidence state: MARKETING_COMPLETE" in result.stderr


def test_validator_rejects_missing_repository_paths(tmp_path: Path) -> None:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    registry["capabilities"][0]["supportingEvidence"] = ["docs/evidence/missing.json"]
    invalid = tmp_path / "missing-evidence.json"
    invalid.write_text(json.dumps(registry), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR), str(invalid)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "repository path does not exist: docs/evidence/missing.json" in result.stderr


def test_backend_ci_executes_the_capability_registry_validator() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    backend_job = workflow.split("\n  backend:\n", maxsplit=1)[1].split(
        "\n  web:\n", maxsplit=1
    )[0]

    assert "python scripts/validate_capability_registry.py" in backend_job
