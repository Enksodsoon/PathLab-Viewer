from datetime import UTC, datetime, timedelta
from pathlib import Path

from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Job, Slide
from wsi_viewer.worker import recover_stale_jobs


def test_stale_worker_job_is_requeued(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    factory = session_factory(settings)
    with factory() as database:
        slide = Slide(
            display_name="Test",
            original_filename="x.ome.tif",
            source_bytes=1,
            state=SlideState.VALIDATING,
        )
        database.add(slide)
        database.flush()
        database.add(
            Job(
                slide_id=slide.id,
                status="running",
                heartbeat_at=datetime.now(UTC) - timedelta(minutes=10),
            )
        )
        database.commit()
    assert recover_stale_jobs(factory, stale_after=timedelta(minutes=5)) == 1
    with factory() as database:
        job = database.query(Job).one()
        assert job.status == "queued"
