from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.generate_asset_rights_ledger import (
    DEFAULT_OUTPUT,
    DEFAULT_POLICY,
    discover_repository_records,
    load_json,
)
from scripts.validate_asset_rights_ledger import (
    ReleaseBlocked,
    reconcile_discovered,
    record_map,
    validate,
    validate_retired_assets,
)

SUBJECT = "3e08440e12110aad649f8b15b1b50454485c40c8"


def test_current_asset_set_reconciles_and_remains_release_blocked() -> None:
    ledger = validate()
    assert ledger["subjectCommit"] == SUBJECT
    assert len(ledger["records"]) == 35
    assert ledger["releaseAdmission"] == "BLOCKED"
    assert len(ledger["releaseBlockers"]) == 31
    with pytest.raises(ReleaseBlocked, match="release BLOCKED by 31"):
        validate(require_release_admission=True)


def test_injected_unknown_asset_is_rejected(tmp_path: Path) -> None:
    policy = copy.deepcopy(load_json(DEFAULT_POLICY))
    policy["governedRoots"] = ["assets"]
    policy["rules"] = [
        {
            "kind": "repository-file",
            "locatorGlob": "assets/*.png",
            "metadata": {
                "creator": "test",
                "provenance": "test",
                "licensePermission": "CC0-1.0",
                "attribution": "none required",
                "permittedUse": "test",
                "privacyClass": "PUBLIC_NON_PERSONAL",
                "distributionScope": "TEST_ONLY",
                "releaseDisposition": "EXCLUDED_NON_RELEASE",
                "blockers": [],
            },
        }
    ]
    asset = tmp_path / "assets" / "unknown.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"injected-unknown-asset")
    discovered = discover_repository_records(tmp_path, policy)
    with pytest.raises(ValueError, match="unknown governed asset: assets/unknown.png"):
        reconcile_discovered(discovered, {})


def test_changed_asset_hash_is_rejected() -> None:
    ledger = json.loads(DEFAULT_OUTPUT.read_text())
    records = record_map(ledger["records"])
    record = copy.deepcopy(next(iter(records.values())))
    recorded = copy.deepcopy(record)
    recorded["contentSha256"] = "0" * 64
    with pytest.raises(ValueError, match="changed asset or rights metadata"):
        reconcile_discovered([record], {record["id"]: recorded})


def test_imported_icon_subset_is_individually_hash_bound() -> None:
    ledger = json.loads(DEFAULT_OUTPUT.read_text())
    icon_set = next(record for record in ledger["records"] if record["kind"] == "package-icon-set")
    assert len(icon_set["embeddedAssets"]) == 87
    assert len({item["name"] for item in icon_set["embeddedAssets"]}) == 87
    assert all(len(item["contentSha256"]) == 64 for item in icon_set["embeddedAssets"])


def test_retired_asset_cannot_return_by_path_or_content(tmp_path: Path) -> None:
    policy = {
        "governedRoots": ["assets"],
        "ignoredDirectories": [],
        "retiredAssets": [
            {"locator": "assets/retired.png", "contentSha256": "a" * 64},
        ],
    }
    retired = tmp_path / "assets" / "retired.png"
    retired.parent.mkdir(parents=True)
    retired.write_bytes(b"different")
    with pytest.raises(ValueError, match="retired asset path returned"):
        validate_retired_assets(tmp_path, policy)

    retired.rename(tmp_path / "assets" / "renamed.png")
    policy["retiredAssets"][0]["contentSha256"] = hashlib.sha256(b"different").hexdigest()
    with pytest.raises(ValueError, match="retired asset content returned"):
        validate_retired_assets(tmp_path, policy)
