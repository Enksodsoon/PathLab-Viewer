# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.browser_distribution import (
    DISTRIBUTION,
    EXACT_BINDINGS,
    FROZEN_WASM_FILES,
    ORT_CHECKSUM,
    ORT_ID,
    RECEIPT_PATH,
    SCHEMA,
    SOURCE_SCOPES,
    apply_exclusions,
    input_set_hash,
    load_authoritative_receipt,
    source_inputs,
    validate_emitted_assets,
    validate_receipt,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root).decode().strip()


def _fixture(root: Path) -> tuple[dict, list[dict]]:
    _git(root, "init", "--quiet")
    _git(root, "config", "user.name", "Disposable qualification fixture")
    _git(root, "config", "user.email", "fixture@example.invalid")
    for relative in ["apps/web/src/main.ts", "apps/web/public/safe.txt", "pnpm-lock.yaml"]:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("fixture input\n")
    _git(root, "add", ".")
    _git(root, "commit", "--quiet", "-m", "Synthetic browser build inputs")
    subject = _git(root, "rev-parse", "HEAD")
    inputs = source_inputs(root, subject)
    records = [
        {
            "id": identifier,
            "checksum": checksum,
            "checksumVerified": True,
            "distribution": "bundled",
            "admission": "BLOCKED",
            "blockers": ["NOTICE_TEXT_NOT_FOUND_IN_ARCHIVE"],
            "noticeFiles": [],
            "license": "retained",
        }
        for identifier, checksum in EXACT_BINDINGS.items()
    ]
    records.append(
        {"id": "npm:retained@1.0.0", "distribution": "bundled", "admission": "RECORDED_UNREVIEWED"}
    )
    receipt = {
        "schema": SCHEMA,
        "subjectCommit": subject,
        "subjectTree": _git(root, "rev-parse", f"{subject}^{{tree}}"),
        "sourceScopes": list(SOURCE_SCOPES),
        "sourceInputs": inputs,
        "sourceInputSetSha256": input_set_hash(inputs),
        "sourceSnapshotStableDuringBuild": True,
        "excludedPackages": [
            {"id": identifier, "checksum": checksum}
            for identifier, checksum in EXACT_BINDINGS.items()
        ],
        "graphs": [
            {
                "role": "main" if index == 0 else "worker",
                "modules": [f"src/fixture{index}.ts"],
                "chunks": [
                    {"fileName": f"assets/{index}.js", "modules": [f"src/fixture{index}.ts"]}
                ],
            }
            for index in range(4)
        ],
        "emittedAssets": [{"path": "assets/0.js", "sha256": "a" * 64, "bytes": 12}],
    }
    return receipt, records


def test_browser_exclusion_keeps_notice_blockers_and_complete_source_records(
    tmp_path: Path,
) -> None:
    receipt, records = _fixture(tmp_path)
    original = copy.deepcopy(records)
    apply_exclusions(records, receipt, tmp_path)
    assert len(records) == len(original)
    assert records[-1] == original[-1]
    for before, after in zip(original[:2], records[:2], strict=True):
        assert after["distribution"] == DISTRIBUTION
        assert {
            key: value
            for key, value in after.items()
            if key not in {"distribution", "distributionEvidence"}
        } == {key: value for key, value in before.items() if key != "distribution"}


