from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, BrokenBarrierError

import pytest
from PIL import Image, ImageDraw
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.alignment_engines import ENGINE_NATIVE, ENGINE_VERSIONS, settings_digest
from wsi_viewer.alignment_policy import current_registration
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout
from wsi_viewer.worker import (
    AlignmentPreempted,
    _candidate_validation_state,
    _load_alignment_overview,
    _load_dzi_overview,
    process_next,
)


def test_candidate_engineering_state_requires_servable_local_evidence() -> None:
    candidate = {"status": "ready", "engineSettings": {}, "evidence": {}}
    assert _candidate_validation_state(candidate, "hisalign-0.2.1", "source", "anchor") == (
        "rejected"
    )
    candidate["evidence"] = {"hisalignLocalEvidenceQualified": True}
    assert _candidate_validation_state(candidate, "hisalign-0.2.1", "source", "anchor") == (
        "engineering_passed"
    )


def test_different_case_ids_hide_existing_map_and_reject_before_image_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    map_value = {
        "status": "approximate",
        "movingToReference": [[1, 0, 2], [0, 1, 3]],
        "overviewTriangles": [{"moving": [[0, 0], [1, 0], [0, 1]],
                               "reference": [[2, 3], [3, 3], [2, 4]]}],
    }
    hidden = current_registration(
        map_value, source_case_id="Case B", anchor_case_id=" case a "
    )
    assert hidden is not None and hidden["status"] == "rejected"
    assert hidden["movingToReference"] is None and not hidden["overviewTriangles"]
    assert current_registration(
        map_value, source_case_id=" CASE A ", anchor_case_id="case a"
    ) == map_value

    settings = Settings(database_url=f"sqlite:///{tmp_path / 'cases.sqlite3'}",
                        data_root=tmp_path / "data")
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        database.add_all([
            Slide(id="reference", public_id="p-ref", display_name="H&E",
                  original_filename="r.tif", source_bytes=1, case_id="Case A",
                  state=SlideState.READY_PRIVATE, sha256="r1",
                  slide_metadata={"width": 1200, "height": 840}),
            Slide(id="moving", public_id="p-mov", display_name="P40",
                  original_filename="m.tif", source_bytes=1, case_id="Case B",
                  state=SlideState.READY_PRIVATE, sha256="m1",
                  slide_metadata={"width": 1200, "height": 840}),
        ])
        database.flush()
        comparison = ComparisonSet(name="Different cases", reference_slide_id="reference",
                                   member_slide_ids=["reference", "moving"],
                                   source_versions={"reference": "r1", "moving": "m1"},
                                   registrations={}, status="queued")
        database.add(comparison)
        database.flush()
        database.add(Job(slide_id="moving", kind="align", resource_class="isolated",
                         checkpoint={"comparisonSetId": comparison.id, "memberId": "moving",
                                     "anchorSlideId": "reference", "setVersion": comparison.version,
                                     "phase": "preview", "foregroundDeadlineAt":
                                     (datetime.now(UTC) + timedelta(seconds=10)).isoformat()},
                         resource_limits={}))
        database.commit()
        comparison_id = comparison.id
    monkeypatch.setattr("wsi_viewer.worker.read_region",
                        lambda *_a, **_kw: pytest.fail("cross-case pixels must not be read"))
    assert process_next(factory, layout) is True
    with factory() as database:
        comparison = database.get(ComparisonSet, comparison_id)
        assert comparison is not None
        assert comparison.registrations["moving"]["status"] == "needs_refinement"
        assert comparison.registrations["moving"]["movingToReference"] is None
    monkeypatch.setattr("wsi_viewer.worker._run_alignment_bounded",
                        lambda *_a, **_kw: pytest.fail("cross-case refinement must not run"))
    assert process_next(factory, layout) is True
    with factory() as database:
        comparison = database.get(ComparisonSet, comparison_id)
        assert comparison is not None
        assert comparison.registrations["moving"]["status"] == "rejected"
        assert not comparison.registrations["moving"].get("overviewTriangles")


