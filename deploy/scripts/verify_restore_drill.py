#!/usr/bin/env python3
"""Restore a production backup into disposable storage and verify integrity."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from contextlib import closing
from pathlib import Path

EXPECTED_FILES = (Path("database/pathlab.sqlite3"), Path("files.tar.gz"))
EXPECTED_ROOTS = ["originals", "private", "public"]
CHUNK_BYTES = 1024 * 1024
SCRATCH_RESERVE_BYTES = 64 * 1024 * 1024


class RestoreDrillFailure(RuntimeError):
    pass


def _verify_checksums(backup: Path) -> None:
    manifest = backup / "SHA256SUMS"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RestoreDrillFailure("backup checksum manifest is missing") from error
    expected: dict[str, str] = {}
    for line in lines:
        parts = line.split()
        if len(parts) != 2:
            raise RestoreDrillFailure("backup checksum manifest is invalid")
        expected[parts[1].lstrip("*")] = parts[0]
    if set(expected) != {path.as_posix() for path in EXPECTED_FILES}:
        raise RestoreDrillFailure("backup checksum manifest is incomplete")
    for relative in EXPECTED_FILES:
        path = backup / relative
        try:
            digest_builder = hashlib.sha256()
            with path.open("rb") as source:
                while chunk := source.read(CHUNK_BYTES):
                    digest_builder.update(chunk)
            digest = digest_builder.hexdigest()
        except OSError as error:
            raise RestoreDrillFailure("backup payload is missing") from error
        if digest != expected[relative.as_posix()]:
            raise RestoreDrillFailure("backup checksum mismatch")


def verify_restore_drill(backup: Path, *, scratch_root: Path) -> dict[str, object]:
    backup = backup.resolve(strict=True)
    scratch_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    scratch_root = scratch_root.resolve(strict=True)
    _verify_checksums(backup)
    database_bytes = (backup / EXPECTED_FILES[0]).stat().st_size
    if shutil.disk_usage(scratch_root).free < database_bytes + SCRATCH_RESERVE_BYTES:
        raise RestoreDrillFailure("restore drill scratch space is insufficient")
    with tempfile.TemporaryDirectory(
        prefix="pathlab-restore-drill-", dir=scratch_root
    ) as temporary_name:
        restored = Path(temporary_name)
        restored_database = restored / "database" / "pathlab.sqlite3"
        restored_database.parent.mkdir()
        with (
            (backup / EXPECTED_FILES[0]).open("rb") as source,
            restored_database.open("wb") as destination,
        ):
            shutil.copyfileobj(source, destination, length=CHUNK_BYTES)
        try:
            with closing(
                sqlite3.connect(f"file:{restored_database.as_posix()}?mode=ro", uri=True)
            ) as database:
                integrity = database.execute("PRAGMA integrity_check").fetchone()
        except sqlite3.DatabaseError as error:
            raise RestoreDrillFailure("restored SQLite database is invalid") from error
        if integrity != ("ok",):
            raise RestoreDrillFailure("restored SQLite integrity check failed")

        roots: set[str] = set()
        sampled_roots: set[str] = set()
        try:
            with tarfile.open(backup / EXPECTED_FILES[1], "r:gz") as archive:
                for member in archive:
                    tarfile.data_filter(member, str(restored / "files"))
                    root = member.name.removeprefix("./").split("/", 1)[0]
                    if root not in EXPECTED_ROOTS:
                        raise RestoreDrillFailure("restored file archive has an invalid root")
                    roots.add(root)
                    if not member.isfile():
                        continue
                    archive_source = archive.extractfile(member)
                    if archive_source is None:
                        raise RestoreDrillFailure("restored file archive member is unreadable")
                    sample = (
                        restored / "files" / root / "representative.sample"
                        if root not in sampled_roots
                        else None
                    )
                    if sample is not None:
                        sample.parent.mkdir(parents=True, exist_ok=True)
                    remaining_sample = CHUNK_BYTES
                    with (
                        archive_source,
                        sample.open("wb")
                        if sample is not None
                        else open(os.devnull, "wb") as sample_output,
                    ):
                        while chunk := archive_source.read(CHUNK_BYTES):
                            if remaining_sample:
                                bounded = chunk[:remaining_sample]
                                sample_output.write(bounded)
                                remaining_sample -= len(bounded)
                    sampled_roots.add(root)
        except (OSError, tarfile.TarError) as error:
            raise RestoreDrillFailure("restored file archive is invalid") from error
        sorted_roots = sorted(roots)
        if sorted_roots != EXPECTED_ROOTS:
            raise RestoreDrillFailure("restored file archive roots are incomplete")
    return {"databaseIntegrity": "ok", "archiveRoots": EXPECTED_ROOTS}


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: verify_restore_drill.py /absolute/path/to/backup", file=sys.stderr)
        return 2
    backup = Path(sys.argv[1])
    if not backup.is_absolute():
        print("Restore drill requires an absolute backup path", file=sys.stderr)
        return 2
    try:
        approved_backup_root = Path("/srv/pathlab/data/backups").resolve(strict=True)
        if not backup.resolve(strict=True).is_relative_to(approved_backup_root):
            raise RestoreDrillFailure("backup path is not on the approved data volume")
        scratch_root = Path(
            os.environ.get("PATHLAB_RESTORE_DRILL_DIR", "/srv/pathlab/data/.restore-drill")
        )
        if scratch_root != Path("/srv/pathlab/data/.restore-drill"):
            raise RestoreDrillFailure("restore drill scratch path is not approved")
        scratch_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        result = verify_restore_drill(backup, scratch_root=scratch_root)
    except (OSError, RestoreDrillFailure) as error:
        print(f"Restore drill failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
