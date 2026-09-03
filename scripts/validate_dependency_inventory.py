"""Validate the P0-T03 dependency inventory against every repository manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INVENTORY = ROOT / "docs" / "supply-chain" / "dependency-inventory.json"
REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\\\s]+)")
ACTION = re.compile(r"\buses:\s*([A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+)@([0-9a-f]{40})\b")
IMAGE = re.compile(
    r"(?:^FROM(?:\s+--\S+)*\s+|\bimage:\s*)([^\s]+)@sha256:([0-9a-f]{64})",
    re.MULTILINE,
)
REQUIRED_FIELDS = {
    "id",
    "ecosystem",
    "name",
    "version",
    "role",
    "optional",
    "source",
    "artifact",
    "checksum",
    "checksumVerified",
    "license",
    "noticeFiles",
    "purpose",
    "distribution",
    "manifestRefs",
    "admission",
    "blockers",
}
REQUIRED_MANUAL_IDS = {
    "terraform-provider:oracle/oci@7.32.0",
    "terraform-provider:oracle/oci@8.29.0-linux-arm64",
    "tool:opentofu@1.12.6-linux-arm64",
    "tool:sops@3.13.3-linux-arm64",
    "tool:age@1.3.2-linux-arm64",
    "tool:barman@3.19.1",
    "tool:restic@0.19.1",
    "tool:rest-server@0.14.0",
    "model:smollm2-1.7b-instruct@31b70e2e869a7173562077fd711b654946d38674",
    "model:smollm2-360m-instruct@a10cc1512eabd3dde888204e902eca88bddb4951",
    "model:trace-sim@2d625b1fad5c97584e1f7c69c3a95a6761fd934adaf17b1cecce329247e9fa0d",
    "standards:owasp-asvs@5.0.0",
    "standards:json-schema@2020-12",
    "standards:fhir-r4-core@4.0.1",
    "standards:dicom@2026c",
    "standards:ome-zarr@0.5.2-zarr-v3",
    "standards:lti-advantage@1.3-2.0",
    "standards:oneroster@1.2-rest-1.2.1-csv",
    "standards:qti@3.0.1",
    "standards:case@1.1",
    "standards:open-badges@3.0-context-3.0.3",
    "standards:clr@2.0-context-2.0.1",
    "standards:w3c-vc-bitstring-rdfc@2.0-1.0-1.0",
    "standards:caliper@1.2",
    "standards:wcag@2.2",
}
REQUIRED_BUNDLED_IDS = {
    "npm:@fontsource-variable/cormorant-garamond@5.3.0",
    "npm:@fontsource-variable/sofia-sans@5.3.0",
    "npm:@fontsource-variable/source-sans-3@5.3.0",
    "npm:@phosphor-icons/react@2.1.10",
    "npm:onnxruntime-web@1.27.0",
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def fail(message: str) -> None:
    raise ValueError(message)


def npm_id(key: str) -> str:
    base = key.split("(", 1)[0]
    boundary = base.rfind("@")
    if boundary <= 0:
        fail(f"invalid pnpm package key: {key}")
    return f"npm:{base[:boundary]}@{base[boundary + 1:]}"


def expected_python_ids() -> set[str]:
    result: set[str] = set()
    for relative in ("deploy/backend-requirements.txt", "deploy/oci-cli-requirements.txt"):
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines():
            match = REQUIREMENT.match(line)
            if match:
                result.add(f"pypi:{match.group(1).replace('_', '-').lower()}@{match.group(2)}")
    return result


def workflow_text() -> str:
    return "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml"))
    )


def expected_action_ids(text: str) -> set[str]:
    return {f"github-action:{name}@{revision}" for name, revision in ACTION.findall(text)}


def expected_container_ids() -> set[str]:
    result: set[str] = set()
    manifests = (
        "deploy/Dockerfile.backend",
        "deploy/Dockerfile.web",
        "deploy/compose.yaml",
        "deploy/compose.postgres.yaml",
    )
    for relative in manifests:
        for image, digest in IMAGE.findall((ROOT / relative).read_text(encoding="utf-8")):
            name = image.rsplit(":", 1)[0]
            result.add(f"container:{name}@sha256:{digest}")
    return result


def validate(path: Path, subject: str | None = None) -> dict[str, Any]:
    inventory = json.loads(path.read_text(encoding="utf-8"))
    if inventory.get("schema") != "pathlab.dependency-inventory/1":
        fail("unexpected inventory schema")
    if subject and inventory.get("subjectCommit") != subject:
        fail("inventory subject does not match requested commit")
    if inventory.get("subjectTree") != git("rev-parse", f"{inventory['subjectCommit']}^{{tree}}"):
        fail("inventory subject tree does not match subject commit")

    records = inventory.get("records")
    if not isinstance(records, list) or not records:
        fail("inventory records must be a non-empty list")
    ids = [record.get("id") for record in records]
    if len(ids) != len(set(ids)):
        fail("inventory record identifiers must be unique")
    by_id = {record["id"]: record for record in records}
    for record in records:
        missing = REQUIRED_FIELDS - record.keys()
        if missing:
            fail(f"{record.get('id', '<unknown>')} missing fields: {sorted(missing)}")
        unresolved = (
            record["license"].upper() in {"", "UNKNOWN", "UNLICENSED", "NOASSERTION"}
            or record["checksum"] == "MISSING"
            or not record["noticeFiles"]
        )
        if unresolved and (record["admission"] != "BLOCKED" or not record["blockers"]):
            fail(f"{record['id']} has unresolved evidence without a fail-closed blocker")
        if record["checksumVerified"] and record["checksum"] == "MISSING":
            fail(f"{record['id']} claims verification without a checksum")

    lock = yaml.safe_load((ROOT / "pnpm-lock.yaml").read_text(encoding="utf-8"))
    expected_npm = {npm_id(key) for key in lock["packages"]}
    actual_npm = {identifier for identifier in ids if identifier.startswith("npm:")}
    if actual_npm != expected_npm:
        fail(
            "npm reconciliation mismatch: "
            f"missing={expected_npm-actual_npm}, extra={actual_npm-expected_npm}"
        )
    actual_python = {identifier for identifier in ids if identifier.startswith("pypi:")}
    expected_python = expected_python_ids()
    if actual_python != expected_python:
        fail(
            "Python reconciliation mismatch: "
            f"missing={expected_python-actual_python}, extra={actual_python-expected_python}"
        )
    expected_actions = expected_action_ids(workflow_text())
    actual_actions = {identifier for identifier in ids if identifier.startswith("github-action:")}
    if actual_actions != expected_actions:
        fail(
            "Actions reconciliation mismatch: "
            f"missing={expected_actions-actual_actions}, extra={actual_actions-expected_actions}"
        )
    expected_images = expected_container_ids()
    actual_images = {identifier for identifier in ids if identifier.startswith("container:")}
    if actual_images != expected_images:
        fail(
            "container reconciliation mismatch: "
            f"missing={expected_images-actual_images}, extra={actual_images-expected_images}"
        )
    missing_manual = REQUIRED_MANUAL_IDS - set(ids)
    if missing_manual:
        fail(f"required manual inventory records missing: {sorted(missing_manual)}")
    missing_bundled = REQUIRED_BUNDLED_IDS - set(ids)
    if missing_bundled:
        fail(f"required bundled font, icon, or binary records missing: {sorted(missing_bundled)}")

    if "npm:combine-errors@3.0.3" in by_id:
        fail("combine-errors must remain absent after P0-T04")
    tus = by_id.get("npm:tus-js-client@4.3.1")
    if not tus or tus["license"] != "MIT" or tus["admission"] == "BLOCKED":
        fail("the patched tus-js-client dependency must retain its admitted MIT evidence")
    trace_id = "model:trace-sim@2d625b1fad5c97584e1f7c69c3a95a6761fd934adaf17b1cecce329247e9fa0d"
    trace = by_id[trace_id]
    if trace["role"] != "excluded-production" or trace["admission"] != "BLOCKED":
        fail("TRACE-SIM must remain excluded and blocked from production")
    hosted = by_id["tool:github-runner@ubuntu-latest"]
    if (
        hosted["distribution"] != "online-service-not-distributed-software"
        or hosted["admission"] != "BLOCKED"
    ):
        fail("mutable hosted CI must not become software or Zero-Cash authority")

    for receipt in inventory.get("sources", []):
        actual_blob = git("hash-object", "--path", receipt["path"], receipt["path"])
        if actual_blob != receipt["gitBlob"]:
            fail(f"source Git blob drifted: {receipt['path']}")
        blob_bytes = subprocess.check_output(["git", "cat-file", "blob", actual_blob], cwd=ROOT)
        if hashlib.sha256(blob_bytes).hexdigest() != receipt["sha256"]:
            fail(f"canonical source receipt drifted: {receipt['path']}")
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--subject")
    args = parser.parse_args()
    inventory = validate(args.inventory, args.subject)
    blocked = sum(record["admission"] == "BLOCKED" for record in inventory["records"])
    print(f"dependency inventory PASS: {len(inventory['records'])} records; {blocked} fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
