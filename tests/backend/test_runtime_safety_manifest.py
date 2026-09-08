from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def load_runtime_safety_manifest() -> ModuleType:
    path = Path(__file__).parents[2] / "deploy" / "scripts" / "runtime_safety_manifest.py"
    spec = importlib.util.spec_from_file_location("runtime_safety_manifest", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime_safety_manifest = load_runtime_safety_manifest()


def service_commands() -> dict[str, str]:
    wrapper = "/bin/bash /opt/pathlab-viewer/deploy/scripts/compose-pathlab.sh "
    return {
        "ExecStart": wrapper + "up -d --build --remove-orphans",
        "ExecReload": wrapper + "up -d --build --remove-orphans",
        "ExecStop": wrapper + "down",
    }


def test_service_manager_preserves_postgres_and_optional_profiles(monkeypatch):
    raw = "\n".join(
        f"{key}={{ path=/bin/bash ; argv[]={value} ; }}"
        for key, value in service_commands().items()
    )
    monkeypatch.setattr(runtime_safety_manifest, "_run", lambda *_args: raw)
    assert runtime_safety_manifest.verify_service_manager() == {"engineAwareServiceManager": True}


@pytest.mark.parametrize("name", ["ExecStart", "ExecReload", "ExecStop"])
@pytest.mark.parametrize(
    "replacement",
    ["/usr/bin/docker compose up -d --remove-orphans", "", "/bin/bash -c unsafe-wrapper"],
)
def test_service_manager_rejects_base_compose_and_overridden_commands(
    monkeypatch, name, replacement
):
    commands = service_commands()
    commands[name] = replacement
    raw = "\n".join(
        f"{key}={{ path=/bin/bash ; argv[]={value} ; }}" for key, value in commands.items()
    )
    monkeypatch.setattr(runtime_safety_manifest, "_run", lambda *_args: raw)
    with pytest.raises(runtime_safety_manifest.RuntimeSafetyError, match="service manager"):
        runtime_safety_manifest.verify_service_manager()


def test_runtime_digest_binds_operator_owned_qualification_routes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plain = runtime_safety_manifest.compose_digest("compose")
    directory = tmp_path / "routes"
    directory.mkdir()
    fragment = directory / "qualification.caddy"
    original_stat, original_lstat = Path.stat, Path.lstat

    def protected_stat(path: Path, *args: object, **kwargs: object) -> object:
        if path == directory:
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFDIR | 0o700)
        return original_stat(path, *args, **kwargs)

    def protected_lstat(path: Path) -> object:
        if path == fragment:
            info = original_lstat(path)
            return SimpleNamespace(st_uid=0, st_mode=stat.S_IFREG | 0o600, st_size=info.st_size)
        return original_lstat(path)

    monkeypatch.setattr(Path, "stat", protected_stat)
    monkeypatch.setattr(Path, "lstat", protected_lstat)
    assert runtime_safety_manifest.compose_digest("compose", directory) == plain
    fragment.write_text("qualify.example.test { respond 200 }")
    first = runtime_safety_manifest.compose_digest("compose", directory)
    assert first != plain
    fragment.write_text("qualify.example.test { respond 503 }")
    assert runtime_safety_manifest.compose_digest("compose", directory) != first


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
