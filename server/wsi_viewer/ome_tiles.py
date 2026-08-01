from __future__ import annotations

import base64
import json
import math
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ome_tile_index import (
    OmeLevel,
    OmeTileIndex,
    TileExtent,
    read_indexed_jpeg,
)
from .tile_cache import TileCache, TileKey

MAX_DECODED_REGION_BYTES = 16 * 1024**2
MAX_INDEX_BYTES = 16 * 1024**2


class OmeTileError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DynamicSlide:
    source: Path
    index: Path
    sha256: str
    width: int
    height: int
    quality: int
    quality_profile: str


@dataclass(frozen=True, slots=True)
class DziRequest:
    level: int
    column: int
    row: int


@dataclass(frozen=True, slots=True)
class RendererStats:
    raw_tiles: int
    fallback_tiles: int
    memory_hits: int


class MemoryTileCache:
    def __init__(self, max_bytes: int) -> None:
        if max_bytes <= 0:
            raise ValueError("Memory tile cache must be positive")
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self._entries: OrderedDict[str, bytes] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> bytes | None:
        with self._lock:
            payload = self._entries.get(key)
            if payload is not None:
                self._entries.move_to_end(key)
            return payload

    def put(self, key: str, payload: bytes) -> None:
        if len(payload) > self.max_bytes:
            return
        with self._lock:
            previous = self._entries.pop(key, None)
            if previous is not None:
                self.bytes_used -= len(previous)
            while self._entries and self.bytes_used + len(payload) > self.max_bytes:
                _, evicted = self._entries.popitem(last=False)
                self.bytes_used -= len(evicted)
            self._entries[key] = payload
            self.bytes_used += len(payload)


