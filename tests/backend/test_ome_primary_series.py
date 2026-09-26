import hashlib
import io
from datetime import UTC, datetime, timedelta

import numpy as np
import tifffile
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from wsi_viewer.models import Base, DesktopCredential, DesktopIngest, User
from wsi_viewer.ome_ingest import desktop_ome_path, install_ome_ingest
from wsi_viewer.ome_tiles import (
    DynamicSlide,
    DziRequest,
    MemoryTileCache,
    OmeTileRenderer,
    load_ome_tile_index,
)
from wsi_viewer.storage import StorageLayout
from wsi_viewer.tile_cache import TileCache


def test_native_ingest_and_fallback_use_highest_resolution_primary_series(tmp_path):
    storage = StorageLayout(tmp_path / "data")
    source = desktop_ome_path(storage, "ingest")
    source.parent.mkdir(parents=True)
    with tifffile.TiffWriter(source, ome=True) as writer:
        for size, color in ((512, (20, 220, 30)), (1024, (120, 30, 210))):
            pixels = np.full((size, size, 3), color, dtype=np.uint8)
            writer.write(
                pixels,
                photometric="rgb",
                tile=(512, 512),
                compression="jpeg",
                compressionargs={"level": 75},
                metadata={"axes": "YXS", "PhysicalSizeX": 0.25, "PhysicalSizeY": 0.25},
            )
    original_bytes = source.read_bytes()
    with tifffile.TiffFile(source) as tif:
        page = tif.series[1].pages[0]
        offset, size = page.dataoffsets[0], page.databytecounts[0]
        original_tile = original_bytes[offset : offset + size]
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as database:
        user = User(username="admin", password_hash="hash")
        database.add(user)
        database.flush()
        credential = DesktopCredential(
            id="credential",
            user_id=user.id,
            device_name="Forge",
            scopes=["desktop:ingest"],
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        database.add(credential)
        ingest = DesktopIngest(
            id="ingest",
            credential_id=credential.id,
            display_name="Primary",
            artifact_revision_id="revision",
            package_length=len(original_bytes),
            package_sha256=hashlib.sha256(original_bytes).hexdigest(),
            manifest_sha256="f" * 64,
            ingest_mode="ome_dynamic_v1",
            ome_profile="ome-dynamic-v1",
            ome_width=1024,
            ome_height=1024,
            ome_downsample=1.0,
            ome_jpeg_quality=75,
            received_bytes=len(original_bytes),
            status="installing",
        )
        database.add(ingest)
        database.commit()
        install_ome_ingest(ingest, source, database, storage)
        database.refresh(ingest)
        assert ingest.status == "ready_private", ingest.error_code
        paths = storage.for_slide(ingest.slide_id)
        assert paths.original.read_bytes() == original_bytes
        index = load_ome_tile_index(paths.ome_index)
        assert (index.width, index.height) == (1024, 1024)
        renderer = OmeTileRenderer(
            TileCache(
                tmp_path / "cache",
                max_bytes=1024**2,
                low_water_bytes=512 * 1024,
                max_temp_bytes=512 * 1024,
            ),
            memory_cache=MemoryTileCache(512 * 1024),
        )
        slide = DynamicSlide(
            paths.original,
            paths.ome_index,
            index.source_sha256,
            index.width,
            index.height,
            75,
            index.quality_profile,
        )
        try:
            assert renderer.tile(slide, DziRequest(10, 0, 0)) == original_tile
            fallback = renderer.tile(slide, DziRequest(9, 0, 0))
            with Image.open(io.BytesIO(fallback)) as image:
                assert image.size == (512, 512)
                pixel = image.convert("RGB").getpixel((32, 32))
                assert (
                    max(
                        abs(actual - expected)
                        for actual, expected in zip(pixel, (120, 30, 210), strict=True)
                    )
                    <= 3
                )
        finally:
            renderer.close()
    engine.dispose()
