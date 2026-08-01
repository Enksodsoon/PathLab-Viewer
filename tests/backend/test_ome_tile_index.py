from pathlib import Path

import numpy as np
import pytest
import tifffile
from wsi_viewer.ome_tile_index import (
    OmeTileIndexError,
    assemble_jpeg_tables,
    build_ome_tile_index,
    read_indexed_jpeg,
)

REAL_FORGE_OME = Path(
    r"C:\Users\enkso\.codex\worktrees\pathlab-forge-plan"
    r"\forge-f1-1\build\real-dzi-benchmark\input.ome.tif"
)


def _write_jpeg_pyramid(path: Path, *, pyramid_factor: int = 2) -> None:
    full = np.arange(96 * 128 * 3, dtype=np.uint8).reshape((96, 128, 3))
    reduced = full[::pyramid_factor, ::pyramid_factor]
    with tifffile.TiffWriter(path, ome=True, bigtiff=True) as writer:
        writer.write(
            full,
            metadata={"axes": "YXS"},
            photometric="ycbcr",
            compression="jpeg",
            tile=(32, 32),
            subifds=1,
        )
        writer.write(
            reduced,
            photometric="ycbcr",
            compression="jpeg",
            tile=(32, 32),
            subfiletype=1,
        )


def test_indexes_factor_two_jpeg_pyramid(tmp_path: Path) -> None:
    source = tmp_path / "factor-two.ome.tif"
    _write_jpeg_pyramid(source)

    index = build_ome_tile_index(source)

    assert [(level.width, level.height) for level in index.levels] == [(128, 96), (64, 48)]
    assert index.tile_width == 32
    assert index.tile_height == 32
    assert index.codec == "jpeg"
    assert index.pyramid_factors == (1, 2)


@pytest.mark.skipif(not REAL_FORGE_OME.is_file(), reason="real Forge OME fixture is unavailable")
def test_indexes_real_forge_factor_four_baseline() -> None:
    index = build_ome_tile_index(REAL_FORGE_OME)

    assert (index.width, index.height) == (110_563, 60_490)
    assert [(level.width, level.height) for level in index.levels] == [
        (110_563, 60_490),
        (27_640, 15_122),
        (6_910, 3_780),
        (1_727, 945),
    ]
    assert index.pyramid_factors == (1, 4, 16, 64)
    assert index.standalone_jpeg


def test_reads_a_standalone_indexed_jpeg(tmp_path: Path) -> None:
    source = tmp_path / "tiles.ome.tif"
    _write_jpeg_pyramid(source)
    tile = build_ome_tile_index(source).levels[0].tiles[0]

    payload = read_indexed_jpeg(source, tile)

    assert payload.startswith(b"\xff\xd8")
    assert payload.endswith(b"\xff\xd9")


def test_assembles_shared_tables_without_duplicate_markers() -> None:
    tables = b"\xff\xd8\xff\xdb\x00\x04\x00\x00\xff\xd9"
    payload = b"\xff\xd8\xff\xda\x00\x03\x00\x01\xff\xd9"

    result = assemble_jpeg_tables(tables, payload)

    assert result == b"\xff\xd8\xff\xdb\x00\x04\x00\x00\xff\xda\x00\x03\x00\x01\xff\xd9"


def test_rejects_tile_offset_past_physical_eof(tmp_path: Path) -> None:
    source = tmp_path / "truncated.ome.tif"
    _write_jpeg_pyramid(source)
    with tifffile.TiffFile(source) as tif:
        page = tif.series[0].levels[-1].pages[0]
        truncated_size = max(
            offset + count
            for offset, count in zip(page.dataoffsets, page.databytecounts, strict=True)
        ) - 1
    with source.open("r+b") as stream:
        stream.truncate(truncated_size)

    with pytest.raises(OmeTileIndexError, match="physical EOF|required"):
        build_ome_tile_index(source)


def test_rejects_non_jpeg_or_stripped_tiff(tmp_path: Path) -> None:
    source = tmp_path / "stripped.ome.tif"
    tifffile.imwrite(
        source,
        np.zeros((32, 48, 3), dtype=np.uint8),
        ome=True,
        metadata={"axes": "YXS"},
        photometric="rgb",
        compression="deflate",
        rowsperstrip=8,
    )

    with pytest.raises(OmeTileIndexError, match="tiled JPEG"):
        build_ome_tile_index(source)
