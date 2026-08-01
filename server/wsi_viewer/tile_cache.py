from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
import threading
import time
import uuid
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
        self._database = sqlite3.connect(
            self.root / "index.sqlite3",
            timeout=30,
            check_same_thread=False,
        )
        self._database.execute("PRAGMA journal_mode=DELETE")
        self._database.execute("PRAGMA synchronous=FULL")
        self._database.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                digest TEXT PRIMARY KEY,
                slide_sha256 TEXT NOT NULL,
                bytes INTEGER NOT NULL CHECK (bytes > 0),
                last_access_ns INTEGER NOT NULL
            )
            """
        )
        columns = {
            str(row[1])
            for row in self._database.execute("PRAGMA table_info(entries)").fetchall()
        }
        if "slide_sha256" not in columns:
            self._database.execute(
                "ALTER TABLE entries ADD COLUMN slide_sha256 TEXT NOT NULL DEFAULT ''"
            )
        self._database.execute(
            "CREATE INDEX IF NOT EXISTS ix_entries_lru ON entries(last_access_ns, digest)"
        )
        self._database.commit()
        self._hits = 0
        self._misses = 0
        self._evictions = 0
        self._coalesced = 0
        self._reconcile()

    def _path(self, digest: str) -> Path:
        if not HEX_SHA256.fullmatch(digest):
            raise TileCacheError("Invalid cache digest")
        return self.root / digest[:2] / f"{digest}.jpg"

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
            slide_hashes = {
                str(row[0]): str(row[1])
                for row in self._database.execute(
                    "SELECT digest, slide_sha256 FROM entries"
                ).fetchall()
            }
            known: dict[str, int] = {}
            for path in self.root.rglob("*"):
                if path.name == "index.sqlite3":
                    continue
                if path.suffix == ".tmp" or path.name.endswith(".tmp"):
                    if path.is_symlink() or self._safe_regular(path):
                        path.unlink(missing_ok=True)
                    continue
                if path.suffix != ".jpg":
                    continue
                digest = path.stem
                if not HEX_SHA256.fullmatch(digest) or not self._safe_regular(path):
                    path.unlink(missing_ok=True)
                    continue
                size = path.stat().st_size
                if size <= 0 or size > self.max_temp_bytes:
                    path.unlink(missing_ok=True)
                    continue
                known[digest] = size

            self._database.execute("DELETE FROM entries")
            now = time.time_ns()
            self._database.executemany(
                """
                INSERT INTO entries(digest, slide_sha256, bytes, last_access_ns)
                VALUES (?, ?, ?, ?)
                """,
                (
                    (digest, slide_hashes.get(digest, ""), size, now)
                    for digest, size in known.items()
                ),
            )
            self._database.commit()
            if self._tile_bytes() > self.max_bytes:
                self._evict_to(self.low_water_bytes)

    def _tile_bytes(self) -> int:
        row = self._database.execute(
            "SELECT COALESCE(SUM(bytes), 0) FROM entries"
        ).fetchone()
        return int(row[0]) if row is not None else 0

    def _tile_entries(self) -> int:
        row = self._database.execute("SELECT COUNT(*) FROM entries").fetchone()
        return int(row[0]) if row is not None else 0

    def get(self, key: TileKey) -> Path | None:
        digest = key.digest()
        with self._lock:
            row = self._database.execute(
                "SELECT bytes FROM entries WHERE digest = ?",
                (digest,),
            ).fetchone()
            if row is None:
                self._misses += 1
                return None
            path = self._path(digest)
            if not self._safe_regular(path) or path.stat().st_size != int(row[0]):
                path.unlink(missing_ok=True)
                self._database.execute("DELETE FROM entries WHERE digest = ?", (digest,))
                self._database.commit()
                self._misses += 1
                return None
            self._database.execute(
                "UPDATE entries SET last_access_ns = ? WHERE digest = ?",
                (time.time_ns(), digest),
            )
            self._database.commit()
            self._hits += 1
            return path

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
            existing = self._database.execute(
                "SELECT bytes FROM entries WHERE digest = ?",
                (digest,),
            ).fetchone()
            if existing is not None:
                return self._path(digest)
            current = self._tile_bytes()
            if current + len(payload) > self.max_bytes:
                self._evict_to(self.low_water_bytes)
                current = self._tile_bytes()
            if current + len(payload) > self.max_bytes:
                raise TileCacheError("Tile cache has insufficient bounded capacity")

            target = self._path(digest)
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
                self._database.execute(
                    """
                    INSERT INTO entries(
                        digest, slide_sha256, bytes, last_access_ns
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (digest, key.slide_sha256, len(payload), time.time_ns()),
                )
                self._database.commit()
            except Exception:
                temporary.unlink(missing_ok=True)
                target.unlink(missing_ok=True)
                self._database.rollback()
                raise
            return target

    def _evict_to(self, target_bytes: int) -> None:
        current = self._tile_bytes()
        while current > target_bytes:
            row = self._database.execute(
                "SELECT digest, bytes FROM entries ORDER BY last_access_ns, digest LIMIT 1"
            ).fetchone()
            if row is None:
                break
            digest, size = str(row[0]), int(row[1])
            self._path(digest).unlink(missing_ok=True)
            self._database.execute("DELETE FROM entries WHERE digest = ?", (digest,))
            current -= size
            self._evictions += 1
        self._database.commit()

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
            self._database.execute("DELETE FROM entries")
            self._database.commit()

    def purge_slide(self, slide_sha256: str) -> int:
        if not HEX_SHA256.fullmatch(slide_sha256):
            raise TileCacheError("Invalid slide hash")
        with self._lock:
            rows = self._database.execute(
                "SELECT digest FROM entries WHERE slide_sha256 = ?",
                (slide_sha256,),
            ).fetchall()
            for row in rows:
                self._path(str(row[0])).unlink(missing_ok=True)
            self._database.execute(
                "DELETE FROM entries WHERE slide_sha256 = ?",
                (slide_sha256,),
            )
            self._database.commit()
            return len(rows)

    def close(self) -> None:
        with self._lock:
            self._database.close()
