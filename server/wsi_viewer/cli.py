import argparse
import getpass
import sys
from pathlib import Path

from sqlalchemy import select

from .auth import issue_recovery_code, reset_password_by_cli
from .config import Settings
from .database import session_factory
from .models import ClassroomSession, Job, User
from .postgres_migration import PostgresMigrationError, migrate_sqlite_to_postgres
from .security import hash_password
from .storage import StorageLayout
from .storage_accounting import reconcile_storage


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
        ],
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from standard input for unattended deployment",
    )
    parser.add_argument("--source", type=Path, help="Closed SQLite source file")
    parser.add_argument("--target", help="Psycopg 3 PostgreSQL SQLAlchemy URL")
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
                select(Job.id).where(Job.status == "running").limit(1)
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
