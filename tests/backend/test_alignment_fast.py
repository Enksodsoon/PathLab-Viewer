import cv2
import numpy as np
import pytest
from PIL import Image, ImageDraw
from wsi_viewer import alignment
from wsi_viewer.worker import _registration_quality


def test_partial_coarse_component_recovers_unique_feature_region_without_full_outline():
    from wsi_viewer.alignment_fast import PreparationCache, register_prepared

    rng = np.random.default_rng(761)
    reference = Image.new("RGB", (640, 480), "white")
    drawing = ImageDraw.Draw(reference)
    drawing.polygon([(35, 80), (235, 40), (275, 310), (55, 350)], fill=(195, 120, 165))
    drawing.polygon([(365, 65), (585, 100), (575, 420), (350, 355)], fill=(190, 130, 155))
    for left, right in ((70, 230), (390, 540)):
        for x, y in rng.integers([left, 120], [right, 290], (300, 2)):
            drawing.ellipse((int(x), int(y), int(x + 4), int(y + 4)), fill=(45, 25, 80))
    moving = reference.copy()
    ImageDraw.Draw(moving).rectangle((325, 0, 639, 479), fill="white")
    cache = PreparationCache()
    fixed, _ = cache.prepare("fixed-partial", reference, reference.size)
    floating, _ = cache.prepare("moving-partial", moving, moving.size)
    result = register_prepared(fixed, floating)
    assert result.status == "approximate"
    assert result.evidence["maskMode"] == "bounded-component-fallback"
    assert result.evidence["componentPairsChecked"] <= 9
    assert result.overview_triangles and not result.triangles
    assert all(
        max(point[0] for point in cell["moving"]) < 300 for cell in result.overview_triangles
    )


def test_coarse_fallback_preserves_stronger_map_and_is_source_bound():
    from copy import deepcopy

    from wsi_viewer.alignment_engines import ENGINE_NATIVE, ENGINE_VERSIONS, settings_digest
    from wsi_viewer.alignment_policy import current_registration
    from wsi_viewer.worker import _with_overview_fallback

    primary = {
        "status": "approximate",
        "provenance": "automatic",
        "sourceVersion": "moving-v1",
        "anchorVersion": "fixed-v1",
        "anchorSlideId": "fixed",
        "engine": ENGINE_NATIVE,
        "engineVersion": ENGINE_VERSIONS[ENGINE_NATIVE],
        "settingsDigest": settings_digest(ENGINE_NATIVE),
        "overviewTriangles": [{"moving": [[0, 0], [1, 0], [0, 1]]}],
        "evidence": {"source": "bounded-pyramid-whole-slide-structure"},
    }
    coarse = {
        **deepcopy(primary),
        "overviewTriangles": [{"moving": [[0, 0], [100, 0], [0, 100]]}],
        "evidence": {"source": "bounded-sparse-overview"},
    }
    saved = deepcopy(primary)
    combined = _with_overview_fallback(primary, coarse)
    assert combined["overviewTriangles"] == primary["overviewTriangles"]
    assert combined["overviewFallback"] == coarse
    assert primary == saved and "overviewFallback" not in coarse
    assert "overviewFallback" not in _with_overview_fallback(coarse, coarse)
    assert _with_overview_fallback(primary, {**coarse, "sourceVersion": "other"}) == primary
    assert (
        _with_overview_fallback({**primary, "provenance": "manual"}, coarse).get("overviewFallback")
        is None
    )
    replacement = {**primary, "status": "ready", "triangles": [{"reviewed": True}]}
    assert _with_overview_fallback(replacement, combined)["overviewFallback"] == coarse
    combined["overviewFallback"]["engineVersion"] = "obsolete"
    served = current_registration(combined)
    assert "overviewFallback" not in served and served["status"] == "approximate"
    assert "overviewFallback" in combined


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
    assert first.thin_mask is not None
    assert first.nbytes >= first.mask.nbytes + first.thin_mask.nbytes
    sampled, hit = cache.prepare("source-a", image, (3200, 2400), sampling_scale=16)
    assert not hit
    assert sampled.full_size == (5120, 3840)


def test_fast_preparation_retains_thin_tissue_when_standard_mask_is_empty():
    from wsi_viewer import alignment_fast as fast

    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    for y in (100, 150, 200, 250, 300):
        draw.line((60, y, 580, y + 20), fill=(140, 80, 150), width=3)
    prepared, _ = fast.PreparationCache().prepare("thin-slide", image, image.size)
    assert prepared.mask.any()
    assert prepared.thin_mask is prepared.mask


