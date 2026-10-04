from copy import deepcopy

import pytest
from wsi_viewer import worker
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.alignment_calibration import metadata_frame_digest
from wsi_viewer.alignment_engines import ENGINE_VALIS, settings_digest
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonRegistrationCandidate, ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout


@pytest.mark.parametrize("frame_changes", [False, True])
def test_adaptive_fallback_retains_normalized_calibration_and_rejects_changed_frame(
    tmp_path, monkeypatch, frame_changes
):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    requested = {"maxImageDimension": 896, "profile": "requested"}
    with factory() as database:
        for name, x, y, unit in (("r", 0.00025, 0.0005, "mm"), ("m", 500, 1000, "nm")):
            database.add(
                Slide(
                    id=name,
                    public_id="p-" + name,
                    display_name=name,
                    original_filename=name + ".tif",
                    source_bytes=1,
                    sha256=name,
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={
                        "width": 100,
                        "height": 100,
                        "physicalSizeX": x,
                        "physicalSizeY": y,
                        "physicalSizeUnit": unit,
                    },
                )
            )
        database.flush()
        comparison = ComparisonSet(
            name="Fallback",
            reference_slide_id="r",
            member_slide_ids=["r", "m"],
            source_versions={"r": "r", "m": "m"},
            registrations={},
            status="queued",
        )
        database.add(comparison)
        database.flush()
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
                    "engine": ENGINE_VALIS,
                    "engineSettings": requested,
                },
            )
        )
        database.commit()
    calls = []

    def bounded(*_args, **options):
        calls.append(deepcopy(options["engine_settings"]))
        if len(calls) == 1:
            raise AlignmentRejected("test registration exceeded the memory ceiling")
        if frame_changes:
            with factory() as editing:
                moving = editing.get(Slide, "m")
                moving.slide_metadata = {**moving.slide_metadata, "physicalSizeUnit": "um"}
                editing.commit()
        return {
            "status": "approximate",
            "confidence": 0.1,
            "inlierCount": 0,
            "engineSettings": deepcopy(options["engine_settings"]),
            "evidence": {},
        }

    monkeypatch.setattr(worker, "_run_alignment_bounded", bounded)
    assert worker.process_next(factory, StorageLayout(settings.data_root)) is True
    assert len(calls) == 2
    assert calls[0]["referenceMicronsPerPixel"] == [0.25, 0.5]
    assert calls[0]["movingMicronsPerPixel"] == [0.5, 1]
    assert calls[1] == {**calls[0], "maxImageDimension": 768}
    with factory() as database:
        job = database.query(Job).one()
        assert job.checkpoint["engineSettings"] == requested
        candidate = database.query(ComparisonRegistrationCandidate).one_or_none()
        if frame_changes:
            assert job.status == "cancelled"
            assert candidate is None
        else:
            assert job.status == "succeeded"
            assert candidate.registration["engineSettings"] == calls[1]
            assert candidate.settings_digest == settings_digest(ENGINE_VALIS, calls[1])
            assert candidate.registration["sourceFrameVersion"] == metadata_frame_digest(
                database.get(Slide, "m").slide_metadata
            )
            assert candidate.registration["anchorFrameVersion"] == metadata_frame_digest(
                database.get(Slide, "r").slide_metadata
            )
            assert candidate.registration["evidence"]["adaptiveMemoryFallback"] is True
