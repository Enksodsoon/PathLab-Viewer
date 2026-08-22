import argparse
import getpass
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from sqlalchemy import inspect, select, text

from .auth import issue_recovery_code, reset_password_by_cli
from .config import Settings
from .database import session_factory
from .models import ClassroomSession, Job, RuntimeGuard, User
from .postgres_migration import (
    PostgresMigrationError,
    migrate_sqlite_to_postgres,
    verify_cutover_source,
)
from .runtime_protection import CLASSROOM_GUARD_ID, IDLE
from .security import hash_password
from .storage import StorageLayout
from .storage_accounting import reconcile_storage

RUNTIME_GUARD_PREDECESSOR_REVISION = "20260821_0023"


def _read_password(password_stdin: bool) -> str:
    if password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not password:
            raise SystemExit("Password must not be empty")
        return password

    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    return password


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage PathLab runtime and administration")
    parser.add_argument(
        "command",
        choices=[
            "create-admin",
            "reset-password",
            "issue-recovery-code",
            "deployment-check",
            "reconcile-storage",
            "migrate-sqlite-to-postgres",
            "postgres-cutover-source-check",
            "install-study-model",
        ],
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from standard input for unattended deployment",
    )
    parser.add_argument("--source", type=Path, help="Closed SQLite source file")
    parser.add_argument("--target", help="Psycopg 3 PostgreSQL SQLAlchemy URL")
    parser.add_argument(
        "--target-password-file",
        type=Path,
        help="Regular file containing the PostgreSQL password",
    )
    parser.add_argument("--manifest", type=Path, help="Private verification manifest path")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Require complete row, key, hash, and foreign-key verification",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = Settings()
    if args.command == "postgres-cutover-source-check":
        if args.source is None:
            raise SystemExit("--source is required")
        try:
            result = verify_cutover_source(args.source)
        except PostgresMigrationError as error:
            raise SystemExit(str(error)) from error
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return
    if args.command == "migrate-sqlite-to-postgres":
        if args.source is None or args.target is None:
            raise SystemExit("--source and --target are required")
        manifest = args.manifest or args.source.with_suffix(
            args.source.suffix + ".postgres-migration-manifest.json"
        )
        try:
            result = migrate_sqlite_to_postgres(
                source_path=args.source,
                target_url=args.target,
                target_password_file=args.target_password_file,
                manifest_path=manifest,
                signing_key=settings.secret_key,
                verify=args.verify,
            )
        except PostgresMigrationError as error:
            raise SystemExit(str(error)) from error
        print(
            f"Migration verified: tables={len(result['tables'])} manifest={manifest}"
        )
        return
    factory = session_factory(settings)
    if args.command == "install-study-model":
        if args.artifact is None or not args.artifact.is_file():
            raise SystemExit("--artifact must identify the TRACE-SIM ONNX file")
        manifest_path = Path(__file__).with_name("trace_sim_release.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload = args.artifact.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != manifest["artifactBytes"] or digest != manifest["artifactSha256"]:
            raise SystemExit(
                "TRACE-SIM artifact size or SHA-256 does not match the release manifest"
            )
        target_dir = settings.data_root / "private" / "study-models"
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / manifest["assetFile"]
        temporary = target.with_suffix(target.suffix + ".installing")
        with args.artifact.open("rb") as source, temporary.open("wb") as destination:
            shutil.copyfileobj(source, destination)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
        print(f"Installed {target.name} ({digest})")
        return
    if args.command == "reconcile-storage":
        summary = reconcile_storage(
            factory,
            StorageLayout(settings.data_root, settings.storage_cap_bytes),
        )
        print(
            "Storage reconciled: "
            f"slides={summary.slide_count} "
            f"derivatives={summary.derivative_count} "
            f"active={summary.active_reservation_count}"
        )
        return
    with factory() as database:
        if args.command == "deployment-check":
            running_job = database.scalar(
                select(Job.id)
                .where(Job.status.in_({"running", "checkpointing"}))
                .limit(1)
            )
            if running_job is not None:
                raise SystemExit("Deployment blocked: worker job is active")
            active_classroom = database.scalar(
                select(ClassroomSession.id)
                .where(ClassroomSession.status == "active")
                .limit(1)
            )
            if active_classroom is not None:
                raise SystemExit("Deployment blocked: a Classroom session is active")
            if inspect(database.get_bind()).has_table(RuntimeGuard.__tablename__):
                runtime_guard = database.get(RuntimeGuard, CLASSROOM_GUARD_ID)
                if runtime_guard is not None and runtime_guard.mode != IDLE:
                    raise SystemExit(
                        f"Deployment blocked: Classroom protection is {runtime_guard.mode}"
                    )
            else:
                revision = database.scalar(text("SELECT version_num FROM alembic_version"))
                if revision != RUNTIME_GUARD_PREDECESSOR_REVISION:
                    raise SystemExit(
                        "Deployment blocked: Classroom protection schema is unavailable"
                    )
            return
        user = database.scalar(select(User).where(User.username == args.username))
        if args.command == "issue-recovery-code":
            if user is None:
                raise SystemExit("Administrator does not exist")
            code = issue_recovery_code(database, user)
            database.commit()
            print(code)
            print(
                "Expires in 15 minutes. Enter only on the PathLab HTTPS recovery form.",
                file=sys.stderr,
            )
            return
        password = _read_password(args.password_stdin)
        if args.command == "create-admin":
            if user is not None:
                raise SystemExit("Administrator already exists")
            database.add(User(username=args.username, password_hash=hash_password(password)))
            database.commit()
            return
        if user is None:
            raise SystemExit("Administrator does not exist")
        reset_password_by_cli(database, user, password)
