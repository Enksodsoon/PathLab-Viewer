import os
import time
from pathlib import Path

from wsi_viewer.worker_health import HeartbeatWriter, check_heartbeat


def test_heartbeat_remains_fresh_during_normal_operation(tmp_path: Path) -> None:
    heartbeat = tmp_path / "worker-heartbeat"
    writer = HeartbeatWriter(heartbeat, interval_seconds=0.01)

    writer.start()
    try:
        deadline = time.monotonic() + 1
        while not heartbeat.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        first = heartbeat.read_text(encoding="ascii")
        time.sleep(0.04)
        second = heartbeat.read_text(encoding="ascii")
        assert second != first
        assert check_heartbeat(heartbeat, stale_after_seconds=1)
    finally:
        writer.stop()
    assert not list(tmp_path.glob(".worker-heartbeat.tmp-*"))


def test_missing_malformed_and_stale_heartbeats_fail(tmp_path: Path) -> None:
    heartbeat = tmp_path / "worker-heartbeat"
    assert not check_heartbeat(heartbeat, stale_after_seconds=45, now=100)

    heartbeat.write_text("not-a-timestamp", encoding="ascii")
    assert not check_heartbeat(heartbeat, stale_after_seconds=45, now=100)

    heartbeat.write_text("10", encoding="ascii")
    assert not check_heartbeat(heartbeat, stale_after_seconds=45, now=100)

    heartbeat.write_text("101", encoding="ascii")
    assert not check_heartbeat(heartbeat, stale_after_seconds=45, now=100)


def test_heartbeat_write_atomically_replaces_existing_file(tmp_path: Path) -> None:
    heartbeat = tmp_path / "worker-heartbeat"
    heartbeat.write_text("1", encoding="ascii")
    previous_inode = heartbeat.stat().st_ino
    writer = HeartbeatWriter(heartbeat, interval_seconds=10)

    writer.refresh()

    assert float(heartbeat.read_text(encoding="ascii")) > 1
    if os.name != "nt":
        assert heartbeat.stat().st_ino != previous_inode
