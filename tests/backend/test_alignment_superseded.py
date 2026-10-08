import pytest
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout
from wsi_viewer.worker import process_next


@pytest.mark.parametrize("during_heartbeat", [True, False])
def test_regional_edit_cancels_old_refinement_without_stuck_running_set(
    tmp_path, monkeypatch, during_heartbeat
):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    saved = {
        "status": "ready",
        "provenance": "manual",
        "confidence": 0.99,
        "sourceVersion": "m1",
        "anchorVersion": "r1",
        "triangles": [{"saved": True}],
    }
    with factory() as database:
        for name, digest in [("reference", "r1"), ("moving", "m1")]:
            database.add(
                Slide(
                    id=name,
                    public_id="p-" + name,
                    display_name=name,
                    original_filename=name + ".tif",
                    source_bytes=1,
                    sha256=digest,
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={"width": 100, "height": 100},
                )
            )
        database.flush()
        comparison = ComparisonSet(
            name="Set",
            reference_slide_id="reference",
            member_slide_ids=["reference", "moving"],
            source_versions={"reference": "r1", "moving": "m1"},
            registrations={"moving": saved},
            status="queued",
        )
        database.add(comparison)
        database.flush()
        comparison_id = comparison.id
        database.add(
            Job(
                slide_id="moving",
                kind="align",
                resource_class="isolated",
                checkpoint={
                    "comparisonSetId": comparison.id,
                    "memberId": "moving",
                    "setVersion": comparison.version,
                    "phase": "refinement",
                },
                resource_limits={},
            )
        )
        database.commit()

    def supersede(*args, **kwargs):
        with factory() as editing:
            current = editing.get(ComparisonSet, comparison_id)
            current.version += 1
            editing.commit()
        if during_heartbeat:
            kwargs["heartbeat"]()
        return {"status": "ready", "confidence": 0.9, "inlierCount": 20, "evidence": {}}

    monkeypatch.setattr("wsi_viewer.worker._run_alignment_bounded", supersede)
    assert process_next(factory, StorageLayout(settings.data_root))
    with factory() as database:
        current = database.get(ComparisonSet, comparison_id)
        job = database.query(Job).one()
        assert job.status == "cancelled"
        assert job.failure_code == "ALIGNMENT_STALE"
        assert job.error and "discarded" in job.error.lower()
        assert current.status == "ready"
        assert current.registrations == {"moving": saved}


def test_pair_timeout_cap_and_inherited_compute_budget():
    from wsi_viewer.worker import _alignment_remaining_budget

    assert _alignment_remaining_budget({}, {"timeoutSeconds": 2700}) == 600
    assert _alignment_remaining_budget({"computeSecondsUsed": 590}, {"timeoutSeconds": 2700}) == 10
    assert _alignment_remaining_budget({"computeSecondsUsed": 601}, {}) == 0


def test_preview_carries_preparation_and_compute_into_total_refinement_budget(monkeypatch):
    from collections import OrderedDict
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from wsi_viewer import worker

    elapsed = [100.0]
    database = MagicMock()
    database.scalar.return_value = None
    comparison = ComparisonSet(
        id="set",
        name="Set",
        version=1,
        reference_slide_id="r",
        member_slide_ids=["r", "m"],
        source_versions={"r": "r", "m": "m"},
        registrations={},
    )
    slides = [
        Slide(id=s, sha256=s, case_id=None, slide_metadata={"width": 100, "height": 100})
        for s in ("r", "m")
    ]
    job = Job(
        id="preview",
        checkpoint={
            "comparisonSetId": "set",
            "setVersion": 1,
            "phase": "preview",
            "computeSecondsUsed": 3,
            "foregroundDeadlineAt": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        },
    )

    def prepare(*_args, **_kwargs):
        elapsed[0] += 2
        return object(), False

    def register(*_args):
        elapsed[0] += 2
        return SimpleNamespace(as_json=lambda: {"status": "approximate", "overviewTriangles": []})

    monkeypatch.setattr(worker.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(worker, "_preparation_cache", SimpleNamespace(prepare=prepare))
    monkeypatch.setattr(worker, "register_prepared", register)
    monkeypatch.setattr(worker, "_preview_maps", OrderedDict())
    monkeypatch.setattr(worker, "_preview_map_bytes", 0)
    monkeypatch.setattr(worker, "_best_compatible_registration", lambda *_a, **_kw: None)
    monkeypatch.setattr(worker, "_process_rss_bytes", lambda *_a, **_kw: 0)
    worker._preview_alignment(database, StorageLayout(Path("private")), job, comparison, *slides)
    refinement = next(
        call.args[0] for call in database.add.call_args_list if isinstance(call.args[0], Job)
    )
    assert job.checkpoint["runtimeSeconds"] == 6
    assert refinement.checkpoint["computeSecondsUsed"] == 9
    assert (
        worker._alignment_remaining_budget(refinement.checkpoint, refinement.resource_limits) == 591
    )
