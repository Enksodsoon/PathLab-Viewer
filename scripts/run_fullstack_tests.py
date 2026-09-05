"""Run real browser journeys on disposable loopback services, never production."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]

# The wrapper cannot launch a command until its owner releases this stdin barrier.
# On Windows it has already been assigned to a kill-on-close Job Object then.
COMMAND_WRAPPER = """
import json
import subprocess
import sys

payload = json.loads(sys.stdin.buffer.readline())
child = subprocess.Popen(payload['command'], stdin=subprocess.PIPE)
data = payload.get('input')
child.communicate(None if data is None else data.encode('utf-8'))
raise SystemExit(child.returncode)
"""


class _BasicLimits(ctypes.Structure):
    _fields_ = [
        ("process_time", ctypes.c_int64),
        ("job_time", ctypes.c_int64),
        ("flags", ctypes.c_uint32),
        ("min_working_set", ctypes.c_size_t),
        ("max_working_set", ctypes.c_size_t),
        ("active_process_limit", ctypes.c_uint32),
        ("affinity", ctypes.c_size_t),
        ("priority", ctypes.c_uint32),
        ("scheduling", ctypes.c_uint32),
    ]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ("basic", _BasicLimits),
        ("io", ctypes.c_uint64 * 6),
        ("process_memory", ctypes.c_size_t),
        ("job_memory", ctypes.c_size_t),
        ("peak_process_memory", ctypes.c_size_t),
        ("peak_job_memory", ctypes.c_size_t),
    ]


class _JobAccounting(ctypes.Structure):
    _fields_ = [
        ("times", ctypes.c_int64 * 4),
        ("page_faults", ctypes.c_uint32),
        ("total_processes", ctypes.c_uint32),
        ("active_processes", ctypes.c_uint32),
        ("terminated_processes", ctypes.c_uint32),
    ]


class WindowsJob:
    def __init__(self) -> None:
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateJobObjectW": ([ctypes.c_void_p, ctypes.c_wchar_p], ctypes.c_void_p),
            "SetInformationJobObject": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32],
                ctypes.c_int,
            ),
            "QueryInformationJobObject": (
                [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p],
                ctypes.c_int,
            ),
            "OpenProcess": ([ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32], ctypes.c_void_p),
            "AssignProcessToJobObject": ([ctypes.c_void_p, ctypes.c_void_p], ctypes.c_int),
            "TerminateJobObject": ([ctypes.c_void_p, ctypes.c_uint32], ctypes.c_int),
            "IsProcessInJob": (
                [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p],
                ctypes.c_int,
            ),
            "WaitForSingleObject": ([ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32),
            "CloseHandle": ([ctypes.c_void_p], ctypes.c_int),
        }
        for name, (arguments, result) in signatures.items():
            function = getattr(self.kernel, name)
            function.argtypes = arguments
            function.restype = result
        self.handle = self.kernel.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = _ExtendedLimits()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE; no breakaway.
        if not self.kernel.SetInformationJobObject(
            self.handle,
            9,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process: subprocess.Popen[bytes]) -> None:
        handle = self.kernel.OpenProcess(0x0101, False, process.pid)  # SET_QUOTA | TERMINATE
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.kernel.AssignProcessToJobObject(self.handle, handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.kernel.CloseHandle(handle)

    def active_processes(self) -> int:
        accounting = _JobAccounting()
        if not self.kernel.QueryInformationJobObject(
            self.handle,
            1,
            ctypes.byref(accounting),
            ctypes.sizeof(accounting),
            None,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(accounting.active_processes)

    def terminate(self) -> None:
        if not self.kernel.TerminateJobObject(self.handle, 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def process_handles(self) -> list[int]:
        capacity = max(16, self.active_processes() + 4)
        while True:
            buffer = ctypes.create_string_buffer(8 + ctypes.sizeof(ctypes.c_size_t) * capacity)
            if self.kernel.QueryInformationJobObject(
                self.handle,
                3,
                buffer,
                ctypes.sizeof(buffer),
                None,
            ):
                break
            if ctypes.get_last_error() != 234 or capacity >= 65536:  # ERROR_MORE_DATA
                raise ctypes.WinError(ctypes.get_last_error())
            capacity *= 2
        count = ctypes.c_uint32.from_buffer(buffer, 4).value
        handles = []
        try:
            for pid in (ctypes.c_size_t * count).from_buffer(buffer, 8):
                handle = self.kernel.OpenProcess(0x100400, False, pid)  # SYNCHRONIZE | QUERY
                if not handle:
                    if ctypes.get_last_error() == 87:  # Already exited.
                        continue
                    raise ctypes.WinError(ctypes.get_last_error())
                handles.append(handle)
                member = ctypes.c_int()
                if not self.kernel.IsProcessInJob(handle, self.handle, ctypes.byref(member)):
                    raise ctypes.WinError(ctypes.get_last_error())
                if not member.value:
                    self.kernel.CloseHandle(handles.pop())
            return handles
        except BaseException:
            for handle in handles:
                self.kernel.CloseHandle(handle)
            raise

    def terminate_and_wait(self) -> None:
        # ActiveProcesses can become zero before asynchronous process teardown
        # releases inherited log handles. Retain handles to wait for real exit.
        handles = self.process_handles()
        try:
            self.terminate()
            deadline = time.monotonic() + 10
            while self.active_processes():
                if time.monotonic() >= deadline:
                    raise RuntimeError("Owned Windows job did not stop")
                time.sleep(0.02)
            for handle in handles:
                remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                if self.kernel.WaitForSingleObject(handle, remaining_ms) != 0:
                    raise RuntimeError("Owned Windows process did not exit")
        finally:
            for handle in handles:
                self.kernel.CloseHandle(handle)

    def close(self) -> None:
        if self.handle:
            handle, self.handle = self.handle, None
            if not self.kernel.CloseHandle(handle):
                raise ctypes.WinError(ctypes.get_last_error())


def _linux_subreaper(value: int | None = None) -> int | None:
    """Adopt/reap only our orphaned groups instead of relying on a container's PID 1."""
    if not sys.platform.startswith("linux"):
        return None
    library = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    if library.prctl(37, ctypes.byref(previous), 0, 0, 0) != 0:  # PR_GET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "Cannot inspect subprocess reaping policy")
    if value is not None and library.prctl(36, value, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), "Cannot set subprocess reaping policy")
    return previous.value


