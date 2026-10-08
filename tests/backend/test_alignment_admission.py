from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from wsi_viewer import worker
from wsi_viewer.alignment_processes import AlignmentContainmentLost
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout


def _database(tmp_path):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'jobs.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    return session_factory(settings), StorageLayout(settings.data_root)


@pytest.mark.parametrize("active_kind", ["align", "align_benchmark"])
@pytest.mark.parametrize("active_status", ["running", "checkpointing"])
@pytest.mark.parametrize("role", [None, {"align", "align_benchmark"}])
def test_any_active_alignment_blocks_another_alignment_claim(
    tmp_path, active_kind, active_status, role
):
    factory, layout = _database(tmp_path)
    with factory() as database:
        active = Job(kind=active_kind, status=active_status)
        queued = Job(kind="align_benchmark", status="queued")
        database.add_all([active, queued])
        database.commit()
        active_id, queued_id = active.id, queued.id
    assert (
        worker.process_next(
            factory, layout, include_kinds=role, exclusive_alignment=True if role else None
        )
        is False
    )
    with factory() as database:
        assert database.get(Job, active_id).status == active_status
        assert database.get(Job, queued_id).status == "queued"
        assert database.get(Job, queued_id).attempts == 0


@pytest.mark.parametrize("role", [None, {"align", "align_benchmark"}])
def test_two_workers_cannot_run_alignment_at_the_same_time(tmp_path, monkeypatch, role):
    factory, layout = _database(tmp_path)
    with factory() as database:
        for name in ("r", "m"):
            database.add(
                Slide(
                    id=name,
                    public_id="p-" + name,
                    display_name=name,
                    original_filename=name + ".tif",
                    source_bytes=1,
                    sha256=name,
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={"width": 100, "height": 100},
                )
            )
        database.flush()
        comparison = ComparisonSet(
            name="Admission",
            reference_slide_id="r",
            member_slide_ids=["r", "m"],
            source_versions={"r": "r", "m": "m"},
            registrations={},
            status="queued",
        )
        database.add(comparison)
        database.flush()
        for _ in range(2):
            database.add(
                Job(
                    slide_id="m",
                    kind="align_benchmark",
                    resource_limits={},
                    checkpoint={
                        "comparisonSetId": comparison.id,
                        "memberId": "m",
                        "setVersion": comparison.version,
                        "phase": "refinement",
                    },
                )
            )
        database.commit()
    started, release = Event(), Event()
    calls = []

    def held_registration(*args, **kwargs):
        calls.append(True)
        started.set()
        assert release.wait(10), "test registration was not released"
        return {"status": "approximate", "confidence": 0.1, "inlierCount": 0, "evidence": {}}

    monkeypatch.setattr(worker, "_run_alignment_bounded", held_registration)
    options = {"include_kinds": role, "exclusive_alignment": True if role else None}
    with ThreadPoolExecutor(max_workers=2) as threads:
        first = threads.submit(worker.process_next, factory, layout, **options)
        try:
            assert started.wait(5)
            second = threads.submit(worker.process_next, factory, layout, **options)
            assert second.result(timeout=3) is False
            assert len(calls) == 1
        finally:
            release.set()
        assert first.result(timeout=5) is True
    with factory() as database:
        statuses = [job.status for job in database.query(Job).all()]
        assert statuses.count("queued") == 1
        assert statuses.count("succeeded") == 1


def test_containment_loss_quarantines_job_and_blocks_other_workers_and_recovery(
    tmp_path, monkeypatch
):
    factory, layout = _database(tmp_path)
    saved = {"status": "ready", "provenance": "manual", "saved": True}
    with factory() as database:
        for name in ("r", "m"):
            database.add(
                Slide(
                    id=name,
                    public_id="p-" + name,
                    display_name=name,
                    original_filename=name + ".tif",
                    source_bytes=1,
                    sha256=name,
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={"width": 100, "height": 100},
                )
            )
        database.flush()
        comparison = ComparisonSet(
            name="Quarantine",
            reference_slide_id="r",
            member_slide_ids=["r", "m"],
            source_versions={"r": "r", "m": "m"},
            registrations={"m": saved},
            status="queued",
        )
        database.add(comparison)
        database.flush()
        comparison_id = comparison.id
        for _ in range(2):
            database.add(
                Job(
                    slide_id="m",
                    kind="align_benchmark",
                    resource_limits={},
                    checkpoint={
                        "comparisonSetId": comparison.id,
                        "memberId": "m",
                        "setVersion": comparison.version,
                        "phase": "refinement",
                    },
                )
            )
        database.commit()
    calls = []

    def unproved_cleanup(*_args, **_kwargs):
        calls.append(True)
        raise AlignmentContainmentLost("test cleanup cannot prove terminal descendants", {})

    monkeypatch.setattr(worker, "_run_alignment_bounded", unproved_cleanup)
    with pytest.raises(AlignmentContainmentLost):
        worker.process_next(factory, layout)
    assert worker.recover_stale_jobs(factory) == 0
    assert worker.process_next(factory, layout) is False
    assert (
        worker.process_next(
            factory, layout, include_kinds={"align", "align_benchmark"}, exclusive_alignment=True
        )
        is False
    )
    assert len(calls) == 1
    with factory() as database:
        statuses = [job.status for job in database.query(Job).all()]
        assert sorted(statuses) == ["checkpointing", "queued"]
        quarantined = database.query(Job).filter_by(status="checkpointing").one()
        assert quarantined.failure_code == "ALIGNMENT_CONTAINMENT_LOST"
        assert quarantined.lease_expires_at is None
        assert quarantined.slide_id is None
        assert quarantined.checkpoint["quarantinedSlideId"] == "m"
        assert database.get(ComparisonSet, comparison_id).registrations == {"m": saved}
        database.delete(database.get(Slide, "m"))
        database.commit()
        assert database.query(Job).filter_by(failure_code="ALIGNMENT_CONTAINMENT_LOST").count() == 1
    assert worker.process_next(factory, layout) is False
    assert worker.recover_stale_jobs(factory) == 0
