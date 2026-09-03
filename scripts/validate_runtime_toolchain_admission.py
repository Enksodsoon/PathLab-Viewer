"""Fail-closed validation for the P0-T03A runtime/toolchain admission set."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "docs" / "supply-chain" / "runtime-toolchain-inputs.json"
DEFAULT_LOCK = ROOT / "docs" / "supply-chain" / "runtime-toolchain-requirements.txt"
DEFAULT_POLICY = ROOT / "docs" / "supply-chain" / "offline-scanner-policy.json"
DEFAULT_RECEIPT = ROOT / "docs" / "supply-chain" / "runtime-toolchain-source-receipt.json"

REQUIRED_IDS = {
    "postgresql@18.6-source",
    "pgbouncer@1.25.2-source",
    "caddy@2.11.4-linux-arm64",
    "nats-server@2.14.6-linux-arm64",
    "syft@1.51.1-linux-arm64",
    "cyclonedx-cli@0.33.1-linux-arm64",
    "cosign@3.1.3-linux-arm64",
    "slsa-verifier@2.7.1-linux-arm64",
    "grype@0.118.0-linux-arm64",
    "osv-scanner@2.5.1-linux-arm64",
    "pypi:cryptography@50.0.1",
    "pypi:rfc8785@0.1.4",
    "pypi:spdx-tools@0.8.5",
    "pypi:webauthn@3.0.0",
}
PYTHON_ROOTS = {
    "cryptography": "50.0.1",
    "rfc8785": "0.1.4",
    "spdx-tools": "0.8.5",
    "webauthn": "3.0.0",
}
FIELDS = {
    "id",
    "name",
    "version",
    "sourceRevision",
    "artifact",
    "sha256",
    "verification",
    "provenance",
    "license",
    "licenseArtifact",
    "licenseSha256",
    "arm64",
    "maintenance",
    "purpose",
    "mirrorPath",
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PIN = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s\\]+)")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")
MUTABLE_WORDS = re.compile(r"(?:^|[/_.-])(latest|main|master|nightly)(?:$|[/_.-])", re.I)


def fail(message: str) -> None:
    raise ValueError(message)


def _validate_url(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        fail(f"{label} must be an HTTPS URL")
    if MUTABLE_WORDS.search(parsed.path):
        fail(f"{label} contains a mutable source selector")


def parse_lock(path: Path) -> dict[str, tuple[str, set[str]]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    packages: dict[str, tuple[str, set[str]]] = {}
    index = 0
    while index < len(lines):
        match = PIN.match(lines[index])
        if not match:
            index += 1
            continue
        name = match.group(1).replace("_", "-").lower()
        version = match.group(2)
        block = [lines[index]]
        index += 1
        while index < len(lines) and not PIN.match(lines[index]):
            block.append(lines[index])
            index += 1
        hashes = set(HASH.findall("\n".join(block)))
        if not hashes:
            fail(f"Python requirement {name}=={version} is not hash locked")
        if name in packages:
            fail(f"duplicate Python requirement: {name}")
        packages[name] = (version, hashes)
    if not packages:
        fail("Python lock contains no exact requirements")
    return packages


def validate(
    manifest_path: Path = DEFAULT_MANIFEST,
    lock_path: Path = DEFAULT_LOCK,
    policy_path: Path = DEFAULT_POLICY,
    mirror_root: Path | None = None,
    receipt_path: Path | None = DEFAULT_RECEIPT,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != "pathlab.runtime-toolchain-inputs/1":
        fail("unexpected runtime toolchain schema")
    if manifest.get("target") != "linux-arm64":
        fail("runtime toolchain target must be linux-arm64")
    records = manifest.get("records")
    if not isinstance(records, list) or not records:
        fail("runtime toolchain records must be a non-empty list")
    ids = [record.get("id") for record in records]
    if len(ids) != len(set(ids)):
        fail("runtime toolchain identifiers must be unique")
    if set(ids) != REQUIRED_IDS:
        missing_ids = REQUIRED_IDS - set(ids)
        extra_ids = set(ids) - REQUIRED_IDS
        fail(f"runtime toolchain membership mismatch: missing={missing_ids}, extra={extra_ids}")

    for record in records:
        missing = FIELDS - record.keys()
        if missing:
            fail(f"{record.get('id', '<unknown>')} missing fields: {sorted(missing)}")
        if not SHA256.fullmatch(record["sha256"]) or not SHA256.fullmatch(
            record["licenseSha256"]
        ):
            fail(f"{record['id']} has an invalid sha256")
        if record["license"].upper() in {"", "UNKNOWN", "NOASSERTION", "PROPRIETARY"}:
            fail(f"{record['id']} has unresolved or non-free license rights")
        if not record["version"] or not record["sourceRevision"]:
            fail(f"{record['id']} is not exactly versioned")
        _validate_url(record["artifact"], f"{record['id']} artifact")
        _validate_url(record["provenance"], f"{record['id']} provenance")
        _validate_url(record["licenseArtifact"], f"{record['id']} license")
        if "arm64" not in record["arm64"].lower():
            fail(f"{record['id']} does not establish ARM64 availability")
        mirror = Path(record["mirrorPath"])
        unsafe = mirror.is_absolute() or ".." in mirror.parts
        if unsafe or mirror.parts[:2] != ("offline", "toolchain"):
            fail(f"{record['id']} has an unsafe mirror path")
        if mirror_root is not None:
            candidate = mirror_root.joinpath(*mirror.parts[2:])
            if not candidate.is_file():
                fail(f"{record['id']} is absent from the offline mirror")
            actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if actual != record["sha256"]:
                fail(f"{record['id']} mirror sha256 mismatch")

    locked = parse_lock(lock_path)
    for name, version in PYTHON_ROOTS.items():
        if name not in locked or locked[name][0] != version:
            fail(f"Python root {name}=={version} is absent from the exact lock")
    for name, (version, hashes) in locked.items():
        if not version or not hashes:
            fail(f"Python transitive input {name} is not fully pinned")

    policy = json.loads(policy_path.read_text(encoding="utf-8"))
    if policy.get("schema") != "pathlab.offline-scanner-policy/1":
        fail("unexpected offline scanner policy schema")
    if policy.get("network") != "disabled" or policy.get("automaticDatabaseUpdate") is not False:
        fail("security scanners must be network-disabled with automatic updates off")
    if policy.get("missingDatabaseDisposition") != "BLOCKED":
        fail("missing scanner databases must fail closed")
    for scanner in ("grype", "osv"):
        entry = policy.get("databases", {}).get(scanner, {})
        if "<release-bound-snapshot-sha256>" not in entry.get("mirrorPathTemplate", ""):
            fail(f"{scanner} database must be bound to an exact release snapshot")
    if receipt_path is not None:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        if receipt.get("schema") != "pathlab.runtime-toolchain-source-verification/1":
            fail("unexpected official-source receipt schema")
        if receipt.get("subjectCommit") != manifest.get("subjectCommit"):
            fail("official-source receipt subject does not match admission subject")
        verified = {entry["id"]: entry for entry in receipt.get("results", [])}
        if set(verified) != set(ids):
            fail("official-source receipt does not cover the complete admitted set")
        for record in records:
            entry = verified[record["id"]]
            if entry.get("artifactSha256") != record["sha256"]:
                fail(f"{record['id']} official-source artifact receipt mismatch")
            if entry.get("licenseSha256") != record["licenseSha256"]:
                fail(f"{record['id']} official-source license receipt mismatch")
            if not SHA256.fullmatch(entry.get("provenanceSha256", "")):
                fail(f"{record['id']} lacks downloaded provenance evidence")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--mirror-root", type=Path)
    args = parser.parse_args()
    manifest = validate(args.manifest, args.lock, args.policy, args.mirror_root)
    packages = parse_lock(args.lock)
    print(
        "runtime toolchain admission PASS: "
        f"{len(manifest['records'])} records; {len(packages)} hash-locked Python packages"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
