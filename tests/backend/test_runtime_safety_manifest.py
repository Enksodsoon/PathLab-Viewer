from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def load_runtime_safety_manifest() -> ModuleType:
    path = Path(__file__).parents[2] / "deploy" / "scripts" / "runtime_safety_manifest.py"
    spec = importlib.util.spec_from_file_location("runtime_safety_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_safety_manifest = load_runtime_safety_manifest()


def runtime(*, postgres: bool = False) -> dict[str, object]:
    services = ["api", "caddy", "classroom", "tile-service", "tusd", "worker"]
    if postgres:
        services.append("postgres")
        services.sort()
    return {
        "releaseSha": "a" * 40,
        "schemaRevision": "20260822_0025",
        "databaseEngine": "postgres" if postgres else "sqlite",
        "services": services,
        "runningServices": services,
        "composeConfigDigest": "b" * 64,
        "classroomEnabled": True,
        "safeCapacity": 300,
        "annotationsEnabled": False,
        "watchdogExpected": True,
        "domain": "viewer.example.test",
    }


@pytest.mark.parametrize("postgres", [False, True])
def test_runtime_manifest_binds_topology_without_a_numeric_service_contract(postgres: bool) -> None:
    manifest = runtime_safety_manifest.build_manifest(
        runtime(postgres=postgres), created_at="2026-08-22T00:00:00+00:00"
    )

    verified = runtime_safety_manifest.validate_manifest(manifest)

    assert verified["services"] == runtime(postgres=postgres)["services"]
    assert len(verified["services"]) == (7 if postgres else 6)
    assert len(verified["manifestDigest"]) == 64


def test_runtime_manifest_rejects_tampering(tmp_path: Path) -> None:
    manifest = runtime_safety_manifest.build_manifest(
        runtime(), created_at="2026-08-22T00:00:00+00:00"
    )
    manifest["safeCapacity"] = 2000
    path = tmp_path / runtime_safety_manifest.MANIFEST_NAME
    path.write_text(json.dumps(manifest), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(runtime_safety_manifest.RuntimeSafetyError, match="invalid"):
        runtime_safety_manifest.load_manifest(path)


def test_runtime_manifest_rejects_database_topology_mismatch() -> None:
    value = runtime(postgres=True)
    value["services"] = [item for item in value["services"] if item != "postgres"]
    value["runningServices"] = value["services"]

    with pytest.raises(runtime_safety_manifest.RuntimeSafetyError, match="database service"):
        runtime_safety_manifest.build_manifest(value)
