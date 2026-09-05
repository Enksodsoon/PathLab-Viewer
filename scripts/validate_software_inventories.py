"""Validate deterministic P0-T06 software inventories and release blocking."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

try:
    from scripts.generate_software_inventories import (
        ASSET_LEDGER,
        BUILD_ROLES,
        CYCLONEDX_VERSION,
        DEFAULT_OUTPUT,
        DEPENDENCY_INVENTORY,
        INPUT_PATHS,
        OUTPUT_NAMES,
        ROOT,
        SCHEMA,
        SPDX_VERSION,
        TOOLCHAIN_INVENTORY,
        asset_components,
        dependency_components,
        generate,
        identifier_digest,
        toolchain_components,
    )
except ModuleNotFoundError:
    from generate_software_inventories import (
        ASSET_LEDGER,
        BUILD_ROLES,
        CYCLONEDX_VERSION,
        DEFAULT_OUTPUT,
        DEPENDENCY_INVENTORY,
        INPUT_PATHS,
        OUTPUT_NAMES,
        ROOT,
        SCHEMA,
        SPDX_VERSION,
        TOOLCHAIN_INVENTORY,
        asset_components,
        dependency_components,
        generate,
        identifier_digest,
        toolchain_components,
    )

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SPDX_ID = re.compile(r"^SPDXRef-[A-Za-z0-9.-]+$")


class ReleaseBlocked(ValueError):
    """Raised when an explicit release-admission check finds blocked inputs."""


def fail(message: str) -> None:
    raise ValueError(message)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        fail(f"invalid JSON artifact {path.name}: {error}")
    if not isinstance(value, dict):
        fail(f"JSON artifact must be an object: {path.name}")
    return value


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=False, capture_output=True, text=True)
    if result.returncode:
        fail("inventory subject is not an available immutable Git object")
    return result.stdout.strip()


def validate_manifest_shape(manifest: dict[str, Any]) -> None:
    required = {
        "schema",
        "subjectCommit",
        "subjectTree",
        "generatedAt",
        "generator",
        "formats",
        "releaseAdmission",
        "releaseBlockers",
        "offlineKit",
        "inputs",
        "coverage",
        "artifacts",
    }
    missing = required - manifest.keys()
    if missing:
        fail(f"software inventory manifest missing fields: {sorted(missing)}")
    if manifest["schema"] != SCHEMA:
        fail("unexpected software inventory manifest schema")
    subject = manifest["subjectCommit"]
    if not isinstance(subject, str) or not re.fullmatch(r"[0-9a-f]{40}", subject):
        fail("manifest subjectCommit must be a full Git SHA")
    if manifest["subjectTree"] != git("rev-parse", f"{subject}^{{tree}}"):
        fail("manifest subjectTree does not match subjectCommit")
    if manifest["formats"] != {"spdx": SPDX_VERSION, "cyclonedx": CYCLONEDX_VERSION}:
        fail("software inventory formats do not match the frozen contract")
    if manifest["releaseAdmission"] not in {"ADMITTED", "BLOCKED"}:
        fail("invalid releaseAdmission")
    blockers = manifest["releaseBlockers"]
    if not isinstance(blockers, list) or blockers != sorted(set(blockers)):
        fail("releaseBlockers must be a sorted unique list")
    expected_admission = "BLOCKED" if blockers else "ADMITTED"
    if manifest["releaseAdmission"] != expected_admission:
        fail("releaseAdmission does not match releaseBlockers")
    offline = manifest["offlineKit"]
    if offline != {
        "state": "CONTRACT_ONLY_NOT_ASSEMBLED",
        "assemblerOwner": "P1-T22A",
        "includedInventoryScopes": ["source", "build"],
    }:
        fail("offline kit must remain an unassembled P1-T22A contract")


def validate_input_receipts(manifest: dict[str, Any]) -> None:
    subject = manifest["subjectCommit"]
    inputs = manifest["inputs"]
    if not isinstance(inputs, list):
        fail("manifest inputs must be a list")
    paths = [item.get("path") for item in inputs]
    if paths != list(INPUT_PATHS) or len(paths) != len(set(paths)):
        fail("manifest input membership or ordering changed")
    for item in inputs:
        if set(item) != {"path", "gitBlob", "sha256", "sizeBytes"}:
            fail(f"invalid input receipt fields: {item.get('path', '<unknown>')}")
        path = item["path"]
        blob = git("rev-parse", f"{subject}:{path}")
        if item["gitBlob"] != blob:
            fail(f"input Git blob mismatch: {path}")
        data = subprocess.check_output(["git", "cat-file", "blob", blob], cwd=ROOT)
        if item["sha256"] != sha256(data) or item["sizeBytes"] != len(data):
            fail(f"input byte receipt mismatch: {path}")
        working_blob = git("hash-object", "--path", path, path)
        if working_blob != blob:
            fail(f"inventory input differs from subject commit: {path}")


def validate_artifact_receipts(root: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list):
        fail("manifest artifacts must be a list")
    paths = [item.get("path") for item in artifacts]
    if paths != sorted(OUTPUT_NAMES) or len(paths) != len(set(paths)):
        fail("manifest artifact membership or ordering changed")
    actual_files = sorted(path.name for path in root.iterdir() if path.is_file())
    if actual_files != sorted((*OUTPUT_NAMES, "manifest.json")):
        fail("software inventory directory contains missing or unbound artifacts")
    for item in artifacts:
        if set(item) != {"path", "sha256", "sizeBytes"}:
            fail(f"invalid artifact receipt fields: {item.get('path', '<unknown>')}")
        if not SHA256.fullmatch(str(item["sha256"])):
            fail(f"invalid artifact digest: {item['path']}")
        path = root / item["path"]
        try:
            data = path.read_bytes()
        except OSError as error:
            fail(f"inventory artifact unavailable: {item['path']}: {error}")
        if item["sha256"] != sha256(data) or item["sizeBytes"] != len(data):
            fail(f"artifact receipt mismatch: {item['path']}")


def validate_spdx(document: dict[str, Any], subject: str, scope: str) -> set[str]:
    if document.get("spdxVersion") != SPDX_VERSION or document.get("dataLicense") != "CC0-1.0":
        fail(f"{scope} SPDX schema/version is invalid")
    if document.get("SPDXID") != "SPDXRef-DOCUMENT":
        fail(f"{scope} SPDX document identifier is invalid")
    if subject not in str(document.get("documentNamespace", "")):
        fail(f"{scope} SPDX namespace is not subject-bound")
    creation = document.get("creationInfo")
    if not isinstance(creation, dict) or creation.get("creators") != ["Organization: PathLab"]:
        fail(f"{scope} SPDX creationInfo is invalid")
    packages = document.get("packages")
    if not isinstance(packages, list) or not packages:
        fail(f"{scope} SPDX packages must be a non-empty list")
    ids = [package.get("SPDXID") for package in packages]
    if len(ids) != len(set(ids)) or any(not SPDX_ID.fullmatch(str(value)) for value in ids):
        fail(f"{scope} SPDX package identifiers are invalid or duplicated")
    for package in packages:
        required = {
            "SPDXID",
            "name",
            "versionInfo",
            "downloadLocation",
            "filesAnalyzed",
            "licenseConcluded",
            "licenseDeclared",
            "copyrightText",
            "comment",
        }
        if required - package.keys() or package["filesAnalyzed"] is not False:
            fail(f"{scope} SPDX package shape is invalid")
        try:
            comment = json.loads(package["comment"])
        except (TypeError, json.JSONDecodeError) as error:
            fail(f"{scope} SPDX package metadata is invalid: {error}")
        if not isinstance(comment.get("blockers"), list) or "admission" not in comment:
            fail(f"{scope} SPDX package loses admission metadata")
    relationships = document.get("relationships")
    if not isinstance(relationships, list):
        fail(f"{scope} SPDX relationships must be a list")
    described = document.get("documentDescribes")
    if not isinstance(described, list) or len(described) != 1 or described[0] not in ids:
        fail(f"{scope} SPDX documentDescribes is invalid")
    dependency_targets = {
        item.get("relatedSpdxElement")
        for item in relationships
        if item.get("spdxElementId") == described[0]
        and item.get("relationshipType") == "DEPENDS_ON"
    }
    if dependency_targets != set(ids) - {described[0]}:
        fail(f"{scope} SPDX relationships do not cover every component")
    return set(ids)


def validate_cyclonedx(document: dict[str, Any], subject: str, scope: str) -> set[str]:
    if document.get("bomFormat") != "CycloneDX" or document.get("specVersion") != CYCLONEDX_VERSION:
        fail(f"{scope} CycloneDX schema/version is invalid")
    if document.get("version") != 1 or not re.fullmatch(
        r"urn:uuid:[0-9a-f-]{36}", str(document.get("serialNumber", ""))
    ):
        fail(f"{scope} CycloneDX serial/version is invalid")
    metadata = document.get("metadata")
    if not isinstance(metadata, dict) or metadata.get("component", {}).get("version") != subject:
        fail(f"{scope} CycloneDX metadata is not subject-bound")
    components = document.get("components")
    if not isinstance(components, list):
        fail(f"{scope} CycloneDX components must be a list")
    refs = [component.get("bom-ref") for component in components]
    if len(refs) != len(set(refs)) or any(
        not isinstance(value, str) or not value for value in refs
    ):
        fail(f"{scope} CycloneDX component references are invalid or duplicated")
    for component in components:
        required = {"type", "bom-ref", "name", "version", "licenses", "properties"}
        if required - component.keys():
            fail(f"{scope} CycloneDX component shape is invalid")
        properties = {
            item.get("name"): item.get("value") for item in component.get("properties", [])
        }
        if not {"pathlab:id", "pathlab:role", "pathlab:admission", "pathlab:blockers"}.issubset(
            properties
        ):
            fail(f"{scope} CycloneDX component loses admission metadata")
    dependencies = document.get("dependencies")
    if not isinstance(dependencies, list):
        fail(f"{scope} CycloneDX dependencies must be a list")
    root_ref = metadata["component"]["bom-ref"]
    by_ref = {item.get("ref"): item for item in dependencies}
    if set(by_ref) != {root_ref, *refs}:
        fail(f"{scope} CycloneDX dependency graph membership is incomplete")
    if by_ref[root_ref].get("dependsOn") != refs:
        fail(f"{scope} CycloneDX root dependency ordering or coverage changed")
    if any(by_ref[ref].get("dependsOn") != [] for ref in refs):
        fail(f"{scope} CycloneDX leaf dependency shape is invalid")
    return set(refs)


def expected_coverage() -> dict[str, int | str]:
    dependencies = dependency_components(load_json(DEPENDENCY_INVENTORY)["records"])
    tools = toolchain_components(load_json(TOOLCHAIN_INVENTORY)["records"])
    assets = asset_components(load_json(ASSET_LEDGER)["records"])
    build = [record for record in dependencies if record["role"] in BUILD_ROLES]
    return {
        "dependencyRecords": len(dependencies),
        "dependencyRecordIdsSha256": identifier_digest([item["id"] for item in dependencies]),
        "toolchainRecords": len(tools),
        "toolchainRecordIdsSha256": identifier_digest([item["id"] for item in tools]),
        "assetRecords": len(assets),
        "assetRecordIdsSha256": identifier_digest([item["id"] for item in assets]),
        "sourceComponents": len(dependencies) + len(tools) + len(assets),
        "buildComponents": len(build) + len(tools) + len(assets),
        "currentShippedInputs": sum(
            item["distribution"]
            in {
                "browser-bundled",
                "bundled",
                "bundled-runtime",
                "bundled-runtime-and-operator-tooling",
            }
            and not item["role"].startswith("planned-")
            for item in dependencies
        ),
    }


def validate(
    root: Path = DEFAULT_OUTPUT,
    *,
    require_release_admission: bool = False,
    compare_regeneration: bool = True,
) -> dict[str, Any]:
    manifest = load_json(root / "manifest.json")
    validate_manifest_shape(manifest)
    validate_input_receipts(manifest)
    validate_artifact_receipts(root, manifest)
    subject = manifest["subjectCommit"]
    source_spdx = validate_spdx(load_json(root / "source.spdx.json"), subject, "source")
    build_spdx = validate_spdx(load_json(root / "build.spdx.json"), subject, "build")
    source_cdx = validate_cyclonedx(load_json(root / "source.cdx.json"), subject, "source")
    build_cdx = validate_cyclonedx(load_json(root / "build.cdx.json"), subject, "build")
    coverage = manifest["coverage"]
    if coverage != expected_coverage():
        fail("software inventory coverage does not reconcile with authoritative ledgers")
    if len(source_spdx) != coverage["sourceComponents"] + 1:
        fail("source SPDX component count does not match manifest coverage")
    if len(build_spdx) != coverage["buildComponents"] + 1:
        fail("build SPDX component count does not match manifest coverage")
    if len(source_cdx) != coverage["sourceComponents"]:
        fail("source CycloneDX component count does not match manifest coverage")
    if len(build_cdx) != coverage["buildComponents"]:
        fail("build CycloneDX component count does not match manifest coverage")
    notices = (root / "THIRD_PARTY_NOTICES.txt").read_text(encoding="utf-8")
    if notices.count("\nID: ") != coverage["sourceComponents"]:
        fail("human notice bundle does not cover every source inventory component")
    if "does not replace missing upstream notice text" not in notices:
        fail("human notice bundle loses its fail-closed notice-text boundary")
    if compare_regeneration:
        with tempfile.TemporaryDirectory(prefix="pathlab-p0-t06-") as temporary:
            regenerated = Path(temporary)
            generate(subject, regenerated)
            for name in (*OUTPUT_NAMES, "manifest.json"):
                if (root / name).read_bytes() != (regenerated / name).read_bytes():
                    fail(f"checked-in inventory is not deterministic or current: {name}")
    if require_release_admission and manifest["releaseAdmission"] != "ADMITTED":
        raise ReleaseBlocked(
            "release software inventory is blocked: " + ", ".join(manifest["releaseBlockers"])
        )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--require-release-admission", action="store_true")
    parser.add_argument("--skip-regeneration", action="store_true")
    args = parser.parse_args()
    try:
        manifest = validate(
            args.root,
            require_release_admission=args.require_release_admission,
            compare_regeneration=not args.skip_regeneration,
        )
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"software inventory validation FAILED: {error}")
        return 1
    print(
        "software inventory validation PASS: "
        f"{manifest['coverage']['sourceComponents']} source components; "
        f"releaseAdmission={manifest['releaseAdmission']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
