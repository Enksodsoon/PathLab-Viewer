from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from scripts.validate_dependency_inventory import DEFAULT_INVENTORY, validate

ROOT = Path(__file__).resolve().parents[2]
SUBJECT = "79800a5d7f6ffaf0ef1280d4ef8a599a65fcbe1f"


def test_inventory_reconciles_every_manifest() -> None:
    inventory = validate(DEFAULT_INVENTORY, SUBJECT)
    assert len(inventory["records"]) >= 500


def test_inventory_preserves_fail_closed_production_boundaries() -> None:
    records = {
        record["id"]: record
        for record in json.loads(DEFAULT_INVENTORY.read_text())["records"]
    }
    assert records["npm:combine-errors@3.0.3"]["admission"] == "BLOCKED"
    assert records[
        "model:trace-sim@2d625b1fad5c97584e1f7c69c3a95a6761fd934adaf17b1cecce329247e9fa0d"
    ]["role"] == "excluded-production"
    assert records["terraform-provider:oracle/oci@7.32.0"]["admission"] == "BLOCKED"
    assert records["terraform-provider:oracle/oci@8.29.0-linux-arm64"]["admission"] == "BLOCKED"


def test_inventory_subject_is_pre_change_tree() -> None:
    inventory = json.loads((ROOT / "docs/supply-chain/dependency-inventory.json").read_text())
    assert inventory["subjectCommit"] == SUBJECT
    assert inventory["subjectTree"] == "4a8610edf7c05e064e2eb0b02671b4fc27c1e00f"


def test_source_sha256_receipts_use_canonical_git_blob_bytes() -> None:
    inventory = json.loads(DEFAULT_INVENTORY.read_text())
    for receipt in inventory["sources"]:
        blob = subprocess.check_output(
            ["git", "cat-file", "blob", receipt["gitBlob"]], cwd=ROOT
        )
        assert hashlib.sha256(blob).hexdigest() == receipt["sha256"]
