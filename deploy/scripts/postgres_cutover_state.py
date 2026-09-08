"""Durable authority boundary for the one-time production PostgreSQL cutover."""

from __future__ import annotations

import hmac
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path


class CutoverError(RuntimeError):
    pass


MAINTENANCE = Path("/var/lib/pathlab-viewer/postgres-cutover-in-progress.json")


def require_compose_authorization(command: str, marker: Path = MAINTENANCE) -> None:
    if command not in {"up", "start", "restart", "run"}:
        return
    if not marker.exists() and not marker.is_symlink():
        return
    info = marker.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o600:
        raise CutoverError("Unsafe PostgreSQL maintenance marker")
    token = json.loads(marker.read_text()).get("token", "")
    supplied = os.environ.get("PATHLAB_CUTOVER_TOKEN", "")
    if not isinstance(token, str) or len(token) < 32 or not hmac.compare_digest(token, supplied):
        raise CutoverError("PostgreSQL cutover maintenance blocks application startup")


def read_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        name, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name):
            raise CutoverError("Unsupported production environment syntax")
        if name in values:
            raise CutoverError("Duplicate production environment entry")
        values[name] = value.strip().strip("\"'")
    return values


def postgres_environment(original: str, *, password_file: Path, signing_key_file: Path) -> str:
    updates = {
        "PATHLAB_DATABASE_ENGINE": "postgres",
        "PATHLAB_POSTGRES_DB": "pathlab",
        "PATHLAB_POSTGRES_USER": "pathlab",
        "PATHLAB_POSTGRES_PASSWORD_FILE": str(password_file),
        "PATHLAB_POSTGRES_BACKUP_SIGNING_KEY_FILE": str(signing_key_file),
    }
    lines = [line for line in original.splitlines() if line.partition("=")[0] not in updates]
    return "\n".join([*lines, *(f"{key}={value}" for key, value in updates.items()), ""])


def durable_write(path: Path, payload: bytes) -> None:
    if path.is_symlink():
        raise CutoverError("Refusing a symbolic-link state destination")
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def record_authority(path: Path, release_sha: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", release_sha):
        raise CutoverError("Exact release SHA is required")
    if path.exists() or path.is_symlink():
        raise CutoverError("PostgreSQL authority was already recorded")
    durable_write(
        path,
        json.dumps(
            {
                "schemaVersion": 1,
                "releaseSha": release_sha,
                "authority": "postgres",
                "sqliteRollbackAllowed": False,
            },
            sort_keys=True,
        ).encode()
        + b"\n",
    )


def sqlite_rollback_allowed(authority_path: Path) -> bool:
    # Any authority marker, even malformed or substituted, closes rollback.
    # Never interpret an unreadable receipt as permission to restore SQLite.
    return not authority_path.exists() and not authority_path.is_symlink()


if __name__ == "__main__":
    try:
        if len(sys.argv) != 2:
            raise CutoverError("Compose command is required")
        require_compose_authorization(sys.argv[1])
    except (CutoverError, OSError, ValueError) as error:
        raise SystemExit(str(error)) from error
