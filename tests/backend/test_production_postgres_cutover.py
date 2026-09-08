from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux production maintenance")
SCRIPTS = Path(__file__).resolve().parents[2] / "deploy/scripts"
SHA = "a" * 40


@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    import postgres_cutover_state as state

    spec = importlib.util.spec_from_file_location(
        "production_postgres_cutover",
        SCRIPTS / "cutover-production-postgres.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return state, module


def test_authority_marker_permanently_closes_sqlite_rollback(modules, tmp_path):
    state, _ = modules
    receipt = tmp_path / "authority.json"
    assert state.sqlite_rollback_allowed(receipt)
    state.record_authority(receipt, SHA)
    assert json.loads(receipt.read_text())["sqliteRollbackAllowed"] is False
    assert not state.sqlite_rollback_allowed(receipt)
    receipt.write_text("interrupted or corrupted receipt")
    assert not state.sqlite_rollback_allowed(receipt)
    with pytest.raises(state.CutoverError):
        state.record_authority(receipt, SHA)


def test_dangling_authority_symlink_never_allows_sqlite_recovery(modules, tmp_path):
    state, _ = modules
    receipt = tmp_path / "authority.json"
    receipt.symlink_to(tmp_path / "missing")
    assert not state.sqlite_rollback_allowed(receipt)
    with pytest.raises(state.CutoverError):
        state.record_authority(receipt, SHA)


def test_failed_atomic_environment_write_preserves_old_file(modules, tmp_path, monkeypatch):
    state, _ = modules
    environment = tmp_path / "environment"
    environment.write_bytes(b"old authority")

    def fail_replace(*args):
        raise OSError("simulated storage failure")

    monkeypatch.setattr(state.os, "replace", fail_replace)
    with pytest.raises(OSError):
        state.durable_write(environment, b"new authority")
    assert environment.read_bytes() == b"old authority"
    assert list(tmp_path.iterdir()) == [environment]


def test_candidate_environment_preserves_flags_and_rejects_duplicates(modules, tmp_path):
    state, _ = modules
    environment = tmp_path / "environment"
    original = (
        "PATHLAB_DATABASE_ENGINE=sqlite\nPATHLAB_ASSESSMENT_ENABLED=false\nDOMAIN=example.org\n"
    )
    environment.write_text(
        state.postgres_environment(
            original,
            password_file=tmp_path / "password",
            signing_key_file=tmp_path / "signing",
        )
    )
    values = state.read_environment(environment)
    assert values["PATHLAB_DATABASE_ENGINE"] == "postgres"
    assert values["PATHLAB_ASSESSMENT_ENABLED"] == "false"
    assert values["DOMAIN"] == "example.org"
    environment.write_text(original + "PATHLAB_DATABASE_ENGINE=postgres\n")
    with pytest.raises(state.CutoverError, match="Duplicate"):
        state.read_environment(environment)


@pytest.fixture
def operation(modules, tmp_path, monkeypatch):
    _, module = modules
    authority = tmp_path / "authority.json"
    monkeypatch.setattr(module, "AUTHORITY", authority)
    monkeypatch.setattr(module, "MAINTENANCE", tmp_path / "maintenance.json")
    instance = object.__new__(module.Cutover)
    instance.sha = SHA
    instance.token = "protected-cutover-owner-token-1234567890"
    instance.journal = tmp_path
    instance.env_file = tmp_path / "live.env"
    instance.original = b"PATHLAB_DATABASE_ENGINE=sqlite\n"
    instance.env_file.write_bytes(b"PATHLAB_DATABASE_ENGINE=postgres\n")
    instance.environment_changed = True
    instance.watchdog = True
    instance.maintenance = True
    instance.data = tmp_path / "data"
    (instance.data / "database").mkdir(parents=True)
    instance.calls = []
    instance.compose = lambda *args, **kwargs: instance.calls.append(args) or ""
    instance.run = lambda *args, **kwargs: instance.calls.append(args) or ""
    return instance, authority


def test_precommit_failure_restores_sqlite_environment_and_services(operation):
    instance, authority = operation
    instance.recover()
    assert not authority.exists()
    assert instance.env_file.read_bytes() == instance.original
    assert any(call[:3] == ("up", "-d", "--no-build") for call in instance.calls)
    assert json.loads((instance.journal / "status.json").read_text())["state"] == (
        "FAILED_SQLITE_RESTORED"
    )


def test_postcommit_failure_keeps_postgres_and_stops_public_writers(operation, modules):
    instance, authority = operation
    state, _ = modules
    state.record_authority(authority, SHA)
    instance.recover()
    assert instance.env_file.read_bytes() != instance.original
    assert not any(call[0] == "up" for call in instance.calls)
    assert ("stop", "caddy", "tusd", "worker") in instance.calls
    assert json.loads((instance.journal / "status.json").read_text())["state"] == (
        "FAILED_POSTGRES_FORWARD_RECOVERY_REQUIRED"
    )


def test_authority_is_durable_before_any_application_start(operation, modules):
    instance, authority = operation
    state, _ = modules

    def fail_start(*args, **kwargs):
        assert authority.exists()
        assert not state.sqlite_rollback_allowed(authority)
        raise RuntimeError("simulated application startup failure")

    instance.compose = fail_start
    with pytest.raises(RuntimeError, match="startup"):
        instance.commit()
    assert not state.sqlite_rollback_allowed(authority)


def test_no_recovery_mutation_before_maintenance(operation):
    instance, _ = operation
    instance.maintenance = False
    instance.recover()
    assert not instance.calls


@pytest.mark.parametrize("command", ["up", "start", "restart", "run"])
def test_restart_guard_requires_the_cutover_owner_token(modules, monkeypatch, command):
    state, _ = modules
    token = "protected-cutover-owner-token-1234567890"
    marker = SimpleNamespace(
        exists=lambda: True,
        is_symlink=lambda: False,
        lstat=lambda: SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_uid=0),
        read_text=lambda: json.dumps({"token": token}),
    )
    monkeypatch.delenv("PATHLAB_CUTOVER_TOKEN", raising=False)
    with pytest.raises(state.CutoverError, match="blocks application startup"):
        state.require_compose_authorization(command, marker)
    monkeypatch.setenv("PATHLAB_CUTOVER_TOKEN", "wrong-owner-token")
    with pytest.raises(state.CutoverError):
        state.require_compose_authorization(command, marker)
    monkeypatch.setenv("PATHLAB_CUTOVER_TOKEN", token)
    state.require_compose_authorization(command, marker)


def test_restart_guard_allows_stopping_services_without_an_owner_token(modules):
    state, _ = modules
    marker = SimpleNamespace(exists=lambda: True)
    for command in ("stop", "ps", "config", "logs"):
        state.require_compose_authorization(command, marker)
