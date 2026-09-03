"""Validate the P0-T05 asset-rights ledger and fail closed on release admission."""

from __future__ import annotations

import argparse
import json
import subprocess
import zipfile
from pathlib import Path
from typing import Any

try:
    from scripts.generate_asset_rights_ledger import (
        DEFAULT_INVENTORY,
        DEFAULT_OUTPUT,
        DEFAULT_POLICY,
        dependency_record,
        discover_inline_records,
        discover_repository_records,
        imported_icons,
        load_json,
        referenced_package_fonts,
        sha256,
    )
except ModuleNotFoundError:
    from generate_asset_rights_ledger import (
        DEFAULT_INVENTORY,
        DEFAULT_OUTPUT,
        DEFAULT_POLICY,
        dependency_record,
        discover_inline_records,
        discover_repository_records,
        imported_icons,
        load_json,
        referenced_package_fonts,
        sha256,
    )

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FIELDS = {
    "id",
    "kind",
    "locator",
    "creator",
    "provenance",
    "licensePermission",
    "attribution",
    "contentSha256",
    "sizeBytes",
    "permittedUse",
    "privacyClass",
    "distributionScope",
    "releaseDisposition",
    "blockers",
}
VALID_DISPOSITIONS = {"ADMITTED", "BLOCKED_RELEASE", "EXCLUDED_NON_RELEASE"}


class ReleaseBlocked(ValueError):
    """Raised only when the explicit release-admission gate is requested."""


def fail(message: str) -> None:
    raise ValueError(message)


