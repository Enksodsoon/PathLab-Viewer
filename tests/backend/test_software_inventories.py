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
        "assetRecords": 17,
        "buildComponents": manifest["coverage"]["buildComponents"],
        "currentShippedInputs": manifest["coverage"]["currentShippedInputs"],
        "dependencyRecordIdsSha256": manifest["coverage"]["dependencyRecordIdsSha256"],
        "dependencyRecords": 581,
        "sourceComponents": 612,
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


def test_notice_bundle_includes_exact_archive_text_and_rejects_tampering(tmp_path, monkeypatch):
    import hashlib

    from scripts import generate_dependency_inventory as dependencies
    from scripts import generate_software_inventories as generator

    text = b"Synthetic copyright and complete grant.\n"
    digest = hashlib.sha256(text).hexdigest()
    path = "docs/supply-chain/notice-material/sha256/" + digest
    target = tmp_path / path
    target.parent.mkdir(parents=True)
    target.write_bytes(text)
    index = {
        "schema": "pathlab.archive-notices/1",
        "records": [
            {
                "id": "npm:synthetic@1",
                "artifact": "https://example.test/exact.tgz",
                "checksum": "sha512-exact",
                "notices": [{"member": "package/LICENSE", "path": path, "sha256": digest}],
            }
        ],
    }
    index_path = tmp_path / "docs/supply-chain/notice-material/archive-notices.json"
    index_path.write_text(json.dumps(index))
    monkeypatch.setattr(dependencies, "ROOT", tmp_path)
    monkeypatch.setattr(generator, "ROOT", tmp_path)
    component = {
        "id": "npm:synthetic@1",
        "artifact": "https://example.test/exact.tgz",
        "checksum": "sha512-exact",
        "license": "MIT",
        "role": "runtime-mandatory",
        "distribution": "bundled",
        "admission": "RECORDED_UNREVIEWED",
        "blockers": [],
        "name": "synthetic",
        "version": "1",
        "source": "https://example.test/exact.tgz",
        "noticeFiles": [{"path": "package/LICENSE", "sha256": digest}],
    }
    output = generator.notice_bundle([component], "Root notice")
    assert text in output
    assert b"RECORDED_UNREVIEWED" in output
    wrong = dict(component, checksum="sha512-other")
    with pytest.raises(ValueError, match="shipped notice text not captured"):
        generator.notice_bundle([wrong], "Root notice")
    target.write_bytes(text + b"changed")
    with pytest.raises(ValueError, match="notice material checksum"):
        generator.notice_bundle([component], "Root notice")
    target.unlink()
    with pytest.raises(FileNotFoundError):
        generator.notice_bundle([component], "Root notice")


def test_web_notice_copy_and_python_container_packaging_use_same_artifact(tmp_path):
    from scripts.generate_software_inventories import inventory_input_paths

    assert "deploy/Dockerfile.alignment" in inventory_input_paths()
    assert "deploy/Dockerfile.alignment-valis" in inventory_input_paths()
    import subprocess
    import tomllib

    root = Path(__file__).resolve().parents[2]
    script = tmp_path / "apps/web/scripts/copy-release-legal-files.mjs"
    script.parent.mkdir(parents=True)
    script.write_bytes((root / "apps/web/scripts/copy-release-legal-files.mjs").read_bytes())
    source = "docs/supply-chain/software-inventories/THIRD_PARTY_NOTICES.txt"
    for name, payload in [
        ("LICENSE", b"root license"),
        ("NOTICE", b"root notice"),
        (source, b"Synthetic upstream copyright and full grant.\n"),
    ]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
    subprocess.run(["node", str(script)], check=True, capture_output=True)
    assert (tmp_path / "apps/web/dist/THIRD_PARTY_NOTICES.txt").read_bytes() == (
        tmp_path / source
    ).read_bytes()
    (tmp_path / source).unlink()
    result = subprocess.run(["node", str(script)], capture_output=True)
    assert result.returncode != 0
    config = tomllib.loads((root / "pyproject.toml").read_text())
    targets = config["tool"]["hatch"]["build"]["targets"]
    assert targets["wheel"]["force-include"][source] == "wsi_viewer/THIRD_PARTY_NOTICES.txt"
    assert targets["sdist"]["force-include"][source] == source
    for name in ("backend", "web", "alignment"):
        docker = (root / f"deploy/Dockerfile.{name}").read_text()
        assert (
            f"COPY {source} ./docs/supply-chain/software-inventories/THIRD_PARTY_NOTICES.txt"
            in docker
        )
        assert "/usr/share/licenses/pathlab-viewer/THIRD_PARTY_NOTICES.txt" in docker


def test_notice_input_receipts_use_platform_independent_posix_order():
    from scripts.generate_software_inventories import inventory_input_paths

    material = [path for path in inventory_input_paths() if "/notice-material/" in path]
    assert material == sorted(material)
