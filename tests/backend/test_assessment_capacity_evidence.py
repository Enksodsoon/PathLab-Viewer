import json
import subprocess
import sys
from pathlib import Path

import jsonschema


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
            "services": {"assessmentWorkers": 2, "restarts": 0, "oomKills": 0},
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
