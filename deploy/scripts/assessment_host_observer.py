#!/usr/bin/env python3
"""Root-operated, read-only, loopback Assessment qualification observer."""

from __future__ import annotations

import argparse
import hmac
import json
import os
import re
import stat
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROLES = {"api", "classroom", "assessment", "postgres", "tile-service", "worker", "caddy", "tusd"}
PRESSURE_ROLES = {"api": (8000, 1), "classroom": (8001, 1), "assessment": (8002, 2)}
WORKER_SAMPLE = r"""
import json,os,sys,time,urllib.request
port,expected=map(int,sys.argv[1:])
token=os.environ.get("PATHLAB_CAPACITY_OBSERVER_TOKEN","")
assert len(token)>=32
seen={}; deadline=time.monotonic()+6
while time.monotonic()<deadline:
    request=urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/internal/capacity/pressure",
        headers={"X-PathLab-Observer-Token":token,"Connection":"close"})
    with urllib.request.urlopen(request,timeout=1) as response:
        sample=json.load(response)
    seen[sample["counterGeneration"]]=sample
    if len(seen)==expected:
        print(json.dumps(list(seen.values()))); break
    if len(seen)>expected: raise RuntimeError("worker replacement during sample")
else: raise RuntimeError("not all workers sampled")
"""


def protected_bytes(path: Path) -> bytes:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o077:
        raise ValueError("observer configuration must be a root-only regular file")
    if info.st_size > 65536:
        raise ValueError("observer configuration is too large")
    return path.read_bytes()


def capacity_lock() -> int:
    import fcntl

    descriptor = os.open("/run/pathlab-capacity-controller.lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("unsafe capacity lock")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def validate_config(value: dict[str, Any]) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value.get("releaseSha", "")):
        raise ValueError("exact release SHA required")
    containers = value.get("containers", {})
    if set(containers) != ROLES or len(set(containers.values())) != len(ROLES):
        raise ValueError("complete distinct container inventory required")
    if any(not re.fullmatch(r"[0-9a-f]{64}", item) for item in containers.values()):
        raise ValueError("containers must be pinned by full ID")
    for name in ("databaseUser", "databaseName"):
        if not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", value.get(name, "")):
            raise ValueError("invalid PostgreSQL identifier")
    live = Path(value.get("liveDir", ""))
    if not live.is_absolute() or live.resolve(strict=True) != live:
        raise ValueError("canonical release directory required")


def run(*args: str) -> str:
    result = subprocess.run(args, capture_output=True, text=True, timeout=12, check=False)
    if result.returncode or len(result.stdout) > 2_000_000:
        # Docker inspect may contain environment secrets. Never log raw output.
        raise RuntimeError("host measurement command failed")
    return result.stdout


def nonnegative_integer(value: Any) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("invalid measured counter")
    return value


def cpu_ticks(raw: str) -> tuple[int, int]:
    fields = raw.splitlines()[0].split()
    if fields[0] != "cpu" or len(fields) < 9:
        raise ValueError("CPU counters unavailable")
    # guest and guest_nice are already included in user and nice.
    values = [int(item) for item in fields[1:9]]
    if any(item < 0 for item in values):
        raise ValueError("invalid CPU counters")
    return sum(values), values[3] + values[4]


def memory_sample(raw: str) -> tuple[float, int]:
    values = {}
    for line in raw.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] == "kB":
            values[fields[0].rstrip(":")] = int(fields[1]) * 1024
    total, available = values["MemTotal"], values["MemAvailable"]
    swap_total, swap_free = values["SwapTotal"], values["SwapFree"]
    if not 0 <= available <= total or total == 0 or not 0 <= swap_free <= swap_total:
        raise ValueError("invalid memory counters")
    return 100 * (total - available) / total, swap_total - swap_free


