from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from wsi_viewer import worker
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ClassroomSession, ClassroomSessionSlide, DesktopSyncEvent, Job, Slide
from wsi_viewer.storage import StorageLayout


def queued_deletion(tmp_path: Path):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'delete.sqlite3'}", data_root=tmp_path)
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(tmp_path)
    with factory() as database:
        slide = Slide(display_name="Synthetic", original_filename="source.ome.tif",
                      source_bytes=4, state=SlideState.DELETING)
        database.add(slide)
        database.flush()
        job = Job(slide_id=slide.id, kind="delete")
        database.add(job)
        database.commit()
        slide_id, public_id, job_id = slide.id, slide.public_id, job.id
    original = layout.for_slide(slide_id).original
    original.parent.mkdir(parents=True)
    original.write_bytes(b"data")
    return factory, layout, slide_id, public_id, job_id


def test_restricted_slide_deletion_preserves_files_and_stops_retry_loop(tmp_path: Path) -> None:
    factory, layout, slide_id, _, job_id = queued_deletion(tmp_path)
    with factory() as database:
        classroom = ClassroomSession(join_code_hash="synthetic-code",
                                     expires_at=datetime.now(UTC) + timedelta(days=1))
        database.add(classroom)
        database.flush()
        database.add(ClassroomSessionSlide(
            session_id=classroom.id, slide_id=slide_id, slide_position=0,
            published_asset_id="synthetic", asset_version="1", dzi_descriptor_path="slide.dzi",
            width=100, height=100, tile_size=512, tile_format="jpg", display_name="Synthetic",
        ))
        database.commit()
    assert worker.process_next(factory, layout)
    assert layout.for_slide(slide_id).original.read_bytes() == b"data"
    with factory() as database:
        assert database.get(Slide, slide_id) is not None
        job = database.get(Job, job_id)
        assert job is not None and job.status == "failed_terminal"
        assert job.failure_code == "SLIDE_IN_USE"
        assert database.query(DesktopSyncEvent).filter_by(operation="delete").count() == 0
    assert not worker.process_next(factory, layout)


def test_filesystem_failure_has_durable_cleanup_job_after_database_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    factory, layout, slide_id, public_id, job_id = queued_deletion(tmp_path)
    cleanup = worker.remove_slide
    def busy(*args):
        raise OSError("busy")

    monkeypatch.setattr(worker, "remove_slide", busy)
    assert worker.process_next(factory, layout)
    with factory() as database:
        assert database.get(Slide, slide_id) is None
        job = database.get(Job, job_id)
        assert job is not None and job.status == "retry_wait"
        assert job.checkpoint == {
            "phase": "delete-files", "slideId": slide_id, "publicId": public_id,
        }
        job.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
        database.commit()
    monkeypatch.setattr(worker, "remove_slide", cleanup)
    assert worker.process_next(factory, layout)
    assert not layout.for_slide(slide_id).original.exists()
    with factory() as database:
        assert database.get(Job, job_id).status == "succeeded"
        events = database.query(DesktopSyncEvent).filter_by(operation="delete").all()
        assert len(events) == 1
        assert (events[0].entity_type, events[0].entity_id) == ("slide", slide_id)


def test_slide_deletion_also_removes_individual_delivery(tmp_path: Path) -> None:
    factory, layout, _, public_id, _ = queued_deletion(tmp_path)
    delivery = layout.individual_delivery_for(public_id)
    delivery.mkdir(parents=True)
    (delivery / "slide.dzi").write_bytes(b"descriptor")
    assert worker.process_next(factory, layout)
    assert not delivery.exists()
