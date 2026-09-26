import numpy as np
import pytest
from PIL import Image, ImageDraw
from wsi_viewer import alignment
from wsi_viewer.worker import _registration_quality


def test_legacy_engine_map_cannot_outrank_current_qualified_overview():
    old = {
        "status": "ready",
        "engine": "hisalign-0.2.1",
        "triangles": [{}],
        "evidence": {"withheldCheck": "engine-cycle-tissue-support-and-overlap"},
    }
    current = {
        "status": "approximate",
        "overviewTriangles": [{}],
        "evidence": {"source": "bounded-pyramid-whole-slide-structure"},
    }
    assert _registration_quality(old) < _registration_quality(current)


def test_manual_points_require_unchanged_source_pair():
    from wsi_viewer.alignment_policy import current_registration

    saved = {
        "status": "ready",
        "provenance": "manual",
        "sourceVersion": "moving-v1",
        "anchorVersion": "reference-v1",
        "triangles": [{"reviewed": True}],
    }
    assert (
        current_registration(saved, source_version="moving-v1", anchor_version="reference-v1")
        == saved
    )
    stale = current_registration(saved, source_version="moving-v2", anchor_version="reference-v1")
    assert stale["status"] == "stale" and not stale["triangles"]
    assert saved["status"] == "ready" and saved["triangles"]


def test_capability_discovery_does_not_load_optional_models(monkeypatch):
    import builtins

    from wsi_viewer.alignment_engines import engine_availability

    original = builtins.__import__

    def checked(name, *args, **kwargs):
        assert not name.startswith(("valis", "hisalign", "torch"))
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", checked)
    assert engine_availability()["native-v12"]["available"]


def test_foreground_preemption_stops_before_expensive_child_start(tmp_path, monkeypatch):
    from wsi_viewer import worker

    def preempt():
        raise worker.AlignmentPreempted()

    def no_spawn(*args):
        pytest.fail("foreground admission must be checked before starting a child")

    monkeypatch.setattr(worker.multiprocessing, "get_context", no_spawn)
    with pytest.raises(worker.AlignmentPreempted):
        worker._run_alignment_bounded(
            tmp_path,
            tmp_path,
            (100, 100),
            (100, 100),
            timeout_seconds=10,
            memory_bytes=1024,
            heartbeat=preempt,
        )


def test_fast_preparation_reuses_source_and_invalidates_geometry_and_version():
    from wsi_viewer import alignment_fast as fast

    cache = fast.PreparationCache(max_bytes=16 * 1024**2)
    image = Image.new("RGB", (320, 240), "white")
    ImageDraw.Draw(image).ellipse((25, 30, 280, 210), fill=(160, 80, 120))
    first, hit = cache.prepare("source-a", image, (3200, 2400))
    assert not hit
    reused, hit = cache.prepare("source-a", image, (3200, 2400))
    assert hit and reused is first
    changed, hit = cache.prepare("source-b", image, (3200, 2400))
    assert not hit and changed is not first
    changed, hit = cache.prepare("source-a", image, (6400, 4800))
    assert not hit and changed is not first
    assert cache.bytes_used <= 16 * 1024**2
    sampled, hit = cache.prepare("source-a", image, (3200, 2400), sampling_scale=16)
    assert not hit
    assert sampled.full_size == (5120, 3840)


def test_fast_pair_recovers_translation_without_local_anatomy_claim():
    from wsi_viewer import alignment_fast as fast

    rng = np.random.default_rng(42)
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(70, 80), (480, 50), (590, 330), (190, 400)], fill=(220, 150, 180))
    for x, y in rng.integers([130, 100], [480, 330], size=(200, 2)):
        draw.ellipse((int(x), int(y), int(x + 5), int(y + 5)), fill=(75, 40, 100))
    moved = Image.new("RGB", image.size, "white")
    moved.paste(image, (20, 15))
    cache = fast.PreparationCache()
    ref, _ = cache.prepare("ref", image, image.size)
    mov, _ = cache.prepare("mov", moved, moved.size)
    result = fast.register_prepared(ref, mov)
    assert result.status == "approximate"
    assert not result.triangles
    assert result.overview_triangles
    x, y = alignment.map_point(result.moving_to_reference, 320, 215)
    assert x == pytest.approx(300, abs=3)
    assert y == pytest.approx(200, abs=3)
    assert len(ref.points) <= 1536


@pytest.mark.parametrize(
    "reference_size,accepted", [((512, 512), True), ((1536, 1536), False), ((512, 1536), False)]
)
def test_fast_scale_gate_uses_level_zero_geometry(monkeypatch, reference_size, accepted):
    from wsi_viewer import alignment_fast as fast

    def prepared(side, size):
        return fast.PreparedSlide(
            np.zeros((side, side), dtype=np.uint8),
            np.full((side, side), 255, dtype=np.uint8),
            np.empty((0, 2), dtype=np.float32),
            None,
            size,
        )

    monkeypatch.setattr(
        fast.cv2, "findTransformECC", lambda *_: (0.9, np.float32([[4, 0, 0], [0, 4, 0]]))
    )
    reference = prepared(128, reference_size)
    moving = prepared(512, (512, 512))
    if not accepted:
        with pytest.raises(alignment.AlignmentRejected, match="weak coarse"):
            fast.register_prepared(reference, moving)
        return
    result = fast.register_prepared(reference, moving)
    assert result.status == "approximate" and result.overview_triangles
    np.testing.assert_allclose(result.moving_to_reference, [[1, 0, 0], [0, 1, 0]], atol=1e-6)


