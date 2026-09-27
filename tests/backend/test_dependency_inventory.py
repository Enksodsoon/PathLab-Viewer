from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from scripts import generate_dependency_inventory as generator
from scripts.validate_dependency_inventory import DEFAULT_INVENTORY, validate

ROOT = Path(__file__).resolve().parents[2]
SUBJECT = "2be62a9ae211a637a5490520212cbca8be6d5d60"


def test_inventory_reconciles_every_manifest() -> None:
    inventory = validate(DEFAULT_INVENTORY, SUBJECT)
    assert len(inventory["records"]) >= 490


def test_inventory_preserves_fail_closed_production_boundaries() -> None:
    records = {
        record["id"]: record
        for record in json.loads(DEFAULT_INVENTORY.read_text())["records"]
    }
    assert "npm:combine-errors@3.0.3" not in records
    assert records["npm:tus-js-client@4.3.1"]["license"] == "MIT"
    assert records[
        "model:trace-sim@2d625b1fad5c97584e1f7c69c3a95a6761fd934adaf17b1cecce329247e9fa0d"
    ]["role"] == "excluded-production"
    assert records["terraform-provider:oracle/oci@7.32.0"]["admission"] == "BLOCKED"
    assert records["terraform-provider:oracle/oci@8.29.0-linux-arm64"]["admission"] == "BLOCKED"


def test_inventory_subject_is_current_implementation_tree() -> None:
    inventory = json.loads((ROOT / "docs/supply-chain/dependency-inventory.json").read_text())
    assert inventory["subjectCommit"] == SUBJECT
    assert inventory["subjectTree"] == "63c25f9c4825fb67c6639a8202f233a6fa2cbc92"


def test_source_sha256_receipts_use_canonical_git_blob_bytes() -> None:
    inventory = json.loads(DEFAULT_INVENTORY.read_text())
    for receipt in inventory["sources"]:
        blob = subprocess.check_output(
            ["git", "cat-file", "blob", receipt["gitBlob"]], cwd=ROOT
        )
        assert hashlib.sha256(blob).hexdigest() == receipt["sha256"]


@pytest.mark.parametrize("corrupt", [False, True])
def test_python_inventory_selects_locked_wheel_before_unlocked_sdist(monkeypatch, corrupt):
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as wheel:
        wheel.writestr("example.dist-info/licenses/LICENSE", "Example license")
    data = archive.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    metadata = {
        "info": {"license_expression": "MIT"},
        "urls": [
            {"packagetype": "sdist", "url": "unlocked.tar.gz", "digests": {"sha256": "0" * 64}},
            {"packagetype": "bdist_wheel", "url": "locked.whl", "digests": {"sha256": digest}},
        ],
    }

    def read(url):
        assert url != "unlocked.tar.gz"
        if url == "locked.whl":
            return data + b"corrupt" if corrupt else data
        return json.dumps(metadata).encode()

    monkeypatch.setattr(generator, "read_url", read)
    record = generator.python_record(
        (
            "runtime-mandatory",
            ROOT / "deploy/backend-requirements.txt",
            {"name": "example", "version": "1", "hashes": [digest]},
        )
    )
    assert record["artifact"] == "locked.whl"
    assert record["checksumVerified"] is not corrupt
    assert ("LOCK_HASH_OR_ARTIFACT_MISMATCH" in record["blockers"]) is corrupt