def _integer(value: Any, label: str, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
        raise OmeTileError(f"Invalid OME tile index {label}")
    return value


def load_ome_tile_index(path: Path) -> OmeTileIndex:
    try:
        if path.stat().st_size > MAX_INDEX_BYTES:
            raise OmeTileError("OME tile index exceeds its bounded limit")
        document = json.loads(path.read_bytes())
        if document.get("schema") != "pathlab.ome-tile-index/v1":
            raise OmeTileError("Unsupported OME tile index")
        source = document["source"]
        level_documents = document["levels"]
        if not isinstance(level_documents, list) or not level_documents:
            raise OmeTileError("OME tile index has no levels")
        levels: list[OmeLevel] = []
        for level_document in level_documents:
            encoded_tables = level_document.get("jpegTables")
            tables = (
                base64.b64decode(encoded_tables, validate=True)
                if encoded_tables is not None
                else None
            )
            tiles = tuple(
                TileExtent(
                    offset=_integer(tile["offset"], "offset"),
                    byte_count=_integer(tile["byteCount"], "byte count", minimum=1),
                    jpeg_tables=tables,
                    standalone_jpeg=bool(tile["standaloneJpeg"]),
                )
                for tile in level_document["tiles"]
            )
            level = OmeLevel(
                width=_integer(level_document["width"], "width", minimum=1),
                height=_integer(level_document["height"], "height", minimum=1),
                tiles_across=_integer(
                    level_document["tilesAcross"], "tiles across", minimum=1
                ),
                tiles_down=_integer(
                    level_document["tilesDown"], "tiles down", minimum=1
                ),
                tiles=tiles,
            )
            if len(tiles) != level.tiles_across * level.tiles_down:
                raise OmeTileError("OME tile index inventory is inconsistent")
            levels.append(level)
        factors = tuple(
            _integer(value, "pyramid factor", minimum=1)
            for value in document["pyramidFactors"]
        )
        if len(factors) != len(levels):
            raise OmeTileError("OME tile index level factors are inconsistent")
        return OmeTileIndex(
            width=_integer(document["width"], "width", minimum=1),
            height=_integer(document["height"], "height", minimum=1),
            tile_width=_integer(document["tileWidth"], "tile width", minimum=1),
            tile_height=_integer(document["tileHeight"], "tile height", minimum=1),
            codec="jpeg",
            levels=tuple(levels),
            pyramid_factors=factors,
            standalone_jpeg=bool(document["standaloneJpeg"]),
            source_size=_integer(source["bytes"], "source bytes", minimum=1),
            source_mtime_ns=_integer(source["mtimeNs"], "source mtime"),
            source_sha256=str(source["sha256"]),
            jpeg_quality=_integer(
                document.get("jpegQuality", 75), "JPEG quality", minimum=1
            ),
            quality_profile=str(
                document.get("qualityProfile", "ome-dynamic-v1-q75")
            ),
        )
    except OmeTileError:
        raise
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise OmeTileError("OME tile index is invalid") from error


class OmeTileRenderer:
    def __init__(
        self,
        persistent_cache: TileCache,
        *,
        memory_cache: MemoryTileCache,
        render_concurrency: int = 2,
    ) -> None:
        if render_concurrency <= 0:
            raise ValueError("Tile render concurrency must be positive")
        self.persistent_cache = persistent_cache
        self.memory_cache = memory_cache
        self._render_semaphore = threading.BoundedSemaphore(render_concurrency)
        self._index_cache: OrderedDict[tuple[Path, int], OmeTileIndex] = OrderedDict()
        self._index_lock = threading.Lock()
        self._stats_lock = threading.Lock()
        self._raw_tiles = 0
        self._fallback_tiles = 0
        self._memory_hits = 0

    @staticmethod
    def descriptor(slide: DynamicSlide) -> bytes:
        if slide.width <= 0 or slide.height <= 0:
            raise OmeTileError("Invalid slide geometry")
        return (
            '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
            'Format="jpg" Overlap="0" TileSize="512">'
            f'<Size Width="{slide.width}" Height="{slide.height}"/></Image>'
        ).encode("ascii")

    def _index(self, slide: DynamicSlide) -> OmeTileIndex:
        try:
            index_mtime = slide.index.stat().st_mtime_ns
            source_stat = slide.source.stat()
        except OSError as error:
            raise OmeTileError("Dynamic OME source is unavailable") from error
        key = (slide.index.resolve(), index_mtime)
        with self._index_lock:
            index = self._index_cache.get(key)
            if index is None:
                index = load_ome_tile_index(slide.index)
                self._index_cache[key] = index
                self._index_cache.move_to_end(key)
                while len(self._index_cache) > 128:
                    self._index_cache.popitem(last=False)
        if (
            index.source_size != source_stat.st_size
            or index.source_mtime_ns != source_stat.st_mtime_ns
            or index.source_sha256 != slide.sha256
            or (index.width, index.height) != (slide.width, slide.height)
        ):
            raise OmeTileError("Dynamic OME identity does not match its index")
        return index

    @staticmethod
    def _geometry(slide: DynamicSlide, request: DziRequest) -> tuple[int, int, int]:
        maximum_level = math.ceil(math.log2(max(slide.width, slide.height)))
        if request.level < 0 or request.level > maximum_level:
            raise OmeTileError("DZI level is out of bounds")
        if request.column < 0 or request.row < 0:
            raise OmeTileError("DZI tile coordinate is out of bounds")
        factor = 2 ** (maximum_level - request.level)
        width = (slide.width + factor - 1) // factor
        height = (slide.height + factor - 1) // factor
        columns = (width + 511) // 512
        rows = (height + 511) // 512
        if request.column >= columns or request.row >= rows:
            raise OmeTileError("DZI tile coordinate is out of bounds")
        return factor, width, height

    @staticmethod
    def _raw_extent(
        index: OmeTileIndex,
        factor: int,
        width: int,
        height: int,
        request: DziRequest,
    ) -> TileExtent | None:
        try:
            level_index = index.pyramid_factors.index(factor)
        except ValueError:
            return None
        level = index.levels[level_index]
        if (
            (level.width, level.height) != (width, height)
            or index.tile_width != 512
            or index.tile_height != 512
        ):
            return None
        position = request.row * level.tiles_across + request.column
        if position >= len(level.tiles):
            return None
        return level.tiles[position]

    def tile(self, slide: DynamicSlide, request: DziRequest) -> bytes:
        factor, width, height = self._geometry(slide, request)
        index = self._index(slide)
        key = TileKey(
            slide.sha256,
            request.level,
            request.column,
            request.row,
            slide.quality_profile,
        )
        digest = key.digest()
        memory = self.memory_cache.get(digest)
        if memory is not None:
            with self._stats_lock:
                self._memory_hits += 1
            return memory

        def produce() -> bytes:
            with self._render_semaphore:
                extent = self._raw_extent(index, factor, width, height, request)
                if extent is not None:
                    payload = read_indexed_jpeg(slide.source, extent)
                    with self._stats_lock:
                        self._raw_tiles += 1
                    return payload
                payload = self._render_fallback(
                    slide,
                    index,
                    request,
                    factor,
                    width,
                    height,
                )
                with self._stats_lock:
                    self._fallback_tiles += 1
                return payload

        path = self.persistent_cache.get_or_create(key, produce)
        payload = path.read_bytes()
        if len(payload) > 8 * 1024**2:
            raise OmeTileError("Cached tile exceeds its bounded limit")
        self.memory_cache.put(digest, payload)
        return payload

    def _render_fallback(
        self,
        slide: DynamicSlide,
        index: OmeTileIndex,
        request: DziRequest,
        factor: int,
        width: int,
        height: int,
    ) -> bytes:
        candidate_indexes = [
            position
            for position, stored_factor in enumerate(index.pyramid_factors)
            if stored_factor <= factor
        ]
        if not candidate_indexes:
            raise OmeTileError("No bounded OME level can serve this tile")
        level_index = candidate_indexes[-1]
        stored_factor = index.pyramid_factors[level_index]
        scale = factor // stored_factor
        output_width = min(512, width - request.column * 512)
        output_height = min(512, height - request.row * 512)
        crop_width = output_width * scale
        crop_height = output_height * scale
        if (crop_width + 16) * (crop_height + 16) * 3 > MAX_DECODED_REGION_BYTES:
            raise OmeTileError("Requested tile exceeds the decoded-region limit")

        try:
            import pyvips  # type: ignore[import-untyped]

            arguments: dict[str, Any] = {"access": "random"}
            if level_index > 0:
                arguments["subifd"] = level_index - 1
            image = pyvips.Image.tiffload(str(slide.source), **arguments)
            if scale > 1:
                image = image.resize(1 / scale)
            left = request.column * 512
            top = request.row * 512
            output_width = min(output_width, image.width - left)
            output_height = min(output_height, image.height - top)
            if output_width <= 0 or output_height <= 0:
                raise OmeTileError("DZI tile coordinate is out of bounds")
            region = image.crop(left, top, output_width, output_height)
            payload = bytes(
                region.jpegsave_buffer(
                    Q=slide.quality,
                    strip=True,
                    optimize_coding=True,
                    keep="none",
                )
            )
        except OmeTileError:
            raise
        except Exception as error:
            raise OmeTileError("Bounded OME tile rendering failed") from error
        if (
            len(payload) > 8 * 1024**2
            or not payload.startswith(b"\xff\xd8")
            or not payload.endswith(b"\xff\xd9")
        ):
            raise OmeTileError("Fallback renderer produced an invalid JPEG")
        return payload

    def thumbnail(self, slide: DynamicSlide) -> bytes:
        maximum_level = math.ceil(math.log2(max(slide.width, slide.height)))
        level = maximum_level
        while level > 0:
            factor = 2 ** (maximum_level - level)
            if max(
                (slide.width + factor - 1) // factor,
                (slide.height + factor - 1) // factor,
            ) <= 512:
                break
            level -= 1
        return self.tile(slide, DziRequest(level=level, column=0, row=0))

    def stats(self) -> RendererStats:
        with self._stats_lock:
            return RendererStats(
                raw_tiles=self._raw_tiles,
                fallback_tiles=self._fallback_tiles,
                memory_hits=self._memory_hits,
            )

    def close(self) -> None:
        self.persistent_cache.close()
