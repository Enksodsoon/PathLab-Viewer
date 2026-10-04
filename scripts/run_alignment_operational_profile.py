"""Owned operational-only public crop profile, maximum7800s including cleanup.

This separate runner does not widen the existing1200s UI acceptance launcher.
The outer Windows Job owns the child, its services and their descendants.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

import httpx
from run_fullstack_tests import (
    ROOT,
    ProcessManager,
    isolated_environment,
    local_caddyfile,
    reserve_ports,
    wait_ready,
)

POLICY = "real-api-nine-serial-operational-jobs/1"
RESOURCE_ADMISSION = {
    "VALIS_DISK": ("var/engine-resources/valis/depth-save.pth",
                   "9c2ee4ded238892dfa51569941372601e35e4a74aa6f84ea80053d2ab1c07abe"),
    "VALIS_LIGHTGLUE": ("var/engine-resources/valis/disk_lightglue.pth",
                        "b5b21d47ea24f2c5e501aec9c91b9716e4c8c3429a4dc1e615c133c4c9378335"),
    "DEEPERHISTREG_SUPERPOINT": (
        "var/benchmark-sources/SuperGluePretrainedNetwork/models/weights/superpoint_v1.pth",
        "52b6708629640ca883673b5d5c097c4ddad37d8048b33f09c8ca0d69db12c40e"),
    "DEEPERHISTREG_SUPERGLUE": (
        "var/benchmark-sources/SuperGluePretrainedNetwork/models/weights/superglue_outdoor.pth",
        "2f5f5e9bb3febf07b69df633c4c3ff7a17f8af26a023aae2b9303d22339195bd"),
}


def operational_environment(directory: Path) -> dict[str, str]:
    env = isolated_environment(directory)
    env.update(OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               NUMEXPR_NUM_THREADS="1", ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS="1")
    for engine in ("VALIS", "WSIREG", "HISALIGN", "DEEPERHISTREG"):
        env[f"PATHLAB_ALIGNMENT_{engine}_ENABLED"] = "true"
    for name, (relative, expected) in RESOURCE_ADMISSION.items():
        resource = ROOT / relative
        if (resource.is_symlink() or not resource.is_file()
                or resource.stat().st_size > 512 * 1024**2):
            raise ValueError("The admitted offline resource is absent or outside bounds")
        with resource.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected:
            raise ValueError("The admitted offline resource digest changed")
        env[f"PATHLAB_ALIGNMENT_{name}_WEIGHTS_PATH"] = str(resource)
        env[f"PATHLAB_ALIGNMENT_{name}_WEIGHTS_SHA256"] = actual
    return env


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False), encoding="utf-8")


def child(args: argparse.Namespace) -> None:
    directory = args.child_root.resolve()
    if (
        not directory.name.startswith("pathlab-fullstack-operational-")
        or directory.is_symlink()
        or not (directory / "owned-marker.json").is_file()
        or os.environ.get("PATHLAB_ENVIRONMENT") != "test"
    ):
        raise ValueError("An outer owned disposable guardian is required")
    env = operational_environment(directory)
    admitted_runtime = ROOT / "var/valis-runtime/Scripts/python.exe"
    if (Path(args.runtime_python).resolve() != admitted_runtime.resolve()
            or not admitted_runtime.is_file()):
        raise ValueError("The admitted shared offline runtime is required")
    manager = ProcessManager(directory, env)
    services = []
    api, tus, web, tiles, edge = reserve_ports(5)
    api_url, base = f"http://127.0.0.1:{api}", f"http://127.0.0.1:{edge}"
    env.update(PATHLAB_DEV_API_URL=api_url, PATHLAB_DEV_TUS_URL=f"http://127.0.0.1:{tus}",
               PATHLAB_TILE_SERVICE_URL=f"http://127.0.0.1:{tiles}", PATHLAB_E2E_BASE_URL=base)
    output = args.report_dir.resolve()
    queue_output = output / "queue"
    queue_output.mkdir()
    (directory / "tus").mkdir()

    def service(name: str, command: list[str], url: str | None = None) -> None:
        process = manager.start(name, command)
        services.append({"name": name, "wrapperPid": process.process.pid,
                         "commandSha256": digest(command)})
        if url:
            wait_ready(url, process)

    try:
        manager.run("native", [sys.executable, "-c", "import pyvips; assert pyvips.version(0)>=8"],
                    timeout=60)
        manager.run("schema", [sys.executable, "-c",
                    "from alembic.config import Config; from alembic import command; import sys; "
                    "c=Config(sys.argv[1]); c.set_main_option('script_location',sys.argv[2]); "
                    "command.upgrade(c,'head')", str(ROOT / "alembic.ini"),
                    str(ROOT / "migrations")], timeout=120)
        manager.run("admin", [sys.executable, "-c", "from wsi_viewer.cli import main; main()",
                    "create-admin", "--username", env["PATHLAB_E2E_USERNAME"], "--password-stdin"],
                    input_text=env["PATHLAB_E2E_PASSWORD"] + "\n", timeout=60)
        manager.run("public-pair", [sys.executable, str(ROOT / "scripts/seed_frontend_qa.py"),
                    "alignment-operational-public-pair"], timeout=60)
        source = json.loads((directory / "public-pair.log").read_text().splitlines()[-1])
        write(output / "public-pair-proof.json", source)
        manager.run("build", [args.pnpm, "--dir", str(ROOT / "apps/web"), "build"], timeout=600)
        manager.run("admission-start", [args.runtime_python,
                    str(ROOT / "scripts/capture_alignment_admission.py"),
                    "--expected-head", args.expected_head,
                    "--output", str(output / "admission-start.json")], timeout=120)
        service("api", [args.runtime_python, "-m", "uvicorn", "wsi_viewer.main:app", "--host",
                         "127.0.0.1", "--port", str(api)], api_url + "/readyz")
        service("worker", [args.runtime_python, "-c", "from wsi_viewer.worker import main; main()"])
        service("tiles", [sys.executable, "-m", "uvicorn", "wsi_viewer.tile_service:app", "--host",
                           "127.0.0.1", "--port", str(tiles)], f"http://127.0.0.1:{tiles}/readyz")
        service("tusd", [args.tusd, "-host=127.0.0.1", f"-port={tus}",
                          "-base-path=/api/v1/uploads/", f"-upload-dir={directory / 'tus'}",
                          "-hooks-enabled-events=pre-create,post-finish",
                          f"-hooks-http={api_url}/api/v1/internal/tus/hooks"],
                f"http://127.0.0.1:{tus}/")
        service("web", [args.pnpm, "--dir", str(ROOT / "apps/web"), "exec", "vite", "preview",
                         "--host", "127.0.0.1", "--port", str(web), "--strictPort"],
                f"http://127.0.0.1:{web}/admin")
        caddy = directory / "Caddyfile"
        caddy.write_text(local_caddyfile(directory, api, tus, web, tiles, edge))
        service("caddy", [args.caddy, "run", "--config", str(caddy), "--adapter", "caddyfile"],
                base + "/readyz")
        with httpx.Client(base_url=base, follow_redirects=False,
                          trust_env=False, timeout=30) as client:
            response = client.post("/api/v1/auth/session", json={
                "username": env["PATHLAB_E2E_USERNAME"], "password": env["PATHLAB_E2E_PASSWORD"]})
            response.raise_for_status()
            cookie = "; ".join(f"{key}={value}" for key, value in client.cookies.items())
            headers = {"Cookie": cookie,
                       "X-CSRF-Token": response.json()["csrfToken"]}
            auth = directory / "private-auth.json"
            write(auth, headers)
            startup_started = time.monotonic()
            response = client.post("/api/v1/admin/comparison-sets", headers=headers, json={
                "name": "Public crop operational profile", "slideIds": source["slideIds"],
                "referenceSlideId": source["slideIds"][0]})
            response.raise_for_status()
            comparison = response.json()
            endpoint = f"/api/v1/admin/comparison-sets/{comparison['id']}"
            startup_ack = time.monotonic()
            deadline = startup_ack + 660
            startup_observations = []
            while time.monotonic() < deadline:
                job_response = client.get(endpoint + "/jobs")
                job_response.raise_for_status()
                jobs = job_response.json()
                startup_observations.append({"elapsedSeconds": time.monotonic() - startup_started,
                                             "jobs": [{"id": job["id"], "status": job["status"]}
                                                      for job in jobs]})
                terminal = {"succeeded", "failed", "failed_terminal", "cancelled"}
                if jobs and all(job["status"] in terminal for job in jobs):
                    break
                time.sleep(0.2)
            else:
                raise RuntimeError("Startup foreground/refinement jobs did not reach terminal")
            comparison = client.get(endpoint).json()
            write(output / "startup-comparison.json", comparison)
            write(output / "startup-jobs.json", {
                "scope": "Additional normal foreground/refinement setup, not timed recipe jobs",
                "requestAckSeconds": startup_ack - startup_started,
                "terminalObservationSeconds": time.monotonic() - startup_started,
                "jobs": jobs, "observations": startup_observations,
                "setupJobCount": len(jobs), "timedBenchmarkJobCount": 9,
            })
        configuration = {"label": "API configured operational defaults; not scientific settings",
                         "cpuThreads": 2, "memoryBytes": 7 * 1024**3, "pairBudgetSeconds": 600,
                         "threadEnvironment": {key: env.get(key) for key in (
                             "OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                             "NUMEXPR_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS",
                             "VIPS_CONCURRENCY")},
                         "runtimePython": args.runtime_python,
                         "sourceHead": args.expected_head,
                         "startupAdmissionSha256": hashlib.sha256(
                             (output / "admission-start.json").read_bytes()).hexdigest(),
                         "researchOnlyOffline": True,
                         "effectiveOptionalEnvironment": {key: value for key, value in env.items()
                                                          if key.startswith("PATHLAB_ALIGNMENT_")},
                         "startupJobIds": [job["id"] for job in jobs],
                         "startupJobsScope": "Additional normal foreground/refinement setup, "
                                             "separate from nine timed benchmark jobs"}
        ownership = {"guardian": json.loads((directory / "owned-marker.json").read_bytes()),
                     "services": services, "ports": [api, tus, web, tiles, edge],
                     "originalPortsUsed": False}
        write(output / "configuration-proof.json", configuration)
        write(output / "service-ownership-proof.json", ownership)
        guard = {"schema": POLICY, "ownedDisposable": True, "disposableRoot": str(directory),
                 "database": str(directory / "database.sqlite3"), "baseUrl": base,
                 "comparisonSetId": comparison["id"], "setVersion": comparison["version"],
                 "outputDirectory": str(queue_output), "sourceProofSha256": digest(source),
                 "configurationProofSha256": digest(configuration),
                 "serviceOwnershipProofSha256": digest(ownership),
                 "qualificationScope": "operational-only-no-anatomical-qualification"}
        guard_file = output / "private-guard.json"
        write(guard_file, guard)
        manager.run("queue", [sys.executable,
                    str(ROOT / "scripts/measure_alignment_operational_profile.py"),
                    "--base-url", base, "--database", guard["database"], "--guard", str(guard_file),
                    "--comparison-set-id", comparison["id"],
                    "--version", str(comparison["version"]),
                    "--auth-file", str(auth), "--output-dir", str(queue_output)], timeout=6000)
        manager.run("browser", [args.node,
                    str(ROOT / "apps/web/scripts/measure-alignment-operational-ui.mjs"),
                    "--queue", str(queue_output / "operational-queue.json"),
                    "--guard", str(guard_file), "--auth-file", str(auth),
                    "--output-dir", str(output / "browser")], timeout=1050)
        with httpx.Client(base_url=base, follow_redirects=False, trust_env=False,
                          headers=headers, timeout=30) as client:
            all_jobs_response = client.get(endpoint + "/jobs")
            all_jobs_response.raise_for_status()
            all_jobs = all_jobs_response.json()
            write(output / "all-service-jobs.json", {"actualTotalJobs": len(all_jobs),
                  "setupJobIds": [job["id"] for job in jobs], "timedRecipeJobsPlanned": 9,
                  "jobs": all_jobs})
        manager.run("admission-terminal", [args.runtime_python,
                    str(ROOT / "scripts/capture_alignment_admission.py"),
                    "--expected-head", args.expected_head,
                    "--output", str(output / "admission-terminal.json"),
                    "--reference", str(output / "admission-start.json")], timeout=120)
        terminal_admission = json.loads((output / "admission-terminal.json").read_bytes())
        if terminal_admission.get("unchangedFromReference") is not True:
            raise ValueError("Actual startup/terminal admission identity changed")
        write(output / "operational-completion.json", {
            "schema": "pathlab.real-api-operational-completion/1",
            "startupAdmissionSha256": configuration["startupAdmissionSha256"],
            "terminalAdmissionSha256": hashlib.sha256(
                (output / "admission-terminal.json").read_bytes()).hexdigest(),
            "admissionUnchanged": True, "actualTotalServiceJobs": len(all_jobs),
            "setupJobs": len(jobs), "timedRecipeJobsPlanned": 9,
            "queueReceiptSha256": hashlib.sha256(
                (queue_output / "operational-queue.json").read_bytes()).hexdigest(),
            "browserReceiptSha256": hashlib.sha256(
                (output / "browser/operational-ui.json").read_bytes()).hexdigest(),
            "qualificationScope": "operational-only-no-anatomical-qualification",
        })
    finally:
        manager.close()
        for log in directory.glob("*.log"):
            shutil.copyfile(log, output / log.name)
        write(output / "inner-cleanup.json", {"ownedServicesClosed": manager.closed,
                                              "serviceOwnership": services})


def main() -> int:
    lifetime_started = time.monotonic()
    hard_deadline = lifetime_started + 7800
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--pnpm", required=True)
    parser.add_argument("--tusd", required=True)
    parser.add_argument("--caddy", required=True)
    parser.add_argument("--node", required=True)
    parser.add_argument("--runtime-python", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--child-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    output = args.report_dir.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("A private output directory outside the repository is required")
    if args.child_root:
        # The outer guardian already created this exact output directory.
        marker = json.loads((args.child_root / "owned-marker.json").read_bytes())
        if marker.get("outputDirectory") != str(output) or not output.is_dir():
            raise ValueError("Child output differs from the guardian's private admission")
        child(args)
        return 0
    if output.exists():
        raise ValueError("A fresh private output directory is required")
    output.mkdir(parents=True)
    cleanup_completed = False
    guardian_closed = False
    temporary_removed = False
    try:
        with tempfile.TemporaryDirectory(prefix="pathlab-fullstack-operational-") as temporary:
            directory = Path(temporary)
            write(directory / "owned-marker.json", {
                "parentPid": os.getpid(), "createdAt": time.time(),
                "outputDirectory": str(output), "maximumLifetimeSeconds": 7800,
                "guardianStartMonotonic": lifetime_started,
                "hardDeadlineMonotonic": hard_deadline,
            })
            (directory / "package.json").write_text((ROOT / "package.json").read_text())
            manager = ProcessManager(directory, isolated_environment(directory))
            try:
                remaining = hard_deadline - time.monotonic() - 30
                if remaining <= 0:
                    raise TimeoutError("Owned setup exhausted the cleanup-reserved lifetime")
                manager.run("operational-child", [sys.executable, str(Path(__file__).resolve()),
                            *sys.argv[1:], "--child-root", str(directory)], timeout=remaining)
            finally:
                manager.close()
                guardian_closed = manager.closed
                log = directory / "operational-child.log"
                if log.is_file():
                    shutil.copyfile(log, output / "guardian.log")
                write(output / "guardian-cleanup.json", {
                    "outerJobClosed": guardian_closed, "cleanupReserveSeconds": 30,
                    "totalBoundSeconds": 7800,
                })
        temporary_removed = True
        cleanup_completed = guardian_closed and temporary_removed
    finally:
        temporary_removed = "directory" in locals() and not directory.exists()
        cleanup_completed = guardian_closed and temporary_removed
        total = time.monotonic() - lifetime_started
        write(output / "lifetime-receipt.json", {
            "actualTotalWallSeconds": total, "hardDeadlineSeconds": 7800,
            "cleanupCompleted": cleanup_completed, "outerJobClosed": guardian_closed,
            "temporaryRemoved": temporary_removed,
            "withinDeclaredBound": total <= 7800,
        })
    if total > 7800:
        raise TimeoutError("Cleanup completed but declared total lifetime was exceeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
