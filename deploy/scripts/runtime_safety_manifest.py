#!/usr/bin/env python3
"""Create and verify the exact deployed runtime used by capacity control."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
REVISION = re.compile(r"^[0-9A-Za-z_]{1,128}$")
DOMAIN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")
SERVICE = re.compile(r"^[a-z][a-z0-9-]{0,63}$")
CORE_SERVICES = {"api", "caddy", "classroom", "tile-service", "tusd", "worker"}
MANIFEST_NAME = ".pathlab-runtime-safety.json"


class RuntimeSafetyError(RuntimeError):
    pass


def _run(*command: str, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise RuntimeSafetyError("runtime inspection command failed") from error


def _canonical(value: dict[str, Any]) -> bytes:
    unsigned = {key: item for key, item in value.items() if key != "manifestDigest"}
    return json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _env(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise RuntimeSafetyError("runtime environment is unavailable") from error
    result: dict[str, str] = {}
    for line in lines:
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        result[name] = value.strip().strip("\"'")
    return result


def _boolean(value: str, name: str) -> bool:
    if value not in {"true", "false"}:
        raise RuntimeSafetyError(f"{name} is invalid")
    return value == "true"


def _services(raw: str) -> list[str]:
    values = sorted({line.strip() for line in raw.splitlines() if line.strip()})
    if not values or any(SERVICE.fullmatch(value) is None for value in values):
        raise RuntimeSafetyError("runtime service inventory is invalid")
    return values


def _compose(live_dir: Path, *arguments: str) -> str:
    script = live_dir / "deploy" / "scripts" / "compose-pathlab.sh"
    return _run("bash", str(script), *arguments, cwd=live_dir / "deploy")


def inspect_runtime(live_dir: Path) -> dict[str, Any]:
    release_path = live_dir / ".pathlab-release"
    try:
        release_sha = release_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeSafetyError("runtime release marker is unavailable") from error
    if SHA.fullmatch(release_sha) is None:
        raise RuntimeSafetyError("runtime release marker is invalid")
    environment = _env(live_dir / "deploy" / ".env")
    try:
        capacity = int(environment.get("PATHLAB_CLASSROOM_MAX_PARTICIPANTS", "300"))
    except ValueError as error:
        raise RuntimeSafetyError("Classroom capacity is invalid") from error
    if capacity < 1 or capacity > 2000:
        raise RuntimeSafetyError("Classroom capacity is invalid")
    classroom_enabled = _boolean(
        environment.get("PATHLAB_PRODUCTION_CLASSROOM_ENABLED", "false"),
        "Classroom production state",
    )
    annotations_enabled = _boolean(
        environment.get("PATHLAB_ANNOTATIONS_ENABLED", "false"),
        "annotation state",
    )
    database_engine = _compose(live_dir, "engine")
    if database_engine not in {"sqlite", "postgres"}:
        raise RuntimeSafetyError("runtime database engine is invalid")
    compose_config = _compose(live_dir, "config")
    configured_services = _services(_compose(live_dir, "config", "--services"))
    running_services = _services(_compose(live_dir, "ps", "--status", "running", "--services"))
    schema_revision = _compose(
        live_dir,
        "exec",
        "-T",
        "api",
        "python",
        "-c",
        "from wsi_viewer.readiness import ALEMBIC_HEAD; print(ALEMBIC_HEAD)",
    )
    if REVISION.fullmatch(schema_revision) is None:
        raise RuntimeSafetyError("runtime schema revision is invalid")
    watchdog_active = (
        subprocess.run(
            ["systemctl", "is-active", "--quiet", "pathlab-viewer-watchdog.timer"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode
        == 0
    )
    return {
        "releaseSha": release_sha,
        "schemaRevision": schema_revision,
        "databaseEngine": database_engine,
        "services": configured_services,
        "runningServices": running_services,
        "composeConfigDigest": hashlib.sha256(compose_config.encode()).hexdigest(),
        "classroomEnabled": classroom_enabled,
        "safeCapacity": capacity,
        "annotationsEnabled": annotations_enabled,
        "watchdogExpected": watchdog_active,
        "domain": environment.get("DOMAIN", ""),
    }


def build_manifest(runtime: dict[str, Any], *, created_at: str | None = None) -> dict[str, Any]:
    services = runtime["services"]
    if runtime["runningServices"] != services:
        raise RuntimeSafetyError("configured and running service topology differ")
    if not CORE_SERVICES.issubset(services):
        raise RuntimeSafetyError("runtime is missing a required production service")
    if (runtime["databaseEngine"] == "postgres") != ("postgres" in services):
        raise RuntimeSafetyError("runtime database service does not match its engine")
    manifest = {
        "schemaVersion": 1,
        "releaseSha": runtime["releaseSha"],
        "schemaRevision": runtime["schemaRevision"],
        "databaseEngine": runtime["databaseEngine"],
        "services": services,
        "composeConfigDigest": runtime["composeConfigDigest"],
        "classroomEnabled": runtime["classroomEnabled"],
        "safeCapacity": runtime["safeCapacity"],
        "annotationsEnabled": runtime["annotationsEnabled"],
        "watchdogExpected": runtime["watchdogExpected"],
        "createdAt": created_at or datetime.now(UTC).isoformat(),
    }
    manifest["manifestDigest"] = _digest(manifest)
    validate_manifest(manifest)
    return manifest


def validate_manifest(value: object) -> dict[str, Any]:
    required = {
        "schemaVersion",
        "releaseSha",
        "schemaRevision",
        "databaseEngine",
        "services",
        "composeConfigDigest",
        "classroomEnabled",
        "safeCapacity",
        "annotationsEnabled",
        "watchdogExpected",
        "createdAt",
        "manifestDigest",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RuntimeSafetyError("runtime safety manifest fields are invalid")
    services = value["services"]
    services_valid = (
        isinstance(services, list)
        and all(isinstance(item, str) and SERVICE.fullmatch(item) for item in services)
        and services == sorted(set(services))
        and CORE_SERVICES.issubset(services)
    )
    try:
        datetime.fromisoformat(str(value["createdAt"]).replace("Z", "+00:00"))
        created_at_valid = True
    except ValueError:
        created_at_valid = False
    if (
        value["schemaVersion"] != 1
        or SHA.fullmatch(str(value["releaseSha"])) is None
        or REVISION.fullmatch(str(value["schemaRevision"])) is None
        or value["databaseEngine"] not in {"sqlite", "postgres"}
        or not services_valid
        or DIGEST.fullmatch(str(value["composeConfigDigest"])) is None
        or not isinstance(value["classroomEnabled"], bool)
        or not isinstance(value["safeCapacity"], int)
        or not 1 <= value["safeCapacity"] <= 2000
        or not isinstance(value["annotationsEnabled"], bool)
        or not isinstance(value["watchdogExpected"], bool)
        or not isinstance(value["createdAt"], str)
        or not created_at_valid
        or DIGEST.fullmatch(str(value["manifestDigest"])) is None
        or not hmac_compare(str(value["manifestDigest"]), _digest(value))
        or (value["databaseEngine"] == "postgres") != ("postgres" in services)
    ):
        raise RuntimeSafetyError("runtime safety manifest is invalid")
    return value


def hmac_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RuntimeSafetyError("runtime safety manifest is not a regular file")
        if os.name == "posix" and stat.S_IMODE(info.st_mode) != 0o600:
            raise RuntimeSafetyError("runtime safety manifest permissions are unsafe")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeSafetyError("runtime safety manifest is unavailable") from error
    return validate_manifest(value)


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _probe(domain: str) -> bool:
    if DOMAIN.fullmatch(domain) is None:
        raise RuntimeSafetyError("runtime domain is invalid")
    for endpoint in ("readyz", "livez"):
        _run(
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--max-time",
            "10",
            "--resolve",
            f"{domain}:443:127.0.0.1",
            f"https://{domain}/{endpoint}",
        )
    return True


def verify_live(
    live_dir: Path, expected_sha: str, expected_digest: str | None, *, require_safe: bool
) -> dict[str, Any]:
    if SHA.fullmatch(expected_sha) is None:
        raise RuntimeSafetyError("expected runtime release is invalid")
    if expected_digest is not None and DIGEST.fullmatch(expected_digest) is None:
        raise RuntimeSafetyError("expected runtime manifest digest is invalid")
    manifest = load_manifest(live_dir / MANIFEST_NAME)
    runtime = inspect_runtime(live_dir)
    if expected_digest is not None and not hmac_compare(
        manifest["manifestDigest"], expected_digest
    ):
        raise RuntimeSafetyError("runtime manifest binding does not match")
    for name in (
        "releaseSha",
        "schemaRevision",
        "databaseEngine",
        "services",
        "composeConfigDigest",
        "classroomEnabled",
        "safeCapacity",
        "annotationsEnabled",
        "watchdogExpected",
    ):
        if runtime[name] != manifest[name]:
            raise RuntimeSafetyError(f"runtime {name} does not match its deployment manifest")
    if runtime["runningServices"] != manifest["services"]:
        raise RuntimeSafetyError("running services do not match the deployment manifest")
    if manifest["releaseSha"] != expected_sha:
        raise RuntimeSafetyError("runtime release does not match the expected SHA")
    if require_safe and not (
        manifest["classroomEnabled"] is True
        and manifest["safeCapacity"] == 300
        and manifest["annotationsEnabled"] is False
        and manifest["watchdogExpected"] is True
    ):
        raise RuntimeSafetyError("runtime is not at the approved Classroom safety floor")
    ready = _probe(runtime["domain"])
    return {
        "releaseSha": manifest["releaseSha"],
        "expectedSha": expected_sha,
        "releaseExact": True,
        "schemaRevision": manifest["schemaRevision"],
        "databaseEngine": manifest["databaseEngine"],
        "runtimeManifestDigest": manifest["manifestDigest"],
        "services": manifest["services"],
        "servicesExact": True,
        "serviceCount": len(manifest["services"]),
        "ready": ready,
        "watchdogExpected": manifest["watchdogExpected"],
        "watchdogActive": runtime["watchdogExpected"],
        "classroomEnabled": manifest["classroomEnabled"],
        "finalCapacity": manifest["safeCapacity"],
        "annotationsEnabled": manifest["annotationsEnabled"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--live-dir", type=Path, required=True)
    create.add_argument("--output", type=Path)
    verify = commands.add_parser("verify-live")
    verify.add_argument("--live-dir", type=Path, required=True)
    verify.add_argument("--expected-sha", required=True)
    verify.add_argument("--manifest-digest")
    verify.add_argument("--require-safe", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        output = args.output or args.live_dir / MANIFEST_NAME
        manifest = build_manifest(inspect_runtime(args.live_dir))
        _write(output, manifest)
        print(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    else:
        print(
            json.dumps(
                verify_live(
                    args.live_dir,
                    args.expected_sha,
                    args.manifest_digest,
                    require_safe=args.require_safe,
                ),
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeSafetyError as error:
        raise SystemExit(str(error)) from error
