from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.validate_dependency_inventory import DEFAULT_INVENTORY, validate

ROOT = Path(__file__).resolve().parents[2]
SUBJECT = "f7c62e2ee2643c69527eac773c608c6b3f0aee72"


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


def test_inventory_subject_is_p0_t04_implementation_tree() -> None:
    inventory = json.loads((ROOT / "docs/supply-chain/dependency-inventory.json").read_text())
    assert inventory["subjectCommit"] == SUBJECT
    assert inventory["subjectTree"] == "bcb7486a98a277bdf0722cd93dbf4033611170d8"


def test_source_sha256_receipts_use_canonical_git_blob_bytes() -> None:
    inventory = json.loads(DEFAULT_INVENTORY.read_text())
    for receipt in inventory["sources"]:
        blob = subprocess.check_output(
            ["git", "cat-file", "blob", receipt["gitBlob"]], cwd=ROOT
        )
        assert hashlib.sha256(blob).hexdigest() == receipt["sha256"]
