import io
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import PublicationGrant, Slide
from wsi_viewer.publication import delivery_version
from wsi_viewer.storage import (
    InsufficientStorage,
    PublicationError,
    StorageLayout,
    measure_derivative,
    publish_derivative,
    publish_individual_derivative,
)
from wsi_viewer.storage_accounting import reconcile_storage
from wsi_viewer.thumbnail_repair import install_thumbnail, recovered_thumbnail


def pyramid(root: Path) -> None:
    tile = root / "slide_files" / "9" / "0_0.jpg"
    tile.parent.mkdir(parents=True)
    (root / "slide.dzi").write_text(
        '<Image TileSize="512" Overlap="1" Format="jpg"><Size Width="8192" Height="4096"/></Image>'
    )
    Image.new("RGB", (512, 256), (120, 70, 30)).save(tile, "JPEG")


def test_recover_complete_overview_and_preserve_existing_image(tmp_path: Path) -> None:
    pyramid(tmp_path)
    payload = recovered_thumbnail(tmp_path)
    assert payload is not None
    with Image.open(io.BytesIO(payload)) as image:
        assert image.size == (512, 256)
        assert image.getpixel((256, 128))[0] == pytest.approx(120, abs=3)
    install_thumbnail(tmp_path, payload)
    assert recovered_thumbnail(tmp_path) is None
    with pytest.raises(FileExistsError):
        install_thumbnail(tmp_path, b"replacement")
    assert (tmp_path / "thumbnail.jpg").read_bytes() == payload
    assert not list(tmp_path.glob(".thumbnail-repair-*"))


@pytest.mark.parametrize("defect", ["missing", "wrong-size", "malformed", "unsafe-format"])
def test_recovery_rejects_incomplete_or_mismatched_pyramids(tmp_path: Path, defect: str) -> None:
    pyramid(tmp_path)
    tile = tmp_path / "slide_files/9/0_0.jpg"
    if defect == "missing":
        tile.unlink()
    elif defect == "wrong-size":
        Image.new("RGB", (256, 256)).save(tile, "JPEG")
    elif defect == "malformed":
        (tmp_path / "slide.dzi").write_text("broken")
    else:
        descriptor = tmp_path / "slide.dzi"
        descriptor.write_text(descriptor.read_text().replace('Format="jpg"', 'Format="../jpg"'))
    with pytest.raises(PublicationError, match="THUMBNAIL_RECOVERY_UNAVAILABLE"):
        recovered_thumbnail(tmp_path)
    assert not (tmp_path / "thumbnail.jpg").exists()


@pytest.mark.parametrize("exhausted", [False, True])
def test_offline_reconciliation_repairs_existing_grants_and_accounting(
    tmp_path: Path, exhausted: bool
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'db.sqlite'}", data_root=tmp_path / "data"
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        slide = Slide(
            display_name="Legacy",
            original_filename="legacy.svs",
            source_bytes=100,
            state=SlideState.PUBLISHED,
            published_at=datetime.now(UTC),
            privacy_status="passed",
        )
        database.add(slide)
        database.flush()
        database.add(
            PublicationGrant(slide_id=slide.id, source_type="individual", source_id=slide.id)
        )
        database.commit()
        slide_id, public_id, version = slide.id, slide.public_id, delivery_version(slide)
    source = layout.for_slide(slide_id).private_derivative
    pyramid(source)
    public = publish_derivative(layout, slide_id, public_id)
    individual = publish_individual_derivative(layout, slide_id, public_id, version)
    descriptor = (individual / "slide.dzi").read_bytes()
    if exhausted:
        layout.cap_bytes = 100 + measure_derivative(source).derivative_bytes
        with pytest.raises(InsufficientStorage):
            reconcile_storage(factory, layout, repair_missing_thumbnails=True)
        assert not (source / "thumbnail.jpg").exists()
        return
    summary = reconcile_storage(factory, layout, repair_missing_thumbnails=True)
    assert summary.repaired_thumbnail_count == 1
    assert (individual / "slide.dzi").read_bytes() == descriptor
    assert (public / "thumbnail.jpg").samefile(source / "thumbnail.jpg")
    assert (individual / "thumbnail.jpg").samefile(source / "thumbnail.jpg")
    with factory() as database:
        slide = database.get(Slide, slide_id)
        assert slide.thumbnail_filename == "thumbnail.jpg"
        assert slide.derivative_bytes == measure_derivative(source).derivative_bytes
        assert slide.derivative_file_count == 3
        assert delivery_version(slide, layout) == version
    assert (
        reconcile_storage(factory, layout, repair_missing_thumbnails=True).repaired_thumbnail_count
        == 0
    )