def oom_kills(pid: int, identity: str) -> int:
    if nonnegative_integer(pid) == 0:
        raise ValueError("container process unavailable")
    groups = (Path("/proc") / str(pid) / "cgroup").read_text().splitlines()
    unified = [line[3:] for line in groups if line.startswith("0::")]
    if len(unified) != 1 or identity not in unified[0]:
        raise ValueError("container cgroup identity unavailable")
    root = Path("/sys/fs/cgroup")
    group = (root / unified[0].lstrip("/")).resolve(strict=True)
    if not group.is_relative_to(root):
        raise ValueError("invalid container cgroup path")
    events = dict(line.split() for line in (group / "memory.events").read_text().splitlines())
    return nonnegative_integer(int(events["oom_kill"]))


def pressure_sample(samples: list[dict[str, Any]], expected: int) -> tuple[set[str], int, int]:
    generations = set()
    pool = locks = 0
    if len(samples) != expected:
        raise ValueError("missing worker measurement")
    for item in samples:
        generation = item.get("counterGeneration", "")
        if not re.fullmatch(r"[0-9a-f]{32}", generation) or generation in generations:
            raise ValueError("invalid or duplicate worker generation")
        generations.add(generation)
        pool += nonnegative_integer(item.get("poolTimeouts"))
        locks += nonnegative_integer(item.get("lockTimeouts"))
    return generations, pool, locks


class Collector:
    def __init__(self, config: dict[str, Any]) -> None:
        validate_config(config)
        self.config = config
        self.generations: dict[str, set[str]] = {}
        self.previous: dict[str, tuple[int, int]] = {}

    def collect(self) -> dict[str, Any]:
        config = self.config
        release = (Path(config["liveDir"]) / ".pathlab-release").read_text().strip()
        if release != config["releaseSha"]:
            raise ValueError("deployed release changed")
        before = cpu_ticks(Path("/proc/stat").read_text())
        ids = config["containers"]
        inspected = json.loads(run("docker", "inspect", *ids.values()))
        by_id = {item["Id"]: item for item in inspected}
        restarts = 0
        for role, identity in ids.items():
            item = by_id[identity]
            state = item["State"]
            if not state["Running"] or state["Paused"] or state["Restarting"]:
                raise ValueError("container is not running normally")
            if "Health" in state and state["Health"]["Status"] != "healthy":
                raise ValueError("container health failed")
            if role not in {"postgres", "tusd"} and not item["Config"]["Image"].endswith(
                ":" + config["releaseSha"]
            ):
                raise ValueError("container release does not match")
            restarts += nonnegative_integer(item["RestartCount"])
        query = (
            "SELECT json_build_object('version',current_setting('server_version_num')::int,"
            "'maximum',current_setting('max_connections')::int,"
            "'current',(SELECT count(*) FROM pg_stat_activity))"
        )
        with ThreadPoolExecutor(max_workers=12) as executor:
            database = executor.submit(
                run,
                "docker",
                "exec",
                ids["postgres"],
                "psql",
                "-XAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                config["databaseUser"],
                "-d",
                config["databaseName"],
                "-c",
                query,
            )
            pressures = {
                role: executor.submit(
                    run,
                    "docker",
                    "exec",
                    ids[role],
                    "python",
                    "-c",
                    WORKER_SAMPLE,
                    str(port),
                    str(workers),
                )
                for role, (port, workers) in PRESSURE_ROLES.items()
            }
            oom_samples = [
                executor.submit(oom_kills, by_id[identity]["State"]["Pid"], identity)
                for identity in ids.values()
            ]
            facts = json.loads(database.result())
            if facts["version"] != 180006:
                raise ValueError("PostgreSQL 18.6 required")
            pool = locks = oom = 0
            for role, future in pressures.items():
                samples = json.loads(future.result())
                expected_role = "general" if role == "api" else role
                if any(item.get("serviceRole") != expected_role for item in samples):
                    raise ValueError("pressure service role mismatch")
                generations, current_pool, current_locks = pressure_sample(
                    samples, PRESSURE_ROLES[role][1]
                )
                if role in self.generations and generations != self.generations[role]:
                    raise ValueError("worker generation changed; restart qualification")
                previous = self.previous.get(role, (0, 0))
                if current_pool < previous[0] or current_locks < previous[1]:
                    raise ValueError("pressure counters decreased")
                self.generations[role] = generations
                self.previous[role] = current_pool, current_locks
                pool += current_pool
                locks += current_locks
            for future in oom_samples:
                oom += future.result()
        after = cpu_ticks(Path("/proc/stat").read_text())
        elapsed, idle = after[0] - before[0], after[1] - before[1]
        if elapsed <= 0 or not 0 <= idle <= elapsed:
            raise ValueError("CPU interval unavailable")
        memory, swap = memory_sample(Path("/proc/meminfo").read_text())
        return {
            "releaseSha": config["releaseSha"],
            "databaseEngine": "postgresql",
            "sampledAt": int(time.time()),
            "databaseMaxConnections": nonnegative_integer(facts["maximum"]),
            "databaseConnections": nonnegative_integer(facts["current"]),
            "poolTimeouts": pool,
            "lockTimeouts": locks,
            "pressureRoles": sorted(PRESSURE_ROLES),
            "workerGenerations": {key: sorted(value) for key, value in self.generations.items()},
            "assessmentWorkers": len(self.generations["assessment"]),
            "restarts": restarts,
            "oomKills": oom,
            "cpuPercent": 100 * (elapsed - idle) / elapsed,
            "memoryPercent": memory,
            "swapBytes": swap,
        }


