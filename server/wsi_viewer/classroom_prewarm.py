import asyncio
import contextlib
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

MAX_PREWARM_SLIDES = 2
COMMON_LEVEL_COUNT = 3
COMMON_TILES_PER_LEVEL = 4
MAX_HOTSET_FILES = MAX_PREWARM_SLIDES * (
    2 + COMMON_LEVEL_COUNT * COMMON_TILES_PER_LEVEL
)
MAX_BYTES_PER_FILE = 64 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class PrewarmSlide:
    root: Path
    width: int
    height: int
    tile_size: int
    tile_format: str
    poster_filename: str | None = "thumbnail.jpg"


@dataclass(frozen=True)
class PrewarmResult:
    files_read: int
    files_missing: int
    bytes_read: int


def _center_coordinates(tile_count: int) -> tuple[int, ...]:
    if tile_count <= 1:
        return (0,)
    return tuple(sorted({(tile_count - 1) // 2, tile_count // 2}))


def hotset_paths(slides: Sequence[PrewarmSlide]) -> tuple[Path, ...]:
    """Derive a fixed current/next hotset without touching the filesystem."""

    paths: list[Path] = []
    for slide in slides[:MAX_PREWARM_SLIDES]:
        if slide.width <= 0 or slide.height <= 0 or slide.tile_size <= 0:
            continue
        tile_format = slide.tile_format.casefold()
        if tile_format not in {"jpg", "jpeg"}:
            continue
        paths.append(slide.root / "slide.dzi")
        poster = slide.poster_filename
        if (
            poster
            and Path(poster).name == poster
            and Path(poster).suffix.casefold() in {".jpg", ".jpeg"}
        ):
            paths.append(slide.root / poster)

        max_level = (max(slide.width, slide.height) - 1).bit_length()
        first_level = max(0, max_level - COMMON_LEVEL_COUNT + 1)
        for level in range(max_level, first_level - 1, -1):
            divisor = 1 << (max_level - level)
            scaled_width = (slide.width + divisor - 1) // divisor
            scaled_height = (slide.height + divisor - 1) // divisor
            columns = (scaled_width + slide.tile_size - 1) // slide.tile_size
            rows = (scaled_height + slide.tile_size - 1) // slide.tile_size
            for column in _center_coordinates(columns):
                for row in _center_coordinates(rows):
                    paths.append(
                        slide.root
                        / "slide_files"
                        / str(level)
                        / f"{column}_{row}.{tile_format}"
                    )
    return tuple(paths[:MAX_HOTSET_FILES])


def warm_hotset(
    paths: Sequence[Path],
    *,
    max_bytes_per_file: int = MAX_BYTES_PER_FILE,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> PrewarmResult:
    """Read bounded prefixes so Caddy can reuse the host page cache."""

    if max_bytes_per_file <= 0 or max_total_bytes <= 0:
        raise ValueError("Prewarm byte limits must be positive")
    files_read = 0
    files_missing = 0
    bytes_read = 0
    for path in paths[:MAX_HOTSET_FILES]:
        remaining = max_total_bytes - bytes_read
        if remaining <= 0:
            break
        try:
            with path.open("rb") as handle:
                payload = handle.read(min(max_bytes_per_file, remaining))
        except OSError:
            files_missing += 1
            continue
        files_read += 1
        bytes_read += len(payload)
    return PrewarmResult(files_read, files_missing, bytes_read)


class ClassroomPrewarmer:
    """One off-loop worker with one replaceable pending current/next window."""

    def __init__(
        self,
        *,
        reader: Callable[[tuple[Path, ...]], object] = warm_hotset,
    ) -> None:
        self._reader = reader
        self._lock = threading.Lock()
        self._pending: tuple[Path, ...] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self.requests = 0
        self.requests_coalesced = 0
        self.completed = 0
        self.failures = 0

    def start(self) -> None:
        if self._task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._task = asyncio.create_task(self._run())

    def request(self, slides: Sequence[PrewarmSlide]) -> None:
        paths = hotset_paths(slides)
        if not paths:
            return
        with self._lock:
            self.requests += 1
            if self._pending is not None:
                self.requests_coalesced += 1
            self._pending = paths
        loop = self._loop
        if loop is not None:
            loop.call_soon_threadsafe(self._wake.set)

    def clear(self) -> None:
        with self._lock:
            self._pending = None

    async def close(self) -> None:
        self.clear()
        task = self._task
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
            self._task = None
        self._loop = None

    async def _run(self) -> None:
        while True:
            self._wake.clear()
            with self._lock:
                paths = self._pending
                self._pending = None
            if paths is None:
                await self._wake.wait()
                continue
            try:
                await asyncio.to_thread(self._reader, paths)
            except Exception:
                self.failures += 1
            else:
                self.completed += 1