def test_browser_exclusion_rejects_actual_import_in_worker_graph(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    receipt["graphs"][3]["modules"].append(
        "node_modules/.pnpm/guid-typescript@1.0.9/node_modules/guid-typescript/dist/guid.js"
    )
    receipt["graphs"][3]["modules"].sort()
    with pytest.raises(ValueError, match="present in a compiled module graph"):
        apply_exclusions(records, receipt, tmp_path)
    assert all(record["distribution"] == "bundled" for record in records)


def test_browser_receipt_rejects_duplicate_worker_graph(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    receipt["graphs"][3] = copy.deepcopy(receipt["graphs"][2])
    with pytest.raises(ValueError, match="roles or identities are incomplete"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_receipt_rejects_unaccounted_chunk_module(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    receipt["graphs"][0]["chunks"][0]["modules"].append("unaccounted.js")
    with pytest.raises(ValueError, match="outside its graph"):
        validate_receipt(receipt, tmp_path, records)


@pytest.mark.parametrize("committed", [False, True])
def test_browser_exclusion_rejects_changed_build_input(tmp_path: Path, committed: bool) -> None:
    receipt, records = _fixture(tmp_path)
    (tmp_path / "apps/web/src/main.ts").write_text("import 'guid-typescript'\n")
    if committed:
        _git(tmp_path, "add", ".")
        _git(tmp_path, "commit", "--quiet", "-m", "Synthetic changed import")
    with pytest.raises(ValueError, match="source changed|membership or content changed"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_exclusion_rejects_ignored_public_copy(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    (tmp_path / ".gitignore").write_text("apps/web/public/vendor.js\n")
    (tmp_path / "apps/web/public/vendor.js").write_text("copied third-party bytes\n")
    with pytest.raises(ValueError, match="untracked build inputs"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_exclusion_rejects_changed_dependency_patch(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    patch = tmp_path / "patches" / "synthetic.patch"
    patch.parent.mkdir()
    patch.write_text("unqualified dependency patch", encoding="utf-8")
    with pytest.raises(ValueError, match="untracked build inputs"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_exclusion_rejects_different_package_integrity(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    records[0]["checksum"] = "sha512:different"
    with pytest.raises(ValueError, match="source record binding mismatch"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_exclusion_cannot_promote_source_notice_admission(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    records[0]["admission"] = "ADMITTED"
    with pytest.raises(ValueError, match="retain its unresolved source notice state"):
        validate_receipt(receipt, tmp_path, records)


@pytest.mark.parametrize(
    "path",
    ["../private.js", "/private.js", "C:/private.js", "assets\\hidden.js", "assets//hidden.js"],
)
def test_browser_receipt_denies_escaping_or_ambiguous_asset_paths(
    tmp_path: Path, path: str
) -> None:
    receipt, records = _fixture(tmp_path)
    receipt["emittedAssets"][0]["path"] = path
    with pytest.raises(ValueError, match="asset path escapes"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_receipt_detects_replaced_bytes_and_added_artifacts(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    output = tmp_path / "artifact"
    target = output / "assets/0.js"
    target.parent.mkdir(parents=True)
    body = b"qualified synthetic bytes"
    target.write_bytes(body)
    receipt["emittedAssets"][0].update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    validate_receipt(receipt, tmp_path, records)
    validate_emitted_assets(receipt, output)
    target.write_bytes(b"replaced synthetic bytes")
    with pytest.raises(ValueError, match="emitted bytes changed"):
        validate_emitted_assets(receipt, output)
    target.write_bytes(body)
    (output / "unexpected.js").write_bytes(b"unaccounted copied module")
    with pytest.raises(ValueError, match="output membership changed"):
        validate_emitted_assets(receipt, output)


@pytest.mark.parametrize("replacement", [b"replaced bytes", b"short"])
def test_browser_emitted_mismatch_identifies_only_relative_asset_and_both_bindings(
    tmp_path: Path, replacement: bytes
) -> None:
    output = tmp_path / "private-host-artifact"
    target = output / "assets" / "fixture.js"
    target.parent.mkdir(parents=True)
    qualified = b"qualified byte"
    expected_sha = hashlib.sha256(qualified).hexdigest()
    receipt = {
        "emittedAssets": [
            {"path": "assets/fixture.js", "bytes": len(qualified), "sha256": expected_sha}
        ]
    }
    target.write_bytes(replacement)
    with pytest.raises(ValueError, match="emitted bytes changed") as caught:
        validate_emitted_assets(receipt, output)
    assert str(caught.value) == (
        "browser distribution emitted bytes changed: 'assets/fixture.js'; "
        f"expected bytes={len(qualified)} sha256={expected_sha}; "
        f"actual bytes={len(replacement)} sha256={hashlib.sha256(replacement).hexdigest()}"
    )
    assert str(tmp_path) not in str(caught.value)
    assert "private-host-artifact" not in str(caught.value)


def test_browser_receipt_requires_all_three_packaged_legal_files(tmp_path: Path) -> None:
    receipt, _ = _fixture(tmp_path)
    output = tmp_path / "artifact"
    (output / "assets").mkdir(parents=True)
    body = b"qualified bytes"
    (output / "assets/0.js").write_bytes(body)
    receipt["emittedAssets"][0].update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    (output / "LICENSE").write_text("synthetic license")
    (output / "NOTICE").write_text("synthetic notice")
    with pytest.raises(ValueError, match="output membership changed"):
        validate_emitted_assets(receipt, output, packaged_legal_files=True)
    (output / "THIRD_PARTY_NOTICES.txt").write_text("synthetic third-party notice")
    validate_emitted_assets(receipt, output, packaged_legal_files=True)


def _add_ort(receipt: dict, records: list[dict]) -> None:
    module = (
        "node_modules/.pnpm/onnxruntime-web@1.27.0/node_modules/"
        "onnxruntime-web/dist/ort.wasm.bundle.min.mjs"
    )
    receipt["graphs"][0]["modules"].append(module)
    receipt["graphs"][0]["modules"].sort()
    receipt["prebuiltInputs"] = [
        {"path": path, "sha256": digest, "bytes": size}
        for path, (digest, size) in sorted(FROZEN_WASM_FILES.items())
    ]
    records.append({"id": ORT_ID, "checksum": ORT_CHECKSUM, "checksumVerified": True})


def test_browser_receipt_binds_frozen_wasm_bytes_and_package(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    _add_ort(receipt, records)
    validate_receipt(receipt, tmp_path, records)
    receipt["prebuiltInputs"][0]["sha256"] = "b" * 64
    with pytest.raises(ValueError, match="prebuilt WASM bytes changed"):
        validate_receipt(receipt, tmp_path, records)
    _add_ort(receipt, [])
    receipt["graphs"][0]["modules"] = sorted(set(receipt["graphs"][0]["modules"]))
    records[-1]["checksum"] = "changed"
    with pytest.raises(ValueError, match="prebuilt package binding mismatch"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_receipt_rejects_full_onnx_export(tmp_path: Path) -> None:
    receipt, records = _fixture(tmp_path)
    _add_ort(receipt, records)
    receipt["graphs"][0]["modules"].append(
        "node_modules/.pnpm/onnxruntime-web@1.27.0/node_modules/onnxruntime-web/dist/ort.all.bundle.min.mjs"
    )
    receipt["graphs"][0]["modules"].sort()
    with pytest.raises(ValueError, match="full or WebGL ONNX exports"):
        validate_receipt(receipt, tmp_path, records)


def test_browser_receipt_must_belong_to_inventory_subject(tmp_path: Path) -> None:
    receipt, _ = _fixture(tmp_path)
    target = tmp_path / RECEIPT_PATH
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(receipt), encoding="utf-8")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "--quiet", "-m", "Synthetic immutable receipt")
    subject = _git(tmp_path, "rev-parse", "HEAD")
    assert load_authoritative_receipt(tmp_path, subject) == receipt
    target.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="not bound to the inventory subject"):
        load_authoritative_receipt(tmp_path, subject)


def test_browser_receipt_checks_packaged_legal_bytes(tmp_path: Path) -> None:
    receipt, _ = _fixture(tmp_path)
    output = tmp_path / "artifact"
    (output / "assets").mkdir(parents=True)
    body = b"qualified bytes"
    (output / "assets/0.js").write_bytes(body)
    receipt["emittedAssets"][0].update(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body))
    sources = {}
    for name in ["LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.txt"]:
        source = tmp_path / name
        source.write_text("synthetic immutable legal text", encoding="utf-8")
        (output / name).write_bytes(source.read_bytes())
        sources[name] = source
    validate_emitted_assets(receipt, output, packaged_legal_files=True, legal_sources=sources)
    (output / "NOTICE").write_text("substituted", encoding="utf-8")
    with pytest.raises(ValueError, match="packaged legal bytes changed"):
        validate_emitted_assets(receipt, output, packaged_legal_files=True, legal_sources=sources)


def test_browser_receipt_rejects_unexpected_linked_directory(tmp_path: Path) -> None:
    receipt, _ = _fixture(tmp_path)
    output = tmp_path / "artifact"
    output.mkdir()
    external = tmp_path / "external"
    external.mkdir()
    try:
        (output / "unaccounted").symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("Host lacks permission to create symbolic links; Linux CI exercises this case")
    with pytest.raises(ValueError, match="symbolic link or junction"):
        validate_emitted_assets(receipt, output)
