import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _fixture(tmp_path: Path, release_sha: str) -> Path:
    artifacts = tmp_path / "artifacts"
    for shard in range(1, 6):
        _write(
            artifacts / f"shard-{shard}" / f"shard-{shard}.json",
            {
                "shard": shard,
                "seats": 100,
                "holdSeconds": 3600,
                "exactRelease": release_sha,
                "metrics": {
                    "assessment_autosaves": {"values": {"count": 2000}},
                    "assessment_reconnects": {"values": {"count": 10}},
                    "assessment_submits": {"values": {"count": 100}},
                    "http_req_duration{name:autosave}": {"values": {"p(95)": 200}},
                    "http_req_duration{name:submit}": {"values": {"p(95)": 400}},
                    "http_req_duration{name:tile}": {"values": {"p(95)": 100}},
                },
            },
        )
    _write(
        artifacts / "observer.json",
        {
            "releaseSha": release_sha,
            "sampleCount": 240,
            "errorCount": 0,
            "tileP95Ms": 120,
            "database": {
                "engine": "postgresql",
                "maxConnections": 32,
                "peakConnections": 24,
                "poolTimeouts": 0,
                "lockTimeouts": 0,
            },
            "services": {
                "assessmentWorkers": 2, "restarts": 0, "oomKills": 0,
                "generationStable": True,
                "workerGenerations": {
                    "api": ["a" * 32], "assessment": ["b" * 32, "c" * 32],
                    "classroom": ["d" * 32],
                },
            },
            "host": {"sustainedCpuPercent": 70, "peakMemoryPercent": 80, "swapBytes": 0},
        },
    )
    _write(
        artifacts / "canaries.json",
        {
            "offlineResume": True,
            "browserOutageRecovery": True,
            "aggregateVerified": True,
            "exportVerified": True,
        },
    )
    _write(
        artifacts / "cleanup.json",
        {
            "fixturesRemoved": True,
            "grantsRemoved": True,
            "sessionsRemoved": True,
            "administrationPurged": True,
        },
    )
    return artifacts


@pytest.mark.parametrize("provenance_state", ["missing", "wrong-run", "matching"])
def test_regional_evidence_requires_same_protected_run(tmp_path, provenance_state):
    sha = "a" * 40
    artifacts = _fixture(tmp_path, sha)
    if provenance_state != "missing":
        _write(artifacts / "regional-provenance.json", {
            "runId": "123" if provenance_state == "matching" else "456",
            "releaseSha": sha, "clientRegion": "southeast-asia",
        })
    output = tmp_path / "regional-evidence.json"
    result = subprocess.run([
        sys.executable, "scripts/assessment_capacity_evidence.py", "--artifacts", str(artifacts),
        "--release-sha", sha, "--output", str(output), "--client-region", "southeast-asia",
        "--run-id", "123",
    ], capture_output=True, text=True, timeout=30)
    value = json.loads(output.read_text())
    assert value["campaign"]["clientRegion"] == "southeast-asia"
    assert (result.returncode == 0) is (provenance_state == "matching")
    if provenance_state == "missing":
        assert value["status"] == "NOT_EVALUABLE"
    elif provenance_state == "wrong-run":
        assert value["status"] == "NEGATIVE"


def test_capacity_evidence_closes_success_only_when_every_gate_passes(tmp_path: Path) -> None:
    release_sha = "a" * 40
    artifacts = _fixture(tmp_path, release_sha)
    output = tmp_path / "evidence.json"
    script = Path(__file__).parents[2] / "scripts" / "assessment_capacity_evidence.py"
    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--artifacts",
            str(artifacts),
            "--release-sha",
            release_sha,
            "--output",
            str(output),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    evidence = json.loads(output.read_text(encoding="utf-8"))
    schema = json.loads(
        (Path(__file__).parents[1] / "load" / "assessment-evidence.schema.json").read_text(
            encoding="utf-8"
        )
    )
    jsonschema.validate(evidence, schema, format_checker=jsonschema.FormatChecker())
    assert evidence["status"] == "SUCCESS"

    observer = artifacts / "observer.json"
    broken = json.loads(observer.read_text(encoding="utf-8"))
    broken["database"]["poolTimeouts"] = 1
    _write(observer, broken)
    failed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--artifacts",
            str(artifacts),
            "--release-sha",
            release_sha,
            "--output",
            str(output),
        ],
        check=False,
    )
    assert failed.returncode == 1
    negative = json.loads(output.read_text(encoding="utf-8"))
    jsonschema.validate(negative, schema, format_checker=jsonschema.FormatChecker())
    assert negative["status"] == "NEGATIVE"


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("host", "swapBytes"), ("database", "poolTimeouts"), ("services", "oomKills"),
        ("services", "workerGenerations"), ("services", "generationStable"),
    ],
)
def test_capacity_evidence_rejects_missing_zero_valued_telemetry(tmp_path, section, field):
    release_sha = "a" * 40
    artifacts = _fixture(tmp_path, release_sha)
    observer_path = artifacts / "observer.json"
    observer = json.loads(observer_path.read_text(encoding="utf-8"))
    del observer[section][field]
    _write(observer_path, observer)
    output = tmp_path / "evidence.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/assessment_capacity_evidence.py",
            "--artifacts",
            str(artifacts),
            "--release-sha",
            release_sha,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    evidence = json.loads(output.read_text(encoding="utf-8"))
    assert evidence["status"] == "NEGATIVE"
    assert any(
        gate["name"] == "complete_host_telemetry" and not gate["passed"]
        for gate in evidence["gates"]
    )
