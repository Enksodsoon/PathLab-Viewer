"""Build the P0-T03 dependency inventory from locked primary-source artifacts."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import subprocess
import tarfile
import time
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "docs" / "supply-chain" / "dependency-inventory.json"
MANUAL_INPUTS = ROOT / "docs" / "supply-chain" / "dependency-manual-inputs.json"
NPM_LOCK = ROOT / "pnpm-lock.yaml"
PYTHON_LOCKS = {
    "runtime-mandatory": ROOT / "deploy" / "backend-requirements.txt",
    "deployment-only": ROOT / "deploy" / "oci-cli-requirements.txt",
}
TEST_ROOTS = {
    "@playwright/test",
    "@testing-library/jest-dom",
    "@testing-library/react",
    "@testing-library/user-event",
    "jsdom",
    "vitest",
}
BUILD_ROOTS = {
    "@eslint/js",
    "@types/node",
    "@types/react",
    "@types/react-dom",
    "@vitejs/plugin-react",
    "eslint",
    "eslint-plugin-react-hooks",
    "eslint-plugin-react-refresh",
    "globals",
    "typescript",
    "typescript-eslint",
    "vite",
}
LICENSE_BASENAME = re.compile(
    r"^(license|licence|copying|copyright|notice)(?:[._-].*)?$", re.IGNORECASE
)
REQ_START = re.compile(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)")
REQ_HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})")


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_url(url: str) -> bytes:
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(url, headers={"User-Agent": "PathLab-P0-T03/1"})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as exc:  # noqa: BLE001 - bounded retry preserves the failed input
            last_error = exc
            if attempt < 2:
                time.sleep(2**attempt)
    assert last_error is not None
    raise last_error


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def manifest_receipt(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "gitBlob": git("hash-object", path.relative_to(ROOT).as_posix()),
        "sha256": sha256(data),
    }


def split_npm_key(key: str) -> tuple[str, str]:
    boundary = key.rfind("@")
    if boundary <= 0:
        raise ValueError(f"invalid pnpm package key: {key}")
    return key[:boundary], key[boundary + 1 :]


def snapshot_key(name: str, resolution: str) -> str | None:
    if resolution.startswith("link:") or resolution.startswith("workspace:"):
        return None
    if resolution.startswith("npm:"):
        alias = resolution[4:]
        alias_boundary = alias.rfind("@")
        if alias_boundary <= 0:
            return None
        return alias
    return f"{name}@{resolution}"


def walk_npm(lock: dict[str, Any], roots: dict[str, str]) -> tuple[set[str], set[str]]:
    snapshots = lock["snapshots"]
    mandatory: set[str] = set()
    optional: set[str] = set()
    queue: list[tuple[str, bool]] = []
    for name, value in roots.items():
        key = snapshot_key(name, str(value["version"]))
        if key:
            queue.append((key, False))
    while queue:
        key, is_optional = queue.pop()
        destination = optional if is_optional else mandatory
        if key in destination:
            continue
        destination.add(key)
        node = snapshots.get(key)
        if node is None:
            continue
        for name, resolution in node.get("dependencies", {}).items():
            child = snapshot_key(name, str(resolution))
            if child:
                queue.append((child, is_optional))
        for name, resolution in node.get("optionalDependencies", {}).items():
            child = snapshot_key(name, str(resolution))
            if child:
                queue.append((child, True))
    optional -= mandatory
    return mandatory, optional


def npm_roles(lock: dict[str, Any]) -> dict[str, tuple[str, bool]]:
    web = lock["importers"]["apps/web"]
    viewer = lock["importers"]["packages/viewer-ui"]
    runtime, runtime_optional = walk_npm(lock, web.get("dependencies", {}))
    dev = {**web.get("devDependencies", {}), **viewer.get("devDependencies", {})}
    test_roots = {name: value for name, value in dev.items() if name in TEST_ROOTS}
    build_roots = {name: value for name, value in dev.items() if name in BUILD_ROOTS}
    test, test_optional = walk_npm(lock, test_roots)
    build, build_optional = walk_npm(lock, build_roots)
    runtime = {key.split("(", 1)[0] for key in runtime}
    runtime_optional = {key.split("(", 1)[0] for key in runtime_optional}
    test = {key.split("(", 1)[0] for key in test}
    test_optional = {key.split("(", 1)[0] for key in test_optional}
    build = {key.split("(", 1)[0] for key in build}
    build_optional = {key.split("(", 1)[0] for key in build_optional}
    roles: dict[str, tuple[str, bool]] = {}
    for key in lock["packages"]:
        base_key = key.split("(", 1)[0]
        if base_key in runtime:
            roles[key] = ("runtime-mandatory", False)
        elif base_key in runtime_optional:
            roles[key] = ("runtime-optional", True)
        elif base_key in build:
            roles[key] = ("build-only", False)
        elif base_key in test:
            roles[key] = ("test-only", False)
        elif base_key in build_optional:
            roles[key] = ("build-optional", True)
        elif base_key in test_optional:
            roles[key] = ("test-optional", True)
        else:
            roles[key] = ("excluded-lock-entry", True)
    return roles


def archive_notices(data: bytes, source: str) -> list[dict[str, str]]:
    notices: list[dict[str, str]] = []

    def is_notice(name: str) -> bool:
        path = PurePosixPath(name)
        return len(path.parts) <= 4 and LICENSE_BASENAME.match(path.name) is not None

    def accept(name: str, payload: bytes) -> None:
        if len(payload) > 2_000_000:
            return
        notices.append({"path": name, "sha256": sha256(payload)})

    if source.endswith((".whl", ".zip")):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                if not info.is_dir() and is_notice(info.filename):
                    accept(info.filename, archive.read(info))
    else:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as archive:
            for member in archive.getmembers():
                if member.isfile() and is_notice(member.name):
                    extracted = archive.extractfile(member)
                    if extracted is not None:
                        accept(member.name, extracted.read())
    return sorted(notices, key=lambda item: item["path"])


def npm_record(item: tuple[str, dict[str, Any], tuple[str, bool]]) -> dict[str, Any]:
    key, package, role_info = item
    name, version = split_npm_key(key.split("(", 1)[0])
    encoded_name = urllib.parse.quote(name, safe="@")
    metadata_url = f"https://registry.npmjs.org/{encoded_name}/{version}"
    metadata_bytes = read_url(metadata_url)
    metadata = json.loads(metadata_bytes)
    archive_url = metadata["dist"]["tarball"]
    archive = read_url(archive_url)
    integrity = package.get("resolution", {}).get("integrity")
    verified = False
    if integrity and "-" in integrity:
        algorithm, expected = integrity.split("-", 1)
        actual = base64.b64encode(hashlib.new(algorithm, archive).digest()).decode()
        verified = actual == expected
    license_value = metadata.get("license")
    if isinstance(license_value, dict):
        license_value = license_value.get("type")
    license_text = str(license_value).strip() if license_value else "UNKNOWN"
    notices = archive_notices(archive, archive_url)
    blockers: list[str] = []
    if not verified:
        blockers.append("LOCK_INTEGRITY_MISMATCH")
    if license_text.upper() in {"", "UNKNOWN", "UNLICENSED", "NOASSERTION"}:
        blockers.append("UNKNOWN_OR_UNLICENSED")
    if not notices:
        blockers.append("NOTICE_TEXT_NOT_FOUND_IN_ARCHIVE")
    role, optional = role_info
    return {
        "id": f"npm:{name}@{version}",
        "ecosystem": "npm",
        "name": name,
        "version": version,
        "role": role,
        "optional": optional,
        "source": metadata_url,
        "artifact": archive_url,
        "checksum": integrity or "MISSING",
        "checksumVerified": verified,
        "license": license_text,
        "noticeFiles": notices,
        "purpose": "web dependency resolved from pnpm-lock.yaml",
        "distribution": "bundled" if role.startswith("runtime") else "not-bundled-tooling",
        "manifestRefs": ["pnpm-lock.yaml"],
        "metadataSha256": sha256(metadata_bytes),
        "admission": "BLOCKED" if blockers else "RECORDED_UNREVIEWED",
        "blockers": blockers,
    }


def parse_requirements(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = REQ_START.match(line)
        if match:
            if current:
                records.append(current)
            current = {"name": match.group(1), "version": match.group(2), "hashes": []}
        if current:
            current["hashes"].extend(REQ_HASH.findall(line))
    if current:
        records.append(current)
    return records


def pypi_license(metadata: dict[str, Any]) -> str:
    info = metadata["info"]
    expression = info.get("license_expression")
    if expression:
        return str(expression)
    classifiers = [
        value.removeprefix("License :: OSI Approved :: ")
        for value in info.get("classifiers", [])
        if value.startswith("License :: OSI Approved :: ")
    ]
    license_value = str(info.get("license") or "").strip()
    if classifiers:
        return " | ".join(sorted(classifiers))
    if license_value and len(license_value) <= 160:
        return license_value
    return "UNKNOWN"


def python_record(item: tuple[str, Path, dict[str, Any]]) -> dict[str, Any]:
    role, path, requirement = item
    name = requirement["name"]
    version = requirement["version"]
    normalized = name.replace("_", "-")
    metadata_url = f"https://pypi.org/pypi/{normalized}/{version}/json"
    metadata_bytes = read_url(metadata_url)
    metadata = json.loads(metadata_bytes)
    artifacts = metadata.get("urls", [])
    selected = next((entry for entry in artifacts if entry.get("packagetype") == "sdist"), None)
    if selected is None:
        selected = next(
            (entry for entry in artifacts if entry.get("packagetype") == "bdist_wheel"),
            None,
        )
    blockers: list[str] = []
    notices: list[dict[str, str]] = []
    source = "MISSING"
    artifact_hash = "MISSING"
    verified = False
    if selected:
        source = selected["url"]
        artifact_hash = selected["digests"]["sha256"]
        archive = read_url(source)
        verified = sha256(archive) == artifact_hash and artifact_hash in requirement["hashes"]
        notices = archive_notices(archive, source)
    if not verified:
        blockers.append("LOCK_HASH_OR_ARTIFACT_MISMATCH")
    license_text = pypi_license(metadata)
    if license_text.upper() in {"", "UNKNOWN", "UNLICENSED", "NOASSERTION"}:
        blockers.append("UNKNOWN_OR_UNLICENSED")
    if not notices:
        blockers.append("NOTICE_TEXT_NOT_FOUND_IN_ARCHIVE")
    return {
        "id": f"pypi:{normalized.lower()}@{version}",
        "ecosystem": "pypi",
        "name": name,
        "version": version,
        "role": role,
        "optional": False,
        "source": metadata_url,
        "artifact": source,
        "checksum": f"sha256:{artifact_hash}",
        "allLockedSha256": sorted(set(requirement["hashes"])),
        "checksumVerified": verified,
        "license": license_text,
        "noticeFiles": notices,
        "purpose": (
            "PathLab API/runtime dependency"
            if role == "runtime-mandatory"
            else "OCI deployment tooling dependency"
        ),
        "distribution": "bundled-runtime" if role == "runtime-mandatory" else "operator-tooling",
        "manifestRefs": [path.relative_to(ROOT).as_posix()],
        "metadataSha256": sha256(metadata_bytes),
        "admission": "BLOCKED" if blockers else "RECORDED_UNREVIEWED",
        "blockers": blockers,
    }


def merge_python_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for record in records:
        identifier = record["id"]
        if identifier not in merged:
            merged[identifier] = record
            continue
        target = merged[identifier]
        target["manifestRefs"] = sorted(set(target["manifestRefs"] + record["manifestRefs"]))
        if target["role"] != record["role"]:
            target["role"] = "runtime-and-deployment"
            target["purpose"] = "PathLab runtime and OCI deployment tooling dependency"
            target["distribution"] = "bundled-runtime-and-operator-tooling"
    return sorted(merged.values(), key=lambda item: item["id"])


def normalize_manual_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for source in records:
        record = dict(source)
        record.setdefault("optional", False)
        record.setdefault("artifact", record.get("source", "UNRESOLVED"))
        record.setdefault("checksum", "MISSING")
        record.setdefault("checksumVerified", False)
        record.setdefault("license", "UNKNOWN")
        record.setdefault("noticeFiles", [])
        record.setdefault("manifestRefs", [])
        record.setdefault("metadataSha256", None)
        record.setdefault("blockers", [])
        record.setdefault("admission", "BLOCKED" if record["blockers"] else "RECORDED_UNREVIEWED")
        normalized.append(record)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--subject", required=True, help="exact audited Git commit")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    lock = yaml.safe_load(NPM_LOCK.read_text(encoding="utf-8"))
    roles = npm_roles(lock)
    npm_items = [(key, value, roles[key]) for key, value in lock["packages"].items()]
    python_items: list[tuple[str, Path, dict[str, Any]]] = []
    for role, path in PYTHON_LOCKS.items():
        python_items.extend((role, path, item) for item in parse_requirements(path))

    npm_records: list[dict[str, Any]] = []
    python_records: list[dict[str, Any]] = []
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_map = {executor.submit(npm_record, item): ("npm", item[0]) for item in npm_items}
        future_map.update(
            {
                executor.submit(python_record, item): ("pypi", item[2]["name"])
                for item in python_items
            }
        )
        for future in as_completed(future_map):
            ecosystem, name = future_map[future]
            try:
                record = future.result()
            except Exception as exc:  # noqa: BLE001 - inventory must report every failed input
                failures.append(f"{ecosystem}:{name}: {type(exc).__name__}: {exc}")
                continue
            if ecosystem == "npm":
                npm_records.append(record)
            else:
                python_records.append(record)

    if failures:
        raise SystemExit("inventory retrieval failed:\n" + "\n".join(sorted(failures)))

    manual = json.loads(MANUAL_INPUTS.read_text(encoding="utf-8"))
    manual_records = normalize_manual_records(manual["records"])
    subject_tree = git("rev-parse", f"{args.subject}^{{tree}}")
    inventory = {
        "schema": "pathlab.dependency-inventory/1",
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "subjectCommit": args.subject,
        "subjectTree": subject_tree,
        "sources": [
            manifest_receipt(NPM_LOCK),
            *(manifest_receipt(path) for path in PYTHON_LOCKS.values()),
            manifest_receipt(MANUAL_INPUTS),
        ],
        "records": sorted(
            npm_records + merge_python_records(python_records) + manual_records,
            key=lambda item: item["id"],
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"wrote {len(inventory['records'])} records "
        f"({len(npm_records)} npm, {len(merge_python_records(python_records))} PyPI, "
        f"{len(manual_records)} manual)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
