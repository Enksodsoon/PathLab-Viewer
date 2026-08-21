from __future__ import annotations

import hashlib
import os
import re
import stat
import threading
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
PROFILE = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


class TileCacheError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TileKey:
    slide_sha256: str
    level: int
    column: int
    row: int
    quality_profile: str

    def digest(self) -> str:
        if not HEX_SHA256.fullmatch(self.slide_sha256):
            raise TileCacheError("Invalid slide hash")
        if min(self.level, self.column, self.row) < 0:
            raise TileCacheError("Invalid tile coordinate")
        if not PROFILE.fullmatch(self.quality_profile):
            raise TileCacheError("Invalid quality profile")
        material = (
            f"{self.slide_sha256}:{self.level}:{self.column}:"
            f"{self.row}:{self.quality_profile}"
        )
        return hashlib.sha256(material.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class TileCacheStats:
    tile_bytes: int
    tile_entries: int
    hits: int
    misses: int
    evictions: int
    coalesced: int


@dataclass(slots=True)
class _Flight:
    event: threading.Event
    path: Path | None = None
    error: BaseException | None = None


@dataclass(slots=True)
class _Entry:
    path: Path
    slide_sha256: str
    size: int
    last_access_ns: int


class TileCache:
    def __init__(
        self,
        root: Path,
        *,
        max_bytes: int,
        low_water_bytes: int,
        max_temp_bytes: int,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        if low_water_bytes < 0 or low_water_bytes >= max_bytes:
            raise ValueError("low_water_bytes must be below max_bytes")
        if max_temp_bytes <= 0 or max_temp_bytes > 8 * 1024**2:
            raise ValueError("max_temp_bytes must be between 1 byte and 8 MiB")
        self.root = root.resolve()
        self.max_bytes = max_bytes
        self.low_water_bytes = low_water_bytes
        self.max_temp_bytes = max_temp_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._flights_lock = threading.Lock()
        self._flights: dict[str, _Flight] = {}
        self._entries: OrderedDict[str, _Entry] = OrderedDict()
        self._tile_bytes_total = 0
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._coalesced = 0
        self._reconcile()

    def _path(self, digest: str, slide_sha256: str) -> Path:
        if not HEX_SHA256.fullmatch(digest):
            raise TileCacheError("Invalid cache digest")
        if not HEX_SHA256.fullmatch(slide_sha256):
            raise TileCacheError("Invalid slide hash")
        return self.root / slide_sha256[:2] / slide_sha256 / f"{digest}.jpg"

    @staticmethod
    def _safe_regular(path: Path) -> bool:
        try:
            return stat.S_ISREG(path.lstat().st_mode)
        except OSError:
            return False

    @staticmethod
    def _is_jpeg(payload: bytes) -> bool:
        return (
            len(payload) >= 4
            and payload.startswith(b"\xff\xd8")
            and payload.endswith(b"\xff\xd9")
        )

    def _reconcile(self) -> None:
        with self._lock:
            self._entries.clear()
            self._tile_bytes_total = 0
            known: list[tuple[str, _Entry]] = []
            for path in self.root.rglob("*"):
                if path.name in {"index.sqlite3", "index.sqlite3-wal", "index.sqlite3-shm"}:
                    if path.is_symlink() or self._safe_regular(path):
                        path.unlink(missing_ok=True)
                    continue
                if path.suffix == ".tmp" or path.name.endswith(".tmp"):
                    if path.is_symlink() or self._safe_regular(path):
                        path.unlink(missing_ok=True)
                    continue
                if path.suffix != ".jpg":
                    continue
                digest = path.stem
                try:
                    relative = path.relative_to(self.root)
                except ValueError:
                    relative = Path()
                parts = relative.parts
                slide_sha256 = parts[1] if len(parts) == 3 else ""
                valid_layout = (
                    len(parts) == 3
                    and HEX_SHA256.fullmatch(slide_sha256) is not None
                    and parts[0] == slide_sha256[:2]
                    and parts[2] == f"{digest}.jpg"
                )
                if (
                    not valid_layout
                    or not HEX_SHA256.fullmatch(digest)
                    or not self._safe_regular(path)
                ):
                    path.unlink(missing_ok=True)
                    continue
                details = path.stat()
                size = details.st_size
                if size <= 0 or size > self.max_temp_bytes:
                    path.unlink(missing_ok=True)
                    continue
                known.append(
                    (
                        digest,
                        _Entry(
                            path=path,
                            slide_sha256=slide_sha256,
                            size=size,
                            last_access_ns=details.st_mtime_ns,
                        ),
                    )
                )
                self._tile_bytes_total += size
            self._entries = OrderedDict(
                sorted(known, key=lambda item: (item[1].last_access_ns, item[0]))
            )
            if self._tile_bytes() > self.max_bytes:
                self._evict_to(self.low_water_bytes)

    def _tile_bytes(self) -> int:
        return self._tile_bytes_total

    def _tile_entries(self) -> int:
        return len(self._entries)

    def get(self, key: TileKey) -> Path | None:
        digest = key.digest()
        with self._lock:
            entry = self._entries.get(digest)
            if entry is None:
                self._misses += 1
                return None
            if (
                entry.slide_sha256 != key.slide_sha256
                or not self._safe_regular(entry.path)
                or entry.path.stat().st_size != entry.size
            ):
                entry.path.unlink(missing_ok=True)
                self._entries.pop(digest, None)
                self._tile_bytes_total -= entry.size
                self._misses += 1
                return None
            entry.last_access_ns = time.time_ns()
            self._entries.move_to_end(digest)
            self._hits += 1
            return entry.path

    def get_or_create(self, key: TileKey, producer: Callable[[], bytes]) -> Path:
        existing = self.get(key)
        if existing is not None:
            return existing
        digest = key.digest()
        with self._flights_lock:
            flight = self._flights.get(digest)
            leader = flight is None
            if flight is None:
                flight = _Flight(threading.Event())
                self._flights[digest] = flight
            else:
                self._coalesced += 1
        if not leader:
            flight.event.wait()
            if flight.error is not None:
                raise flight.error
            if flight.path is None:
                raise TileCacheError("Coalesced tile render completed without a result")
            return flight.path

        try:
            payload = producer()
            path = self._commit(key, digest, payload)
            flight.path = path
            return path
        except BaseException as error:
            flight.error = error
            raise
        finally:
            with self._flights_lock:
                self._flights.pop(digest, None)
                flight.event.set()

    def _commit(self, key: TileKey, digest: str, payload: bytes) -> Path:
        if not self._is_jpeg(payload):
            raise TileCacheError("Tile producer did not return a complete JPEG")
        if len(payload) > self.max_temp_bytes:
            raise TileCacheError("Tile exceeds the temporary-file limit")
        if len(payload) > self.max_bytes:
            raise TileCacheError("Tile exceeds the cache limit")

        with self._lock:
            existing = self._entries.get(digest)
            if existing is not None:
                return existing.path
            current = self._tile_bytes()
            if current + len(payload) > self.max_bytes:
                self._evict_to(self.low_water_bytes)
                current = self._tile_bytes()
            if current + len(payload) > self.max_bytes:
                raise TileCacheError("Tile cache has insufficient bounded capacity")

            target = self._path(digest, key.slide_sha256)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f"{digest}.{uuid.uuid4().hex}.tmp")
            descriptor = os.open(
                temporary,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb") as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                os.replace(temporary, target)
                self._entries[digest] = _Entry(
                    path=target,
                    slide_sha256=key.slide_sha256,
                    size=len(payload),
                    last_access_ns=time.time_ns(),
                )
                self._tile_bytes_total += len(payload)
            except Exception:
                temporary.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                removed = self._entries.pop(digest, None)
                if removed is not None:
                    self._tile_bytes_total -= removed.size
                raise
            return target

    def _evict_to(self, target_bytes: int) -> None:
        current = self._tile_bytes()
        while current > target_bytes:
            if not self._entries:
                break
            _, entry = self._entries.popitem(last=False)
            entry.path.unlink(missing_ok=True)
            self._tile_bytes_total -= entry.size
            current = self._tile_bytes_total
            self._evictions += 1

    def stats(self) -> TileCacheStats:
        with self._lock:
            return TileCacheStats(
                tile_bytes=self._tile_bytes(),
                tile_entries=self._tile_entries(),
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
                coalesced=self._coalesced,
            )

    def purge(self) -> None:
        with self._lock:
            for path in self.root.rglob("*.jpg"):
                if path.is_symlink() or self._safe_regular(path):
                    path.unlink(missing_ok=True)
            for path in self.root.rglob("*.tmp"):
                if path.is_symlink() or self._safe_regular(path):
                    path.unlink(missing_ok=True)
            self._entries.clear()
            self._tile_bytes_total = 0

    def purge_slide(self, slide_sha256: str) -> int:
        if not HEX_SHA256.fullmatch(slide_sha256):
            raise TileCacheError("Invalid slide hash")
        with self._lock:
            digests = [
                digest
                for digest, entry in self._entries.items()
                if entry.slide_sha256 == slide_sha256
            ]
            for digest in digests:
                entry = self._entries.pop(digest)
                entry.path.unlink(missing_ok=True)
                self._tile_bytes_total -= entry.size
            return len(digests)

    def close(self) -> None:
        return
