"""Inject bounded faults only into the disposable fullstack test database."""

import argparse
from datetime import UTC, datetime, timedelta

if __package__:
    from .seed_frontend_qa import qa_settings
else:
    from seed_frontend_qa import qa_settings
from sqlalchemy import select, update
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import AssessmentAdministration, LibraryShare, Session, Slide, User


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fault",
        choices=[
            "quota-full",
            "quota-clear",
            "expire-session",
            "expire-share",
            "expire-assessment-cooldown",
        ],
    )
    parser.add_argument("subject", nargs="?")
    args = parser.parse_args()
    settings = qa_settings()
    with session_factory(settings)() as database:
        if args.fault.startswith("quota-"):
            item = database.get(Slide, "qa-quota-reservation")
            if item is None:
                item = Slide(
                    id="qa-quota-reservation",
                    display_name="QA synthetic quota accounting",
                    original_filename="qa.ome.tif",
                    state=SlideState.FAILED,
                    source_bytes=0,
                    error_code="QA_METADATA_ONLY",
                )
                database.add(item)
            item.source_bytes = settings.storage_cap_bytes if args.fault == "quota-full" else 0
        elif args.fault == "expire-session":
            user = database.scalar(select(User).where(User.username == args.subject))
            if user is None:
                raise ValueError("Synthetic user not found")
            database.execute(
                update(Session)
                .where(Session.user_id == user.id)
                .values(expires_at=datetime.now(UTC) - timedelta(minutes=1))
            )
        elif args.fault == "expire-assessment-cooldown":
            database.execute(
                update(AssessmentAdministration)
                .where(AssessmentAdministration.status == "closed")
                .values(closes_at=datetime.now(UTC) - timedelta(seconds=121))
            )
        else:
            share = database.scalar(
                select(LibraryShare).where(LibraryShare.public_id == args.subject)
            )
            if share is None:
                raise ValueError("Synthetic share not found")
            share.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        database.commit()
    print(args.fault)


if __name__ == "__main__":
    main()
