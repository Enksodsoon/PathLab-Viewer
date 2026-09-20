from pathlib import Path

from PIL import Image, ImageDraw
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import ComparisonSet, Job, Slide
from wsi_viewer.storage import StorageLayout
from wsi_viewer.worker import process_next


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

    assert process_next(
        factory,
        layout,
        include_kinds=frozenset({"align", "align_benchmark"}),
        exclusive_alignment=True,
    ) is False