def _image(path: Path, *, offset: int = 0) -> None:
    image = Image.new("RGB", (600, 420), "white")
    draw = ImageDraw.Draw(image)
    draw.ellipse(
        (70 + offset, 50, 530 + offset, 370), fill=(220, 155, 185), outline=(60, 40, 90), width=7
    )
    for x in range(110, 500, 35):
        for y in range(90, 340, 35):
            draw.ellipse((x + offset, y, x + 7 + offset, y + 7), fill=(65, 45, 110))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


@pytest.mark.parametrize("requested_maximum", [None, 1024])
def test_alignment_overview_prefers_bounded_pyramid_for_external_engines(
    tmp_path: Path,
    monkeypatch,
    requested_maximum: int | None,
) -> None:
    bound = requested_maximum or 4096
    divisor = 8192 // bound
    expected = Image.new("RGB", (bound, 2400 // divisor), "red")
    geometry = {"sourceSize": [8192, 2400], "samplingScale": [divisor, divisor]}
    expected.info["alignmentGeometry"] = geometry
    thumbnail = Image.new("RGB", (320, 100), "blue")
    thumbnail.save(tmp_path / "thumbnail.jpg")
    calls = []

    def bounded_pyramid(path: Path, *, maximum: int = 4096) -> Image.Image:
        calls.append((path, maximum))
        return expected

    monkeypatch.setattr("wsi_viewer.worker._load_dzi_overview", bounded_pyramid)

    loaded = (
        _load_alignment_overview(tmp_path)
        if requested_maximum is None
        else _load_alignment_overview(tmp_path, maximum=requested_maximum)
    )

    assert loaded is expected
    assert loaded.size == (bound, 2400 // divisor)
    assert loaded.info["alignmentGeometry"] is geometry
    assert calls == [(tmp_path, bound)]


def test_native_child_routes_compatible_seed_to_patches_without_whole_pair(monkeypatch):
    from wsi_viewer import worker

    seed = {"status": "approximate", "overviewTriangles": [{"moving": [], "reference": []}]}
    messages = []
    image = Image.new("RGB", (512, 512))
    monkeypatch.setattr(worker, "_load_alignment_overview", lambda _: image)
    monkeypatch.setattr(worker.sys, "platform", "win32")

    def patches(*args, **kwargs):
        assert args[5] is seed
        kwargs["progress"](1, 64)
        return seed

    def whole_pair(*args, **kwargs):
        pytest.fail("Compatible seed must bypass whole-pair discovery")

    monkeypatch.setattr(worker, "refine_supported_patches", patches)
    monkeypatch.setattr(worker, "register_pair", whole_pair)

    class Output:
        def put(self, value):
            messages.append(value)

    worker._alignment_child(
        "ref", "mov", (512, 512), (512, 512), worker.ENGINE_NATIVE, None, None, Output(), seed
    )
    assert messages[0]["progress"]["stage"] == "guided-patches"
    assert messages[-1] == {"ok": True, "result": seed}


def test_alignment_overview_falls_back_to_thumbnail(tmp_path: Path) -> None:
    thumbnail = Image.new("RGB", (320, 100), "blue")
    thumbnail.save(tmp_path / "thumbnail.jpg")

    loaded = _load_alignment_overview(tmp_path)

    assert loaded.size == thumbnail.size


def test_valis_child_composes_fragments_and_resumes_cached_components(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace

    from wsi_viewer import worker
    from wsi_viewer.alignment import map_registration_point

    for name in ("ref", "mov"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "slide.dzi").touch()
    image = Image.new("RGB", (512, 512))
    boxes = [(0, 0, 10, 10), (20, 20, 30, 30)]
    monkeypatch.setattr(worker.sys, "platform", "win32")
    monkeypatch.setattr(worker, "_load_alignment_overview", lambda _: image)
    monkeypatch.setattr(worker, "component_bounds", lambda *_: boxes)
    monkeypatch.setattr(worker, "_candidate_component_pairs", lambda *_: ([(0, 0), (1, 1)], set()))
    monkeypatch.setattr(
        worker,
        "read_region",
        lambda path, bounds, maximum: (
            image,
            ((100 if path.name == "ref" else 300) + bounds[0], 200 + bounds[1], 16),
        ),
    )
    calls = []

    def run(engine, **kwargs):
        calls.append(kwargs)
        assert kwargs["reference_full_size"] == (8192, 8192)
        payload = {
            "engineVersion": worker.ENGINE_VERSIONS[engine],
            "status": "ready",
            "movingToReference": [[1, 0, 2], [0, 1, 0]],
            "confidence": 0.9,
            "triangles": [
                {"moving": [[0, 0], [10, 0], [0, 10]], "reference": [[2, 0], [12, 0], [2, 10]]}
            ],
            "evidence": {"valisLocalEvidenceQualified": True},
        }
        folder = kwargs["artifact_dir"]
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "valis-coordinate-map.json").write_text(json.dumps(payload))
        return SimpleNamespace(registration=payload)

    monkeypatch.setattr(worker, "run_engine", run)
    messages = []
    output = SimpleNamespace(put=messages.append)
    args = (
        str(tmp_path / "ref"),
        str(tmp_path / "mov"),
        (512, 512),
        (512, 512),
        worker.ENGINE_VALIS,
        None,
        str(tmp_path / "artifacts"),
        output,
    )
    worker._alignment_child(*args)
    result = messages[-1]["result"]
    assert map_registration_point(result, 302, 202) == pytest.approx((104, 202))
    assert len(result["triangles"]) == 2
    assert len(calls) == 2
    messages.clear()
    worker._alignment_child(*args)
    assert messages[-1]["result"] == result
    assert len(calls) == 2
    receipt = next((tmp_path / "artifacts").glob("component-*/valis-coordinate-map.json"))
    receipt.write_text("{}")
    worker._alignment_child(*args)
    assert len(calls) == 3
    receipt.write_text("{}")

    def rejected(*args, **kwargs):
        raise AlignmentRejected("component rematching failed")

    monkeypatch.setattr(worker, "run_engine", rejected)
    worker._alignment_child(*args)
    partial = messages[-1]["result"]
    assert len(partial["triangles"]) == 1
    assert partial["evidence"]["totalComponentPairs"] == 2
    assert partial["evidence"]["acceptedComponentPairs"] == 1
    assert partial["evidence"]["componentFailures"][0]["reason"] == "component rematching failed"
    assert "Partial component coverage" in partial["reason"]
    # Identical geometry/settings must not reuse maps after source pixels change.
    monkeypatch.setattr(worker, "run_engine", run)
    image.putpixel((0, 0), (255, 255, 255))
    worker._alignment_child(*args)
    assert len(calls) == 5
    worker._alignment_child(*args)
    assert len(calls) == 5


def test_dzi_overview_preserves_sparse_white_tiles(tmp_path: Path) -> None:
    (tmp_path / "slide.dzi").write_text(
        '<Image TileSize="256" Overlap="0" Format="jpg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        '<Size Width="512" Height="256"/></Image>',
        encoding="utf-8",
    )
    tile_root = tmp_path / "slide_files" / "9"
    tile_root.mkdir(parents=True)
    Image.new("RGB", (256, 256), "red").save(tile_root / "0_0.jpg")

    loaded = _load_dzi_overview(tmp_path)

    assert loaded.size == (512, 256)
    assert loaded.getpixel((64, 64))[0] > 240
    assert loaded.getpixel((400, 64)) == (255, 255, 255)


def test_dzi_overview_materializes_dynamic_tiles_instead_of_blank_tissue(tmp_path, monkeypatch):
    from wsi_viewer import tile_routes

    (tmp_path / "slide.dzi").write_text(
        '<Image TileSize="256" Overlap="0" Format="jpg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        '<Size Width="512" Height="256"/></Image>',
        encoding="utf-8",
    )
    (tmp_path / ".openslide-source.json").write_text("{}", encoding="utf-8")
    requested = []

    def materialize(root, slide_id, relative):
        requested.append(relative)
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (256, 256), (120, 60, 150)).save(target)
        return target

    monkeypatch.setattr(tile_routes, "materialize_local_openslide_tile_from_root", materialize)
    loaded = _load_dzi_overview(tmp_path)
    assert requested == ["slide_files/9/0_0.jpg", "slide_files/9/1_0.jpg"]
    assert loaded.getpixel((400, 64)) == pytest.approx((120, 60, 150), abs=3)


def test_alignment_job_persists_map_without_changing_slide_state(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        reference = Slide(
            id="reference",
            public_id="p-reference",
            display_name="H&E",
            original_filename="r.tif",
            source_bytes=1,
            state=SlideState.READY_PRIVATE,
            sha256="r1",
            slide_metadata={"width": 1200, "height": 840},
        )
        moving = Slide(
            id="moving",
            public_id="p-moving",
            display_name="IHC",
            original_filename="m.tif",
            source_bytes=1,
            state=SlideState.READY_PRIVATE,
            sha256="m1",
            slide_metadata={"width": 1200, "height": 840},
        )
        database.add_all([reference, moving])
        database.flush()
        comparison = ComparisonSet(
            name="Set",
            reference_slide_id="reference",
            member_slide_ids=["reference", "moving"],
            source_versions={"reference": "r1", "moving": "m1"},
            registrations={},
            status="queued",
        )
        database.add(comparison)
        database.flush()
        database.add(
            Job(
                slide_id="moving",
                kind="align",
                resource_class="isolated",
                checkpoint={"comparisonSetId": comparison.id, "memberId": "moving", "progress": 0},
                resource_limits={},
            )
        )
        database.commit()
        comparison_id = comparison.id
    _image(layout.for_slide("reference").private_derivative / "thumbnail.jpg")
    _image(layout.for_slide("moving").private_derivative / "thumbnail.jpg", offset=15)

    assert process_next(factory, layout) is True

    with factory() as database:
        comparison = database.get(ComparisonSet, comparison_id)
        job = database.query(Job).one()
        assert comparison is not None
        assert comparison.registrations["moving"]["status"] == "ready"
        assert comparison.registrations["moving"]["provenance"] == "automatic"
        assert comparison.registrations["moving"]["anchorSlideId"] == "reference"
        assert abs(comparison.registrations["moving"]["movingToReference"][0][2]) > 20
        assert comparison.status == "ready"
        assert job.status == "succeeded"
        assert job.checkpoint["progress"] == 100
        assert database.get(Slide, "moving").state is SlideState.READY_PRIVATE


@pytest.mark.parametrize("preempted", [False, True, "conversion"])
def test_failed_reregistration_preserves_previous_usable_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preempted: bool | str
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'rerun.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    previous = {
        "status": "approximate",
        "provenance": "automatic",
        "engine": ENGINE_NATIVE,
        "engineVersion": ENGINE_VERSIONS[ENGINE_NATIVE],
        "settingsDigest": settings_digest(ENGINE_NATIVE),
        "anchorSlideId": "reference",
        "sourceVersion": "m1",
        "anchorVersion": "r1",
        "overviewTriangles": [
            {"moving": [[0, 0], [1, 0], [0, 1]], "reference": [[0, 0], [1, 0], [0, 1]]}
        ],
    }
    with factory() as database:
        database.add_all(
            [
                Slide(
                    id="reference",
                    public_id="p-reference",
                    display_name="H&E",
                    original_filename="r.tif",
                    source_bytes=1,
                    state=SlideState.READY_PRIVATE,
                    sha256="r1",
                    slide_metadata={"width": 1200, "height": 840},
                ),
                Slide(
                    id="moving",
                    public_id="p-moving",
                    display_name="IHC",
                    original_filename="m.tif",
                    source_bytes=1,
                    state=SlideState.READY_PRIVATE,
                    sha256="m1",
                    slide_metadata={"width": 1200, "height": 840},
                ),
            ]
        )
        database.flush()
        comparison = ComparisonSet(
            name="Set",
            reference_slide_id="reference",
            member_slide_ids=["reference", "moving"],
            source_versions={"reference": "r1", "moving": "m1"},
            registrations={"moving": previous},
            status="queued",
        )
        database.add(comparison)
        database.flush()
        database.add(
            Job(
                slide_id="moving",
                kind="align",
                resource_class="isolated",
                checkpoint={
                    "comparisonSetId": comparison.id,
                    "memberId": "moving",
                    "anchorSlideId": "reference",
                    "setVersion": comparison.version,
                    "preserveExisting": True,
                    "progress": 0,
                },
                resource_limits={},
            )
        )
        database.commit()
        comparison_id = comparison.id

    def bounded(*args, **kwargs):
        if preempted == "conversion":
            with factory() as incoming:
                incoming.add(Job(kind="convert", resource_class="background", status="queued"))
                incoming.commit()
            kwargs["heartbeat"]()
            raise AlignmentRejected("conversion did not preempt refinement")
        raise AlignmentPreempted() if preempted else AlignmentRejected("no replacement")

    monkeypatch.setattr("wsi_viewer.worker._run_alignment_bounded", bounded)

    assert process_next(factory, layout) is True

    with factory() as database:
        comparison = database.get(ComparisonSet, comparison_id)
        assert comparison is not None
        assert comparison.registrations["moving"] == previous
        assert comparison.status == ("running" if preempted else "partial")
        assert database.query(Job).filter(Job.kind == "align").one().status == (
            "queued" if preempted else "failed_terminal"
        )


def test_successful_reregistration_does_not_replace_stronger_existing_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'rerun-quality.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    previous = {
        "status": "approximate",
        "provenance": "automatic",
        "engine": ENGINE_NATIVE,
        "engineVersion": ENGINE_VERSIONS[ENGINE_NATIVE],
        "settingsDigest": settings_digest(ENGINE_NATIVE),
        "anchorSlideId": "reference",
        "sourceVersion": "m1",
        "anchorVersion": "r1",
        "confidence": 0.4,
        "overviewTriangles": [
            {"moving": [[0, 0], [1, 0], [0, 1]], "reference": [[0, 0], [1, 0], [0, 1]]}
        ],
        "evidence": {"source": "bounded-pyramid-whole-slide-structure"},
    }
    with factory() as database:
        database.add_all(
            [
                Slide(
                    id="reference",
                    public_id="p-reference",
                    display_name="H&E",
                    original_filename="r.tif",
                    source_bytes=1,
                    state=SlideState.READY_PRIVATE,
                    sha256="r1",
                    slide_metadata={"width": 1200, "height": 840},
                ),
                Slide(
                    id="moving",
                    public_id="p-moving",
                    display_name="IHC",
                    original_filename="m.tif",
                    source_bytes=1,
                    state=SlideState.READY_PRIVATE,
                    sha256="m1",
                    slide_metadata={"width": 1200, "height": 840},
                ),
            ]
        )
        database.flush()
        comparison = ComparisonSet(
            name="Set",
            reference_slide_id="reference",
            member_slide_ids=["reference", "moving"],
            source_versions={"reference": "r1", "moving": "m1"},
            registrations={"moving": previous},
            status="queued",
        )
        database.add(comparison)
        database.flush()
        database.add(
            Job(
                slide_id="moving",
                kind="align",
                resource_class="isolated",
                checkpoint={
                    "comparisonSetId": comparison.id,
                    "memberId": "moving",
                    "anchorSlideId": "reference",
                    "setVersion": comparison.version,
                    "preserveExisting": True,
                    "progress": 0,
                },
                resource_limits={},
            )
        )
        database.commit()
        comparison_id = comparison.id

    weaker = {
        **previous,
        "confidence": 0.49,
        "inlierCount": 0,
        "matchCount": 0,
        "evidence": {"source": "bounded-pyramid-component-flow"},
    }
    monkeypatch.setattr("wsi_viewer.worker._run_alignment_bounded", lambda *_a, **_k: weaker)

    assert process_next(factory, layout) is True

    with factory() as database:
        comparison = database.get(ComparisonSet, comparison_id)
        job = database.query(Job).one()
        assert comparison is not None
        assert comparison.registrations["moving"] == previous
        assert job.status == "succeeded"
        assert job.output_manifest["preservedExisting"] is True


def test_alignment_jobs_have_exclusive_heavy_work_admission(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'admission.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        database.add_all(
            [
                Job(kind="align_benchmark", resource_class="isolated", status="running"),
                Job(kind="convert", resource_class="background", status="queued"),
            ]
        )
        database.commit()

    assert process_next(factory, layout, exclusive_alignment=False) is False

    with factory() as database:
        alignment = database.query(Job).filter(Job.kind == "align_benchmark").one()
        alignment.status = "running"
        ordinary = database.query(Job).filter(Job.kind == "convert").one()
        ordinary.status = "running"
        database.commit()

    assert (
        process_next(
            factory,
            layout,
            include_kinds=frozenset({"align", "align_benchmark"}),
            exclusive_alignment=True,
        )
        is False
    )


@pytest.mark.parametrize("split_roles", [False, True])
def test_queued_conversion_runs_before_background_alignment(tmp_path: Path, split_roles: bool):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'priority.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        database.add_all(
            [
                Job(kind="align_benchmark", resource_class="isolated", status="queued"),
                Job(kind="convert", resource_class="background", status="queued"),
            ]
        )
        database.commit()
    if split_roles:
        assert (
            process_next(
                factory,
                layout,
                include_kinds=frozenset({"align", "align_benchmark"}),
                exclusive_alignment=True,
            )
            is False
        )
    assert process_next(
        factory,
        layout,
        exclude_kinds=frozenset({"align", "align_benchmark"}) if split_roles else None,
        exclusive_alignment=False if split_roles else None,
    )
    with factory() as database:
        assert database.query(Job).filter(Job.kind == "align_benchmark").one().status == "queued"
        assert database.query(Job).filter(Job.kind == "convert").one().status == "failed_terminal"


