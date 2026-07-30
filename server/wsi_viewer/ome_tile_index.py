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


def read_indexed_jpeg(path: Path, tile: TileExtent) -> bytes:
    payload = _read_exact(path, offset=tile.offset, length=tile.byte_count)
    if tile.standalone_jpeg:
        return _validated_jpeg(payload)
    if tile.jpeg_tables is None:
        raise OmeTileIndexError("Indexed JPEG tables are unavailable")
    return assemble_jpeg_tables(tile.jpeg_tables, payload)


def _without_outer_markers(payload: bytes) -> bytes:
    start = 2 if payload.startswith(b"\xff\xd8") else 0
    end = -2 if payload.endswith(b"\xff\xd9") else len(payload)
    return payload[start:end]


def assemble_jpeg_tables(tables: bytes, payload: bytes) -> bytes:
    result = b"\xff\xd8" + _without_outer_markers(tables) + _without_outer_markers(payload)
    return _validated_jpeg(result + b"\xff\xd9")


def _validated_jpeg(payload: bytes) -> bytes:
    if len(payload) > 8 * 1024**2:
        raise OmeTileIndexError("Indexed JPEG exceeds the 8 MiB safety limit")
    if not payload.startswith(b"\xff\xd8") or not payload.endswith(b"\xff\xd9"):
        raise OmeTileIndexError("Indexed payload is not a complete JPEG")
    return payload