def test_foreground_admission_precedes_older_refinement(tmp_path):
    from datetime import UTC, datetime

    from wsi_viewer.config import Settings
    from wsi_viewer.database import create_schema, session_factory
    from wsi_viewer.models import Job, Slide
    from wsi_viewer.worker import _next_job_statement

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'priority.db'}")
    create_schema(settings)
    with session_factory(settings)() as db:
        db.add(
            Slide(
                id="slide",
                public_id="public",
                display_name="Slide",
                original_filename="slide.tif",
                source_bytes=1,
            )
        )
        db.flush()
        db.add(
            Job(
                id="old",
                slide_id="slide",
                kind="align",
                checkpoint={"phase": "refinement"},
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        db.add(
            Job(
                id="new",
                slide_id="slide",
                kind="align",
                checkpoint={"phase": "preview"},
                created_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
        )
        db.commit()
        selected = db.scalar(_next_job_statement(now=datetime.now(UTC), postgres=False))
        assert selected.id == "new"


@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("member_count", [2, 4, 8, 12])
def test_stacking_publishes_first_pass_before_refinement(tmp_path, expired, member_count):
    from datetime import UTC, datetime, timedelta

    from wsi_viewer.config import Settings
    from wsi_viewer.database import create_schema, session_factory
    from wsi_viewer.domain import SlideState
    from wsi_viewer.models import ComparisonSet, Job, Slide
    from wsi_viewer.stack_service import queue_ready_registrations
    from wsi_viewer.storage import StorageLayout
    from wsi_viewer.worker import process_next

    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'stack.db'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(50, 60), (400, 80), (580, 300), (110, 430)], fill=(220, 150, 190))
    for x, y in np.random.default_rng(22).integers([110, 120], [440, 330], (300, 2)):
        draw.ellipse((int(x), int(y), int(x + 6), int(y + 6)), fill=(75, 30, 95))
    ids = ["ref"] + [f"mov-{i}" for i in range(1, member_count)]
    with factory() as db:
        for sid in ids:
            db.add(
                Slide(
                    id=sid,
                    public_id=f"p-{sid}",
                    display_name=sid,
                    original_filename=sid,
                    source_bytes=1,
                    sha256=sid,
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={"width": 640, "height": 480},
                )
            )
            path = layout.for_slide(sid).private_derivative
            path.mkdir(parents=True)
            image.save(path / "thumbnail.jpg")
        db.flush()
        item = ComparisonSet(
            id="stack",
            name="Stack",
            reference_slide_id="ref",
            member_slide_ids=ids,
            registrations={},
            source_versions={},
        )
        db.add(item)
        db.flush()
        assert queue_ready_registrations(db, item) == member_count - 1
        db.commit()
        if expired:
            for job in db.query(Job).all():
                job.checkpoint = {
                    **job.checkpoint,
                    "foregroundDeadlineAt": (datetime.now(UTC) - timedelta(seconds=1)).isoformat(),
                }
            db.commit()
    for _ in range(member_count - 1):
        assert process_next(factory, layout)
    with factory() as db:
        item = db.get(ComparisonSet, "stack")
        for sid in ids[1:]:
            assert item.registrations[sid]["status"] == (
                "needs_refinement" if expired else "approximate"
            )
            assert bool(item.registrations[sid]["overviewTriangles"]) is not expired
        jobs = list(db.query(Job).all())
        assert (
            sum(j.status == "queued" and j.checkpoint.get("phase") == "refinement" for j in jobs)
            == member_count - 1
        )
        assert (
            sum(j.status == "succeeded" and j.checkpoint.get("phase") == "preview" for j in jobs)
            == member_count - 1
        )
        if member_count == 2 and not expired:
            db.get(Slide, "mov-1").sha256 = "replacement-source"
            db.flush()
            assert queue_ready_registrations(db, item) == 1
            db.commit()
    if member_count == 2 and not expired:
        assert process_next(factory, layout)  # replacement preview precedes old refinement
        assert process_next(factory, layout)  # old source-bound refinement is discarded
        with factory() as db:
            item = db.get(ComparisonSet, "stack")
            assert item.registrations["mov-1"]["sourceVersion"] == "replacement-source"
            old = [
                j
                for j in db.query(Job).all()
                if j.checkpoint.get("phase") == "refinement"
                and j.checkpoint.get("sourceVersion") == "mov-1"
            ]
            assert len(old) == 1 and old[0].status == "cancelled"
