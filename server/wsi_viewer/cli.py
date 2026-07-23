import argparse
import getpass
import sys

from sqlalchemy import select

from .auth import issue_recovery_code, reset_password_by_cli
from .config import Settings
from .database import session_factory
from .models import Job, User
from .security import hash_password


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
    parser = argparse.ArgumentParser(description="Manage the single PathLab administrator")
    parser.add_argument(
        "command",
        choices=[
            "create-admin",
            "reset-password",
            "issue-recovery-code",
            "deployment-check",
        ],
    )
    parser.add_argument("--username", default="admin")
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="Read one password line from standard input for unattended deployment",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    settings = Settings()
    with session_factory(settings)() as database:
        if args.command == "deployment-check":
            running_job = database.scalar(
                select(Job.id).where(Job.status == "running").limit(1)
            )
            if running_job is not None:
                raise SystemExit("Deployment blocked: worker job is active")
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
