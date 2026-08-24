from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"evidence input must be an object: {path}")
    return payload


def metric(summary: dict[str, Any], name: str, value: str) -> float:
    return float(summary.get("metrics", {}).get(name, {}).get("values", {}).get(value, 0))


def main() -> int:
    parser = argparse.ArgumentParser(description="Close protected Assessment capacity evidence")
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    gates: list[dict[str, Any]] = []

    def gate(name: str, passed: bool, observed: object) -> None:
        gates.append({"name": name, "passed": bool(passed), "observed": observed})

    shard_paths = sorted(args.artifacts.rglob("shard-*.json"))
    observer_paths = list(args.artifacts.rglob("observer.json"))
    canary_paths = list(args.artifacts.rglob("canaries.json"))
    cleanup_paths = list(args.artifacts.rglob("cleanup.json"))
    shards = [read(path) for path in shard_paths]
    observer = read(observer_paths[0]) if len(observer_paths) == 1 else {}
    canaries = read(canary_paths[0]) if len(canary_paths) == 1 else {}
    cleanup = read(cleanup_paths[0]) if len(cleanup_paths) == 1 else {}
    canary_values = {
        name: canaries.get(name) is True
        for name in (
            "offlineResume",
            "browserOutageRecovery",
            "aggregateVerified",
            "exportVerified",
        )
    }
    cleanup = {
        name: cleanup.get(name) is True
        for name in (
            "fixturesRemoved",
            "grantsRemoved",
            "sessionsRemoved",
            "administrationPurged",
        )
    }

    gate(
        "five_unique_shards",
        len(shards) == 5 and {item.get("shard") for item in shards} == set(range(1, 6)),
        len(shards),
    )
    gate(
        "exact_release",
        len(args.release_sha) == 40
        and all(item.get("exactRelease") == args.release_sha for item in shards),
        args.release_sha,
    )
    seats = sum(int(item.get("seats", 0)) for item in shards)
    gate("exact_500_seats", seats == 500, seats)
    hold = min((int(item.get("holdSeconds", 0)) for item in shards), default=0)
    gate("sixty_minute_hold", hold >= 3600, hold)
    autosaves = sum(int(metric(item, "assessment_autosaves", "count")) for item in shards)
    reconnects = sum(int(metric(item, "assessment_reconnects", "count")) for item in shards)
    submits = sum(int(metric(item, "assessment_submits", "count")) for item in shards)
    gate("twenty_saves_per_seat", autosaves == 10_000, autosaves)
    gate("ten_percent_reconnect", reconnects == 50, reconnects)
    gate("all_submitted", submits == 500, submits)
    autosave_p95 = max(
        (metric(item, "http_req_duration{name:autosave}", "p(95)") for item in shards), default=0
    )
    submit_p95 = max(
        (metric(item, "http_req_duration{name:submit}", "p(95)") for item in shards), default=0
    )
    tile_p95 = max(
        [metric(item, "http_req_duration{name:tile}", "p(95)") for item in shards]
        + [float(observer.get("tileP95Ms", 0))]
    )
    gate("autosave_p95", 0 < autosave_p95 <= 500, autosave_p95)
    gate("submit_p95", 0 < submit_p95 <= 1000, submit_p95)
    gate("tile_p95", 0 < tile_p95 < 500, tile_p95)
    database = {
        "engine": "unknown",
        "maxConnections": 0,
        "peakConnections": 0,
        "poolTimeouts": 0,
        "lockTimeouts": 0,
        **observer.get("database", {}),
    }
    services = {
        "assessmentWorkers": 0,
        "restarts": 0,
        "oomKills": 0,
        **observer.get("services", {}),
    }
    host = {
        "sustainedCpuPercent": 0,
        "peakMemoryPercent": 0,
        "swapBytes": 0,
        **observer.get("host", {}),
    }
    gate("postgresql", database.get("engine") == "postgresql", database.get("engine"))
    gate(
        "database_connections",
        database.get("maxConnections", 0) >= 32 and database.get("peakConnections", 99) < 26,
        database.get("peakConnections"),
    )
    gate(
        "no_database_timeouts",
        database.get("poolTimeouts") == 0 and database.get("lockTimeouts") == 0,
        database,
    )
    gate(
        "two_healthy_workers",
        services.get("assessmentWorkers") == 2
        and services.get("restarts") == 0
        and services.get("oomKills") == 0,
        services,
    )
    gate(
        "host_resources",
        host.get("sustainedCpuPercent", 100) < 80
        and host.get("peakMemoryPercent", 100) < 85
        and host.get("swapBytes", 1) == 0,
        host,
    )
    gate(
        "observer_watchdog",
        observer.get("sampleCount", 0) >= 230 and observer.get("errorCount") == 0,
        {"samples": observer.get("sampleCount"), "errors": observer.get("errorCount")},
    )
    for name, value in canary_values.items():
        gate(name, value, value)
    for name, value in cleanup.items():
        gate(name, value, value)

    prerequisites_present = (
        len(shard_paths) == 5
        and len(observer_paths) == len(canary_paths) == len(cleanup_paths) == 1
    )
    passed = all(item["passed"] for item in gates)
    status = (
        "SUCCESS"
        if prerequisites_present and passed
        else ("NEGATIVE" if prerequisites_present else "NOT_EVALUABLE")
    )
    evidence = {
        "status": status,
        "releaseSha": args.release_sha,
        "generatedAt": datetime.now(UTC).isoformat(),
        "campaign": {
            "shards": len(shards),
            "seats": seats,
            "holdSeconds": hold,
            "autosaves": autosaves,
            "reconnects": reconnects,
            "submits": submits,
            "submitStormSeconds": 10,
            "monitorSampleCount": observer.get("sampleCount", 0),
            **canary_values,
        },
        "database": database,
        "services": services,
        "latency": {
            "autosaveP95Ms": autosave_p95,
            "submitP95Ms": submit_p95,
            "tileP95Ms": tile_p95,
        },
        "host": host,
        "cleanup": cleanup,
        "gates": gates,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status,
                "failedGates": [item["name"] for item in gates if not item["passed"]],
            }
        )
    )
    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
