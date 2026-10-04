"""Bind narrow browser distribution observations without granting source rights.

SPDX-License-Identifier: Apache-2.0
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "pathlab.browser-distribution/1"
DISTRIBUTION = "not-bundled-in-current-browser-build"
RECEIPT_PATH = "docs/supply-chain/browser-distribution-receipt.json"
SOURCE_SCOPES = (
    "apps/web",
    "packages",
    "patches",
    "package.json",
    "pnpm-lock.yaml",
    "pnpm-workspace.yaml",
    ".npmrc",
    ".pnpmfile.cjs",
    ".gitattributes",
    ".node-version",
    ".nvmrc",
    "scripts/qualify_browser_distribution.mjs",
    "scripts/browser_distribution.py",
    ".github/workflows/ci.yml",
)
KNOWN_BUILD_OUTPUTS = (
    "apps/web/node_modules/",
    "apps/web/dist/",
    "apps/web/test-results/",
    "apps/web/playwright-report/",
)
KNOWN_BUILD_FILES = {"apps/web/tsconfig.app.tsbuildinfo", "apps/web/tsconfig.node.tsbuildinfo"}
EXACT_BINDINGS = {
    "npm:eastasianwidth@0.2.0": (
        "sha512-I88TYZWc9XiYHRQ4/3c5rjjfgkjhLyW2luGIheGERbNQ6OY7yTybanSpDXZa8y7VUP9YmDcYa+eyq4ca7iLqWA=="
    ),
    "npm:guid-typescript@1.0.9": (
        "sha512-Y8T4vYhEfwJOTbouREvG+3XDsjr8E3kIr7uf+JZ0BYloFsttiHU0WfvANVsR7TxNUJa/WpCnw/Ino/p+DeBhBQ=="
    ),
}
ORT_ID = "npm:onnxruntime-web@1.27.0"
ORT_CHECKSUM = (
    "sha512-ogDLsqIozHZwifPuN37OproAo0byX6t43/bP8GzeZWBWD6MO"
    "GExswFAx3up4NS/vvWBOg2u2PXomDt3rMmdQSg=="
)
FROZEN_WASM_FILES = {
    "dist/ort.wasm.bundle.min.mjs": (
        "1db5e1c5cd2b860eed85e6eeff23e2aaa7cffcc407f67093bcc888f631b94ba9",
        72799,
    ),
    "dist/ort-wasm-simd-threaded.mjs": (
        "0a1e718d99c41b22c21f2520ff4f9e883a6b5533856e398d21816ee8eb8185d3",
        24180,
    ),
    "dist/ort-wasm-simd-threaded.wasm": (
        "d1ab1b94b16a65b29d710d0b587b29e7bed336827577623913479b8afe8113e6",
        13479978,
    ),
}


def git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root).decode("utf-8").strip()


def input_set_hash(inputs: list[dict[str, str]]) -> str:
    content = "".join(f"{item['path']}\t{item['gitBlob']}\n" for item in inputs)
    return hashlib.sha256(content.encode()).hexdigest()


def source_inputs(root: Path, subject: str) -> list[dict[str, str]]:
    if not re.fullmatch(r"[0-9a-f]{40}", subject):
        raise ValueError("browser distribution subject must be an immutable commit")
    entries = git(root, "ls-tree", "-r", "-z", subject, "--", *SOURCE_SCOPES).split("\0")
    result = []
    for entry in entries:
        if not entry:
            continue
        metadata, path = entry.split("\t", 1)
        mode, kind, blob = metadata.split()
        if mode not in {"100644", "100755"} or kind != "blob":
            raise ValueError("browser input must be a regular immutable source file")
        result.append({"path": path, "gitBlob": blob})
    return sorted(result, key=lambda item: item["path"])


def untracked_build_inputs(root: Path) -> list[str]:
    paths = git(root, "ls-files", "--others", "-z", "--", *SOURCE_SCOPES).split("\0")
    return [
        path
        for path in paths
        if path and path not in KNOWN_BUILD_FILES and not path.startswith(KNOWN_BUILD_OUTPUTS)
    ]


def safe_asset_path(raw_path: str) -> bool:
    path = PurePosixPath(raw_path)
    return bool(
        raw_path
        and path.parts
        and not path.is_absolute()
        and ".." not in path.parts
        and "\\" not in raw_path
        and ":" not in path.parts[0]
        and path.as_posix() == raw_path
    )


def qualifying_source_inputs(root: Path, subject: str) -> list[dict[str, str]]:
    expected = source_inputs(root, subject)
    if not expected or expected != source_inputs(root, git(root, "rev-parse", "HEAD")):
        raise ValueError("browser distribution build input membership or content changed")
    if untracked_build_inputs(root):
        raise ValueError("browser distribution has untracked build inputs")
    for item in expected:
        path = root / item["path"]
        if (
            not path.is_file()
            or path.is_symlink()
            or git(root, "hash-object", item["path"]) != item["gitBlob"]
        ):
            raise ValueError("browser distribution working source changed")
    return expected


def validate_receipt(receipt: dict[str, Any], root: Path, records: list[dict[str, Any]]) -> None:
    if receipt.get("schema") != SCHEMA or receipt.get("sourceScopes") != list(SOURCE_SCOPES):
        raise ValueError("browser distribution receipt has an unsupported source boundary")
    subject = receipt.get("subjectCommit", "")
    expected = qualifying_source_inputs(root, subject)
    if receipt.get("subjectTree") != git(root, "rev-parse", f"{subject}^{{tree}}"):
        raise ValueError("browser distribution subject tree mismatch")
    if receipt.get("sourceInputs") != expected or receipt.get(
        "sourceInputSetSha256"
    ) != input_set_hash(expected):
        raise ValueError("browser distribution immutable source receipt mismatch")
    if receipt.get("sourceSnapshotStableDuringBuild") is not True:
        raise ValueError("browser distribution inputs were not stable during qualification")
    exclusions = receipt.get("excludedPackages", [])
    if not isinstance(exclusions, list) or len(exclusions) != len(EXACT_BINDINGS):
        raise ValueError("browser distribution requires the two exact package bindings")
    bindings = {item.get("id"): item.get("checksum") for item in exclusions}
    if bindings != EXACT_BINDINGS:
        raise ValueError("browser distribution package version or integrity mismatch")
    indexed = {record["id"]: record for record in records}
    for identifier, checksum in EXACT_BINDINGS.items():
        record = indexed.get(identifier)
        if (
            record is None
            or record.get("checksum") != checksum
            or record.get("checksumVerified") is not True
        ):
            raise ValueError("browser distribution source record binding mismatch")
        if record.get("admission") != "BLOCKED" or not record.get("blockers"):
            raise ValueError("browser exclusion must retain its unresolved source notice state")
    graphs = receipt.get("graphs", [])
    if (
        not isinstance(graphs, list)
        or len(graphs) < 4
        or sum(g.get("role") == "main" for g in graphs) != 1
    ):
        raise ValueError("browser distribution lacks complete main and worker graphs")
    uses_ort = False
    graph_signatures = set()
    for graph in graphs:
        modules = graph.get("modules", [])
        chunks = graph.get("chunks", [])
        if not modules or not chunks or modules != sorted(set(modules)):
            raise ValueError("browser distribution graph is incomplete")
        signature = tuple(modules)
        if graph.get("role") not in {"main", "worker"} or signature in graph_signatures:
            raise ValueError("browser distribution graph roles or identities are incomplete")
        graph_signatures.add(signature)
        if any(not set(chunk.get("modules", [])).issubset(modules) for chunk in chunks):
            raise ValueError("browser distribution chunk modules are outside its graph")
        observed = modules + [module for chunk in chunks for module in chunk.get("modules", [])]
        for module in observed:
            normalized = module.replace("\\", "/")
            if "/node_modules/onnxruntime-web/" in f"/{normalized}":
                uses_ort = True
                member = normalized.split("/node_modules/onnxruntime-web/", 1)[1].split("?", 1)[0]
                if member not in FROZEN_WASM_FILES:
                    raise ValueError(
                        "browser exclusion does not qualify full or WebGL ONNX exports"
                    )
            if any(
                f"/node_modules/{identifier.split('@')[0][4:]}/" in f"/{normalized}"
                for identifier in EXACT_BINDINGS
            ):
                raise ValueError("excluded browser package is present in a compiled module graph")
    expected_prebuilt = (
        [
            {"path": path, "sha256": blob, "bytes": size}
            for path, (blob, size) in sorted(FROZEN_WASM_FILES.items())
        ]
        if uses_ort
        else []
    )
    if receipt.get("prebuiltInputs", []) != expected_prebuilt:
        raise ValueError("browser distribution prebuilt WASM bytes changed")
    if uses_ort:
        ort = indexed.get(ORT_ID)
        if (
            ort is None
            or ort.get("checksum") != ORT_CHECKSUM
            or ort.get("checksumVerified") is not True
        ):
            raise ValueError("browser distribution prebuilt package binding mismatch")
    assets = receipt.get("emittedAssets", [])
    if not assets or len({asset.get("path") for asset in assets}) != len(assets):
        raise ValueError("browser distribution emitted asset membership is incomplete")
    for asset in assets:
        if not safe_asset_path(asset.get("path", "")):
            raise ValueError("browser distribution asset path escapes its output")
        if (
            not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", ""))
            or not isinstance(asset.get("bytes"), int)
            or asset["bytes"] < 0
        ):
            raise ValueError("browser distribution asset hash or size is invalid")


def validate_emitted_assets(
    receipt: dict[str, Any],
    output: Path,
    *,
    packaged_legal_files: bool = False,
    legal_sources: dict[str, Path] | None = None,
) -> None:
    """Inspect the actual artifact, including unexpected and replaced files."""
    expected = {item["path"]: item for item in receipt["emittedAssets"]}
    entries = [output, *output.rglob("*")]
    if any(path.is_symlink() or path.is_junction() for path in entries):
        raise ValueError("browser distribution output contains a symbolic link or junction")
    actual = {
        path.relative_to(output).as_posix(): path for path in entries[1:] if path.is_file()
    }
    legal = {"LICENSE", "NOTICE", "THIRD_PARTY_NOTICES.txt"} if packaged_legal_files else set()
    if set(actual) != set(expected) | legal:
        raise ValueError("browser distribution output membership changed")
    for relative, item in expected.items():
        if not safe_asset_path(relative):
            raise ValueError("browser distribution asset path escapes its output")
        path = actual[relative]
        if path.is_symlink() or not path.resolve().is_relative_to(output.resolve()):
            raise ValueError("browser distribution asset must be a confined regular file")
        if (
            path.stat().st_size != item["bytes"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != item["sha256"]
        ):
            raise ValueError("browser distribution emitted bytes changed")
    if legal_sources is not None:
        if set(legal_sources) != legal:
            raise ValueError("browser distribution legal source boundary mismatch")
        for name, source in legal_sources.items():
            target = actual[name]
            if target.is_symlink() or not target.resolve().is_relative_to(output.resolve()):
                raise ValueError("browser distribution legal file is not confined")
            if target.read_bytes() != source.read_bytes():
                raise ValueError("browser distribution packaged legal bytes changed")


def apply_exclusions(records: list[dict[str, Any]], receipt: dict[str, Any], root: Path) -> None:
    """Change only physical browser membership; retain every admission field."""
    validate_receipt(receipt, root, records)
    for record in records:
        if record["id"] in EXACT_BINDINGS:
            record["distribution"] = DISTRIBUTION
            record["distributionEvidence"] = RECEIPT_PATH


def load_authoritative_receipt(root: Path, subject: str) -> dict[str, Any]:
    path = root / RECEIPT_PATH
    expected = git(root, "rev-parse", f"{subject}:{RECEIPT_PATH}")
    if git(root, "hash-object", RECEIPT_PATH) != expected:
        raise ValueError("browser distribution receipt is not bound to the inventory subject")
    return json.loads(path.read_text(encoding="utf-8"))


def validate_applied_exclusions(records: list[dict[str, Any]], root: Path, subject: str) -> None:
    selected = [record for record in records if record.get("distribution") == DISTRIBUTION]
    if not selected:
        return
    if {record["id"] for record in selected} != set(EXACT_BINDINGS) or any(
        record.get("distributionEvidence") != RECEIPT_PATH for record in selected
    ):
        raise ValueError("unsupported browser distribution exclusion")
    receipt = load_authoritative_receipt(root, subject)
    validate_receipt(receipt, root, records)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    capture = modes.add_parser("inputs")
    capture.add_argument("--subject", required=True)
    verify = modes.add_parser("verify")
    verify.add_argument("--receipt", type=Path, default=root / RECEIPT_PATH)
    verify.add_argument("--dist", type=Path)
    verify.add_argument("--packaged-legal-files", action="store_true")
    args = parser.parse_args()
    if args.mode == "inputs":
        inputs = qualifying_source_inputs(root, args.subject)
        print(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "subjectCommit": args.subject,
                    "subjectTree": git(root, "rev-parse", f"{args.subject}^{{tree}}"),
                    "sourceScopes": list(SOURCE_SCOPES),
                    "sourceInputs": inputs,
                    "sourceInputSetSha256": input_set_hash(inputs),
                    "excludedPackages": [
                        {"id": key, "checksum": value} for key, value in EXACT_BINDINGS.items()
                    ],
                }
            )
        )
        return 0
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    records = json.loads(
        (root / "docs/supply-chain/dependency-inventory.json").read_text(encoding="utf-8")
    )["records"]
    validate_receipt(receipt, root, records)
    if args.dist:
        legal_sources = (
            {
                "LICENSE": root / "LICENSE",
                "NOTICE": root / "NOTICE",
                "THIRD_PARTY_NOTICES.txt": root
                / "docs/supply-chain/software-inventories/THIRD_PARTY_NOTICES.txt",
            }
            if args.packaged_legal_files
            else None
        )
        validate_emitted_assets(
            receipt,
            args.dist,
            packaged_legal_files=args.packaged_legal_files,
            legal_sources=legal_sources,
        )
    print("browser distribution receipt verified; source notice/admission states preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
