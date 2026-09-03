from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.validate_runtime_toolchain_admission import (
    DEFAULT_LOCK,
    DEFAULT_MANIFEST,
    DEFAULT_POLICY,
    DEFAULT_RECEIPT,
    parse_lock,
    validate,
)


def _copy_manifest(tmp_path: Path) -> tuple[Path, Path, dict[str, object]]:
    manifest = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))
    receipt = json.loads(DEFAULT_RECEIPT.read_text(encoding="utf-8"))
    path = tmp_path / "manifest.json"
    receipt_path = tmp_path / "receipt.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    return path, receipt_path, manifest


def test_admission_reconciles_exact_tools_and_python_closure() -> None:
    manifest = validate()
    assert len(manifest["records"]) == 14
    assert len(parse_lock(DEFAULT_LOCK)) >= 20


def test_mutable_source_selector_is_rejected(tmp_path: Path) -> None:
    path, receipt_path, manifest = _copy_manifest(tmp_path)
    manifest["records"][0]["artifact"] = "https://example.invalid/latest/tool.tar.gz"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="mutable source selector"):
        validate(path, DEFAULT_LOCK, DEFAULT_POLICY, receipt_path=receipt_path)


def test_unpinned_python_requirement_is_rejected(tmp_path: Path) -> None:
    lock = tmp_path / "requirements.txt"
    lock.write_text("cryptography>=50\n", encoding="utf-8")
    with pytest.raises(ValueError, match="contains no exact requirements"):
        validate(DEFAULT_MANIFEST, lock, DEFAULT_POLICY)


def test_scanner_automatic_update_is_rejected(tmp_path: Path) -> None:
    policy = json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))
    policy["automaticDatabaseUpdate"] = True
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    with pytest.raises(ValueError, match="automatic updates off"):
        validate(DEFAULT_MANIFEST, DEFAULT_LOCK, path)


def test_offline_mirror_smoke_detects_tampering(tmp_path: Path) -> None:
    path, receipt_path, manifest = _copy_manifest(tmp_path)
    mirror = tmp_path / "mirror"
    payload = b"non-secret-offline-smoke-fixture\n"
    digest = hashlib.sha256(payload).hexdigest()
    for record in manifest["records"]:
        record["sha256"] = digest
        destination = mirror.joinpath(*Path(record["mirrorPath"]).parts[2:])
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    path.write_text(json.dumps(manifest), encoding="utf-8")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for entry in receipt["results"]:
        entry["artifactSha256"] = digest
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    validate(path, DEFAULT_LOCK, DEFAULT_POLICY, mirror, receipt_path)

    first = manifest["records"][0]
    mirror.joinpath(*Path(first["mirrorPath"]).parts[2:]).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="mirror sha256 mismatch"):
        validate(path, DEFAULT_LOCK, DEFAULT_POLICY, mirror, receipt_path)
