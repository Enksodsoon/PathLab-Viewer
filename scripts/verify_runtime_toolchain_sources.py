"""Download immutable P0-T03A sources and verify their recorded SHA-256 values."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.validate_runtime_toolchain_admission import DEFAULT_MANIFEST, validate
except ModuleNotFoundError:  # Direct `python scripts/...` execution.
    from validate_runtime_toolchain_admission import DEFAULT_MANIFEST, validate


def digest_download(url: str, destination: Path) -> str:
    if destination.is_file():
        return hashlib.sha256(destination.read_bytes()).hexdigest()
    request = urllib.request.Request(url, headers={"User-Agent": "PathLab-P0-T03A/1"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    return digest


def verify_sources(
    manifest_path: Path, cache: Path, selected: set[str] | None = None
) -> dict[str, Any]:
    manifest = validate(manifest_path, receipt_path=None)
    results: list[dict[str, str]] = []
    for record in manifest["records"]:
        if selected and record["id"] not in selected:
            continue
        artifact_path = cache / record["mirrorPath"]
        actual = digest_download(record["artifact"], artifact_path)
        if actual != record["sha256"]:
            raise ValueError(f"{record['id']} official artifact sha256 mismatch")
        license_name = record["id"].replace(":", "_").replace("/", "_")
        license_path = cache / "offline" / "notices" / f"{license_name}.LICENSE"
        license_actual = digest_download(record["licenseArtifact"], license_path)
        if license_actual != record["licenseSha256"]:
            raise ValueError(f"{record['id']} official license sha256 mismatch")
        provenance_name = record["id"].replace(":", "_").replace("/", "_")
        provenance_path = cache / "offline" / "provenance" / f"{provenance_name}.evidence"
        provenance_actual = digest_download(record["provenance"], provenance_path)
        results.append(
            {
                "id": record["id"],
                "artifactSha256": actual,
                "licenseSha256": license_actual,
                "provenanceSha256": provenance_actual,
            }
        )
    return {
        "schema": "pathlab.runtime-toolchain-source-verification/1",
        "subjectCommit": manifest["subjectCommit"],
        "verifiedAt": datetime.now(UTC).isoformat(),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--id", action="append", dest="ids")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    receipt = verify_sources(args.manifest, args.cache, set(args.ids) if args.ids else None)
    if args.receipt:
        args.receipt.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(
        "official source verification PASS: "
        f"{len(receipt['results'])} artifacts, licenses, and provenance records"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
