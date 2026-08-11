import io
import os
from pathlib import Path

import numpy as np
import pytest
import tifffile
from PIL import Image
from wsi_viewer.ome_tile_index import (
    OmeTileIndexError,
    TileExtent,
    assemble_jpeg_tables,
    build_ome_tile_index,
    read_indexed_jpeg,
)

_REAL_FORGE_OME_PATH = os.environ.get("PATHLAB_REAL_FORGE_OME")
REAL_FORGE_OME = (
    Path(_REAL_FORGE_OME_PATH)
    if _REAL_FORGE_OME_PATH
    else Path("__pathlab_real_forge_ome_not_configured__")
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


def _abbreviated_jpeg() -> tuple[bytes, bytes, bytes]:
    output = io.BytesIO()
    Image.new("RGB", (32, 32), (120, 30, 210)).save(output, "JPEG", quality=82)
    standalone = output.getvalue()
    tables = bytearray(b"\xff\xd8")
    payload = bytearray(b"\xff\xd8")
    cursor = 2
    while cursor < len(standalone) - 2:
        assert standalone[cursor] == 0xFF
        marker = standalone[cursor + 1]
        length = int.from_bytes(standalone[cursor + 2 : cursor + 4], "big")
        segment = standalone[cursor : cursor + 2 + length]
        if marker in {0xDB, 0xC4}:
            tables.extend(segment)
        elif marker == 0xDA:
            payload.extend(standalone[cursor:])
            break
        else:
            payload.extend(segment)
        cursor += len(segment)
    tables.extend(b"\xff\xd9")
    return standalone, bytes(tables), bytes(payload)


def test_indexes_factor_two_jpeg_pyramid(tmp_path: Path) -> None:
    source = tmp_path / "factor-two.ome.tif"
    _write_jpeg_pyramid(source)

    index = build_ome_tile_index(source)

    assert [(level.width, level.height) for level in index.levels] == [(128, 96), (64, 48)]
    assert index.tile_width == 32
    assert index.tile_height == 32
    assert index.codec == "jpeg"
    assert index.pyramid_factors == (1, 2)


@pytest.mark.skipif(
    not REAL_FORGE_OME.is_file(),
    reason="set PATHLAB_REAL_FORGE_OME to run the optional real-file regression",
)
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


def test_assembles_shared_tables_into_a_decodable_jpeg() -> None:
    standalone, tables, payload = _abbreviated_jpeg()
    metadata_tables = (
        tables[:2]
        + b"\xff\xe0\x00\x04ok"
        + b"\xff\xdd\x00\x04\x00\x08"
        + tables[2:]
    )

    result = assemble_jpeg_tables(tables, payload, expected_width=32, expected_height=32)
    metadata_result = assemble_jpeg_tables(
        metadata_tables,
        payload,
        expected_width=32,
        expected_height=32,
    )

    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (32, 32)
        assert (
            image.convert("RGB").tobytes()
            == Image.open(io.BytesIO(standalone)).convert("RGB").tobytes()
        )
    assert metadata_result == result


def test_reads_an_soi_wrapped_abbreviated_tile_using_shared_tables(tmp_path: Path) -> None:
    standalone, tables, payload = _abbreviated_jpeg()
    source = tmp_path / "abbreviated.bin"
    source.write_bytes(payload)
    tile = TileExtent(
        offset=0,
        byte_count=len(payload),
        jpeg_tables=tables,
        standalone_jpeg=True,
    )

    result = read_indexed_jpeg(
        source,
        tile,
        expected_width=32,
        expected_height=32,
    )

    assert Image.open(io.BytesIO(result)).convert("RGB").tobytes() == Image.open(
        io.BytesIO(standalone)
    ).convert("RGB").tobytes()


def test_rejects_shared_tables_that_redefine_a_payload_table() -> None:
    _, tables, payload = _abbreviated_jpeg()
    duplicated = payload[:2] + tables[2:-2] + payload[2:]

    with pytest.raises(OmeTileIndexError, match="redefines"):
        assemble_jpeg_tables(tables, duplicated)


def test_rejects_malformed_jpeg_segment_length() -> None:
    malformed = b"\xff\xd8\xff\xdb\x00\x20\x00\xff\xd9"

    with pytest.raises(OmeTileIndexError, match="malformed"):
        assemble_jpeg_tables(malformed, b"\xff\xd8\xff\xd9")


def test_rejects_a_truncated_abbreviated_tile() -> None:
    _, tables, payload = _abbreviated_jpeg()

    with pytest.raises(OmeTileIndexError, match="complete JPEG"):
        assemble_jpeg_tables(tables, payload[:-2])


def test_rejects_missing_tables_wrong_geometry_and_progressive_jpeg() -> None:
    _, tables, payload = _abbreviated_jpeg()

    with pytest.raises(OmeTileIndexError, match="unavailable table"):
        assemble_jpeg_tables(b"\xff\xd8\xff\xd9", payload)
    with pytest.raises(OmeTileIndexError, match="width"):
        assemble_jpeg_tables(tables, payload, expected_width=31)
    progressive = payload.replace(b"\xff\xc0", b"\xff\xc2", 1)
    with pytest.raises(OmeTileIndexError, match="unsupported marker"):
        assemble_jpeg_tables(tables, progressive)


def test_rejects_tile_offset_past_physical_eof(tmp_path: Path) -> None:
    source = tmp_path / "truncated.ome.tif"
    _write_jpeg_pyramid(source)
    with tifffile.TiffFile(source) as tif:
        page = tif.series[0].levels[-1].pages[0]
        truncated_size = (
            max(
                offset + count
                for offset, count in zip(page.dataoffsets, page.databytecounts, strict=True)
            )
            - 1
        )
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
