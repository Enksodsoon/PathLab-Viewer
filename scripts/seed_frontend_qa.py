"""Seed metadata-only synthetic library rows in the disposable fullstack database."""

import json
import os
import sys
from pathlib import Path

from sqlalchemy import select
from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Slide


def qa_settings() -> Settings:
    if os.environ.get("PATHLAB_ENVIRONMENT") != "test":
        raise RuntimeError("Only the disposable fullstack launcher may seed QA records")
    settings = Settings()
    root = Path(settings.data_root).resolve().parent
    # Never accept an arbitrary configured database or a production target.
    expected = f"sqlite:///{(root / 'database.sqlite3').as_posix()}"
    if (
        not root.name.startswith("pathlab-fullstack-")
        or settings.database_url != expected
    ):
        raise RuntimeError("Only the disposable fullstack launcher may seed QA records")
    return settings


def main() -> None:
    settings = qa_settings()
    count = int(sys.argv[1])
    if count not in (0, 1, 100, 1000):
        raise ValueError("Unsupported QA fixture size")
    with session_factory(settings)() as database:
        existing = database.scalars(select(Slide).where(Slide.id.like("frontend-qa-%"))).all()
        if len(existing) > count:
            raise RuntimeError("Fixture sizes must increase; no fixture deletion during a campaign")
        for index in range(len(existing), count):
            database.add(Slide(
                id=f"frontend-qa-{index:04d}",
                display_name=f"Frontend QA {index:04d}",
                original_filename=f"synthetic-{index:04d}.ome.tif",
                source_bytes=0,
                state=SlideState.FAILED,
                error_code="QA_SYNTHETIC_METADATA",
                error_message="Metadata-only QA fixture; no imaging data",
                organ_site="Synthetic",
                stain="QA",
                tags=["frontend-qa"],
            ))
        database.commit()
    print(json.dumps({"seeded": count, "imagingData": False}))


if __name__ == "__main__":
    main()
