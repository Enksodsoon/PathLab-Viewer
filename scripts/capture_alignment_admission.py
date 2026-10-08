"""Private startup/terminal byte admission using the common runtime; no model/decoder calls."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MODULES = (
    "server/wsi_viewer/alignment.py",
    "server/wsi_viewer/alignment_artifacts.py",
    "server/wsi_viewer/alignment_fast.py",
    "server/wsi_viewer/alignment_engines.py",
    "server/wsi_viewer/alignment_optional.py",
    "server/wsi_viewer/alignment_recipes.py",
    "server/wsi_viewer/alignment_geometry.py",
    "server/wsi_viewer/alignment_inputs.py",
    "server/wsi_viewer/alignment_calibration.py",
    "server/wsi_viewer/alignment_resources.py",
    "server/wsi_viewer/alignment_processes.py",
    "server/wsi_viewer/alignment_routes.py",
    "server/wsi_viewer/alignment_policy.py",
    "server/wsi_viewer/alignment_warm.py",
    "server/wsi_viewer/alignment_benchmark.py",
    "server/wsi_viewer/worker.py",
    "server/wsi_viewer/config.py",
    "server/wsi_viewer/main.py",
    "scripts/capture_alignment_admission.py",
    "scripts/benchmark_alignment_warm_process.py",
    "scripts/measure_alignment_operational_profile.py",
    "scripts/run_alignment_operational_profile.py",
    "scripts/run_fullstack_tests.py",
    "scripts/seed_frontend_qa.py",
    "apps/web/scripts/measure-alignment-operational-ui.mjs",
    "apps/web/src/pages/ComparisonPage.tsx",
    "apps/web/src/candidatePreview.ts",
    "apps/web/src/alignment.ts",
    "apps/web/src/components/OpenSeadragonViewer.tsx",
)
PACKAGES = (
    "numpy",
    "opencv-python",
    "opencv-python-headless",
    "opencv-contrib-python",
    "opencv-contrib-python-headless",
    "Pillow",
    "torch",
    "wsireg",
    "itk-elastix",
    "valis-wsi",
    "hisalign",
    "deeperhistreg",
)
RESOURCE_FILES = (
    "var/engine-resources/valis/depth-save.pth",
    "var/engine-resources/valis/disk_lightglue.pth",
    "var/benchmark-sources/SuperGluePretrainedNetwork/models/weights/superpoint_v1.pth",
    "var/benchmark-sources/SuperGluePretrainedNetwork/models/weights/superglue_outdoor.pth",
)


def fingerprint(path: Path) -> dict[str, Any]:
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError("admission requires regular files without linked parents")
    before = path.stat()
    if not path.is_file() or before.st_size > 512 * 1024**2:
        raise ValueError("admission file is absent or exceeds512MiB")
    with path.open("rb") as file:
        digest = hashlib.file_digest(file, "sha256").hexdigest()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("admission file changed during read")
    return {
        "sha256": digest,
        "bytes": before.st_size,
        "mtimeNs": before.st_mtime_ns,
        "ctimeNs": before.st_ctime_ns,
    }


def source_state(expected_head: str) -> dict[str, str]:
    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=ROOT, text=True, capture_output=True, check=True, timeout=10
        ).stdout.strip()

    head, status = git("rev-parse", "HEAD"), git("status", "--porcelain")
    if head != expected_head or status:
        raise ValueError("admission requires exact clean reviewed source")
    return {"head": head, "gitStatus": status}


def runtime_identity() -> dict[str, Any]:
    import cv2  # Version/binary identity only; no image operation or model import.

    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    native = getattr(cv2, "_native", None)
    binary = Path(native.__file__) if native is not None else None
    if binary is None:
        candidates = list(Path(cv2.__file__).parent.glob("*.pyd"))
        if len(candidates) != 1:
            raise ValueError("actual loaded OpenCV binary cannot be identified")
        binary = candidates[0]
    return {
        "python": platform.python_version(),
        "architecture": platform.machine(),
        "os": platform.platform(),
        "executable": fingerprint(Path(sys.executable)),
        "baseExecutable": fingerprint(Path(getattr(sys, "_base_executable", sys.executable))),
        "distributions": versions,
        "loadedCv2Version": cv2.__version__,
        "loadedCv2Binary": fingerprint(binary),
        "scope": (
            "distribution metadata; Python launcher/base executable and OpenCV binary bytes; "
            "no model import"
        ),
    }


def host_hardware() -> dict[str, Any]:
    result: dict[str, Any] = {
        "machine": platform.machine(),
        "processor": platform.processor(),
        "os": platform.platform(),
    }
    if sys.platform == "win32":
        import ctypes
        import winreg

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                *[
                    (name, ctypes.c_ulonglong)
                    for name in (
                        "totalPhysical",
                        "availablePhysical",
                        "totalPageFile",
                        "availablePageFile",
                        "totalVirtual",
                        "availableVirtual",
                        "extended",
                    )
                ],
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise OSError("current physical-memory metadata is unavailable")
        result["totalMemoryBytes"] = int(status.totalPhysical)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        ) as key:
            result["cpuName"] = winreg.QueryValueEx(key, "ProcessorNameString")[0].strip()
    return result


def warm_input_identity(manifest: Path) -> dict[str, Any]:
    admitted_manifest = fingerprint(manifest)
    document = json.loads(manifest.read_bytes())
    inputs = {}
    for pair in document["pairs"]:
        for ordinal, side in enumerate(("reference", "moving")):
            source = pair[side]
            directory = Path(source["path"])
            key = str(directory) + json.dumps(source["size"])
            if key not in inputs:
                digest = hashlib.sha256()
                files = {}
                for path in sorted(p for p in directory.rglob("*") if p.is_file()):
                    name = path.relative_to(directory).as_posix()
                    files[name] = fingerprint(path)
                    digest.update(name.encode())
                    with path.open("rb") as file:
                        for block in iter(lambda: file.read(1024**2), b""):
                            digest.update(block)
                    if files[name] != fingerprint(path):
                        raise ValueError("registered input changed while binding")
                digest.update(json.dumps(source["size"]).encode())
                inputs[key] = {
                    "size": source["size"],
                    "files": files,
                    "registeredInputDigest": digest.hexdigest(),
                }
            if inputs[key]["registeredInputDigest"] != pair["inputDigests"][ordinal]:
                raise ValueError("warm original registered bytes/geometry differ")
    if fingerprint(manifest) != admitted_manifest:
        raise ValueError("warm manifest changed during input binding")
    return {
        "manifest": admitted_manifest,
        "pairCount": len(document["pairs"]),
        "uniqueInputs": inputs,
        "scope": "ordinary published image directories; no decoding",
    }


def capture(expected_head: str, *, manifest: Path | None = None) -> dict[str, Any]:
    started = time.monotonic()
    admitted = ROOT / "var/valis-runtime/Scripts/python.exe"
    if Path(sys.executable).resolve() != admitted.resolve():
        raise ValueError("admission must run in the actual common registration runtime")
    state = source_state(expected_head)
    ledger_path = ROOT / "deploy/alignment-sources.json"
    ledger = json.loads(ledger_path.read_bytes())
    licenses = {}
    expected = {}
    for engine in ledger["engines"]:
        for item in (engine, *engine.get("weights", [])):
            if item.get("licenseFile"):
                name = item["licenseFile"]
                licenses[name] = fingerprint(ROOT / name)
                if (
                    item.get("licenseFileSha256")
                    and licenses[name]["sha256"] != item["licenseFileSha256"]
                ):
                    raise ValueError("declared license bytes differ")
            if item.get("sha256") and item.get("name"):
                expected[Path(item.get("file", item["name"])).name] = item["sha256"]
    resources = {name: fingerprint(ROOT / name) for name in RESOURCE_FILES}
    if any(value["sha256"] != expected.get(Path(name).name) for name, value in resources.items()):
        raise ValueError("resource bytes are not admitted by the source ledger")
    modules = {name: fingerprint(ROOT / name) for name in MODULES}
    assets = {}
    dist = ROOT / "apps/web/dist"
    if dist.is_dir():
        files = sorted(p for p in dist.rglob("*") if p.is_file())
        if len(files) > 2000 or sum(p.stat().st_size for p in files) > 256 * 1024**2:
            raise ValueError("frontend build inventory exceeds bounded admission")
        assets = {p.relative_to(dist).as_posix(): fingerprint(p) for p in files}
    identity = {
        "sourceState": state,
        "moduleBytes": modules,
        "runtime": runtime_identity(),
        "resourceBytes": resources,
        "licenseBytes": licenses,
        "sourceLedger": fingerprint(ledger_path),
        "hardwareReceipt": fingerprint(ROOT / "var/benchmark-inputs/hardware.json"),
        "currentHostHardware": host_hardware(),
        "frontendBuildBytes": assets,
        "warmInputBytes": warm_input_identity(manifest) if manifest else None,
    }
    if source_state(expected_head) != state:
        raise ValueError("source state changed during admission")
    return {
        "schema": "alignment-startup-terminal-byte-admission/1",
        "identity": identity,
        "admissionWallSeconds": time.monotonic() - started,
        "modelImports": False,
        "imageOperations": False,
        "qualificationEvidence": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    value = capture(args.expected_head, manifest=args.manifest)
    if args.reference:
        original = json.loads(args.reference.read_bytes())
        value["unchangedFromReference"] = value["identity"] == original["identity"]
        value["referenceSha256"] = fingerprint(args.reference)["sha256"]
    with args.output.open("x", encoding="utf-8", newline="\n") as file:
        json.dump(value, file, sort_keys=True, indent=2, allow_nan=False)
        file.write("\n")
    if args.reference and not value["unchangedFromReference"]:
        raise ValueError("startup/terminal admission identity changed")
    print(
        json.dumps(
            {
                "receiptSha256": fingerprint(args.output)["sha256"],
                "unchangedFromReference": value.get("unchangedFromReference"),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
