#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path
from typing import Any


class CertificationAbort(RuntimeError):
    pass


class Watchdog:
    def __init__(self) -> None:
        self.ready_failures = 0
        self.cpu_90_samples = 0
        self.cpu_85_samples = 0
        self.memory_90_samples = 0
        self.baseline_swap: int | None = None
        self.baseline_restarts: int | None = None
        self.request_points = 0
        self.request_failures = 0

    def observe_host(self, sample: dict[str, Any]) -> None:
        ready = sample.get("ready") is True
        self.ready_failures = 0 if ready else self.ready_failures + 1
        if self.ready_failures >= 2:
            raise CertificationAbort("readiness failed twice consecutively")

        cpu = float(sample.get("cpuPct", 100))
        self.cpu_90_samples = self.cpu_90_samples + 1 if cpu >= 90 else 0
        self.cpu_85_samples = self.cpu_85_samples + 1 if cpu >= 85 else 0
        if self.cpu_90_samples >= 3:
            raise CertificationAbort("CPU remained at or above 90% for 30 seconds")
        if self.cpu_85_samples >= 6:
            raise CertificationAbort("CPU remained at or above 85% for 60 seconds")

        memory = float(sample.get("memoryPct", 100))
        self.memory_90_samples = self.memory_90_samples + 1 if memory >= 90 else 0
        if self.memory_90_samples >= 3:
            raise CertificationAbort("memory remained at or above 90% for 30 seconds")

        swap = int(sample.get("swapUsedBytes", -1))
        restarts = int(sample.get("restartCount", -1))
        if self.baseline_swap is None:
            self.baseline_swap = swap
            self.baseline_restarts = restarts
        elif swap > self.baseline_swap:
            raise CertificationAbort("swap usage increased")
        elif restarts > (self.baseline_restarts or 0):
            raise CertificationAbort("a production container restarted")
        if sample.get("oomKilled") is not False:
            raise CertificationAbort("an OOM kill was reported")
        if sample.get("servicesExact") is not True:
            raise CertificationAbort("the exact production service set is not running")
        if float(sample.get("diskFreePct", 0)) < 10:
            raise CertificationAbort("disk free space fell below 10%")

    def observe_request(self, failed: float, *, elapsed_seconds: float) -> None:
        self.request_points += 1
        if failed:
            self.request_failures += 1
        if (
            elapsed_seconds >= 30
            and self.request_points >= 100
            and self.request_failures / self.request_points >= 0.01
        ):
            raise CertificationAbort("request failure rate reached 1% after warm-up")


def _consume_lines(path: Path, offset: int) -> tuple[list[dict[str, Any]], int]:
    if not path.exists():
        return [], offset
    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        stream.seek(offset)
        while True:
            record_offset = stream.tell()
            line = stream.readline()
            if not line:
                break
            if not line.endswith("\n"):
                stream.seek(record_offset)
                break
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise CertificationAbort("monitor stream contained malformed JSON") from error
            if not isinstance(value, dict):
                raise CertificationAbort("monitor stream contained a non-object record")
            records.append(value)
        return records, stream.tell()


def monitor(observer_path: Path, k6_path: Path, done_path: Path) -> None:
    watchdog = Watchdog()
    observer_offset = 0
    k6_offset = 0
    started = time.monotonic()
    while not done_path.exists():
        host_records, observer_offset = _consume_lines(observer_path, observer_offset)
        for record in host_records:
            watchdog.observe_host(record)
        k6_records, k6_offset = _consume_lines(k6_path, k6_offset)
        for record in k6_records:
            if record.get("type") != "Point" or record.get("metric") != "http_req_failed":
                continue
            data = record.get("data")
            if isinstance(data, dict):
                watchdog.observe_request(
                    float(data.get("value", 1)),
                    elapsed_seconds=time.monotonic() - started,
                )
        time.sleep(2)
    host_records, _ = _consume_lines(observer_path, observer_offset)
    for record in host_records:
        watchdog.observe_host(record)


def main() -> None:
    parser = argparse.ArgumentParser(description="Abort unsafe production capacity runs")
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--k6-json", type=Path, required=True)
    parser.add_argument("--done", type=Path, required=True)
    args = parser.parse_args()
    try:
        monitor(args.observer, args.k6_json, args.done)
    except CertificationAbort as error:
        print(f"CAPACITY_ABORT: {error}", flush=True)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
