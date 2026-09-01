from __future__ import annotations

import argparse
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def fetch(url: str, headers: dict[str, str]) -> tuple[bytes, float]:
    started = time.perf_counter()
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - protected input
        if response.status != 200:
            raise RuntimeError(f"unexpected HTTP {response.status}")
        payload = response.read()
    return payload, (time.perf_counter() - started) * 1000


def fetch_json(url: str, headers: dict[str, str]) -> tuple[dict[str, Any], float]:
    payload, elapsed_ms = fetch(url, headers)
    return json.loads(payload.decode()), elapsed_ms


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * percent))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed PathLab Assessment campaign observer")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--administration-id", required=True)
    parser.add_argument("--tile-url", required=True)
    parser.add_argument("--host-observer-url", required=True)
    parser.add_argument("--start-epoch", required=True, type=int)
    parser.add_argument("--duration-seconds", type=int, default=3700)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    headers = {
        "Authorization": f"Bearer {os.environ['ASSESSMENT_OBSERVER_TOKEN']}",
        "Cookie": os.environ["ASSESSMENT_ADMIN_COOKIE"],
        "X-CSRF-Token": os.environ["ASSESSMENT_ADMIN_CSRF"],
    }
    wait_seconds = args.start_epoch - int(time.time())
    if wait_seconds < -30:
        raise RuntimeError("observer missed the synchronized campaign barrier")
    if wait_seconds > 0:
        time.sleep(wait_seconds)
    samples: list[dict[str, Any]] = []
    failures = 0
    deadline = time.monotonic() + args.duration_seconds
    while time.monotonic() < deadline:
        try:
            ready, ready_ms = fetch_json(f"{args.base_url}/readyz", headers)
            monitor, monitor_ms = fetch_json(
                f"{args.base_url}/api/v2/admin/assessment/administrations/"
                f"{args.administration_id}/monitor",
                headers,
            )
            _, tile_ms = fetch(args.tile_url, headers)
            host, _ = fetch_json(args.host_observer_url, headers)
            if ready.get("status") not in {"ok", "ready"}:
                raise RuntimeError("readiness failed during campaign")
            samples.append(
                {
                    "timestamp": int(time.time()),
                    "readyMs": ready_ms,
                    "monitorMs": monitor_ms,
                    "tileMs": tile_ms,
                    "monitor": monitor,
                    "host": host,
                }
            )
            failures = 0
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
            failures += 1
            samples.append({"timestamp": int(time.time()), "error": type(error).__name__})
            if failures >= 3:
                raise RuntimeError(
                    "observer watchdog recorded three consecutive failures"
                ) from error
        time.sleep(15)
    host_samples = [item["host"] for item in samples if "host" in item]
    output = {
        "sampleCount": len(samples),
        "errorCount": sum("error" in item for item in samples),
        "tileP95Ms": percentile([item["tileMs"] for item in samples if "tileMs" in item], 0.95),
        "monitorP95Ms": percentile(
            [item["monitorMs"] for item in samples if "monitorMs" in item], 0.95
        ),
        "database": {
            "engine": host_samples[-1].get("databaseEngine") if host_samples else None,
            "maxConnections": max(
                (item.get("databaseMaxConnections", 0) for item in host_samples), default=0
            ),
            "peakConnections": max(
                (item.get("databaseConnections", 0) for item in host_samples), default=0
            ),
            "poolTimeouts": max((item.get("poolTimeouts", 0) for item in host_samples), default=0),
            "lockTimeouts": max((item.get("lockTimeouts", 0) for item in host_samples), default=0),
        },
        "services": {
            "assessmentWorkers": min(
                (item.get("assessmentWorkers", 0) for item in host_samples), default=0
            ),
            "restarts": max((item.get("restarts", 0) for item in host_samples), default=0),
            "oomKills": max((item.get("oomKills", 0) for item in host_samples), default=0),
        },
        "host": {
            "sustainedCpuPercent": statistics.fmean(
                [item.get("cpuPercent", 0) for item in host_samples]
            )
            if host_samples
            else 0,
            "peakMemoryPercent": max(
                (item.get("memoryPercent", 0) for item in host_samples), default=0
            ),
            "swapBytes": max((item.get("swapBytes", 0) for item in host_samples), default=0),
        },
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