def test_worker_claim_is_serialized_before_dispatch(tmp_path: Path, monkeypatch):
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'claims.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        database.add(Job(kind="convert", resource_class="background", status="queued"))
        database.commit()
    barrier = Barrier(2, timeout=0.5)
    original = Session.scalar

    def simultaneous_claim(session, *args, **kwargs):
        value = original(session, *args, **kwargs)
        if isinstance(value, Job):
            with suppress(BrokenBarrierError):
                barrier.wait()
        return value

    monkeypatch.setattr(Session, "scalar", simultaneous_claim)
    with ThreadPoolExecutor(max_workers=2) as threads:
        results = list(threads.map(lambda _: process_next(factory, layout), range(2)))
    assert sorted(results) == [False, True]


def test_worker_retries_admission_after_sqlite_writer_releases_lock(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'busy.sqlite3'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        database.add(Job(kind="convert", resource_class="background", status="queued"))
        database.commit()
    polling_engine = create_engine(settings.database_url, connect_args={"timeout": 0})
    polling_factory = sessionmaker(bind=polling_engine)
    with factory() as writer:
        writer.connection().exec_driver_sql("BEGIN IMMEDIATE")
        assert process_next(polling_factory, layout) is False
        assert writer.query(Job).one().status == "queued"
        writer.rollback()
    polling_engine.dispose()
    assert process_next(factory, layout) is True
    with factory() as database:
        assert database.query(Job).one().status == "failed_terminal"