class ManagedProcess:
    def __init__(self, name: str, process: subprocess.Popen[bytes], job: WindowsJob | None) -> None:
        self.name = name
        self.process = process
        self.job = job
        self.closed = False

    def poll(self) -> int | None:
        return self.process.poll()

    def wait(self, timeout: float) -> int:
        return self.process.wait(timeout=timeout)

    def _group_exists(self) -> bool:
        # The wrapper has already been reaped. Linux subreaper mode lets us reap
        # orphaned descendants in this exact group without touching other children.
        try:
            while os.waitpid(-self.process.pid, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            pass
        try:
            os.killpg(self.process.pid, 0)
            return True
        except ProcessLookupError:
            return False

    def _signal_group(self, value: int) -> None:
        with suppress(ProcessLookupError):
            os.killpg(self.process.pid, value)

    def stop(self) -> None:
        if self.closed:
            return
        try:
            if self.job is not None:
                # This remains valid after the wrapper/command leader has exited.
                self.job.terminate_and_wait()
                self.process.wait(timeout=10)
            else:
                self._signal_group(signal.SIGTERM)
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self._signal_group(signal.SIGKILL)
                    self.process.wait(timeout=5)
                deadline = time.monotonic() + 2
                while self._group_exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                if self._group_exists():
                    self._signal_group(signal.SIGKILL)
                    deadline = time.monotonic() + 5
                    while self._group_exists() and time.monotonic() < deadline:
                        time.sleep(0.02)
                    if self._group_exists():
                        raise RuntimeError(f"Owned process group did not stop: {self.name}")
        finally:
            self.closed = True
            if self.process.stdin is not None:
                self.process.stdin.close()
            if self.job is not None:
                self.job.close()


class ProcessManager:
    """Own every setup, build, service and browser process through final cleanup."""

    def __init__(self, directory: Path, env: dict[str, str]) -> None:
        self.directory = directory
        self.env = env
        self.processes: list[ManagedProcess] = []
        self.logs: dict[str, BinaryIO] = {}
        self.closed = False
        self.previous_subreaper = _linux_subreaper(1)

    def start(
        self, name: str, command: list[str], *, input_text: str | None = None
    ) -> ManagedProcess:
        if self.closed or name in self.logs:
            raise RuntimeError("Process manager is closed or command name is duplicated")
        log = (self.directory / f"{name}.log").open("wb")
        self.logs[name] = log
        job = WindowsJob() if os.name == "nt" else None
        try:
            process = subprocess.Popen(
                [sys.executable, "-c", COMMAND_WRAPPER],
                stdin=subprocess.PIPE,
                stdout=log,
                stderr=log,
                cwd=self.directory,
                env=self.env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                start_new_session=os.name != "nt",
            )
        except BaseException:
            if job is not None:
                job.close()
            raise
        owned = ManagedProcess(name, process, job)
        self.processes.append(owned)
        try:
            if job is not None:
                job.assign(process)
            assert process.stdin is not None
            process.stdin.write(
                json.dumps({"command": command, "input": input_text}).encode() + b"\n"
            )
            process.stdin.close()
        except BaseException:
            # A failed assignment must never release the barrier or run the command.
            process.kill()
            process.wait(timeout=10)
            raise
        return owned

    def run(
        self, name: str, command: list[str], *, timeout: float, input_text: str | None = None
    ) -> None:
        owned = self.start(name, command, input_text=input_text)
        try:
            result = owned.wait(timeout)
        except BaseException:
            owned.stop()
            raise
        # Build/browser wrappers may exit while leaving a descendant. Reap their
        # complete tree at each command boundary, including non-zero outcomes.
        owned.stop()
        if result:
            raise RuntimeError(f"Isolated command {name} failed with exit code {result}")

    def dump_logs(self) -> None:
        for name, log in self.logs.items():
            if not log.closed:
                log.flush()
            content = (self.directory / f"{name}.log").read_text(errors="replace")[-3000:]
            for key in ("PATHLAB_SECRET_KEY", "PATHLAB_E2E_PASSWORD"):
                if self.env.get(key):
                    content = content.replace(self.env[key], "[redacted]")
            print(f"{name}: {content}", file=sys.stderr)

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        failures = []
        try:
            for owned in reversed(self.processes):
                try:
                    owned.stop()
                except BaseException as error:
                    failures.append(f"{owned.name}: {type(error).__name__}")
        finally:
            for log in self.logs.values():
                try:
                    log.close()
                except OSError as error:
                    failures.append(f"log: {type(error).__name__}")
            if self.previous_subreaper is not None:
                _linux_subreaper(self.previous_subreaper)
        if failures:
            raise RuntimeError("Isolated process cleanup failed: " + ", ".join(failures))


def isolated_environment(directory: Path) -> dict[str, str]:
    """Discard inherited application credentials, targets and feature switches."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("PATHLAB_", "LOAD_TEST_", "CAPACITY_"))
    }
    env.update(
        {
            "PYTHONPATH": str(ROOT / "server"),
            "PATHLAB_ENVIRONMENT": "test",
            "PATHLAB_DATABASE_URL": f"sqlite:///{(directory / 'database.sqlite3').as_posix()}",
            "PATHLAB_DATA_ROOT": str(directory / "data"),
            "PATHLAB_TUS_INTERNAL_UPLOAD_DIR": str(directory / "tus"),
            "PATHLAB_SECRET_KEY": secrets.token_hex(32),
            "PATHLAB_SECURE_COOKIES": "false",
            "PATHLAB_SERVICE_ROLE": "all",
            "PATHLAB_SERVE_PUBLIC_TILES": "true",
            "PATHLAB_CLASSROOM_ENABLED": "true",
            "PATHLAB_ADMIN_ANNOTATION_CANARY_ENABLED": "true",
            "PATHLAB_WORKER_HEARTBEAT_PATH": str(directory / "worker-heartbeat.json"),
            "PATHLAB_TILE_CACHE_ROOT": str(directory / "tile-cache"),
            "VIPS_CONCURRENCY": "1",
            "XDG_DATA_HOME": str(directory / "xdg-data"),
            "XDG_CONFIG_HOME": str(directory / "xdg-config"),
            "PATHLAB_E2E_USERNAME": "fixture-admin",
            "PATHLAB_E2E_PASSWORD": secrets.token_urlsafe(24),
        }
    )
    return env


def reserve_ports(count: int) -> list[int]:
    sockets = [socket.socket() for _ in range(count)]
    try:
        for item in sockets:
            item.bind(("127.0.0.1", 0))
        return [item.getsockname()[1] for item in sockets]
    finally:
        for item in sockets:
            item.close()


def local_caddyfile(
    directory: Path, api_port: int, tus_port: int, web_port: int, tile_port: int, edge_port: int
) -> str:
    """Reuse production authorization and tile handlers on disposable loopback targets."""
    production = (ROOT / "deploy/Caddyfile").read_text()
    body = production.split("{$DOMAIN} {", 1)[1].split("\n\thandle /assets/* {", 1)[0]
    body = body.replace("api:8000", f"127.0.0.1:{api_port}")
    body = body.replace("tusd:8080", f"127.0.0.1:{tus_port}")
    body = body.replace("tile-service:8090", f"127.0.0.1:{tile_port}")
    body = body.replace("{$PATHLAB_CLASSROOM_SERVICE_URL}", f"http://127.0.0.1:{api_port}")
    delivery = (directory / "data/delivery/individual").as_posix()
    body = body.replace("/pathlab-individual", f'"{delivery}"')
    return (
        "{\n admin off\n auto_https off\n}\n"
        f"http://127.0.0.1:{edge_port} {{\n bind 127.0.0.1\n"
        + body
        + f"\n handle {{\n reverse_proxy 127.0.0.1:{web_port}\n }}\n}}\n"
    )


def wait_ready(url: str, process: ManagedProcess) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("An isolated service exited before readiness")
        try:
            with urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (URLError, TimeoutError):
            pass
        time.sleep(0.2)
    raise RuntimeError("An isolated service did not become ready within 60 seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tusd", default=shutil.which("tusd"))
    parser.add_argument("--pnpm", default=shutil.which("pnpm"))
    parser.add_argument("--caddy", default=shutil.which("caddy"))
    args = parser.parse_args()
    if not args.tusd or not args.pnpm or not args.caddy:
        parser.error("tusd, pnpm and caddy must be installed or supplied by absolute path")
    with tempfile.TemporaryDirectory(prefix="pathlab-fullstack-") as temporary:
        directory = Path(temporary)
        env = isolated_environment(directory)
        api_port, tus_port, web_port, tile_port, edge_port = reserve_ports(5)
        api_url = f"http://127.0.0.1:{api_port}"
        env["PATHLAB_DEV_API_URL"] = api_url
        env["PATHLAB_DEV_TUS_URL"] = f"http://127.0.0.1:{tus_port}"
        env["PATHLAB_TILE_SERVICE_URL"] = f"http://127.0.0.1:{tile_port}"
        env["PATHLAB_E2E_BASE_URL"] = f"http://127.0.0.1:{edge_port}"
        env["PATHLAB_E2E_OME"] = str(directory / "synthetic.ome.tif")
        (directory / "tus").mkdir()
        # Settings reads .env relative to cwd. The empty disposable directory prevents
        # a developer's production .env from supplying any unoverridden setting.
        manager = ProcessManager(directory, env)
        services: list[ManagedProcess] = []
        try:
            manager.run(
                "native",
                [sys.executable, "-c", "import pyvips; assert pyvips.version(0) >= 8"],
                timeout=60,
            )
            manager.run(
                "schema",
                [
                    sys.executable,
                    "-c",
                    "from alembic.config import Config; from alembic import command; import sys; "
                    "config = Config(sys.argv[1]); "
                    'config.set_main_option("script_location", sys.argv[2]); '
                    'command.upgrade(config, "head")',
                    str(ROOT / "alembic.ini"),
                    str(ROOT / "migrations"),
                ],
                timeout=120,
            )
            manager.run(
                "fixture-admin",
                [
                    sys.executable,
                    "-c",
                    "from wsi_viewer.cli import main; main()",
                    "create-admin",
                    "--username",
                    env["PATHLAB_E2E_USERNAME"],
                    "--password-stdin",
                ],
                input_text=env["PATHLAB_E2E_PASSWORD"] + "\n",
                timeout=60,
            )
            manager.run(
                "fixture-ome",
                [
                    sys.executable,
                    str(ROOT / "tests/load/generate_synthetic_ome.py"),
                    "--output",
                    env["PATHLAB_E2E_OME"],
                    "--width",
                    "4096",
                    "--height",
                    "3072",
                ],
                timeout=120,
            )
            manager.run("build", [args.pnpm, "--dir", str(ROOT / "apps/web"), "build"], timeout=600)

            def service(name: str, command: list[str]) -> ManagedProcess:
                owned = manager.start(name, command)
                services.append(owned)
                return owned

            api = service(
                "api",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "wsi_viewer.main:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(api_port),
                ],
            )
            wait_ready(api_url + "/readyz", api)
            service("worker", [sys.executable, "-c", "from wsi_viewer.worker import main; main()"])
            tiles = service(
                "tiles",
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "wsi_viewer.tile_service:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(tile_port),
                ],
            )
            wait_ready(f"http://127.0.0.1:{tile_port}/readyz", tiles)
            tus = service(
                "tusd",
                [
                    args.tusd,
                    "-host=127.0.0.1",
                    f"-port={tus_port}",
                    "-base-path=/api/v1/uploads/",
                    f"-upload-dir={directory / 'tus'}",
                    "-hooks-enabled-events=pre-create,post-finish",
                    f"-hooks-http={api_url}/api/v1/internal/tus/hooks",
                ],
            )
            wait_ready(f"http://127.0.0.1:{tus_port}/", tus)
            web = service(
                "web",
                [
                    args.pnpm,
                    "--dir",
                    str(ROOT / "apps/web"),
                    "exec",
                    "vite",
                    "preview",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(web_port),
                    "--strictPort",
                ],
            )
            wait_ready(f"http://127.0.0.1:{web_port}/admin", web)
            caddy_config = directory / "Caddyfile"
            caddy_config.write_text(
                local_caddyfile(
                    directory,
                    api_port,
                    tus_port,
                    web_port,
                    tile_port,
                    edge_port,
                )
            )
            edge = service(
                "caddy",
                [args.caddy, "run", "--config", str(caddy_config), "--adapter", "caddyfile"],
            )
            wait_ready(env["PATHLAB_E2E_BASE_URL"] + "/readyz", edge)
            manager.run(
                "browser",
                [
                    args.pnpm,
                    "--dir",
                    str(ROOT / "apps/web"),
                    "exec",
                    "playwright",
                    "test",
                    "--config",
                    "playwright.fullstack.config.ts",
                ],
                timeout=600,
            )
            if any(process.poll() is not None for process in services):
                raise RuntimeError("An isolated service stopped during the browser journey")
        except BaseException:
            manager.dump_logs()
            raise
        finally:
            manager.close()
    # No PASS until process trees, logs, and the disposable directory are gone.
    print(json.dumps({"fullstack": "passed", "productionTouched": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