def sample_response(
    path: str, authorization: str, token: bytes, value: dict[str, Any], now: float
) -> tuple[int, dict[str, Any]]:
    if path != "/sample" or not hmac.compare_digest(authorization.encode(), b"Bearer " + token):
        return 404, {"error": "NOT_FOUND"}
    if not 0 <= now - value.get("sampledAt", 0) <= 20:
        return 503, {"error": "MEASUREMENT_UNAVAILABLE"}
    return 200, value


def serve(collector: Collector, token: bytes, port: int, unix_socket: Path | None = None) -> None:
    state: dict[str, Any] = {}
    mutex = threading.Lock()

    def update() -> None:
        while True:
            try:
                result = collector.collect()
            except Exception as error:
                result = {"error": type(error).__name__}
            with mutex:
                state.clear()
                state.update(result)
            time.sleep(5)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            with mutex:
                value = dict(state)
            code, body = sample_response(
                self.path, self.headers.get("Authorization", ""), token, value, time.time()
            )
            payload = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format: str, *args: Any) -> None:
            pass

    if unix_socket is not None:
        from socketserver import ThreadingUnixStreamServer

        parent = unix_socket.parent
        info = parent.stat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or parent.resolve(strict=True) != parent
            or info.st_uid != 0
            or info.st_mode & 0o077
            or unix_socket.exists()
            or unix_socket.is_symlink()
        ):
            raise ValueError("observer socket requires an empty path in a root-only directory")
        os.umask(0o077)
        server = ThreadingUnixStreamServer(str(unix_socket), Handler)
    else:
        server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=update, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if unix_socket is not None:
            unix_socket.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--port", type=int, default=5331)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--unix-socket", type=Path)
    parser.add_argument("--cohost-production", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0 or not 1024 <= args.port <= 65535:
        raise ValueError("root and an unprivileged loopback port required")
    collector = Collector(json.loads(protected_bytes(args.config)))
    if args.once:
        if args.cohost_production:
            raise ValueError("cohost exclusion applies to the supervised campaign listener")
        print(json.dumps(collector.collect(), sort_keys=True))
        return 0
    if args.token_file is None:
        raise ValueError("dedicated host observer token file required")
    token = protected_bytes(args.token_file).strip()
    if not 32 <= len(token) <= 256 or not token.isascii():
        raise ValueError("invalid host observer token")
    descriptor = capacity_lock() if args.cohost_production else None
    try:
        serve(collector, token, args.port, args.unix_socket)
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
