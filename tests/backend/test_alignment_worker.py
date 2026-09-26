from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout
from wsi_viewer.worker import (
    AlignmentPreempted,
    _load_alignment_overview,
    _load_dzi_overview,
    process_next,
)


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


def test_alignment_overview_prefers_bounded_pyramid_for_external_engines(
    tmp_path: Path,
    monkeypatch,
) -> None:
    expected = Image.new("RGB", (4096, 1200), "red")
    thumbnail = Image.new("RGB", (320, 100), "blue")
    thumbnail.save(tmp_path / "thumbnail.jpg")
    monkeypatch.setattr("wsi_viewer.worker._load_dzi_overview", lambda _path: expected)

    loaded = _load_alignment_overview(tmp_path)

    assert loaded is expected
    assert loaded.size == (4096, 1200)


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


@pytest.mark.parametrize("preempted", [False, True])
def test_failed_reregistration_preserves_previous_usable_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, preempted: bool
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

    monkeypatch.setattr(
        "wsi_viewer.worker._run_alignment_bounded",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AlignmentPreempted() if preempted else AlignmentRejected("no replacement")
        ),
    )

    assert process_next(factory, layout) is True

    with factory() as database:
        comparison = database.get(ComparisonSet, comparison_id)
        assert comparison is not None
        assert comparison.registrations["moving"] == previous
        assert comparison.status == ("running" if preempted else "partial")
        assert database.query(Job).one().status == ("queued" if preempted else "failed_terminal")


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
                Job(kind="align_benchmark", resource_class="isolated", status="queued"),
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
