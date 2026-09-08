#!/usr/bin/env python3
"""Root-operated, exact-release, one-time SQLite to PostgreSQL maintenance cutover.

Run from a reviewed deployed release in a supervised service. This command keeps
Assessment disabled; its independent qualification and activation are separate.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
import subprocess
from contextlib import closing, nullcontext
from datetime import UTC, datetime
from pathlib import Path

from postgres_cutover_state import (
    MAINTENANCE,
    CutoverError,
    durable_write,
    postgres_environment,
    read_environment,
    record_authority,
    sqlite_rollback_allowed,
)

LIVE = Path("/opt/pathlab-viewer")
AUTHORITY = Path("/var/lib/pathlab-viewer/postgres-authority.json")
APP_SERVICES = ("caddy", "tusd", "worker", "classroom", "tile-service", "api")


def lock(path: Path) -> int:
    descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW)
    info = os.fstat(descriptor)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        os.close(descriptor)
        raise CutoverError("Unsafe maintenance lock")
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return descriptor


class Cutover:
    def __init__(self, sha: str) -> None:
        self.sha = sha
        self.scripts = LIVE / "deploy/scripts"
        self.env_file = LIVE / "deploy/.env"
        self.values = read_environment(self.env_file)
        self.original = self.env_file.read_bytes()
        self.data = Path(self.values.get("PATHLAB_DATA_DIR", ""))
        self.journal: Path | None = None
        self.watchdog = False
        self.maintenance = False
        self.environment_changed = False
        self.locks: list[int] = []
        self.token = secrets.token_urlsafe(48)

    def run(
        self,
        *command: str,
        timeout: int = 120,
        extra_env: dict[str, str] | None = None,
        input_file: Path | None = None,
    ) -> str:
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("PATHLAB_", "COMPOSE_"))
        }
        environment.update(PATHLAB_RELEASE_IMAGE_TAG=self.sha)
        environment.update(PATHLAB_CUTOVER_TOKEN=self.token)
        environment.update(extra_env or {})
        with input_file.open("rb") if input_file else nullcontext(subprocess.DEVNULL) as stream:
            result = subprocess.run(
                command,
                cwd=LIVE / "deploy",
                env=environment,
                stdin=stream,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        if self.journal:
            with (self.journal / "operations.log").open("a") as output:
                output.write(result.stdout + result.stderr)
        if result.returncode:
            raise CutoverError(f"Maintenance command failed: {Path(command[0]).name}")
        return result.stdout.strip()

    def compose(
        self,
        *args: str,
        timeout: int = 120,
        candidate: bool = False,
        input_file: Path | None = None,
    ) -> str:
        extra = (
            {"PATHLAB_COMPOSE_ENV_FILE": str(self.journal / "postgres.env")} if candidate else {}
        )
        return self.run(
            "bash",
            str(self.scripts / "compose-pathlab.sh"),
            *args,
            timeout=timeout,
            extra_env=extra,
            input_file=input_file,
        )

    def status(self, state: str) -> None:
        assert self.journal
        durable_write(
            self.journal / "status.json",
            json.dumps(
                {
                    "releaseSha": self.sha,
                    "state": state,
                    "sqliteRollbackAllowed": sqlite_rollback_allowed(AUTHORITY),
                    "updatedAt": datetime.now(UTC).isoformat(),
                }
            ).encode()
            + b"\n",
        )
        print(state, flush=True)

    def preflight(self) -> None:
        if os.geteuid() != 0 or not re.fullmatch(r"[0-9a-f]{40}", self.sha):
            raise CutoverError("Root and an exact release SHA are required")
        if (LIVE / ".pathlab-release").read_text().strip() != self.sha:
            raise CutoverError("Requested release is not deployed")
        if self.env_file.is_symlink() or self.data.resolve(strict=True) != self.data:
            raise CutoverError("Unsafe production paths")
        database_dir = self.data / "database"
        database = database_dir / "pathlab.sqlite3"
        if (
            database_dir.resolve(strict=True) != database_dir
            or database.is_symlink()
            or not database.is_file()
        ):
            raise CutoverError("Unsafe SQLite database path")
        if AUTHORITY.parent.is_symlink():
            raise CutoverError("Unsafe authority directory")
        if self.values.get("PATHLAB_DATABASE_ENGINE", "sqlite") != "sqlite":
            raise CutoverError("Production is not on SQLite")
        if self.values.get("PATHLAB_ASSESSMENT_ENABLED", "false") != "false":
            raise CutoverError("Assessment must remain disabled during database cutover")
        if not sqlite_rollback_allowed(AUTHORITY):
            raise CutoverError("An authority receipt already exists; use PostgreSQL recovery")
        if MAINTENANCE.exists() or MAINTENANCE.is_symlink():
            raise CutoverError("An interrupted cutover requires explicit recovery")
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.values.get("DOMAIN", "")):
            raise CutoverError("Invalid production domain")
        self.locks.append(lock(Path("/var/lock/pathlab-viewer-deploy.lock")))
        self.locks.append(lock(Path("/run/pathlab-capacity-controller.lock")))
        for name in ("pathlab-capacity-active.json", "pathlab-capacity-controller"):
            path = Path("/run") / name
            if path.exists() or path.is_symlink():
                raise CutoverError("Capacity work must be retired before cutover")
        self.run(
            "python3",
            str(self.scripts / "runtime_safety_manifest.py"),
            "verify-live",
            "--live-dir",
            str(LIVE),
            "--expected-sha",
            self.sha,
        )
        self.compose("exec", "-T", "api", "pathlab-admin", "deployment-check")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.journal = self.data / f".postgres-cutover-{stamp}-{self.sha[:12]}"
        self.journal.mkdir(mode=0o700)
        durable_write(self.journal / "sqlite.env", self.original)
        for name in ("source", "migration"):
            directory = self.journal / name
            directory.mkdir(mode=0o700)
            os.chown(directory, 10001, 10001)
        password = self.journal / "postgres-password"
        signing = self.journal / "backup-signing-key"
        durable_write(password, secrets.token_urlsafe(48).encode())
        # Host parent stays root-only. Docker binds this individual read-only
        # secret into containers with different unprivileged numeric users.
        password.chmod(0o444)
        durable_write(signing, secrets.token_urlsafe(48).encode())
        durable_write(
            self.journal / "postgres.env",
            postgres_environment(
                self.original.decode(),
                password_file=password,
                signing_key_file=signing,
            ).encode(),
        )
        self.compose("config", "--quiet", candidate=True)
        # Refuse reuse of any production PG volume, including an aborted copy.
        volumes = self.run(
            "docker",
            "volume",
            "ls",
            "--filter",
            "label=com.docker.compose.project=pathlab-viewer",
            "--format",
            "{{.Name}}",
        )
        if "pathlab-viewer_pathlab-postgres" in volumes.splitlines():
            raise CutoverError(
                "Production PostgreSQL volume already exists; explicit recovery required"
            )
        self.status("READY_FOR_MAINTENANCE")

    def migrate(self) -> None:
        assert self.journal
        result = subprocess.run(
            ["systemctl", "is-active", "--quiet", "pathlab-viewer-watchdog.timer"],
            check=False,
            timeout=30,
        )
        self.watchdog = result.returncode == 0
        MAINTENANCE.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        durable_write(
            MAINTENANCE,
            json.dumps(
                {
                    "token": self.token,
                    "releaseSha": self.sha,
                    "journal": str(self.journal),
                }
            ).encode(),
        )
        self.maintenance = True
        self.run(
            "systemctl", "stop", "pathlab-viewer-watchdog.timer", "pathlab-viewer-watchdog.service"
        )
        self.compose("stop", *APP_SERVICES, timeout=180)
        if self.compose("ps", "--status", "running", "--services"):
            raise CutoverError("Application writers did not stop")
        self.status("SQLITE_QUIESCED")
        source = self.journal / "source/source.sqlite3"
        with (
            closing(
                sqlite3.connect(
                    f"file:{self.data}/database/pathlab.sqlite3?mode=ro",
                    uri=True,
                )
            ) as old,
            closing(sqlite3.connect(source)) as snapshot,
        ):
            old.backup(snapshot)
            if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise CutoverError("SQLite snapshot integrity failed")
        os.chown(source, 10001, 10001)
        source.chmod(0o400)
        mounts = (
            "-v",
            f"{self.journal / 'source'}:/cutover-source:ro",
            "-v",
            f"{self.journal / 'migration'}:/cutover-evidence",
            "-e",
            f"PATHLAB_RELEASE_SHA={self.sha}",
        )
        self.compose(
            "up", "-d", "--no-build", "--wait", "--wait-timeout", "90", "postgres", candidate=True
        )
        self.compose(
            "run",
            "--rm",
            "--no-deps",
            *mounts,
            "api",
            "pathlab-admin",
            "postgres-cutover-source-check",
            "--source",
            "/cutover-source/source.sqlite3",
            candidate=True,
        )
        self.compose(
            "run",
            "--rm",
            "--no-deps",
            *mounts,
            "api",
            "pathlab-admin",
            "migrate-sqlite-to-postgres",
            "--source",
            "/cutover-source/source.sqlite3",
            "--target",
            "postgresql+psycopg://pathlab@postgres:5432/pathlab",
            "--target-password-file",
            "/run/secrets/pathlab-postgres-password",
            "--manifest",
            "/cutover-evidence/migration.json",
            "--verify",
            candidate=True,
            timeout=1800,
        )
        manifest = json.loads((self.journal / "migration/migration.json").read_text())
        payload = {key: value for key, value in manifest.items() if key != "signature"}
        expected = hmac.new(
            self.values["PATHLAB_SECRET_KEY"].encode(),
            json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not (
            hmac.compare_digest(expected, manifest["signature"]["value"])
            and manifest["releaseSha"] == self.sha
            and manifest["verified"]
            and manifest["source"]["unchanged"]
        ):
            raise CutoverError("Migration evidence is invalid")
        self.status("COPY_VERIFIED")
        # Persist the candidate environment for the existing backup wrappers.
        # Writers and watchdog remain stopped until recovery is verified.
        self.environment_changed = True
        durable_write(self.env_file, (self.journal / "postgres.env").read_bytes())
        backup_env = {
            "PATHLAB_DATA_DIR": str(self.data),
            "PATHLAB_BACKUP_DIR": str(self.journal / "backups"),
            "PATHLAB_RELEASE_SHA": self.sha,
        }
        backup = self.run(
            "bash",
            str(self.scripts / "backup-current-database.sh"),
            timeout=3600,
            extra_env=backup_env,
        ).splitlines()[-1]
        if not Path(backup).is_relative_to(self.journal / "backups"):
            raise CutoverError("Unexpected PostgreSQL backup destination")
        result = self.run(
            "bash",
            str(self.scripts / "verify-current-restore-drill.sh"),
            backup,
            timeout=3600,
            extra_env=backup_env,
        )
        receipt = json.loads(result.splitlines()[-1])
        if receipt["filesIntegrity"] != "restored" or receipt["databaseIntegrity"] != "restored":
            raise CutoverError("PostgreSQL restore verification failed")
        durable_write(self.journal / "restore.json", json.dumps(receipt).encode())
        restored_database = f"pathlab_cutover_restore_{self.sha[:12]}"
        self.compose("exec", "-T", "postgres", "createdb", "-U", "pathlab", restored_database)
        # Cleanup applies only after this invocation successfully created the
        # disposable database. Never drop a pre-existing database on failure.
        try:
            self.compose(
                "exec",
                "-T",
                "postgres",
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-acl",
                "-U",
                "pathlab",
                "-d",
                restored_database,
                input_file=Path(backup) / "database/pathlab.dump",
            )
            comparison = self.compose(
                "run",
                "--rm",
                "--no-deps",
                "-v",
                f"{self.scripts / 'verify_postgres_database_copy.py'}:/verify-copy.py:ro",
                "api",
                "python",
                "/verify-copy.py",
                "--restored-database",
                restored_database,
            )
            compared = json.loads(comparison.splitlines()[-1])
            if compared.get("allRowsAndPrimaryKeysMatch") is not True:
                raise CutoverError("Restored row reconciliation did not pass")
            durable_write(self.journal / "restored-rows.json", json.dumps(compared).encode())
        finally:
            self.compose("exec", "-T", "postgres", "dropdb", "-U", "pathlab", restored_database)
        self.status("RESTORE_VERIFIED")

    def commit(self) -> None:
        assert self.journal
        AUTHORITY.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Close SQLite rollback BEFORE starting any application process that
        # could accept writes, including background/startup writes.
        record_authority(AUTHORITY, self.sha)
        # Retain the original authority files as root-only evidence. The
        # application UID must no longer be able to open the old database.
        for suffix in ("", "-wal", "-shm"):
            original = self.data / "database" / f"pathlab.sqlite3{suffix}"
            if original.is_symlink():
                raise CutoverError("Unsafe retained SQLite authority file")
            if original.exists():
                os.chown(original, 0, 0)
                original.chmod(0o400)
        self.status("POSTGRES_AUTHORITY_COMMITTED")
        self.compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=240)
        for path in ("readyz", "livez"):
            self.run(
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--retry",
                "20",
                "--retry-all-errors",
                "--retry-delay",
                "2",
                "--max-time",
                "5",
                f"https://{self.values['DOMAIN']}/{path}",
                timeout=180,
            )
        expected = sorted((*APP_SERVICES, "postgres"))
        if sorted(self.compose("ps", "--status", "running", "--services").splitlines()) != expected:
            raise CutoverError("PostgreSQL service inventory is incomplete")
        MAINTENANCE.unlink()
        if self.watchdog:
            self.run("systemctl", "start", "pathlab-viewer-watchdog.timer")
        self.run(
            "python3",
            str(self.scripts / "runtime_safety_manifest.py"),
            "create",
            "--live-dir",
            str(LIVE),
            "--output",
            str(LIVE / ".pathlab-runtime-safety.json"),
        )
        self.status("SUCCEEDED")

    def recover(self) -> None:
        if not self.maintenance:
            return
        if sqlite_rollback_allowed(AUTHORITY):
            self.compose("stop", *APP_SERVICES, "postgres", candidate=True, timeout=180)
            if self.environment_changed:
                durable_write(self.env_file, self.original)
            self.compose("up", "-d", "--no-build", "--wait", "--wait-timeout", "180", timeout=240)
            MAINTENANCE.unlink(missing_ok=True)
            if self.watchdog:
                self.run("systemctl", "start", "pathlab-viewer-watchdog.timer")
            self.status("FAILED_SQLITE_RESTORED")
        else:
            if not MAINTENANCE.exists():
                durable_write(
                    MAINTENANCE,
                    json.dumps(
                        {
                            "token": self.token,
                            "releaseSha": self.sha,
                            "journal": str(self.journal),
                        }
                    ).encode(),
                )
            self.run(
                "systemctl",
                "stop",
                "pathlab-viewer-watchdog.timer",
                "pathlab-viewer-watchdog.service",
            )
            self.compose("stop", "caddy", "tusd", "worker", timeout=180)
            self.status("FAILED_POSTGRES_FORWARD_RECOVERY_REQUIRED")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-release", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    operation = Cutover(args.expected_release)
    try:
        operation.preflight()
        operation.migrate()
        operation.commit()
    except Exception:
        operation.recover()
        raise
    finally:
        for descriptor in operation.locks:
            os.close(descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
