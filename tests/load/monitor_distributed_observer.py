#!/usr/bin/env python3
"""Continuously fail a capacity run on host safety breach or observer loss."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

MAX_SAMPLE_GAP_MS = 15_000


def signal_protected_stop(
    session_id: str,
    run_id: str,
    plan_digest: str,
    safety_nonce: str,
    stage_name: str,
    causes: list[str],
) -> None:
    base_url = os.environ["PATHLAB_CLASSROOM_BASE_URL"].rstrip("/")
    with httpx.Client(base_url=base_url, timeout=10) as client:
        login = client.post(
            "/api/v1/auth/session",
            json={
                "username": os.environ["PATHLAB_CLASSROOM_ADMIN_USERNAME"],
                "password": os.environ["PATHLAB_CLASSROOM_ADMIN_PASSWORD"],
            },
        )
        login.raise_for_status()
        response = client.post(
            f"/api/v1/admin/classroom/sessions/{session_id}/synthetic-safety-stop",
            headers={
                "X-CSRF-Token": login.json()["csrfToken"],
                "X-PathLab-Synthetic-Run": run_id,
                "X-PathLab-Plan-Digest": plan_digest,
                "X-PathLab-Stage-Nonce": safety_nonce,
            },
            json={"stageName": stage_name, "causes": sorted(set(causes))},
        )
        response.raise_for_status()


def timeline_causes(timestamp_ms: int, previous_ms: int | None, plan_start_ms: int) -> list[str]:
    if previous_ms is None:
        return (
            ["observer-coverage"] if abs(timestamp_ms - plan_start_ms) > MAX_SAMPLE_GAP_MS else []
        )
    if timestamp_ms <= previous_ms:
        return ["observer-order"]
    if timestamp_ms - previous_ms > MAX_SAMPLE_GAP_MS:
        return ["observer-gap"]
    return []


def monitor(plan: dict[str, Any], observer: Path, done: Path, session_id: str) -> None:
    manifest_path = Path(os.environ["PATHLAB_CLASSROOM_STAGE_MANIFEST"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    recovery_ms = next(
        item["startEpochMs"] for item in plan["stages"] if item["name"] == "recovery-1200"
    )
    first_sample_deadline = plan["stages"][0]["startEpochMs"] / 1000 + 15
    offset = 0
    cpu_high = 0
    baseline_swap: int | None = None
    baseline_restarts: int | None = None
    previous_timestamp_ms: int | None = None
    last_sample = time.monotonic()
    signaled_stages: set[str] = set()
    while True:
        if observer.exists():
            with observer.open("r", encoding="utf-8") as stream:
                stream.seek(offset)
                while line := stream.readline():
                    if not line.endswith("\n"):
                        break
                    offset = stream.tell()
                    item = json.loads(line)
                    timestamp_ms = int(
                        datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")).timestamp()
                        * 1000
                    )
                    baseline_swap = (
                        int(item["swapUsedBytes"]) if baseline_swap is None else baseline_swap
                    )
                    baseline_restarts = (
                        int(item["restartCount"])
                        if baseline_restarts is None
                        else baseline_restarts
                    )
                    cpu_high = cpu_high + 1 if float(item["cpuPct"]) >= 80 else 0
                    causes = timeline_causes(
                        timestamp_ms, previous_timestamp_ms, plan["startEpochMs"]
                    )
                    if cpu_high >= 3:
                        causes.append("cpu-sustained")
                    if float(item["memoryPct"]) >= 85:
                        causes.append("memory")
                    if int(item["swapUsedBytes"]) > baseline_swap:
                        causes.append("swap-growth")
                    if item.get("oomKilled") is True:
                        causes.append("oom")
                    if float(item["diskFreePct"]) < 10:
                        causes.append("disk")
                    if timestamp_ms < recovery_ms:
                        if item.get("ready") is not True:
                            causes.append("readiness")
                        if item.get("servicesExact") is not True:
                            causes.append("services")
                        if int(item["restartCount"]) != baseline_restarts:
                            causes.append("restart")
                    if item.get("releaseSha") != plan["workflowSha"]:
                        causes.append("release-sha")
                    breakpoint = next(
                        (
                            stage
                            for stage in plan["stages"]
                            if stage["name"].startswith("breakpoint-")
                            and stage["holdStartEpochMs"] <= timestamp_ms <= stage["holdEndEpochMs"]
                        ),
                        None,
                    )
                    protected_causes = [
                        cause for cause in causes if cause in {"cpu-sustained", "memory"}
                    ]
                    if breakpoint is not None and protected_causes:
                        if breakpoint["name"] not in signaled_stages:
                            signal_protected_stop(
                                session_id,
                                str(plan["runId"]),
                                str(plan["planDigest"]),
                                str(manifest[breakpoint["name"]]["safetyNonce"]),
                                str(breakpoint["name"]),
                                protected_causes,
                            )
                            signaled_stages.add(breakpoint["name"])
                        causes = [cause for cause in causes if cause not in protected_causes]
                    if causes:
                        raise RuntimeError(",".join(causes))
                    previous_timestamp_ms = timestamp_ms
                    last_sample = time.monotonic()
        if done.exists():
            if done.read_text(encoding="utf-8").strip() != "0":
                raise RuntimeError("observer-process-failed")
            return
        if offset == 0 and time.time() <= first_sample_deadline:
            time.sleep(1)
            continue
        if time.monotonic() - last_sample > 30:
            raise RuntimeError("observer-stalled")
        time.sleep(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--observer", type=Path, required=True)
    parser.add_argument("--done", type=Path, required=True)
    parser.add_argument("--session-id", required=True)
    args = parser.parse_args()
    monitor(
        json.loads(args.plan.read_text(encoding="utf-8")),
        args.observer,
        args.done,
        args.session_id,
    )


if __name__ == "__main__":
    main()
