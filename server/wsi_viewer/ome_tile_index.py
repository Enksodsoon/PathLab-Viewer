from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
import tifffile


class OmeTileIndexError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TileExtent:
    offset: int
    byte_count: int
    jpeg_tables: bytes | None
    standalone_jpeg: bool


@dataclass(frozen=True, slots=True)
class OmeLevel:
    width: int
    height: int
    tiles_across: int
    tiles_down: int
    tiles: tuple[TileExtent, ...]


@dataclass(frozen=True, slots=True)
class OmeTileIndex:
    width: int
    height: int
    tile_width: int
    tile_height: int
    codec: Literal["jpeg"]
    levels: tuple[OmeLevel, ...]
    pyramid_factors: tuple[int, ...]
    standalone_jpeg: bool
    source_size: int
    source_mtime_ns: int
    source_sha256: str
    jpeg_quality: int = 75
    quality_profile: str = "ome-dynamic-v1-q75"


def _sha256(stream: BinaryIO) -> str:
    digest = hashlib.sha256()
    stream.seek(0)
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(block)
    return digest.hexdigest()


def _enum_name(value: object) -> str:
    return str(getattr(value, "name", value)).upper()


def _tile_markers(stream: BinaryIO, offset: int, byte_count: int) -> tuple[bytes, bytes]:
    stream.seek(offset)
    prefix = stream.read(2)
    stream.seek(offset + byte_count - 2)
    suffix = stream.read(2)
    return prefix, suffix


