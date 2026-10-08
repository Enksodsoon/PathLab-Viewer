"""Bounded source-harness regressions; no services, browser, or engines launched."""

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def launcher(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("run_alignment_operational_profile")


def arguments(output, child=None):
    values = ["launcher", "--report-dir", str(output), "--pnpm", "pnpm", "--tusd", "tusd",
              "--caddy", "caddy", "--node", "node", "--runtime-python", "runtime",
              "--expected-head", "0" * 40]
    return values + (["--child-root", str(child)] if child else [])


def test_admitted_child_uses_existing_guardian_output(launcher, tmp_path, monkeypatch):
    output, child = tmp_path / "report", tmp_path / "child"
    output.mkdir()
    child.mkdir()
    (child / "owned-marker.json").write_text(json.dumps({"outputDirectory": str(output)}))
    observed = []
    monkeypatch.setattr(sys, "argv", arguments(output, child))
    monkeypatch.setattr(launcher, "child", observed.append)
    assert launcher.main() == 0
    assert len(observed) == 1
    assert observed[0].report_dir == output


def test_child_rejects_different_guardian_output(launcher, tmp_path, monkeypatch):
    output, child = tmp_path / "report", tmp_path / "child"
    output.mkdir()
    child.mkdir()
    (child / "owned-marker.json").write_text(json.dumps({"outputDirectory": "another-output"}))
    monkeypatch.setattr(sys, "argv", arguments(output, child))
    monkeypatch.setattr(launcher, "child", lambda _: pytest.fail("Unadmitted child started"))
    with pytest.raises(ValueError, match="guardian"):
        launcher.main()


@pytest.mark.parametrize("fail", [False, True])
def test_outer_reserves_cleanup_and_records_failure_lifetime(
    launcher, tmp_path, monkeypatch, fail
):
    output = tmp_path / "report"
    clock = iter([100.0, 104.0, 109.0])
    monkeypatch.setattr(launcher.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(sys, "argv", arguments(output))
    observed = []

    class Manager:
        closed = False

        def __init__(self, directory, env):
            self.directory = directory

        def run(self, name, command, *, timeout):
            observed.append(timeout)
            (self.directory / f"{name}.log").write_text("bounded mock child")
            if fail:
                raise RuntimeError("Observed child failure")

        def close(self):
            self.closed = True

    monkeypatch.setattr(launcher, "ProcessManager", Manager)
    if fail:
        with pytest.raises(RuntimeError, match="Observed child"):
            launcher.main()
    else:
        assert launcher.main() == 0
    assert observed == [7766.0]
    receipt = json.loads((output / "lifetime-receipt.json").read_text())
    assert receipt == {
        "actualTotalWallSeconds": 9.0, "hardDeadlineSeconds": 7800,
        "cleanupCompleted": True, "outerJobClosed": True,
        "temporaryRemoved": True, "withinDeclaredBound": True,
    }


def test_service_ownership_uses_managed_process_handle(launcher, tmp_path, monkeypatch):
    directory = tmp_path / "pathlab-fullstack-operational-fixture"
    directory.mkdir()
    output = tmp_path / "report"
    output.mkdir()
    (directory / "owned-marker.json").write_text("{}")
    runtime = tmp_path / "var/valis-runtime/Scripts/python.exe"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"not executed")
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setenv("PATHLAB_ENVIRONMENT", "test")
    monkeypatch.setattr(launcher, "operational_environment", lambda _: {
        "PATHLAB_E2E_USERNAME": "fixture", "PATHLAB_E2E_PASSWORD": "fixture",
    })
    monkeypatch.setattr(launcher, "reserve_ports", lambda _: [18001, 18002, 18003, 18004, 18005])

    class Manager:
        closed = False

        def __init__(self, directory, env):
            self.directory = directory

        def run(self, name, command, *, timeout, input_text=None):
            if name == "admission-start":
                (output / "admission-start.json").write_text("{}")
            if name == "public-pair":
                (self.directory / "public-pair.log").write_text('{"slideIds":["a","b"]}')

        def start(self, name, command):
            # Match the real ManagedProcess contract; there is no top-level .pid.
            return SimpleNamespace(process=SimpleNamespace(pid=321))

        def close(self):
            self.closed = True

    def readiness(url, process):
        assert process.process.pid == 321
        raise RuntimeError("Reached readiness with owned handle")

    monkeypatch.setattr(launcher, "ProcessManager", Manager)
    monkeypatch.setattr(launcher, "wait_ready", readiness)
    args = SimpleNamespace(child_root=directory, report_dir=output, pnpm="pnpm",
                           runtime_python=str(runtime), expected_head="0" * 40)
    with pytest.raises(RuntimeError, match="Reached readiness"):
        launcher.child(args)
    receipt = json.loads((output / "inner-cleanup.json").read_text())
    assert receipt["ownedServicesClosed"] is True
    assert receipt["serviceOwnership"][0]["wrapperPid"] == 321


def test_research_runtime_environment_binds_offline_resources(launcher, tmp_path, monkeypatch):
    resource = tmp_path / "weights.pth"
    resource.write_bytes(b"bounded fixture resource; never loaded")
    expected = hashlib.sha256(resource.read_bytes()).hexdigest()
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "RESOURCE_ADMISSION", {"VALIS_DISK": (resource.name, expected)})
    env = launcher.operational_environment(tmp_path)
    assert env["PATHLAB_ALIGNMENT_VALIS_DISK_WEIGHTS_SHA256"] == expected
    assert env["PATHLAB_ALIGNMENT_VALIS_DISK_WEIGHTS_PATH"] == str(resource)
    for engine in ("VALIS", "WSIREG", "HISALIGN", "DEEPERHISTREG"):
        assert env[f"PATHLAB_ALIGNMENT_{engine}_ENABLED"] == "true"
    for key in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "ITK_GLOBAL_DEFAULT_NUMBER_OF_THREADS"):
        assert env[key] == "1"
    resource.write_bytes(b"changed fixture resource")
    with pytest.raises(ValueError, match="digest changed"):
        launcher.operational_environment(tmp_path)
