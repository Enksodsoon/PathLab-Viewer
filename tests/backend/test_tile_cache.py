import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from wsi_viewer.tile_cache import TileCache, TileCacheError, TileKey


def _key(column: int) -> TileKey:
    return TileKey("a" * 64, 17, column, 0, "ome-dynamic-v1-q95")


def test_coalesces_same_key_to_one_producer(tmp_path: Path) -> None:
    calls = 0
    calls_lock = threading.Lock()
    cache = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)

    def produce() -> bytes:
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return b"\xff\xd8" + b"x" * 20 + b"\xff\xd9"

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cache.get_or_create(_key(0), produce), range(8)))

    assert calls == 1
    assert len({result.read_bytes() for result in results}) == 1
    cache.close()


def test_evicts_oldest_entry_to_low_water_before_write(tmp_path: Path) -> None:
    cache = TileCache(tmp_path, max_bytes=100, low_water_bytes=60, max_temp_bytes=60)
    payload = b"\xff\xd8" + b"x" * 36 + b"\xff\xd9"
    first = cache.get_or_create(_key(0), lambda: payload)
    cache.get_or_create(_key(1), lambda: payload)
    cache.get_or_create(_key(2), lambda: payload)

    assert not first.exists()
    assert cache.stats().tile_bytes == 80
    assert cache.stats().evictions == 1
    cache.close()


def test_failed_producer_is_shared_and_not_cached(tmp_path: Path) -> None:
    cache = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)

    def fail() -> bytes:
        raise RuntimeError("render failed")

    with pytest.raises(RuntimeError, match="render failed"):
        cache.get_or_create(_key(0), fail)
    assert cache.get(_key(0)) is None
    cache.close()


def test_inflight_tile_is_not_visible_before_atomic_commit(tmp_path: Path) -> None:
    cache = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)
    producing = threading.Event()
    release = threading.Event()

    def produce() -> bytes:
        producing.set()
        assert release.wait(timeout=2)
        return b"\xff\xd8atomic\xff\xd9"

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(cache.get_or_create, _key(0), produce)
        assert producing.wait(timeout=2)
        assert not list(tmp_path.rglob("*.jpg"))
        release.set()
        assert future.result(timeout=2).read_bytes() == b"\xff\xd8atomic\xff\xd9"
    cache.close()


def test_rejects_oversized_or_invalid_jpeg_without_temp_leak(tmp_path: Path) -> None:
    cache = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=16)

    with pytest.raises(TileCacheError, match="temporary"):
        cache.get_or_create(_key(0), lambda: b"\xff\xd8" + b"x" * 20 + b"\xff\xd9")
    with pytest.raises(TileCacheError, match="JPEG"):
        cache.get_or_create(_key(1), lambda: b"not-jpeg")

    assert not list(tmp_path.rglob("*.tmp"))
    assert cache.stats().tile_bytes == 0
    cache.close()


def test_startup_reconciles_orphan_and_removes_stale_temp(tmp_path: Path) -> None:
    first = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)
    path = first.get_or_create(
        _key(0),
        lambda: b"\xff\xd8" + b"x" * 20 + b"\xff\xd9",
    )
    first.close()
    stale = path.with_suffix(".stale.tmp")
    stale.write_bytes(b"partial")

    reopened = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)

    assert reopened.get(_key(0)) == path
    assert not stale.exists()
    assert reopened.stats().tile_entries == 1
    reopened.close()


def test_startup_rejects_symlinked_cache_entry(tmp_path: Path) -> None:
    digest = _key(0).digest()
    shard = tmp_path / digest[:2]
    shard.mkdir(parents=True)
    outside = tmp_path.parent / f"{tmp_path.name}-outside.jpg"
    outside.write_bytes(b"\xff\xd8private\xff\xd9")
    linked = shard / f"{digest}.jpg"
    try:
        linked.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")

    cache = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)

    assert cache.get(_key(0)) is None
    assert outside.read_bytes() == b"\xff\xd8private\xff\xd9"
    cache.close()
    outside.unlink()


def test_purge_removes_tiles_but_keeps_cache_usable(tmp_path: Path) -> None:
    cache = TileCache(tmp_path, max_bytes=1024, low_water_bytes=768, max_temp_bytes=512)
    cache.get_or_create(_key(0), lambda: b"\xff\xd8x\xff\xd9")

    cache.purge()

    assert cache.stats().tile_entries == 0
    assert cache.get_or_create(_key(1), lambda: b"\xff\xd8y\xff\xd9").is_file()
    cache.close()
