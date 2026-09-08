import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import TimeoutError as PoolTimeout
from wsi_viewer.config import Settings
from wsi_viewer.database_pressure import PressureQueuePool
from wsi_viewer.main import create_app


def test_exhausted_pool_records_actual_timeout_and_preserves_exception() -> None:
    pool = PressureQueuePool(
        lambda: sqlite3.connect(":memory:"), pool_size=1, max_overflow=0, timeout=0.01
    )
    held = pool.connect()
    try:
        with pytest.raises(PoolTimeout):
            pool.connect()
        assert pool.pressure_snapshot()["poolTimeouts"] == 1
        assert pool.pressure_snapshot()["lockTimeouts"] == 0
    finally:
        held.close()
    recovered = pool.connect()
    recovered.close()
    assert pool.pressure_snapshot()["poolTimeouts"] == 1
    pool.dispose()


def test_concurrent_counts_are_not_lost_and_recreated_pool_has_new_generation() -> None:
    pool = PressureQueuePool(lambda: sqlite3.connect(":memory:"))
    with ThreadPoolExecutor(max_workers=8) as workers:
        list(workers.map(lambda _: pool.record_lock_pressure(), range(1000)))
    snapshot = pool.pressure_snapshot()
    assert snapshot["lockTimeouts"] == 1000
    replacement = pool.recreate()
    assert isinstance(replacement, PressureQueuePool)
    assert replacement.pressure_snapshot()["counterGeneration"] != snapshot["counterGeneration"]
    assert replacement.pressure_snapshot()["lockTimeouts"] == 0


def test_non_pool_failure_is_not_mislabeled() -> None:
    def broken_connection() -> None:
        raise RuntimeError("connection unavailable")

    pool = PressureQueuePool(broken_connection)
    with pytest.raises(RuntimeError, match="connection unavailable"):
        pool.connect()
    assert pool.pressure_snapshot()["poolTimeouts"] == 0


@pytest.mark.parametrize("role", ["general", "classroom", "assessment"])
def test_internal_counter_route_requires_a_dedicated_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, role: str
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'metrics.sqlite3'}",
        data_root=tmp_path / "data",
        service_role=role,
        capacity_observer_token="test-observer-token-32-characters-long",
    )
    pool = PressureQueuePool(lambda: sqlite3.connect(":memory:"))
    pool.record_lock_pressure()
    app = create_app(settings)
    monkeypatch.setattr("wsi_viewer.main.engine_for", lambda _: SimpleNamespace(pool=pool))
    with TestClient(app, raise_server_exceptions=False) as client:
        path = "/api/v1/internal/capacity/pressure"
        assert client.get(path).status_code == 404
        assert client.get(path, headers={"X-PathLab-Observer-Token": "wrong"}).status_code == 404
        result = client.get(path, headers={
            "X-PathLab-Observer-Token": settings.capacity_observer_token
        })
        assert result.status_code == 200
        assert result.json()["lockTimeouts"] == 1
        assert result.json()["serviceRole"] == role
        assert result.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("token,expected_status", [
    ("", 404), ("too-short", 404), ("valid-test-observer-token-32-characters", 503)
])
def test_unconfigured_or_unmeasured_counters_fail_closed(
    tmp_path: Path, token: str, expected_status: int
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'sqlite.sqlite3'}",
        data_root=tmp_path / "data",
        capacity_observer_token=token,
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/internal/capacity/pressure", headers={
            "X-PathLab-Observer-Token": token
        })
        assert response.status_code == expected_status
        assert "poolTimeouts" not in response.json()
