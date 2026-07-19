import argparse
import getpass

from sqlalchemy import select

from .config import Settings
from .database import create_schema, session_factory
from .models import User
from .security import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage the single PathLab administrator")
    parser.add_argument("command", choices=["create-admin", "reset-password"])
    parser.add_argument("--username", default="admin")
    args = parser.parse_args()
    password = getpass.getpass("Admin password: ")
    confirmation = getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("Passwords do not match")
    settings = Settings()
    create_schema(settings)
    with session_factory(settings)() as database:
        user = database.scalar(select(User).where(User.username == args.username))
        if args.command == "create-admin":
            if user is not None:
                raise SystemExit("Administrator already exists")
            database.add(User(username=args.username, password_hash=hash_password(password)))
        else:
            if user is None:
                raise SystemExit("Administrator does not exist")
            user.password_hash = hash_password(password)
        database.commit()
