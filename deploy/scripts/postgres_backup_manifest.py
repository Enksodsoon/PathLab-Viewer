#!/usr/bin/env python3
"""Create and verify private PostgreSQL backup evidence manifests."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import tarfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "pathlab-postgres-backup-manifest-v1"
EXPECTED_FILES = (Path("database/pathlab.dump"), Path("files.tar.gz"))
EXPECTED_ARCHIVE_ROOTS = ["originals", "private", "public"]
SHA_PATTERN = re.compile(r"[0-9a-f]{64}")
RELEASE_PATTERN = re.compile(r"[0-9a-f]{40}")
REVISION_PATTERN = re.compile(r"[0-9A-Za-z_]{1,128}")
DATABASE_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}")
CHUNK_BYTES = 1024 * 1024


class BackupManifestError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError as error:
        raise BackupManifestError(f"backup payload is unavailable: {path.name}") from error
    return digest.hexdigest()


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sign(payload: dict[str, Any], signing_key: str) -> str:
    if len(signing_key.encode("utf-8")) < 32:
        raise BackupManifestError("backup signing key must contain at least 32 bytes")
    return hmac.new(
        signing_key.encode("utf-8"), _canonical_json(payload), hashlib.sha256
    ).hexdigest()


def _archive_roots(path: Path) -> list[str]:
    roots: set[str] = set()
    try:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                tarfile.data_filter(member, "/restore-validation")
                root = member.name.removeprefix("./").split("/", 1)[0]
                if root not in EXPECTED_ARCHIVE_ROOTS:
                    raise BackupManifestError("private-file archive has an invalid root")
                roots.add(root)
    except (OSError, tarfile.TarError) as error:
        raise BackupManifestError("private-file archive is invalid") from error
    result = sorted(roots)
    if result != EXPECTED_ARCHIVE_ROOTS:
        raise BackupManifestError("private-file archive roots are incomplete")
    return result


def create_manifest(
    backup: Path,
    *,
    release_sha: str,
    schema_revision: str,
    database_name: str,
    signing_key: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    backup = backup.resolve(strict=True)
    if RELEASE_PATTERN.fullmatch(release_sha) is None:
        raise BackupManifestError("release SHA must contain exactly 40 lowercase hex characters")
    if REVISION_PATTERN.fullmatch(schema_revision) is None:
        raise BackupManifestError("schema revision is invalid")
    if DATABASE_PATTERN.fullmatch(database_name) is None:
        raise BackupManifestError("database name is invalid")
    roots = _archive_roots(backup / EXPECTED_FILES[1])
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "createdAt": created_at or datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "releaseSha": release_sha,
        "schemaRevision": schema_revision,
        "database": {
            "name": database_name,
            "format": "pg_dump-custom",
            "sha256": _sha256_file(backup / EXPECTED_FILES[0]),
        },
        "privateFiles": {
            "format": "tar-gzip",
            "roots": roots,
            "sha256": _sha256_file(backup / EXPECTED_FILES[1]),
        },
    }
    return {
        **payload,
        "signature": {
            "algorithm": "hmac-sha256",
            "value": _sign(payload, signing_key),
        },
    }


def verify_manifest(backup: Path, *, signing_key: str) -> dict[str, Any]:
    backup = backup.resolve(strict=True)
    try:
        manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BackupManifestError("backup manifest is missing or invalid") from error
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise BackupManifestError("backup manifest schema is unsupported")
    if set(manifest) != {
        "schema",
        "createdAt",
        "releaseSha",
        "schemaRevision",
        "database",
        "privateFiles",
        "signature",
    }:
        raise BackupManifestError("backup manifest fields are invalid")
    if not isinstance(manifest.get("createdAt"), str):
        raise BackupManifestError("backup creation timestamp is invalid")
    try:
        created_at = datetime.fromisoformat(manifest["createdAt"].replace("Z", "+00:00"))
    except ValueError as error:
        raise BackupManifestError("backup creation timestamp is invalid") from error
    if created_at.tzinfo is None:
        raise BackupManifestError("backup creation timestamp must include a timezone")
    if not isinstance(manifest.get("releaseSha"), str) or RELEASE_PATTERN.fullmatch(
        manifest["releaseSha"]
    ) is None:
        raise BackupManifestError("backup release SHA is invalid")
    if not isinstance(manifest.get("schemaRevision"), str) or REVISION_PATTERN.fullmatch(
        manifest["schemaRevision"]
    ) is None:
        raise BackupManifestError("backup schema revision is invalid")
    signature = manifest.pop("signature", None)
    if not isinstance(signature, dict) or signature.get("algorithm") != "hmac-sha256":
        raise BackupManifestError("backup manifest signature is missing or unsupported")
    supplied = signature.get("value")
    if not isinstance(supplied, str) or SHA_PATTERN.fullmatch(supplied) is None:
        raise BackupManifestError("backup manifest signature is invalid")
    expected = _sign(manifest, signing_key)
    if not hmac.compare_digest(supplied, expected):
        raise BackupManifestError("backup manifest signature does not match")
    database = manifest.get("database")
    private_files = manifest.get("privateFiles")
    if (
        not isinstance(database, dict)
        or set(database) != {"name", "format", "sha256"}
        or database.get("format") != "pg_dump-custom"
        or not isinstance(database.get("name"), str)
        or DATABASE_PATTERN.fullmatch(database["name"]) is None
        or not isinstance(database.get("sha256"), str)
        or SHA_PATTERN.fullmatch(database["sha256"]) is None
    ):
        raise BackupManifestError("database backup format is invalid")
    if (
        not isinstance(private_files, dict)
        or set(private_files) != {"format", "roots", "sha256"}
        or private_files.get("format") != "tar-gzip"
        or not isinstance(private_files.get("sha256"), str)
        or SHA_PATTERN.fullmatch(private_files["sha256"]) is None
    ):
        raise BackupManifestError("private-file backup format is invalid")
    if database.get("sha256") != _sha256_file(backup / EXPECTED_FILES[0]):
        raise BackupManifestError("database backup checksum mismatch")
    if private_files.get("sha256") != _sha256_file(backup / EXPECTED_FILES[1]):
        raise BackupManifestError("private-file backup checksum mismatch")
    if private_files.get("roots") != _archive_roots(backup / EXPECTED_FILES[1]):
        raise BackupManifestError("private-file archive roots do not match the manifest")
    return {**manifest, "signature": signature}


def _signing_key() -> str:
    key = os.getenv("PATHLAB_BACKUP_SIGNING_KEY", "")
    if not key:
        raise BackupManifestError("PATHLAB_BACKUP_SIGNING_KEY is required")
    return key


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("backup", type=Path)
    create.add_argument("--release-sha", required=True)
    create.add_argument("--schema-revision", required=True)
    create.add_argument("--database-name", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            manifest = create_manifest(
                args.backup,
                release_sha=args.release_sha,
                schema_revision=args.schema_revision,
                database_name=args.database_name,
                signing_key=_signing_key(),
            )
            destination = args.backup / "manifest.json"
            destination.write_bytes(_canonical_json(manifest) + b"\n")
            os.chmod(destination, 0o600)
        else:
            manifest = verify_manifest(args.backup, signing_key=_signing_key())
    except (OSError, BackupManifestError) as error:
        print(f"PostgreSQL backup evidence failed: {error}", file=sys.stderr)
        return 1
    print(_canonical_json(manifest).decode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