def test_fast_preparation_recovers_tissue_on_tinted_glass_without_accepting_empty_glass():
    from wsi_viewer import alignment_fast as fast

    image = Image.new("RGB", (640, 480), (235, 229, 233))
    ImageDraw.Draw(image).ellipse((120, 80, 520, 400), fill=(140, 80, 150))
    prepared, _ = fast.PreparationCache().prepare("tinted-tissue", image, image.size)
    assert prepared.mask[240, 320] != 0
    assert prepared.mask[20, 20] == 0
    with pytest.raises(alignment.AlignmentRejected, match="insufficient tissue"):
        fast.PreparationCache().prepare(
            "empty-glass", Image.new("RGB", image.size, (235, 229, 233)), image.size
        )


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


def test_overview_seed_recovers_clear_quarter_turn_without_claiming_ambiguous_shape(monkeypatch):
    from wsi_viewer import alignment_fast as fast

    reference = np.zeros((128, 128), dtype=np.uint8)
    cv2.rectangle(reference, (23, 30), (95, 43), 255, -1)
    cv2.rectangle(reference, (23, 30), (39, 108), 255, -1)
    moving = cv2.rotate(reference, cv2.ROTATE_90_CLOCKWISE)
    monkeypatch.setattr(fast, "_mask_seed", lambda *_: (np.eye(2, 3, dtype=np.float32), 0.5))

    seed = fast._overview_mask_seed(reference, moving)
    warped = cv2.warpAffine(moving, seed, reference.shape[::-1])
    assert np.count_nonzero((warped > 0) & (reference > 0)) / np.count_nonzero(reference) > 0.95

    symmetric = np.zeros((128, 128), dtype=np.uint8)
    cv2.circle(symmetric, (64, 64), 35, 255, -1)
    np.testing.assert_array_equal(
        fast._overview_mask_seed(symmetric, symmetric), np.eye(2, 3, dtype=np.float32)
    )


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


def test_fast_ecc_seed_uses_rounded_resize_pixel_centers(monkeypatch):
    from wsi_viewer import alignment_fast as fast

    def prepared(width, height):
        mask = np.full((height, width), 255, dtype=np.uint8)
        ramp = np.tile(np.linspace(0, 255, width, dtype=np.float32), (height, 1))
        return fast.PreparedSlide(ramp, mask, np.empty((0, 2)), None, (width, height))

    received = []

    def ecc(fixed, moving, inverse, *_):
        expected_pixels = fast.cv2.resize(reference.structure, fixed.shape[::-1]) / 255
        np.testing.assert_allclose(fixed, expected_pixels, atol=1e-7)
        received.append((fixed.shape, moving.shape, inverse.copy()))
        return 0.9, inverse

    monkeypatch.setattr(fast.cv2, "findTransformECC", ecc)
    monkeypatch.setattr(fast.cv2, "GaussianBlur", lambda image, *_: image)
    reference = prepared(997, 1019)
    fast.register_prepared(reference, prepared(983, 1001))
    fixed_shape, moving_shape, inverse = received[0]

    def frame(shape, width, height):
        sx, sy = shape[1] / width, shape[0] / height
        return np.asarray([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1]])

    reference_frame = frame(fixed_shape, 997, 1019)
    moving_frame = frame(moving_shape, 983, 1001)
    scanner = np.diag([997 / 983, 1019 / 1001, 1])
    expected = moving_frame @ np.linalg.inv(scanner) @ np.linalg.inv(reference_frame)
    np.testing.assert_allclose(inverse, expected[:2], atol=1e-6)


@pytest.mark.parametrize(
    "first_rejected,second_rejected", [(False, False), (True, False), (True, True)]
)
def test_thin_mask_is_a_bounded_fallback_not_an_acceptance_override(
    monkeypatch, first_rejected, second_rejected
):
    from wsi_viewer import alignment_fast as fast

    mask = np.ones((64, 64), dtype=np.uint8)
    thin = mask * 255
    prepared = fast.PreparedSlide(mask, mask, np.empty((0, 2)), None, (64, 64), thin)
    result = alignment.RegistrationResult(
        "approximate", [[1, 0, 0], [0, 1, 0]], (0, 0, 64, 64), (0, 0, 64, 64), 0.4, 0, 0, -1
    )
    calls = []

    def register(reference, moving, *, sigma):
        calls.append(sigma)
        assert reference.mask is (mask if sigma == 3 else thin)
        if first_rejected and (sigma == 3 or second_rejected):
            raise alignment.AlignmentRejected("insufficient evidence")
        return result

    monkeypatch.setattr(fast, "_register_prepared", register)
    if first_rejected and second_rejected:
        with pytest.raises(alignment.AlignmentRejected):
            fast.register_prepared(prepared, prepared)
    else:
        registered = fast.register_prepared(prepared, prepared)
        assert (registered.evidence.get("maskMode") == "thin-tissue-fallback") == first_rejected
    assert calls == ([3, 5] if first_rejected else [3])


