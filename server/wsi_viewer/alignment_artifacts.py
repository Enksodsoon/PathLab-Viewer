"""Bounded atomic replacement of an already written private artifact."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def replace_pending(pending: Path, target: Path, *, deadline: float | None = None) -> None:
    """Retry transient Windows sharing denial without changing the pending bytes."""
    stop = None
    while True:
        try:
            os.replace(pending, target)
            return
        except OSError as error:
            if sys.platform != "win32" or getattr(error, "winerror", None) not in {5, 32, 33}:
                raise
            now = time.monotonic()
            if stop is None:
                stop = now + 0.5
                if deadline is not None:
                    stop = min(stop, deadline)
            remaining = stop - now
            if remaining <= 0:
                raise
            time.sleep(min(0.02, remaining))
            if time.monotonic() >= stop:
                raise
