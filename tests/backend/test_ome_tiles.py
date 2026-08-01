import io
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import tifffile
from PIL import Image
from wsi_viewer.ome_ingest import serialize_ome_tile_index
from wsi_viewer.ome_tile_index import OmeTileIndex, build_ome_tile_index, read_indexed_jpeg
from wsi_viewer.ome_tiles import (
    DynamicSlide,
    DziRequest,
    MemoryTileCache,
    OmeTileError,
    OmeTileRenderer,
)
from wsi_viewer.tile_cache import TileCache


def _slide(tmp_path: Path) -> tuple[DynamicSlide, OmeTileIndex]:
    source = tmp_path / "source.ome.tif"
    full = np.zeros((1024, 1024, 3), dtype=np.uint8)
    full[:512, :512] = (180, 30, 90)
    with tifffile.TiffWriter(source, ome=True, bigtiff=True) as writer:
        writer.write(
            full,
            metadata={"axes": "YXS"},
            photometric="ycbcr",
            compression="jpeg",
            tile=(512, 512),
            subifds=1,
        )
        writer.write(
            full[::2, ::2],
            photometric="ycbcr",
            compression="jpeg",
            tile=(512, 512),
            subfiletype=1,
        )
    index = build_ome_tile_index(source)
    index_path = tmp_path / "tile-index.json"
    index_path.write_bytes(serialize_ome_tile_index(index))
    return (
        DynamicSlide(
            source=source,
            index=index_path,
            sha256=index.source_sha256,
            width=index.width,
            height=index.height,
            quality=95,
            quality_profile="ome-dynamic-v1-q95",
        ),
        index,
    )


def _renderer(tmp_path: Path) -> OmeTileRenderer:
    return OmeTileRenderer(
        TileCache(
            tmp_path / "cache",
            max_bytes=4 * 1024**2,
            low_water_bytes=3 * 1024**2,
            max_temp_bytes=1024**2,
        ),
        memory_cache=MemoryTileCache(1024**2),
    )


def test_descriptor_preserves_exact_geometry(tmp_path: Path) -> None:
    slide, _ = _slide(tmp_path)
    renderer = _renderer(tmp_path)

    assert renderer.descriptor(slide) == (
        b'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        b'Format="jpg" Overlap="0" TileSize="512">'
        b'<Size Width="1024" Height="1024"/></Image>'
    )
    renderer.close()


def test_full_resolution_tile_uses_raw_indexed_jpeg(tmp_path: Path) -> None:
    slide, index = _slide(tmp_path)
    renderer = _renderer(tmp_path)

    result = renderer.tile(slide, DziRequest(level=10, column=0, row=0))

    assert result == read_indexed_jpeg(slide.source, index.levels[0].tiles[0])
    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (512, 512)
    assert renderer.stats().raw_tiles == 1
    assert renderer.stats().fallback_tiles == 0
    renderer.close()


def test_factor_two_level_uses_matching_raw_page(tmp_path: Path) -> None:
    slide, index = _slide(tmp_path)
    renderer = _renderer(tmp_path)

    result = renderer.tile(slide, DziRequest(level=9, column=0, row=0))

    assert result == read_indexed_jpeg(slide.source, index.levels[1].tiles[0])
    assert renderer.stats().raw_tiles == 1
    renderer.close()


def test_missing_ome_level_uses_bounded_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slide, _ = _slide(tmp_path)
    renderer = _renderer(tmp_path)
    fallback = b"\xff\xd8fallback\xff\xd9"
    monkeypatch.setattr(renderer, "_render_fallback", lambda *_: fallback)

    assert renderer.tile(slide, DziRequest(level=8, column=0, row=0)) == fallback
    assert renderer.stats().fallback_tiles == 1
    renderer.close()


def test_missing_ome_level_encodes_a_compatible_jpeg(tmp_path: Path) -> None:
    try:
        import pyvips  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("libvips runtime is unavailable")
    slide, _ = _slide(tmp_path)
    renderer = _renderer(tmp_path)

    result = renderer.tile(slide, DziRequest(level=8, column=0, row=0))

    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (256, 256)
        assert image.mode == "RGB"
    assert renderer.stats().fallback_tiles == 1
    renderer.close()


def test_fallback_jpeg_uses_debian_libvips_compatible_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slide, _ = _slide(tmp_path)
    renderer = _renderer(tmp_path)
    options: dict[str, object] = {}

    class FakeImage:
        width = 512
        height = 512

        def resize(self, _: float) -> "FakeImage":
            self.width = 256
            self.height = 256
            return self

        def crop(self, *_: int) -> "FakeImage":
            return self

        def jpegsave_buffer(self, **kwargs: object) -> bytes:
            options.update(kwargs)
            return b"\xff\xd8fallback\xff\xd9"

    fake_image = FakeImage()
    fake_pyvips = SimpleNamespace(
        Image=SimpleNamespace(tiffload=lambda *_args, **_kwargs: fake_image)
    )
    monkeypatch.setitem(sys.modules, "pyvips", fake_pyvips)

    assert renderer.tile(slide, DziRequest(level=8, column=0, row=0)).startswith(
        b"\xff\xd8"
    )
    assert options == {"Q": 95, "strip": True, "optimize_coding": True}
    renderer.close()


def test_rejects_out_of_bounds_coordinate_before_file_read(tmp_path: Path) -> None:
    slide, _ = _slide(tmp_path)
    renderer = _renderer(tmp_path)

    with pytest.raises(OmeTileError, match="coordinate"):
        renderer.tile(slide, DziRequest(level=10, column=2, row=0))
    with pytest.raises(OmeTileError, match="level"):
        renderer.tile(slide, DziRequest(level=11, column=0, row=0))
    renderer.close()


def test_memory_cache_evicts_without_exceeding_budget() -> None:
    cache = MemoryTileCache(10)
    cache.put("a", b"123456")
    cache.put("b", b"abcdef")

    assert cache.get("a") is None
    assert cache.get("b") == b"abcdef"
    assert cache.bytes_used == 6
