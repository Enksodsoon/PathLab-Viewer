"""Validate the P0-T04 removal of the unresolved combine-errors path."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOCK = ROOT / "pnpm-lock.yaml"
DEFAULT_WORKSPACE = ROOT / "pnpm-workspace.yaml"
DEFAULT_INVENTORY = ROOT / "docs" / "supply-chain" / "dependency-inventory.json"
DEFAULT_PATCH = ROOT / "patches" / "tus-js-client-4.3.1.patch"
DEFAULT_WEB_DOCKERFILE = ROOT / "deploy" / "Dockerfile.web"
FORBIDDEN_ID = "npm:combine-errors@3.0.3"
PATCHED_PACKAGE = "tus-js-client@4.3.1"


def fail(message: str) -> None:
    raise ValueError(message)


def validate(
    lock_path: Path = DEFAULT_LOCK,
    workspace_path: Path = DEFAULT_WORKSPACE,
    inventory_path: Path = DEFAULT_INVENTORY,
    patch_path: Path = DEFAULT_PATCH,
    web_dockerfile_path: Path = DEFAULT_WEB_DOCKERFILE,
) -> dict[str, Any]:
    lock_text = lock_path.read_text(encoding="utf-8")
    if "combine-errors" in lock_text:
        fail("combine-errors remains in the resolved pnpm graph")

    lock = yaml.safe_load(lock_text)
    workspace = yaml.safe_load(workspace_path.read_text(encoding="utf-8"))
    configured_patch = workspace.get("patchedDependencies", {}).get(PATCHED_PACKAGE)
    if configured_patch != "patches/tus-js-client-4.3.1.patch":
        fail("the exact tus-js-client patch is not configured")
    expected_hash = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    if lock.get("patchedDependencies", {}).get(PATCHED_PACKAGE) != expected_hash:
        fail("the pnpm lock does not bind the exact tus-js-client patch hash")

    patched_snapshot = next(
        (
            value
            for key, value in lock.get("snapshots", {}).items()
            if key.startswith("tus-js-client@4.3.1(patch_hash=")
        ),
        None,
    )
    if not patched_snapshot:
        fail("the patched tus-js-client snapshot is absent")
    if "combine-errors" in patched_snapshot.get("dependencies", {}):
        fail("the patched tus-js-client snapshot still resolves combine-errors")

    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    ids = {record["id"] for record in inventory.get("records", [])}
    if FORBIDDEN_ID in ids:
        fail("combine-errors remains in the dependency inventory")

    dockerfile = web_dockerfile_path.read_text(encoding="utf-8")
    if "COPY patches ./patches" not in dockerfile:
        fail("the web image does not copy the content-addressed patch")
    if ".pnpmfile.cjs" not in dockerfile:
        fail("the web image does not copy the dependency-resolution hook")
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--patch", type=Path, default=DEFAULT_PATCH)
    args = parser.parse_args()
    inventory = validate(args.lock, args.workspace, args.inventory, args.patch)
    print(f"combine-errors removal PASS: {len(inventory['records'])} admitted inventory records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