def record_map(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for record in records:
        record_id = record.get("id")
        if record_id in result:
            fail(f"duplicate ledger entry: {record_id}")
        result[record_id] = record
    return result


def validate_subject(root: Path, subject: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{subject}^{{commit}}"],
        cwd=root,
        check=False,
        capture_output=True,
    )
    if result.returncode:
        fail("ledger subjectCommit is not an available immutable Git commit")


def validate_subject_paths(root: Path, subject: str, discovered: list[dict[str, Any]]) -> None:
    paths: set[str] = set()
    for record in discovered:
        locator = record["locator"]
        paths.add(locator.split("!", 1)[0].split("#", 1)[0])
    if not paths:
        return
    result = subprocess.run(
        ["git", "diff", "--quiet", subject, "--", *sorted(paths)],
        cwd=root,
        check=False,
    )
    if result.returncode:
        fail("governed asset inputs differ from ledger subjectCommit")


def validate_record_fields(record: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - record.keys())
    if missing:
        fail(f"{record.get('id', '<unknown>')}: missing fields: {', '.join(missing)}")
    empty = [field for field in REQUIRED_FIELDS - {"blockers"} if record[field] in {None, ""}]
    if empty:
        fail(f"{record['id']}: empty fields: {', '.join(sorted(empty))}")
    if record["releaseDisposition"] not in VALID_DISPOSITIONS:
        fail(f"{record['id']}: invalid release disposition")
    risky = (
        "UNVERIFIED" in record["creator"]
        or "UNVERIFIED" in record["licensePermission"]
        or record["attribution"] == "REQUIRED_UNAVAILABLE"
        or record["privacyClass"].startswith("PHI_RISK")
        or record["permittedUse"].startswith(("NONE_", "PROHIBITED_"))
        or bool(record["blockers"])
    )
    if risky and record["releaseDisposition"] != "BLOCKED_RELEASE":
        fail(f"{record['id']}: unresolved or prohibited rights are not release-blocking")
    if record["releaseDisposition"] == "ADMITTED" and record["blockers"]:
        fail(f"{record['id']}: admitted asset retains blockers")


def validate_retired_assets(root: Path, policy: dict[str, Any]) -> None:
    retired = policy.get("retiredAssets", [])
    locators = [item.get("locator") for item in retired]
    hashes = [item.get("contentSha256") for item in retired]
    if len(locators) != len(set(locators)) or len(hashes) != len(set(hashes)):
        fail("retired asset policy contains duplicate locators or hashes")
    if any(not isinstance(locator, str) or not locator for locator in locators):
        fail("retired asset policy contains an invalid locator")
    if any(not isinstance(digest, str) or len(digest) != 64 for digest in hashes):
        fail("retired asset policy contains an invalid SHA-256")
    for locator in locators:
        if (root / locator).exists():
            fail(f"retired asset path returned: {locator}")
    retired_hashes = set(hashes)
    ignored = set(policy["ignoredDirectories"])
    for relative_root in policy["governedRoots"]:
        search_root = root / relative_root
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if not path.is_file() or any(part in ignored for part in path.parts):
                continue
            if sha256(path.read_bytes()) in retired_hashes:
                fail(f"retired asset content returned: {path.relative_to(root).as_posix()}")


def reconcile_discovered(
    discovered: list[dict[str, Any]], records: dict[str, dict[str, Any]]
) -> set[str]:
    discovered_map = record_map(discovered)
    for record_id, current in discovered_map.items():
        recorded = records.get(record_id)
        if not recorded:
            fail(f"unknown governed asset: {current['locator']}")
        if recorded != current:
            fail(f"changed asset or rights metadata: {current['locator']}")
    return set(discovered_map)


def validate_package_assets(
    root: Path,
    policy: dict[str, Any],
    inventory: dict[str, Any],
    records: dict[str, dict[str, Any]],
) -> set[str]:
    configured_fonts = sorted(item["installedPath"] for item in policy["packageAssets"])
    if configured_fonts != referenced_package_fonts(root, policy):
        fail("package font policy does not match shipped font references")
    expected_ids: set[str] = set()
    for config in policy["packageAssets"]:
        record_id = f"asset:{config['kind']}:{config['locator']}"
        expected_ids.add(record_id)
        record = records.get(record_id)
        if not record:
            fail(f"unknown or missing package asset: {config['locator']}")
        dependency = dependency_record(inventory, config["dependencyId"])
        for field, value in config.items():
            if field != "installedPath" and record.get(field) != value:
                fail(f"{record_id}: policy field {field} does not match")
        if record.get("sourceArtifact") != dependency["artifact"]:
            fail(f"{record_id}: source artifact does not match dependency inventory")
        if record.get("sourceArtifactChecksum") != dependency["checksum"]:
            fail(f"{record_id}: source checksum does not match dependency inventory")
        if record.get("sourceNoticeHashes") != dependency["noticeFiles"]:
            fail(f"{record_id}: notice hashes do not match dependency inventory")
        installed = root / config["installedPath"]
        if installed.exists():
            if record["contentSha256"] != sha256(installed.read_bytes()):
                fail(f"{record_id}: installed package asset hash changed")
            if record["sizeBytes"] != installed.stat().st_size:
                fail(f"{record_id}: installed package asset size changed")
    return expected_ids


def validate_icon_set(
    root: Path,
    config: dict[str, Any],
    inventory: dict[str, Any],
    records: dict[str, dict[str, Any]],
) -> str:
    record_id = f"asset:{config['kind']}:{config['locator']}"
    record = records.get(record_id)
    if not record:
        fail(f"unknown or missing package icon set: {config['locator']}")
    dependency = dependency_record(inventory, config["dependencyId"])
    for field, value in config.items():
        if (
            field not in {"installedDefinitions", "scanRoots", "importSpecifier"}
            and record.get(field) != value
        ):
            fail(f"{record_id}: policy field {field} does not match")
    if record.get("sourceArtifact") != dependency["artifact"]:
        fail(f"{record_id}: source artifact does not match dependency inventory")
    if record.get("sourceArtifactChecksum") != dependency["checksum"]:
        fail(f"{record_id}: source checksum does not match dependency inventory")
    if record.get("sourceNoticeHashes") != dependency["noticeFiles"]:
        fail(f"{record_id}: notice hashes do not match dependency inventory")

    expected_names = imported_icons(root, config)
    embedded = record.get("embeddedAssets", [])
    actual_names = [item.get("name") for item in embedded]
    if actual_names != expected_names:
        fail(f"{record_id}: imported icon set changed")
    canonical = json.dumps(embedded, separators=(",", ":"), sort_keys=True).encode()
    if record["contentSha256"] != sha256(canonical):
        fail(f"{record_id}: icon-set content hash is not canonical")
    for item in embedded:
        installed = root / config["installedDefinitions"].format(name=item["name"])
        if installed.exists() and item["contentSha256"] != sha256(installed.read_bytes()):
            fail(f"{record_id}: installed icon hash changed for {item['name']}")
    return record_id


def validate(
    root: Path = ROOT,
    ledger_path: Path = DEFAULT_OUTPUT,
    policy_path: Path = DEFAULT_POLICY,
    inventory_path: Path = DEFAULT_INVENTORY,
    require_release_admission: bool = False,
) -> dict[str, Any]:
    policy = load_json(policy_path)
    ledger = load_json(ledger_path)
    inventory = load_json(inventory_path)
    if ledger.get("schemaVersion") != policy.get("schemaVersion"):
        fail("ledger and policy schema versions differ")
    policy_hash = sha256(json.dumps(policy, separators=(",", ":"), sort_keys=True).encode())
    if ledger.get("policySha256") != policy_hash:
        fail("ledger is not bound to the current asset policy")
    validate_retired_assets(root, policy)
    validate_subject(root, ledger.get("subjectCommit", ""))

    records = record_map(ledger.get("records", []))
    for record in records.values():
        validate_record_fields(record)

    discovered = discover_repository_records(root, policy) + discover_inline_records(root, policy)
    validate_subject_paths(root, ledger["subjectCommit"], discovered)
    discovered_ids = reconcile_discovered(discovered, records)

    package_ids = validate_package_assets(root, policy, inventory, records)
    package_ids.add(validate_icon_set(root, policy["packageIconSet"], inventory, records))
    expected_ids = discovered_ids | package_ids
    extra = sorted(set(records) - expected_ids)
    if extra:
        fail(f"ledger contains stale or ungoverned entries: {', '.join(extra)}")

    blocked = sorted(
        record_id
        for record_id, record in records.items()
        if record["releaseDisposition"] == "BLOCKED_RELEASE"
    )
    admission = "BLOCKED" if blocked else "ADMITTED"
    if ledger.get("releaseAdmission") != admission or ledger.get("releaseBlockers") != blocked:
        fail("release-admission summary does not match record dispositions")
    if require_release_admission and blocked:
        raise ReleaseBlocked(f"release BLOCKED by {len(blocked)} asset-rights entries")
    return ledger


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--release", action="store_true")
    args = parser.parse_args()
    try:
        ledger = validate(
            ledger_path=args.ledger,
            policy_path=args.policy,
            inventory_path=args.inventory,
            require_release_admission=args.release,
        )
    except (ValueError, OSError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f"asset rights ledger FAIL: {exc}")
        return 1
    print(
        f"asset rights ledger PASS: {len(ledger['records'])} records; "
        f"release {ledger['releaseAdmission']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