def test_calibrated_pair_is_used_only_after_primary_masks_reject(monkeypatch):
    from wsi_viewer import alignment_fast as fast

    original = np.ones((64, 64), dtype=np.uint8)
    alternate = np.full((64, 64), 255, dtype=np.uint8)
    calibrated = fast.PreparedSlide(alternate, alternate, np.empty((0, 2)), None, (64, 64))
    prepared = fast.PreparedSlide(
        original, original, np.empty((0, 2)), None, (64, 64), original, calibrated
    )
    result = alignment.RegistrationResult(
        "approximate", [[1, 0, 0], [0, 1, 0]], (0, 0, 64, 64), (0, 0, 64, 64), 0.4, 0, 0, -1
    )
    calls = []

    def register(reference, moving, *, sigma):
        calls.append((reference.structure is calibrated.structure, sigma))
        if reference.structure is not calibrated.structure:
            raise alignment.AlignmentRejected("insufficient evidence")
        return result

    monkeypatch.setattr(fast, "_register_prepared", register)
    registered = fast.register_prepared(prepared, prepared)
    assert calls == [(False, 3), (False, 5), (True, 3)]
    assert registered.evidence["maskMode"] == "calibrated-fallback"
    assert prepared.nbytes == calibrated.nbytes + sum(
        value.nbytes
        for value in (prepared.structure, prepared.mask, prepared.points, prepared.thin_mask)
    )


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


@pytest.mark.parametrize(
    "field", ["engine", "engineVersion", "settingsDigest", "preparationVersion"]
)
@pytest.mark.parametrize("obsolete", ["obsolete", None])
def test_saved_automatic_map_rejects_obsolete_versions_without_mutating_revision(field, obsolete):
    from wsi_viewer.alignment_engines import ENGINE_NATIVE, ENGINE_VERSIONS, settings_digest
    from wsi_viewer.alignment_fast import PREPARATION_VERSION
    from wsi_viewer.alignment_policy import current_registration

    saved = {
        "status": "ready",
        "provenance": "automatic",
        "engine": ENGINE_NATIVE,
        "engineVersion": ENGINE_VERSIONS[ENGINE_NATIVE],
        "settingsDigest": settings_digest(ENGINE_NATIVE),
        "triangles": [{"supported": True}],
        "evidence": {"phase": "preview", "preparationVersion": PREPARATION_VERSION},
    }
    assert current_registration(saved)["status"] == "ready"
    if field == "preparationVersion":
        saved["evidence"][field] = obsolete
    else:
        saved[field] = obsolete
    stale = current_registration(saved)
    assert stale["status"] == "stale" and not stale["triangles"]
    assert _registration_quality(saved) == (0, 0.0, 0)
    assert saved["status"] == "ready" and saved["triangles"]


def test_saved_fallback_settings_are_bound_to_the_current_adapter_digest():
    from wsi_viewer.alignment_engines import ENGINE_VALIS, ENGINE_VERSIONS, settings_digest
    from wsi_viewer.alignment_policy import current_registration

    settings = {"maxImageDimension": 768}
    saved = {
        "status": "ready",
        "provenance": "automatic",
        "triangles": [{}],
        "engine": ENGINE_VALIS,
        "engineVersion": ENGINE_VERSIONS[ENGINE_VALIS],
        "engineSettings": settings,
        "settingsDigest": settings_digest(ENGINE_VALIS, settings),
        "evidence": {"valisLocalEvidenceQualified": True},
    }
    assert current_registration(saved)["status"] == "ready"
    settings["maxImageDimension"] = 512
    assert current_registration(saved)["status"] == "stale"


@pytest.mark.parametrize("status", ["ready", "approximate"])
@pytest.mark.parametrize("missing_field", ["sourceVersion", "anchorVersion"])
def test_automatic_map_requires_both_source_identities_when_served(status, missing_field):
    from copy import deepcopy

    from wsi_viewer.alignment_engines import ENGINE_NATIVE, ENGINE_VERSIONS, settings_digest
    from wsi_viewer.alignment_policy import current_registration

    saved = {
        "status": status,
        "provenance": "automatic",
        "sourceVersion": "moving-v1",
        "anchorVersion": "reference-v1",
        "engine": ENGINE_NATIVE,
        "engineVersion": ENGINE_VERSIONS[ENGINE_NATIVE],
        "settingsDigest": settings_digest(ENGINE_NATIVE),
        "movingToReference": [[1, 0, 0], [0, 1, 0]],
        "triangles": [{"supported": True}],
        "overviewTriangles": [{"supported": True}],
        "overviewFallback": {"status": "approximate"},
    }
    del saved[missing_field]
    original = deepcopy(saved)
    served = current_registration(saved, source_version="moving-v1", anchor_version="reference-v1")
    assert served["status"] == "stale"
    assert served["movingToReference"] is None
    assert not served["triangles"] and not served["overviewTriangles"]
    assert "overviewFallback" not in served
    assert saved == original
