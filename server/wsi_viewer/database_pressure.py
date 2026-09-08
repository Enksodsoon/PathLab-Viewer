"""Per-pool measured pressure counters, without retaining SQL or identifiers."""

import threading
import uuid
from typing import Any

from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.pool import PoolProxiedConnection, QueuePool


class PressureQueuePool(QueuePool):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._pressure_lock = threading.Lock()
        self._pressure_generation = uuid.uuid4().hex
        self._pool_timeouts = 0
        self._lock_timeouts = 0

    def connect(self) -> PoolProxiedConnection:
        try:
            return super().connect()
        except PoolTimeout:
            with self._pressure_lock:
                self._pool_timeouts += 1
            raise

    def record_lock_pressure(self) -> None:
        with self._pressure_lock:
            self._lock_timeouts += 1

    def pressure_snapshot(self) -> dict[str, str | int]:
        with self._pressure_lock:
            return {
                "counterGeneration": self._pressure_generation,
                "poolTimeouts": self._pool_timeouts,
                "lockTimeouts": self._lock_timeouts,
            }
