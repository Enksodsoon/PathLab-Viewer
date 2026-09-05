"""Generate deterministic P0-T06 SPDX, CycloneDX, and notice inventories."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

try:
    from scripts.validate_asset_rights_ledger import validate as validate_assets
    from scripts.validate_dependency_inventory import validate as validate_dependencies
    from scripts.validate_runtime_toolchain_admission import validate as validate_toolchain
except ModuleNotFoundError:
    from validate_asset_rights_ledger import validate as validate_assets
    from validate_dependency_inventory import validate as validate_dependencies
    from validate_runtime_toolchain_admission import validate as validate_toolchain

ROOT = Path(__file__).resolve().parents[1]
SUPPLY_CHAIN = ROOT / "docs" / "supply-chain"
DEFAULT_OUTPUT = SUPPLY_CHAIN / "software-inventories"
DEPENDENCY_INVENTORY = SUPPLY_CHAIN / "dependency-inventory.json"
TOOLCHAIN_INVENTORY = SUPPLY_CHAIN / "runtime-toolchain-inputs.json"
ASSET_LEDGER = SUPPLY_CHAIN / "ASSET_RIGHTS_LEDGER.json"
SCHEMA = "pathlab.software-inventory-manifest/1"
SPDX_VERSION = "SPDX-2.3"
CYCLONEDX_VERSION = "1.6"

OUTPUT_NAMES = (
    "source.spdx.json",
    "source.cdx.json",
    "build.spdx.json",
    "build.cdx.json",
    "THIRD_PARTY_NOTICES.txt",
)
INPUT_PATHS = (
    "LICENSE",
    "NOTICE",
    "package.json",
    "pnpm-lock.yaml",
    "pyproject.toml",
    "apps/web/package.json",
    "deploy/backend-requirements.txt",
    "deploy/oci-cli-requirements.txt",
    "deploy/Dockerfile.backend",
    "deploy/Dockerfile.web",
    "deploy/compose.yaml",
    "deploy/compose.postgres.yaml",
    "docs/supply-chain/dependency-inventory.json",
    "docs/supply-chain/runtime-toolchain-inputs.json",
    "docs/supply-chain/runtime-toolchain-source-receipt.json",
    "docs/supply-chain/runtime-toolchain-requirements.txt",
    "docs/supply-chain/ASSET_RIGHTS_LEDGER.json",
    "docs/supply-chain/asset-rights-policy.json",
    "scripts/generate_software_inventories.py",
    "scripts/validate_software_inventories.py",
)

BUILD_ROLES = {
    "build-and-deployment",
    "build-and-test",
    "build-only",
    "build-optional",
    "current-deployment-tooling",
    "current-development-runtime",
    "deployment-only",
    "runtime-and-deployment",
    "runtime-mandatory",
    "runtime-optional",
    "test-only",
    "test-optional",
}
SHIPPED_DISTRIBUTIONS = {
    "browser-bundled",
    "bundled",
    "bundled-runtime",
    "bundled-runtime-and-operator-tooling",
}

LICENSE_ALIASES = {
    "Apache License 2.0": "Apache-2.0",
    "Apache Software License": "Apache-2.0",
    "BSD License": "BSD-3-Clause",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "MIT License": "MIT",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "Unlicense": "Unlicense",
}
VALID_LICENSE_EXPRESSION = re.compile(r"^[A-Za-z0-9.+-]+(?: (?:AND|OR) [A-Za-z0-9.+-]+)*$")


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def git_bytes(subject: str, path: str) -> bytes:
    return subprocess.check_output(["git", "show", f"{subject}:{path}"], cwd=ROOT)


def subject_timestamp(subject: str) -> str:
    epoch = int(git("show", "-s", "--format=%ct", subject))
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_license(value: str) -> str:
    candidate = LICENSE_ALIASES.get(value, value)
    if candidate.upper() in {"", "UNKNOWN", "NOASSERTION", "UNLICENSED"}:
        return "NOASSERTION"
    return candidate if VALID_LICENSE_EXPRESSION.fullmatch(candidate) else "NOASSERTION"


def valid_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"https", "http"} and parsed.netloc else None


def sha256_checksum(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"(?:sha256:)?([0-9a-f]{64})", value)
    return match.group(1) if match else None


def package_url(record: dict[str, Any]) -> str | None:
    ecosystem = record.get("ecosystem")
    name = str(record.get("name", ""))
    version = str(record.get("version", ""))
    if ecosystem == "npm":
        return f"pkg:npm/{quote(name, safe='')}@{quote(version, safe='')}"
    if ecosystem == "pypi":
        return f"pkg:pypi/{quote(name, safe='')}@{quote(version, safe='')}"
    if ecosystem == "container":
        return f"pkg:oci/{quote(name, safe='/')}@{quote(version, safe='')}"
    if ecosystem == "github-action":
        return f"pkg:github/{quote(name, safe='/')}@{quote(version, safe='')}"
    return None


def component_ref(prefix: str, identifier: str) -> str:
    return f"{prefix}:{identifier}"


def dependency_components(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ref": component_ref("dependency", record["id"]),
            "kind": "dependency",
            "id": record["id"],
            "name": record["name"],
            "version": record["version"],
            "license": record["license"],
            "source": record["source"],
            "artifact": record["artifact"],
            "checksum": record["checksum"],
            "ecosystem": record["ecosystem"],
            "role": record["role"],
            "distribution": record["distribution"],
            "admission": record["admission"],
            "blockers": sorted(record["blockers"]),
            "noticeFiles": sorted(record["noticeFiles"], key=lambda item: item["path"]),
            "manifestRefs": sorted(record["manifestRefs"]),
            "purl": package_url(record),
        }
        for record in sorted(records, key=lambda item: item["id"])
    ]


def toolchain_components(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ref": component_ref("toolchain", record["id"]),
            "kind": "toolchain",
            "id": record["id"],
            "name": record["name"],
            "version": record["version"],
            "license": record["license"],
            "source": record["provenance"],
            "artifact": record["artifact"],
            "checksum": f"sha256:{record['sha256']}",
            "ecosystem": "verification-toolchain",
            "role": "build-and-verification",
            "distribution": "offline-toolchain",
            "admission": "ADMITTED",
            "blockers": [],
            "noticeFiles": [{"path": record["licenseArtifact"], "sha256": record["licenseSha256"]}],
            "manifestRefs": [record["mirrorPath"]],
            "purl": None,
        }
        for record in sorted(records, key=lambda item: item["id"])
    ]


def asset_components(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "ref": component_ref("asset", record["id"]),
            "kind": "asset",
            "id": record["id"],
            "name": record["locator"],
            "version": record["contentSha256"][:16],
            "license": record["licensePermission"],
            "source": record["provenance"],
            "artifact": record["locator"],
            "checksum": f"sha256:{record['contentSha256']}",
            "ecosystem": record["kind"],
            "role": "release-asset",
            "distribution": record["distributionScope"],
            "admission": record["releaseDisposition"],
            "blockers": sorted(record["blockers"]),
            "noticeFiles": [],
            "manifestRefs": [record["locator"]],
            "purl": None,
        }
        for record in sorted(records, key=lambda item: item["id"])
    ]


def spdx_id(ref: str) -> str:
    return f"SPDXRef-{hashlib.sha256(ref.encode()).hexdigest()[:24]}"


def spdx_package(component: dict[str, Any]) -> dict[str, Any]:
    checksum = sha256_checksum(component["checksum"])
    package = {
        "SPDXID": spdx_id(component["ref"]),
        "name": component["name"],
        "versionInfo": component["version"],
        "downloadLocation": valid_url(component["artifact"]) or "NOASSERTION",
        "filesAnalyzed": False,
        "licenseConcluded": "NOASSERTION",
        "licenseDeclared": normalize_license(component["license"]),
        "copyrightText": "NOASSERTION",
        "comment": json.dumps(
            {
                "pathlabId": component["id"],
                "kind": component["kind"],
                "role": component["role"],
                "distribution": component["distribution"],
                "admission": component["admission"],
                "blockers": component["blockers"],
                "recordedLicense": component["license"],
            },
            separators=(",", ":"),
            sort_keys=True,
        ),
    }
    if checksum:
        package["checksums"] = [{"algorithm": "SHA256", "checksumValue": checksum}]
    external_refs = []
    if component["purl"]:
        external_refs.append(
            {
                "referenceCategory": "PACKAGE-MANAGER",
                "referenceType": "purl",
                "referenceLocator": component["purl"],
            }
        )
    if external_refs:
        package["externalRefs"] = external_refs
    return package


def spdx_document(
    *, subject: str, tree: str, created: str, scope: str, components: list[dict[str, Any]]
) -> dict[str, Any]:
    root_ref = f"pathlab:{scope}:{subject}"
    root = {
        "ref": root_ref,
        "kind": "application",
        "id": f"pathlab-{scope}",
        "name": f"PathLab Viewer {scope} inventory",
        "version": subject,
        "license": "Apache-2.0",
        "source": f"git+https://github.com/Enksodsoon/PathLab-Viewer@{subject}",
        "artifact": f"https://github.com/Enksodsoon/PathLab-Viewer/tree/{subject}",
        "checksum": tree,
        "ecosystem": "application",
        "role": scope,
        "distribution": "source" if scope == "source" else "build-contract",
        "admission": "RECORDED",
        "blockers": [],
        "noticeFiles": [],
        "manifestRefs": [],
        "purl": f"pkg:github/Enksodsoon/PathLab-Viewer@{subject}",
    }
    packages = [spdx_package(root), *(spdx_package(item) for item in components)]
    relationships = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": spdx_id(root_ref),
        },
        *(
            {
                "spdxElementId": spdx_id(root_ref),
                "relationshipType": "DEPENDS_ON",
                "relatedSpdxElement": spdx_id(item["ref"]),
            }
            for item in components
        ),
    ]
    return {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": SPDX_VERSION,
        "dataLicense": "CC0-1.0",
        "name": f"pathlab-viewer-{scope}-{subject}",
        "documentNamespace": f"https://sbom.pathlab.invalid/{scope}/{subject}/{tree}",
        "creationInfo": {"created": created, "creators": ["Organization: PathLab"]},
        "documentDescribes": [spdx_id(root_ref)],
        "packages": packages,
        "relationships": relationships,
    }


def cdx_type(component: dict[str, Any]) -> str:
    if component["kind"] == "asset":
        return "file"
    if component["ecosystem"] == "container":
        return "container"
    if component["ecosystem"] == "operating-system":
        return "operating-system"
    if component["kind"] == "application":
        return "application"
    return "library"


def cdx_component(component: dict[str, Any]) -> dict[str, Any]:
    checksum = sha256_checksum(component["checksum"])
    normalized = normalize_license(component["license"])
    license_entry = (
        {"expression": normalized}
        if normalized != "NOASSERTION"
        else {"license": {"name": component["license"]}}
    )
    result: dict[str, Any] = {
        "type": cdx_type(component),
        "bom-ref": component["ref"],
        "name": component["name"],
        "version": component["version"],
        "licenses": [license_entry],
        "properties": [
            {"name": "pathlab:id", "value": component["id"]},
            {"name": "pathlab:role", "value": component["role"]},
            {"name": "pathlab:distribution", "value": component["distribution"]},
            {"name": "pathlab:admission", "value": component["admission"]},
            {
                "name": "pathlab:blockers",
                "value": json.dumps(component["blockers"], separators=(",", ":")),
            },
        ],
    }
    if checksum:
        result["hashes"] = [{"alg": "SHA-256", "content": checksum}]
    if component["purl"]:
        result["purl"] = component["purl"]
    references = []
    for reference_type, value in (
        ("distribution", valid_url(component["artifact"])),
        ("vcs", valid_url(component["source"])),
    ):
        if value:
            references.append({"type": reference_type, "url": value})
    if references:
        result["externalReferences"] = references
    return result


def cdx_document(
    *, subject: str, tree: str, created: str, scope: str, components: list[dict[str, Any]]
) -> dict[str, Any]:
    root_ref = f"pathlab:{scope}:{subject}"
    serial_number = (
        f"urn:uuid:{subject[:8]}-{subject[8:12]}-4{subject[13:16]}-"
        f"a{subject[17:20]}-{subject[20:32]}"
    )
    root = {
        "ref": root_ref,
        "kind": "application",
        "id": f"pathlab-{scope}",
        "name": f"PathLab Viewer {scope} inventory",
        "version": subject,
        "license": "Apache-2.0",
        "source": f"https://github.com/Enksodsoon/PathLab-Viewer/tree/{subject}",
        "artifact": f"https://github.com/Enksodsoon/PathLab-Viewer/tree/{subject}",
        "checksum": tree,
        "ecosystem": "application",
        "role": scope,
        "distribution": "source" if scope == "source" else "build-contract",
        "admission": "RECORDED",
        "blockers": [],
        "noticeFiles": [],
        "manifestRefs": [],
        "purl": f"pkg:github/Enksodsoon/PathLab-Viewer@{subject}",
    }
    return {
        "bomFormat": "CycloneDX",
        "specVersion": CYCLONEDX_VERSION,
        "serialNumber": serial_number,
        "version": 1,
        "metadata": {"timestamp": created, "component": cdx_component(root)},
        "components": [cdx_component(item) for item in components],
        "dependencies": [
            {"ref": root_ref, "dependsOn": [item["ref"] for item in components]},
            *({"ref": item["ref"], "dependsOn": []} for item in components),
        ],
    }


def notice_bundle(components: list[dict[str, Any]], root_notice: str) -> bytes:
    lines = [
        "PATHLAB VIEWER THIRD-PARTY NOTICE BUNDLE",
        "",
        "This deterministic bundle is an inventory of recorded licenses and notice-file hashes.",
        "It does not replace missing upstream notice text or admit a blocked component.",
        "",
        "PATHLAB ROOT NOTICE",
        "-------------------",
        root_notice.rstrip(),
        "",
        "RECORDED COMPONENTS",
        "-------------------",
    ]
    for component in components:
        lines.extend(
            [
                "",
                f"ID: {component['id']}",
                f"Name: {component['name']}",
                f"Version: {component['version']}",
                f"License: {component['license']}",
                f"Admission: {component['admission']}",
                f"Source: {component['source']}",
                "Blockers: " + (", ".join(component["blockers"]) or "NONE"),
            ]
        )
        notices = component["noticeFiles"]
        if notices:
            lines.append("Notice files:")
            lines.extend(f"  - {item['path']} sha256:{item['sha256']}" for item in notices)
        else:
            lines.append("Notice files: NONE RECORDED")
    return ("\n".join(lines) + "\n").encode()


def input_receipts(subject: str) -> list[dict[str, Any]]:
    receipts = []
    for relative in INPUT_PATHS:
        data = git_bytes(subject, relative)
        subject_blob = git("rev-parse", f"{subject}:{relative}")
        working_blob = git("hash-object", "--path", relative, relative)
        if working_blob != subject_blob:
            raise ValueError(f"inventory input differs from subject commit: {relative}")
        receipts.append(
            {
                "path": relative,
                "gitBlob": subject_blob,
                "sha256": sha256(data),
                "sizeBytes": len(data),
            }
        )
    return receipts


def identifier_digest(values: list[str]) -> str:
    return sha256(("\n".join(sorted(values)) + "\n").encode())


def generate(subject: str, output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{40}", subject):
        raise ValueError("inventory subject must be a full lowercase Git SHA")
    git("cat-file", "-e", f"{subject}^{{commit}}")
    dependencies = validate_dependencies(DEPENDENCY_INVENTORY)["records"]
    toolchain = validate_toolchain()["records"]
    assets = validate_assets()["records"]
    input_records = dependency_components(dependencies)
    tool_records = toolchain_components(toolchain)
    asset_records = asset_components(assets)
    source_components = [*input_records, *tool_records, *asset_records]
    build_components = [
        *[record for record in input_records if record["role"] in BUILD_ROLES],
        *tool_records,
        *asset_records,
    ]
    tree = git("rev-parse", f"{subject}^{{tree}}")
    created = subject_timestamp(subject)
    documents = {
        "source.spdx.json": spdx_document(
            subject=subject,
            tree=tree,
            created=created,
            scope="source",
            components=source_components,
        ),
        "source.cdx.json": cdx_document(
            subject=subject,
            tree=tree,
            created=created,
            scope="source",
            components=source_components,
        ),
        "build.spdx.json": spdx_document(
            subject=subject,
            tree=tree,
            created=created,
            scope="build",
            components=build_components,
        ),
        "build.cdx.json": cdx_document(
            subject=subject,
            tree=tree,
            created=created,
            scope="build",
            components=build_components,
        ),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, bytes] = {name: canonical_bytes(value) for name, value in documents.items()}
    rendered["THIRD_PARTY_NOTICES.txt"] = notice_bundle(
        source_components, (ROOT / "NOTICE").read_text(encoding="utf-8")
    )
    for name, data in rendered.items():
        (output_dir / name).write_bytes(data)

    shipped = [
        record
        for record in input_records
        if record["distribution"] in SHIPPED_DISTRIBUTIONS
        and not record["role"].startswith("planned-")
    ]
    release_blockers = sorted(
        f"{record['admission']}:{record['id']}"
        for record in shipped
        if record["admission"] != "ADMITTED"
    )
    manifest = {
        "schema": SCHEMA,
        "subjectCommit": subject,
        "subjectTree": tree,
        "generatedAt": created,
        "generator": "scripts/generate_software_inventories.py",
        "formats": {"spdx": SPDX_VERSION, "cyclonedx": CYCLONEDX_VERSION},
        "releaseAdmission": "BLOCKED" if release_blockers else "ADMITTED",
        "releaseBlockers": release_blockers,
        "offlineKit": {
            "state": "CONTRACT_ONLY_NOT_ASSEMBLED",
            "assemblerOwner": "P1-T22A",
            "includedInventoryScopes": ["source", "build"],
        },
        "inputs": input_receipts(subject),
        "coverage": {
            "dependencyRecords": len(input_records),
            "dependencyRecordIdsSha256": identifier_digest(
                [record["id"] for record in input_records]
            ),
            "toolchainRecords": len(tool_records),
            "toolchainRecordIdsSha256": identifier_digest(
                [record["id"] for record in tool_records]
            ),
            "assetRecords": len(asset_records),
            "assetRecordIdsSha256": identifier_digest([record["id"] for record in asset_records]),
            "sourceComponents": len(source_components),
            "buildComponents": len(build_components),
            "currentShippedInputs": len(shipped),
        },
        "artifacts": [
            {"path": name, "sha256": sha256(data), "sizeBytes": len(data)}
            for name, data in sorted(rendered.items())
        ],
    }
    (output_dir / "manifest.json").write_bytes(canonical_bytes(manifest))
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    manifest = generate(args.subject, args.output)
    print(
        "software inventories generated: "
        f"{manifest['coverage']['sourceComponents']} source components; "
        f"releaseAdmission={manifest['releaseAdmission']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