def _pyramid_factor(full_width: int, full_height: int, width: int, height: int) -> int:
    factor = max(1, round(max(full_width / width, full_height / height)))
    if factor & (factor - 1):
        raise OmeTileIndexError("OME pyramid levels must use power-of-two reductions")
    accepted_widths = {full_width // factor, (full_width + factor - 1) // factor}
    accepted_heights = {full_height // factor, (full_height + factor - 1) // factor}
    if width not in accepted_widths or height not in accepted_heights:
        raise OmeTileIndexError("OME pyramid geometry is inconsistent")
    return factor


def build_ome_tile_index(
    path: Path,
    *,
    expected_sha256: str | None = None,
) -> OmeTileIndex:
    try:
        before = path.lstat()
    except OSError as error:
        raise OmeTileIndexError("OME source is unavailable") from error
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISREG(before.st_mode):
        raise OmeTileIndexError("OME source must be a regular file")
    if before.st_size <= 0:
        raise OmeTileIndexError("OME source is empty")

    levels: list[OmeLevel] = []
    data_ranges: list[tuple[int, int]] = []
    all_standalone = True
    tile_width: int | None = None
    tile_height: int | None = None

    try:
        with path.open("rb") as stream:
            source_sha256 = _sha256(stream)
        if expected_sha256 is not None and source_sha256 != expected_sha256:
            raise OmeTileIndexError("OME source hash does not match")
        with path.open("rb") as stream, tifffile.TiffFile(path) as tif:
            if not tif.ome_metadata or not tif.series:
                raise OmeTileIndexError("A valid OME pyramid is required")
            series = tif.series[0]
            if not series.levels:
                raise OmeTileIndexError("An OME pyramid is required")

            for series_level in series.levels:
                page = series_level.pages[0]
                if page is None or not isinstance(page, tifffile.TiffPage):
                    raise OmeTileIndexError("OME pyramid page is invalid")
                if (
                    not page.is_tiled
                    or _enum_name(page.compression) != "JPEG"
                    or _enum_name(page.photometric) not in {"RGB", "YCBCR"}
                    or _enum_name(page.planarconfig) not in {"CONTIG", "1"}
                    or np.dtype(page.dtype) != np.dtype("uint8")
                    or int(page.samplesperpixel or 1) != 3
                ):
                    raise OmeTileIndexError("OME pyramid must be tiled JPEG RGB")

                current_tile_width = int(page.tilewidth)
                current_tile_height = int(page.tilelength)
                if tile_width is None:
                    tile_width = current_tile_width
                    tile_height = current_tile_height
                elif (current_tile_width, current_tile_height) != (tile_width, tile_height):
                    raise OmeTileIndexError("OME pyramid tile geometry is inconsistent")

                width = int(page.imagewidth)
                height = int(page.imagelength)
                tiles_across = (width + current_tile_width - 1) // current_tile_width
                tiles_down = (height + current_tile_height - 1) // current_tile_height
                offsets = tuple(int(value) for value in page.dataoffsets)
                byte_counts = tuple(int(value) for value in page.databytecounts)
                if (
                    not offsets
                    or len(offsets) != len(byte_counts)
                    or len(offsets) != tiles_across * tiles_down
                ):
                    raise OmeTileIndexError("OME pyramid tile inventory is inconsistent")

                jpeg_tables = bytes(page.jpegtables) if page.jpegtables else None
                tile_extents: list[TileExtent] = []
                for offset, byte_count in zip(offsets, byte_counts, strict=True):
                    if (
                        offset < 0
                        or byte_count < 4
                        or offset > before.st_size
                        or byte_count > before.st_size - offset
                    ):
                        raise OmeTileIndexError("OME tile extends past physical EOF")
                    prefix, suffix = _tile_markers(stream, offset, byte_count)
                    standalone = prefix == b"\xff\xd8" and suffix == b"\xff\xd9"
                    if not standalone and jpeg_tables is None:
                        raise OmeTileIndexError(
                            "OME JPEG tile is neither standalone nor backed by JPEG tables"
                        )
                    all_standalone = all_standalone and standalone
                    data_ranges.append((offset, offset + byte_count))
                    tile_extents.append(
                        TileExtent(
                            offset=offset,
                            byte_count=byte_count,
                            jpeg_tables=jpeg_tables,
                            standalone_jpeg=standalone,
                        )
                    )
                levels.append(
                    OmeLevel(
                        width=width,
                        height=height,
                        tiles_across=tiles_across,
                        tiles_down=tiles_down,
                        tiles=tuple(tile_extents),
                    )
                )
    except OmeTileIndexError:
        raise
    except (OSError, ValueError, tifffile.TiffFileError) as error:
        raise OmeTileIndexError("OME TIFF structure reaches past physical EOF") from error

    after = path.lstat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise OmeTileIndexError("OME source changed during indexing")

    ordered_ranges = sorted(data_ranges)
    for previous, current in zip(ordered_ranges, ordered_ranges[1:], strict=False):
        if current[0] < previous[1]:
            raise OmeTileIndexError("OME tile byte ranges overlap")

    first = levels[0]
    factors = tuple(
        _pyramid_factor(first.width, first.height, level.width, level.height)
        for level in levels
    )
    if factors != tuple(sorted(set(factors))):
        raise OmeTileIndexError("OME pyramid levels are duplicated or out of order")
    if tile_width is None or tile_height is None:
        raise OmeTileIndexError("OME pyramid has no tiles")
    return OmeTileIndex(
        width=first.width,
        height=first.height,
        tile_width=tile_width,
        tile_height=tile_height,
        codec="jpeg",
        levels=tuple(levels),
        pyramid_factors=factors,
        standalone_jpeg=all_standalone,
        source_size=before.st_size,
        source_mtime_ns=before.st_mtime_ns,
        source_sha256=source_sha256,
    )


def _read_exact(path: Path, *, offset: int, length: int) -> bytes:
    if offset < 0 or length <= 0:
        raise OmeTileIndexError("Indexed JPEG extent is invalid")
    if hasattr(os, "pread"):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            payload = bytes(os.pread(descriptor, length, offset))
        finally:
            os.close(descriptor)
    else:
        with path.open("rb") as stream:
            stream.seek(offset)
            payload = stream.read(length)
    if len(payload) != length:
        raise OmeTileIndexError("Indexed JPEG extends past physical EOF")
    return payload


def read_indexed_jpeg(
    path: Path,
    tile: TileExtent,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> bytes:
    payload = _read_exact(path, offset=tile.offset, length=tile.byte_count)
    if tile.standalone_jpeg:
        try:
            return _validated_jpeg(
                payload,
                expected_width=expected_width,
                expected_height=expected_height,
            )
        except OmeTileIndexError:
            if tile.jpeg_tables is None:
                raise
    if tile.jpeg_tables is None:
        raise OmeTileIndexError("Indexed JPEG tables are unavailable")
    return assemble_jpeg_tables(
        tile.jpeg_tables,
        payload,
        expected_width=expected_width,
        expected_height=expected_height,
    )


def _without_outer_markers(payload: bytes) -> bytes:
    start = 2 if payload.startswith(b"\xff\xd8") else 0
    end = -2 if payload.endswith(b"\xff\xd9") else len(payload)
    return payload[start:end]


def _jpeg_segments(payload: bytes, *, tables_only: bool) -> list[tuple[int, bytes]]:
    if len(payload) > 8 * 1024**2:
        raise OmeTileIndexError("Indexed JPEG exceeds the 8 MiB safety limit")
    if not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        raise OmeTileIndexError("Indexed payload is not a complete JPEG")
    segments: list[tuple[int, bytes]] = []
    cursor = 2
    while cursor < len(payload):
        if payload[cursor] != 0xFF:
            raise OmeTileIndexError("Indexed JPEG marker stream is malformed")
        while cursor < len(payload) and payload[cursor] == 0xFF:
            cursor += 1
        if cursor >= len(payload):
            raise OmeTileIndexError("Indexed JPEG marker stream is malformed")
        marker = payload[cursor]
        cursor += 1
        if marker == 0xD9:
            if cursor != len(payload):
                raise OmeTileIndexError("Indexed JPEG has trailing data")
            if not tables_only:
                raise OmeTileIndexError("Indexed JPEG has no image scan")
            return segments
        if marker == 0xDA:
            if tables_only or cursor + 2 > len(payload):
                raise OmeTileIndexError("Indexed JPEG tables are malformed")
            length = int.from_bytes(payload[cursor : cursor + 2], "big")
            if length < 2 or cursor + length > len(payload):
                raise OmeTileIndexError("Indexed JPEG scan header is malformed")
            segments.append((marker, payload[cursor + 2 : cursor + length]))
            cursor += length
            while cursor < len(payload):
                marker_start = payload.find(b"\xff", cursor)
                if marker_start < 0 or marker_start + 1 >= len(payload):
                    break
                following = payload[marker_start + 1]
                if following == 0x00 or 0xD0 <= following <= 0xD7:
                    cursor = marker_start + 2
                    continue
                if following == 0xD9 and marker_start + 2 == len(payload):
                    return segments
                raise OmeTileIndexError("Indexed JPEG entropy stream is malformed")
            raise OmeTileIndexError("Indexed JPEG entropy stream is truncated")
        if marker in {0x01, *range(0xD0, 0xD9)} or cursor + 2 > len(payload):
            raise OmeTileIndexError("Indexed JPEG marker stream is malformed")
        length = int.from_bytes(payload[cursor : cursor + 2], "big")
        if length < 2 or cursor + length > len(payload) - 2:
            raise OmeTileIndexError("Indexed JPEG segment is malformed")
        segments.append((marker, payload[cursor + 2 : cursor + length]))
        cursor += length
    raise OmeTileIndexError("Indexed JPEG marker stream is truncated")


def _table_ids(segments: list[tuple[int, bytes]]) -> tuple[set[int], set[tuple[int, int]]]:
    quantization: set[int] = set()
    huffman: set[tuple[int, int]] = set()
    for marker, data in segments:
        if marker == 0xDB:
            cursor = 0
            while cursor < len(data):
                precision_and_id = data[cursor]
                cursor += 1
                precision = precision_and_id >> 4
                table_id = precision_and_id & 0x0F
                size = 64 * (precision + 1)
                if precision > 1 or table_id > 3 or cursor + size > len(data):
                    raise OmeTileIndexError("Indexed JPEG quantization table is malformed")
                quantization.add(table_id)
                cursor += size
        elif marker == 0xC4:
            cursor = 0
            while cursor < len(data):
                if cursor + 17 > len(data):
                    raise OmeTileIndexError("Indexed JPEG Huffman table is malformed")
                class_and_id = data[cursor]
                counts = data[cursor + 1 : cursor + 17]
                cursor += 17
                table_class = class_and_id >> 4
                table_id = class_and_id & 0x0F
                symbol_count = sum(counts)
                if table_class > 1 or table_id > 3 or cursor + symbol_count > len(data):
                    raise OmeTileIndexError("Indexed JPEG Huffman table is malformed")
                huffman.add((table_class, table_id))
                cursor += symbol_count
    return quantization, huffman


def _validate_baseline(
    segments: list[tuple[int, bytes]],
    *,
    expected_width: int | None,
    expected_height: int | None,
) -> None:
    allowed_markers = {0xC0, 0xC4, 0xDA, 0xDB, 0xDD, 0xFE}
    if any(
        marker not in allowed_markers and not 0xE0 <= marker <= 0xEF
        for marker, _ in segments
    ):
        raise OmeTileIndexError("Indexed JPEG contains an unsupported marker")
    frames = [
        (marker, data)
        for marker, data in segments
        if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}
    ]
    if len(frames) != 1 or frames[0][0] != 0xC0:
        raise OmeTileIndexError("Indexed JPEG must use one baseline frame")
    frame = frames[0][1]
    if len(frame) < 6 or frame[0] != 8 or len(frame) != 6 + 3 * frame[5]:
        raise OmeTileIndexError("Indexed JPEG baseline frame is malformed")
    height = int.from_bytes(frame[1:3], "big")
    width = int.from_bytes(frame[3:5], "big")
    if frame[5] != 3:
        raise OmeTileIndexError("Indexed JPEG must contain three color components")
    scans = [data for marker, data in segments if marker == 0xDA]
    if len(scans) != 1:
        raise OmeTileIndexError("Indexed JPEG must contain one baseline scan")
    scan = scans[0]
    if not scan or len(scan) != 1 + 2 * scan[0] + 3 or scan[0] != frame[5]:
        raise OmeTileIndexError("Indexed JPEG baseline scan is malformed")
    quantization, huffman = _table_ids(segments)
    required_quantization = {frame[8 + 3 * component] for component in range(frame[5])}
    required_huffman = {
        (selector >> 4, selector & 0x0F)
        for selector in (scan[2 + 2 * component] for component in range(scan[0]))
    }
    if not required_quantization <= quantization or not required_huffman <= huffman:
        raise OmeTileIndexError("Indexed JPEG references an unavailable table")
    if expected_width is not None and width != expected_width:
        raise OmeTileIndexError("Indexed JPEG width does not match TIFF tile geometry")
    if expected_height is not None and height != expected_height:
        raise OmeTileIndexError("Indexed JPEG height does not match TIFF tile geometry")


def assemble_jpeg_tables(
    tables: bytes,
    payload: bytes,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> bytes:
    table_segments = _jpeg_segments(tables, tables_only=True)
    if any(
        marker not in {0xC4, 0xCC, 0xDB, 0xDD, 0xFE}
        and not 0xE0 <= marker <= 0xEF
        for marker, _ in table_segments
    ):
        raise OmeTileIndexError("Indexed JPEG tables contain an unsupported marker")
    payload_segments = _jpeg_segments(payload, tables_only=False)
    global_quantization, global_huffman = _table_ids(table_segments)
    local_quantization, local_huffman = _table_ids(payload_segments)
    if global_quantization & local_quantization or global_huffman & local_huffman:
        raise OmeTileIndexError("Indexed JPEG payload redefines a shared table")
    shared_tables = b"".join(
        b"\xff" + bytes((marker,)) + (len(data) + 2).to_bytes(2, "big") + data
        for marker, data in table_segments
        if marker in {0xC4, 0xDB}
    )
    result = b"\xff\xd8" + shared_tables + _without_outer_markers(payload)
    return _validated_jpeg(
        result + b"\xff\xd9",
        expected_width=expected_width,
        expected_height=expected_height,
    )


def _validated_jpeg(
    payload: bytes,
    *,
    expected_width: int | None = None,
    expected_height: int | None = None,
) -> bytes:
    segments = _jpeg_segments(payload, tables_only=False)
    _validate_baseline(
        segments,
        expected_width=expected_width,
        expected_height=expected_height,
    )
    return payload
