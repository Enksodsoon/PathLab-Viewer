from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path

import pytest

from scripts.generate_software_inventories import DEFAULT_OUTPUT, OUTPUT_NAMES, generate
from scripts.validate_software_inventories import (
    ReleaseBlocked,
    load_json,
    validate,
    validate_cyclonedx,
    validate_spdx,
)


def copy_inventories(tmp_path: Path) -> Path:
    destination = tmp_path / "software-inventories"
    shutil.copytree(DEFAULT_OUTPUT, destination)
    return destination


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_checked_in_software_inventories_reconcile_and_repeat() -> None:
    manifest = validate(DEFAULT_OUTPUT)

    assert manifest["coverage"] == {
        "assetRecordIdsSha256": manifest["coverage"]["assetRecordIdsSha256"],
        "assetRecords": 8,
        "buildComponents": manifest["coverage"]["buildComponents"],
        "currentShippedInputs": manifest["coverage"]["currentShippedInputs"],
        "dependencyRecordIdsSha256": manifest["coverage"]["dependencyRecordIdsSha256"],
        "dependencyRecords": 497,
        "sourceComponents": 519,
        "toolchainRecordIdsSha256": manifest["coverage"]["toolchainRecordIdsSha256"],
        "toolchainRecords": 14,
    }
    assert manifest["offlineKit"]["state"] == "CONTRACT_ONLY_NOT_ASSEMBLED"


def test_generation_is_byte_identical_across_directories(tmp_path: Path) -> None:
    manifest = load_json(DEFAULT_OUTPUT / "manifest.json")
    first = tmp_path / "first"
    second = tmp_path / "second"

    generate(manifest["subjectCommit"], first)
    generate(manifest["subjectCommit"], second)

    for name in (*OUTPUT_NAMES, "manifest.json"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_release_admission_fails_closed_for_recorded_or_blocked_shipped_inputs() -> None:
    with pytest.raises(ReleaseBlocked, match="release software inventory is blocked"):
        validate(DEFAULT_OUTPUT, require_release_admission=True, compare_regeneration=False)


def test_changed_artifact_bytes_are_rejected(tmp_path: Path) -> None:
    root = copy_inventories(tmp_path)
    with (root / "THIRD_PARTY_NOTICES.txt").open("ab") as output:
        output.write(b"tampered\n")

    with pytest.raises(ValueError, match="artifact receipt mismatch"):
        validate(root, compare_regeneration=False)


def test_missing_artifact_receipt_is_rejected(tmp_path: Path) -> None:
    root = copy_inventories(tmp_path)
    manifest = load_json(root / "manifest.json")
    manifest["artifacts"] = manifest["artifacts"][:-1]
    write_json(root / "manifest.json", manifest)

    with pytest.raises(ValueError, match="artifact membership"):
        validate(root, compare_regeneration=False)


def test_unbound_output_artifact_is_rejected(tmp_path: Path) -> None:
    root = copy_inventories(tmp_path)
    (root / "unbound.txt").write_text("not in manifest", encoding="utf-8")

    with pytest.raises(ValueError, match="missing or unbound"):
        validate(root, compare_regeneration=False)


def test_generator_rejects_noncanonical_subject(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="full lowercase Git SHA"):
        generate("HEAD", tmp_path)


def test_false_offline_kit_completion_is_rejected(tmp_path: Path) -> None:
    root = copy_inventories(tmp_path)
    manifest = load_json(root / "manifest.json")
    manifest["offlineKit"]["state"] = "ASSEMBLED"
    write_json(root / "manifest.json", manifest)

    with pytest.raises(ValueError, match="must remain an unassembled"):
        validate(root, compare_regeneration=False)


def test_coverage_drift_is_rejected(tmp_path: Path) -> None:
    root = copy_inventories(tmp_path)
    manifest = load_json(root / "manifest.json")
    manifest["coverage"]["dependencyRecords"] -= 1
    write_json(root / "manifest.json", manifest)

    with pytest.raises(ValueError, match="does not reconcile"):
        validate(root, compare_regeneration=False)


def test_spdx_requires_complete_dependency_relationships() -> None:
    manifest = load_json(DEFAULT_OUTPUT / "manifest.json")
    document = load_json(DEFAULT_OUTPUT / "source.spdx.json")
    document["relationships"] = document["relationships"][:-1]

    with pytest.raises(ValueError, match="relationships do not cover"):
        validate_spdx(document, manifest["subjectCommit"], "source")


def test_cyclonedx_rejects_duplicate_component_references() -> None:
    manifest = load_json(DEFAULT_OUTPUT / "manifest.json")
    document = load_json(DEFAULT_OUTPUT / "source.cdx.json")
    document["components"].append(copy.deepcopy(document["components"][0]))

    with pytest.raises(ValueError, match="invalid or duplicated"):
        validate_cyclonedx(document, manifest["subjectCommit"], "source")


def test_notice_bundle_preserves_missing_text_and_blocker_boundaries() -> None:
    notices = (DEFAULT_OUTPUT / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")

    assert "does not replace missing upstream notice text" in notices
    assert "ID: npm:react@19.2.8" in notices
    assert "ID: model:trace-sim@" in notices
    assert "PRODUCTION_APPROVAL_REJECTED" in notices
