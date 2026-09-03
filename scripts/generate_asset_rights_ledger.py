"""Generate the deterministic P0-T05 asset-rights ledger."""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import json
import re
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import unquote_to_bytes

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POLICY = ROOT / "docs" / "supply-chain" / "asset-rights-policy.json"
DEFAULT_INVENTORY = ROOT / "docs" / "supply-chain" / "dependency-inventory.json"
DEFAULT_OUTPUT = ROOT / "docs" / "supply-chain" / "ASSET_RIGHTS_LEDGER.json"

SVG_PATTERN = re.compile(r"<svg\b.*?</svg>", re.DOTALL | re.IGNORECASE)
DATA_PATTERN = re.compile(
    r"data:image/(?P<mime>[a-z0-9.+-]+)(?P<base64>;base64)?,(?P<data>[^\"')\s]+)",
    re.IGNORECASE,
)
IMPORT_PATTERN = re.compile(
    r"import\s*\{(?P<names>[^}]+)\}\s*from\s*['\"](?P<package>[^'\"]+)['\"]",
    re.DOTALL,
)
FONT_REFERENCE_PATTERN = re.compile(
    r"@fontsource-variable/(?P<package>[^/'\")]+)/files/(?P<file>[^'\")]+\.woff2)",
    re.IGNORECASE,
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_files(root: Path, relative_roots: list[str], ignored: set[str]):
    for relative_root in relative_roots:
        search_root = root / relative_root
        if not search_root.exists():
            continue
        for path in search_root.rglob("*"):
            if path.is_file() and not any(part in ignored for part in path.parts):
                yield path


def matching_metadata(policy: dict[str, Any], kind: str, locator: str) -> dict[str, Any]:
    matches = [
        rule["metadata"]
        for rule in policy["rules"]
        if rule["kind"] == kind and fnmatch.fnmatchcase(locator, rule["locatorGlob"])
    ]
    if len(matches) != 1:
        raise ValueError(f"{locator}: expected exactly one rights rule, found {len(matches)}")
    return matches[0]


def make_record(
    policy: dict[str, Any], kind: str, locator: str, content: bytes, **extra: Any
) -> dict[str, Any]:
    return {
        "id": f"asset:{kind}:{locator}",
        "kind": kind,
        "locator": locator,
        "contentSha256": sha256(content),
        "sizeBytes": len(content),
        **matching_metadata(policy, kind, locator),
        **extra,
    }


def discover_repository_records(root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    ignored = set(policy["ignoredDirectories"])
    governed = set(policy["governedFileExtensions"])
    records: list[dict[str, Any]] = []
    governed_files = [
        path
        for path in iter_files(root, policy["governedRoots"], ignored)
        if path.suffix.lower() in governed
    ]
    for path in sorted(governed_files):
        locator = path.relative_to(root).as_posix()
        content = path.read_bytes()
        records.append(make_record(policy, "repository-file", locator, content))
        if path.suffix.lower() not in policy["archiveExtensions"]:
            continue
        with zipfile.ZipFile(path) as archive:
            members = [
                name
                for name in archive.namelist()
                if Path(name).suffix.lower() in policy["archiveMemberExtensions"]
            ]
            for name in sorted(members):
                member = archive.read(name)
                member_locator = f"{locator}!{name}"
                records.append(
                    make_record(
                        policy,
                        "archive-member",
                        member_locator,
                        member,
                        container=locator,
                    )
                )
    return records


def discover_inline_records(root: Path, policy: dict[str, Any]) -> list[dict[str, Any]]:
    ignored = set(policy["ignoredDirectories"])
    extensions = set(policy["inlineSourceExtensions"])
    records: list[dict[str, Any]] = []
    svg_files = iter_files(root, policy["inlineSvgRoots"], ignored)
    for path in sorted(path for path in svg_files if path.suffix.lower() in extensions):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        for index, match in enumerate(SVG_PATTERN.finditer(text), start=1):
            locator = f"{relative}#inline-svg-{index}"
            records.append(make_record(policy, "inline-svg", locator, match.group().encode()))

    data_files = iter_files(root, policy["inlineDataRoots"], ignored)
    for path in sorted(path for path in data_files if path.suffix.lower() in extensions):
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(root).as_posix()
        for index, match in enumerate(DATA_PATTERN.finditer(text), start=1):
            raw = match.group("data")
            content = base64.b64decode(raw) if match.group("base64") else unquote_to_bytes(raw)
            locator = f"{relative}#data-image-{index}"
            records.append(
                make_record(
                    policy,
                    "inline-data",
                    locator,
                    content,
                    mediaType=f"image/{match.group('mime').lower()}",
                )
            )
    return records


def dependency_record(inventory: dict[str, Any], dependency_id: str) -> dict[str, Any]:
    matches = [record for record in inventory["records"] if record["id"] == dependency_id]
    if len(matches) != 1:
        raise ValueError(f"{dependency_id}: expected exactly one dependency inventory record")
    return matches[0]


def package_record(root: Path, config: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    path = root / config["installedPath"]
    if not path.is_file():
        raise ValueError(
            f"install dependencies before generation; missing {config['installedPath']}"
        )
    dependency = dependency_record(inventory, config["dependencyId"])
    metadata = {key: value for key, value in config.items() if key not in {"installedPath"}}
    return {
        "id": f"asset:{config['kind']}:{config['locator']}",
        **metadata,
        "contentSha256": sha256(path.read_bytes()),
        "sizeBytes": path.stat().st_size,
        "sourceArtifact": dependency["artifact"],
        "sourceArtifactChecksum": dependency["checksum"],
        "sourceNoticeHashes": dependency["noticeFiles"],
    }


def imported_icons(root: Path, config: dict[str, Any]) -> list[str]:
    names: set[str] = set()
    for path in iter_files(root, config["scanRoots"], {"node_modules", "dist"}):
        if path.suffix.lower() not in {".ts", ".tsx"}:
            continue
        text = path.read_text(encoding="utf-8")
        for match in IMPORT_PATTERN.finditer(text):
            if match.group("package") != config["importSpecifier"]:
                continue
            for raw_name in match.group("names").split(","):
                name = raw_name.strip()
                if not name or name.startswith("type "):
                    continue
                names.add(re.split(r"\s+as\s+", name, maxsplit=1)[0])
    return sorted(names)


def referenced_package_fonts(root: Path, policy: dict[str, Any]) -> list[str]:
    references: set[str] = set()
    ignored = set(policy["ignoredDirectories"])
    extensions = set(policy["inlineSourceExtensions"])
    files = iter_files(root, policy["inlineDataRoots"], ignored)
    for path in (path for path in files if path.suffix.lower() in extensions):
        text = path.read_text(encoding="utf-8")
        for match in FONT_REFERENCE_PATTERN.finditer(text):
            references.add(
                "apps/web/node_modules/@fontsource-variable/"
                f"{match.group('package')}/files/{match.group('file')}"
            )
    return sorted(references)


def icon_set_record(
    root: Path, config: dict[str, Any], inventory: dict[str, Any]
) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    for name in imported_icons(root, config):
        relative_path = config["installedDefinitions"].format(name=name)
        path = root / relative_path
        if not path.is_file():
            raise ValueError(f"install dependencies before generation; missing {relative_path}")
        assets.append({"name": name, "contentSha256": sha256(path.read_bytes())})
    canonical = json.dumps(assets, separators=(",", ":"), sort_keys=True).encode()
    dependency = dependency_record(inventory, config["dependencyId"])
    metadata = {
        key: value
        for key, value in config.items()
        if key not in {"installedDefinitions", "scanRoots", "importSpecifier"}
    }
    return {
        "id": f"asset:{config['kind']}:{config['locator']}",
        **metadata,
        "contentSha256": sha256(canonical),
        "sizeBytes": sum(
            (root / config["installedDefinitions"].format(name=item["name"])).stat().st_size
            for item in assets
        ),
        "embeddedAssets": assets,
        "sourceArtifact": dependency["artifact"],
        "sourceArtifactChecksum": dependency["checksum"],
        "sourceNoticeHashes": dependency["noticeFiles"],
    }


def generate(
    root: Path, policy: dict[str, Any], inventory: dict[str, Any], subject: str
) -> dict[str, Any]:
    configured_fonts = sorted(item["installedPath"] for item in policy["packageAssets"])
    referenced_fonts = referenced_package_fonts(root, policy)
    if configured_fonts != referenced_fonts:
        raise ValueError("package font policy does not match shipped font references")
    records = discover_repository_records(root, policy)
    records.extend(discover_inline_records(root, policy))
    records.extend(package_record(root, item, inventory) for item in policy["packageAssets"])
    records.append(icon_set_record(root, policy["packageIconSet"], inventory))
    records.sort(key=lambda record: record["id"])
    blocked = [
        record["id"] for record in records if record["releaseDisposition"] == "BLOCKED_RELEASE"
    ]
    return {
        "schemaVersion": 1,
        "subjectCommit": subject,
        "policySha256": sha256(json.dumps(policy, separators=(",", ":"), sort_keys=True).encode()),
        "releaseAdmission": "BLOCKED" if blocked else "ADMITTED",
        "releaseBlockers": blocked,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subject", required=True, help="exact audited Git commit")
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    ledger = generate(ROOT, load_json(args.policy), load_json(args.inventory), args.subject)
    args.output.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"asset rights ledger generated: {len(ledger['records'])} records; "
        f"release {ledger['releaseAdmission']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
