"""Bounded protocol-level classroom SSE harness (never targets production by default)."""

import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass

import httpx


@dataclass
class Result:
    join_ms: float
    stream_ready_ms: float
    events: int
    error: str | None = None


async def participant(
    base_url: str,
    join_code: str,
    duration_seconds: float,
    sequence: int,
) -> Result:
    await asyncio.sleep(sequence * 0.01)
    async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:
        joined_at = time.perf_counter()
        response = await client.post("/api/v1/classroom/join", json={"joinCode": join_code})
        response.raise_for_status()
        session_id = response.json()["sessionId"]
        join_ms = (time.perf_counter() - joined_at) * 1000
        opened_at = time.perf_counter()
        events = 0
        ready_ms: float | None = None
        try:
            async with client.stream(
                "GET", f"/api/v1/classroom/sessions/{session_id}/events"
            ) as stream:
                stream.raise_for_status()
                async with asyncio.timeout(20):
                    async for line in stream.aiter_lines():
                        if line.startswith("event:"):
                            events += 1
                            if line == "event: stream-ready":
                                ready_ms = (time.perf_counter() - opened_at) * 1000
                                break
                if ready_ms is None:
                    return Result(join_ms, 20_000, events, "stream_closed")
                await asyncio.sleep(duration_seconds)
                return Result(join_ms, ready_ms, events)
        except TimeoutError:
            return Result(join_ms, 20_000, events, "stream_ready_timeout")
    return Result(join_ms, duration_seconds * 1000, events, "stream_closed")


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


async def run() -> int:
    base_url = os.environ.get("PATHLAB_CLASSROOM_BASE_URL", "http://127.0.0.1:8000")
    join_code = os.environ.get("PATHLAB_CLASSROOM_JOIN_CODE", "")
    count = int(os.environ.get("PATHLAB_CLASSROOM_PARTICIPANTS", "30"))
    duration = float(os.environ.get("PATHLAB_CLASSROOM_DURATION_SECONDS", "30"))
    if not join_code:
        raise SystemExit("PATHLAB_CLASSROOM_JOIN_CODE is required")
    if count < 1 or count > 300 or duration <= 0:
        raise SystemExit("participants must be 1..300 and duration must be positive")
    started = time.perf_counter()
    gathered = await asyncio.gather(
        *(participant(base_url, join_code, duration, sequence) for sequence in range(count)),
        return_exceptions=True,
    )
    results = [item for item in gathered if isinstance(item, Result)]
    errors = [str(item) for item in gathered if isinstance(item, BaseException)]
    errors.extend(item.error for item in results if item.error)
    joins = [item.join_ms for item in results]
    ready = [item.stream_ready_ms for item in results]
    report = {
        "participantsRequested": count,
        "participantsCompleted": len(results),
        "durationSeconds": round(time.perf_counter() - started, 3),
        "joinMs": {
            "p50": round(statistics.median(joins), 3) if joins else 0,
            "p95": round(percentile(joins, 0.95), 3),
            "p99": round(percentile(joins, 0.99), 3),
        },
        "streamReadyMs": {
            "p50": round(statistics.median(ready), 3) if ready else 0,
            "p95": round(percentile(ready, 0.95), 3),
            "p99": round(percentile(ready, 0.99), 3),
        },
        "errors": errors,
    }
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
