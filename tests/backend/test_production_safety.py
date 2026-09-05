from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).parents[2]
BASH = Path(r"C:\Program Files\Git\bin\bash.exe")
PORTABLE_BASH = str(BASH) if BASH.exists() else shutil.which("bash")


def _bash_path(path: Path) -> str:
    resolved = path.resolve().as_posix()
    return f"/{resolved[0].lower()}{resolved[2:]}"


def _shell_path(path: Path) -> str:
    if os.name == "nt":
        return _bash_path(path)
    return path.resolve().as_posix()


def _load_script(name: str) -> ModuleType:
    path = ROOT / "deploy" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _successful_check_runs(sha: str) -> dict[str, object]:
    names = (
        "backend",
        "browser",
        "web",
        "containers",
        "repository-and-dependencies",
        "CodeQL (python)",
        "CodeQL (javascript-typescript)",
    )
    return {
        "check_runs": [
            {
                "name": name,
                "id": index + 100,
                "head_sha": sha,
                "status": "completed",
                "conclusion": "success",
            }
            for index, name in enumerate(names)
        ]
    }


def test_evidence_builder_uses_current_authoritative_check_runs() -> None:
    builder = _load_script("build_deploy_evidence")
    safety = _load_script("production_safety")
    sha = "f" * 40
    evidence = builder.build_evidence(
        _successful_check_runs(sha),
        sha=sha,
        repository="Enksodsoon/PathLab-Viewer",
        workflow_run_id="456",
        nonce="run-456-attempt-1",
        projected_monthly_egress_bytes=1_000,
        month_to_date_cost_sgd=12.34,
        now=1_700_000_000,
    )
    assert evidence["cost"] == {
        "currency": "SGD",
        "monthToDate": 12.34,
        "projectedIncremental": 0,
    }
    key = b"test-only-deployment-evidence-key-32-bytes"
    safety.validate_signed(
        evidence,
        sha,
        safety.sign_evidence(evidence, key),
        key,
        now=1_700_000_100,
        expected_nonce="run-456-attempt-1",
    )


def test_evidence_builder_rejects_wrong_sha_or_missing_check() -> None:
    builder = _load_script("build_deploy_evidence")
    sha = "f" * 40
    payload = _successful_check_runs(sha)
    payload["check_runs"] = [run for run in payload["check_runs"] if run["name"] != "browser"]
    with pytest.raises(builder.EvidenceBuildFailure):
        builder.build_evidence(
            payload,
            sha=sha,
            repository="Enksodsoon/PathLab-Viewer",
            workflow_run_id="456",
            nonce="run-456-attempt-1",
            projected_monthly_egress_bytes=1_000,
            month_to_date_cost_sgd=0,
            now=1_700_000_000,
        )


class FakeRunner:
    def __init__(self, failing: set[str] | None = None, restart_fails: bool = False) -> None:
        self.failing = failing or set()
        self.restart_fails = restart_fails
        self.commands: list[tuple[str, ...]] = []

    def __call__(
        self, command: list[str], *, timeout: int, capture: bool = False
    ) -> tuple[int, str]:
        del timeout, capture
        self.commands.append(tuple(command))
        component = next(
            (name for name in ("api", "classroom", "tile-service") if name in command),
            "",
        )
        if "curl" in command and component in self.failing:
            return 1, "probe failed"
        if "restart" in command and self.restart_fails:
            return 1, "restart failed"
        return 0, "ok"


def _valid_evidence(sha: str) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "candidateSha": sha,
        "issuedAt": 1_700_000_000,
        "expiresAt": 1_700_000_600,
        "nonce": "run-123-attempt-1",
        "workflowRunId": "123",
        "repository": "Enksodsoon/PathLab-Viewer",
        "ci": {
            "sha": sha,
            "required": {
                name: {"conclusion": "success", "runId": index + 1}
                for index, name in enumerate(("backend", "browser", "web", "containers"))
            },
        },
        "security": {
            "sha": sha,
            "required": {
                name: {"conclusion": "success", "runId": index + 10}
                for index, name in enumerate(
                    (
                        "repository-and-dependencies",
                        "CodeQL (python)",
                        "CodeQL (javascript-typescript)",
                    )
                )
            },
        },
        "backup": {"created": True, "restoreDrillSucceeded": True},
        "classroom": {"activeRealSessions": 0},
        "fixtures": {"syntheticOnly": True},
        "rollback": {"releaseAvailable": True},
        "annotations": {"enabled": False},
        "egress": {"projectedMonthlyBytes": 8_999_999_999_999},
        "cost": {"currency": "SGD", "monthToDate": 0, "projectedIncremental": 0},
    }


def _capacity_evidence(strict_1200: bool, strict_1500: bool) -> dict[str, Any]:
    stage_results = {
        "smoke-2": {"durationSeconds": 1, "status": "passed"},
        "smoke-100": {"durationSeconds": 1, "status": "passed"},
        "boundary-300": {"durationSeconds": 600, "status": "passed"},
        "boundary-600": {"durationSeconds": 600, "status": "passed"},
        "boundary-900": {"durationSeconds": 600, "status": "passed"},
        "certification-1200": {
            "durationSeconds": 3600 if strict_1200 else 1,
            "status": "passed" if strict_1200 else "failed",
        },
        "headroom-1500": {
            "durationSeconds": 600 if strict_1500 else 1,
            "status": "passed" if strict_1500 else ("failed" if strict_1200 else "skipped"),
        },
        "stress-1750": {"durationSeconds": 1, "status": "early-stopped"},
        "stress-2000": {"durationSeconds": 0, "status": "skipped"},
        "recovery-1200": {
            "durationSeconds": 1 if strict_1200 else 0,
            "status": "passed" if strict_1200 else "skipped",
        },
    }
    return {
        "schemaVersion": 2,
        "candidateSha": "d" * 40,
        "runId": "run-456",
        "nonce": "capacity-nonce",
        "startedAt": 1_786_649_400,
        "completedAt": 1_786_653_600,
        "authorizedWindowStart": 1_786_647_600,
        "authorizedWindowEnd": 1_786_658_400,
        "withinAuthorizedIctWindow": True,
        "allPreflightGatesPassed": True,
        "fixtureCleanupSucceeded": True,
        "evidenceDigest": "e" * 64,
        "strictStages": {
            "1200": {"durationSeconds": 3600, "passed": strict_1200},
            "1500": {"durationSeconds": 600, "passed": strict_1500},
        },
        "stageResults": stage_results,
        "functionalSentinels": {
            "uploadConversion": strict_1200,
            "annotations": strict_1200,
            "libraryShare": strict_1200,
            "dynamicViewer": strict_1200,
            "desktop": strict_1200,
        },
    }


def test_annotation_activation_requires_signed_strict_capacity_and_sentinel() -> None:
    safety = _load_script("production_safety")
    key = b"test-only-deployment-evidence-key-32-bytes"
    evidence = {"certification": _capacity_evidence(True, False)}
    signature = safety.sign_evidence(evidence, key)
    assert safety.validate_annotation_activation(evidence, signature, key) == 1200

    evidence["certification"]["functionalSentinels"]["annotations"] = False
    signature = safety.sign_evidence(evidence, key)
    with pytest.raises(safety.GuardFailure, match="sentinel"):
        safety.validate_annotation_activation(evidence, signature, key)

    with pytest.raises(safety.GuardFailure, match="signature"):
        safety.validate_annotation_activation(evidence, "0" * 64, key)


def test_watchdog_restarts_only_failed_component_after_third_failure(tmp_path: Path) -> None:
    watchdog = _load_script("component_watchdog")
    runner = FakeRunner({"classroom"})
    events: list[dict[str, object]] = []

    for now in (100, 115, 130):
        watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda now=now: now, events.append)

    restarts = [command for command in runner.commands if "restart" in command]
    assert restarts == [("docker", "compose", "restart", "classroom")]
    assert not any("api" in command or "tile-service" in command for command in restarts)
    inspect_commands = [
        command for command in runner.commands if command[:2] == ("docker", "inspect")
    ]
    assert len(inspect_commands) == 1
    assert "--format" in inspect_commands[0]
    assert inspect_commands[0][-1] == "ok"
    assert any(event["decision"] == "diagnostics-captured" for event in events)
    assert not any("logs" in command for command in runner.commands)
    assert not any("{{json .State}}" in command for command in runner.commands)
    api_probes = [command for command in runner.commands if "api" in command and "curl" in command]
    assert api_probes and all(command[-1].endswith("/livez") for command in api_probes)


def test_watchdog_stops_after_three_restarts_in_ten_minutes(tmp_path: Path) -> None:
    watchdog = _load_script("component_watchdog")
    runner = FakeRunner({"api"})
    events: list[dict[str, object]] = []

    for now in range(100, 100 + 12 * 15, 15):
        watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda now=now: now, events.append)

    restarts = [command for command in runner.commands if "restart" in command]
    assert restarts == [("docker", "compose", "restart", "api")] * 3
    assert any(event["decision"] == "restart-refused-anti-flap" for event in events)


def test_watchdog_anti_flap_limit_is_global_across_components(tmp_path: Path) -> None:
    watchdog = _load_script("component_watchdog")
    runner = FakeRunner()
    events: list[dict[str, object]] = []

    now = 100
    for component in ("api", "classroom", "tile-service"):
        runner.failing = {component}
        for _ in range(3):
            watchdog.run_cycle(
                tmp_path, ROOT / "deploy", runner, lambda now=now: now, events.append
            )
            now += 15
    runner.failing = {"classroom"}
    for _ in range(3):
        watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda now=now: now, events.append)
        now += 15

    restarts = [command for command in runner.commands if "restart" in command]
    assert len(restarts) == 3
    classroom_decisions = [
        event["decision"] for event in events if event.get("component") == "classroom"
    ]
    assert classroom_decisions[-2:] == [
        "diagnostics-captured",
        "restart-refused-anti-flap",
    ]


def test_watchdog_fails_closed_when_state_is_corrupt(tmp_path: Path) -> None:
    watchdog = _load_script("component_watchdog")
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "state.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(watchdog.WatchdogStateError):
        watchdog.run_cycle(
            tmp_path, ROOT / "deploy", FakeRunner({"api"}), lambda: 100, lambda _: None
        )


def test_watchdog_counts_failed_restart_action_and_rejects_invalid_history(tmp_path: Path) -> None:
    watchdog = _load_script("component_watchdog")
    runner = FakeRunner({"api"}, restart_fails=True)
    for now in (100, 115, 130):
        watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda now=now: now, lambda _: None)
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["restartActions"] == [{"at": 130, "component": "api", "outcome": "failed"}]

    state["restartActions"].append("corrupt")
    (tmp_path / "state.json").write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(watchdog.WatchdogStateError):
        watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda: 145, lambda _: None)


def test_watchdog_recovery_clears_failure_counter(tmp_path: Path) -> None:
    watchdog = _load_script("component_watchdog")
    runner = FakeRunner({"tile-service"})
    events: list[dict[str, object]] = []

    watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda: 100, events.append)
    runner.failing.clear()
    watchdog.run_cycle(tmp_path, ROOT / "deploy", runner, lambda: 115, events.append)

    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    assert state["components"]["tile-service"]["consecutiveFailures"] == 0
    assert any(
        event["component"] == "tile-service" and event["decision"] == "recovered"
        for event in events
    )
    healthy_components = {
        event["component"] for event in events if event["decision"] == "probe-healthy"
    }
    assert healthy_components == {"api", "classroom", "tile-service"}


def test_watchdog_timer_and_installer_contract() -> None:
    timer = (ROOT / "deploy" / "systemd" / "pathlab-viewer-watchdog.timer").read_text(
        encoding="utf-8"
    )
    service = (ROOT / "deploy" / "systemd" / "pathlab-viewer-watchdog.service").read_text(
        encoding="utf-8"
    )
    installer = (ROOT / "deploy" / "scripts" / "install-watchdog.sh").read_text(encoding="utf-8")

    assert "OnUnitActiveSec=15s" in timer
    assert "Persistent=false" in timer
    assert "component_watchdog.py" in service
    assert "install -m 0644" in installer
    assert "systemctl enable --now pathlab-viewer-watchdog.timer" in installer
    assert "systemctl disable --now pathlab-viewer-watchdog.timer" in installer
    override = (ROOT / "deploy" / "scripts" / "with-capacity-override.sh").read_text(
        encoding="utf-8"
    )
    assert "trap restore_prior EXIT" in override
    assert "trap 'exit 130' INT" in override
    assert "trap 'exit 143' TERM" in override
    assert "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=2000" in override
    assert 'RESTORE_LIMIT="300"' in override
    assert "PATHLAB_CAPACITY_WINDOW_START_EPOCH" in override
    assert "PATHLAB_CAPACITY_WINDOW_END_EPOCH" in override
    assert "WINDOW_END_EPOCH - WINDOW_START_EPOCH" in override
    assert "today 05:00:00" not in override
    assert override.index('"$@"') < override.index('FINAL_LIMIT="$("${PYTHON_BIN}"')


def test_preflight_and_postflight_accept_complete_exact_sha_evidence() -> None:
    safety = _load_script("production_safety")
    sha = "a" * 40
    evidence = _valid_evidence(sha)
    key = b"test-only-deployment-evidence-key-32-bytes"
    signature = safety.sign_evidence(evidence, key)

    safety.validate_signed(
        evidence, sha, signature, key, now=1_700_000_100, expected_nonce="run-123-attempt-1"
    )


def test_signed_evidence_rejects_tampering_staleness_and_nonce_replay() -> None:
    safety = _load_script("production_safety")
    sha = "c" * 40
    key = b"test-only-deployment-evidence-key-32-bytes"
    evidence = _valid_evidence(sha)
    signature = safety.sign_evidence(evidence, key)

    evidence["cost"]["projectedIncremental"] = 0.01
    with pytest.raises(safety.GuardFailure):
        safety.validate_signed(
            evidence, sha, signature, key, now=1_700_000_100, expected_nonce="run-123-attempt-1"
        )
    evidence = _valid_evidence(sha)
    signature = safety.sign_evidence(evidence, key)
    with pytest.raises(safety.GuardFailure):
        safety.validate_signed(
            evidence, sha, signature, key, now=1_700_000_700, expected_nonce="run-123-attempt-1"
        )
    with pytest.raises(safety.GuardFailure):
        safety.validate_signed(
            evidence, sha, signature, key, now=1_700_000_100, expected_nonce="another-run"
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("ci", "required", "backend", "conclusion"), "failure"),
        (("security", "required", "CodeQL (python)", "conclusion"), "failure"),
        (("fixtures", "syntheticOnly"), False),
        (("annotations", "enabled"), True),
        (("egress", "projectedMonthlyBytes"), 9_000_000_000_000),
        (("cost", "monthToDate"), -0.01),
        (("cost", "projectedIncremental"), 0.01),
    ],
)
def test_deployment_guards_fail_closed(path: tuple[str, ...], value: object) -> None:
    safety = _load_script("production_safety")
    sha = "b" * 40
    evidence = _valid_evidence(sha)
    target: dict[str, Any] = evidence
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    with pytest.raises(safety.GuardFailure):
        safety.validate(evidence, sha)


def test_capacity_override_restores_prior_limit_and_applies_only_allowed_final_limit(
    tmp_path: Path,
) -> None:
    safety = _load_script("production_safety")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DOMAIN=viewer.test\nPATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n",
        encoding="utf-8",
    )

    with safety.capacity_override(env_file, temporary_limit=2000) as restore:
        assert "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=2000" in env_file.read_text(encoding="utf-8")
        restore(1200)

    assert "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=1200" in env_file.read_text(encoding="utf-8")

    with (
        pytest.raises(safety.GuardFailure),
        safety.capacity_override(env_file, temporary_limit=2000) as restore,
    ):
        restore(1750)

    assert "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=1200" in env_file.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("strict_1200", "strict_1500", "expected"),
    [(False, False, 300), (True, False, 1200), (True, True, 1500)],
)
def test_final_capacity_is_derived_from_strict_evidence(
    strict_1200: bool, strict_1500: bool, expected: int
) -> None:
    safety = _load_script("production_safety")

    evidence = _capacity_evidence(strict_1200, strict_1500)
    assert (
        safety.select_final_capacity(
            evidence,
            expected_sha="d" * 40,
            expected_run_id="run-456",
            expected_nonce="capacity-nonce",
            not_before=1_786_649_400,
        )
        == expected
    )


def test_failed_strict_run_can_select_300_without_claiming_earlier_gates() -> None:
    safety = _load_script("production_safety")
    evidence = _capacity_evidence(False, False)
    for name in ("smoke-2", "smoke-100", "boundary-300", "boundary-600", "boundary-900"):
        evidence["stageResults"][name] = {"durationSeconds": 0, "status": "skipped"}
    assert (
        safety.select_final_capacity(
            evidence,
            expected_sha="d" * 40,
            expected_run_id="run-456",
            expected_nonce="capacity-nonce",
            not_before=1_786_649_400,
        )
        == 300
    )


def test_final_capacity_rejects_inconsistent_evidence() -> None:
    safety = _load_script("production_safety")

    with pytest.raises(safety.GuardFailure):
        safety.select_final_capacity(
            _capacity_evidence(False, True),
            expected_sha="d" * 40,
            expected_run_id="run-456",
            expected_nonce="capacity-nonce",
            not_before=1_786_649_400,
        )


def test_final_capacity_rejects_completion_after_authorized_window() -> None:
    safety = _load_script("production_safety")
    evidence = _capacity_evidence(True, True)
    evidence["startedAt"] = 1_786_658_340  # 04:59 ICT
    evidence["completedAt"] = 1_786_662_540
    with pytest.raises(safety.GuardFailure, match="authorized capacity window"):
        safety.select_final_capacity(
            evidence,
            expected_sha="d" * 40,
            expected_run_id="run-456",
            expected_nonce="capacity-nonce",
            not_before=1_786_658_340,
        )


def test_final_capacity_accepts_a_signed_custom_three_hour_window() -> None:
    safety = _load_script("production_safety")
    evidence = _capacity_evidence(True, True)
    evidence["authorizedWindowStart"] = 1_786_676_400  # 10:00 ICT
    evidence["authorizedWindowEnd"] = 1_786_687_200  # 13:00 ICT
    evidence["startedAt"] = 1_786_678_200
    evidence["completedAt"] = 1_786_682_400

    assert safety.select_final_capacity(
        evidence,
        expected_sha="d" * 40,
        expected_run_id="run-456",
        expected_nonce="capacity-nonce",
        not_before=1_786_676_400,
    ) == 1500


def test_release_flow_installs_watchdog_and_runs_guards() -> None:
    release = (ROOT / "deploy" / "scripts" / "deploy-release.sh").read_text(encoding="utf-8")

    assert "production_safety.py" in release
    assert "preflight" in release
    assert "capacity-postflight" in release
    assert "install-watchdog.sh" in release
    assert "restore_watchdog" in release
    assert "systemctl disable --now pathlab-viewer-watchdog.timer" in release
    assert '"${ROLLBACK_DIR}/deploy/scripts/install-watchdog.sh" uninstall' not in release
    assert release.index('compose_release "${LIVE_DIR}" stop worker') < release.index(
        'bash "${STAGE_DIR}/deploy/scripts/backup-current-database.sh"'
    )
    assert release.index("OLD_SERVICES_STOPPED=1") < release.index(
        'compose_release "${LIVE_DIR}" stop worker'
    )
    assert release.index('compose_release "${LIVE_DIR}" stop caddy tusd') < release.index(
        'bash "${STAGE_DIR}/deploy/scripts/backup-current-database.sh"'
    )
    old_topology_stop = release[
        release.index("OLD_WORKER_STOPPED=1") : release.index("BACKUP_PATH=")
    ]
    assert "docker compose stop caddy classroom tusd" not in old_topology_stop
    assert '"https://${DOMAIN}/livez"' in release
    assert '"https://${DOMAIN}/"' in release
    assert "Tus-Resumable: 1.0.0" in release
    assert ".State.Health.Status" in release


def test_release_flow_uses_candidate_backup_format_against_candidate_compose() -> None:
    release = (ROOT / "deploy" / "scripts" / "deploy-release.sh").read_text(
        encoding="utf-8"
    )

    backup_start = release.index('BACKUP_PATH="$(')
    backup_block = release[
        backup_start : release.index('mv "${LIVE_DIR}"', backup_start)
    ]
    assert 'cd "${STAGE_DIR}/deploy"' in backup_block
    assert 'bash "${STAGE_DIR}/deploy/scripts/backup-current-database.sh"' in backup_block
    assert 'bash "${STAGE_DIR}/deploy/scripts/verify-current-restore-drill.sh"' in backup_block
    assert "bash scripts/backup.sh" not in backup_block
    backup = (ROOT / "deploy" / "scripts" / "backup.sh").read_text(encoding="utf-8")
    assert "docker compose run --rm --no-deps --entrypoint python api" in backup
    assert "docker compose exec -T api" not in backup


def test_release_flow_atomically_refreshes_forced_command_after_health() -> None:
    release = (ROOT / "deploy" / "scripts" / "deploy-release.sh").read_text(
        encoding="utf-8"
    )

    install_call = 'install_stable_dispatcher "${LIVE_DIR}/deploy/scripts/deploy-release.sh"'
    assert 'STABLE_DISPATCHER="/usr/local/sbin/pathlab-viewer-deploy"' in release
    assert "mktemp \"${dispatcher_directory}/.pathlab-viewer-deploy.XXXXXX\"" in release
    assert 'mv -f -- "${TEMP_DISPATCHER}" "${STABLE_DISPATCHER}"' in release
    assert "os.fsync" in release
    assert release.index('[[ "$(cat "${LIVE_DIR}/.pathlab-release")"') < release.index(
        install_call
    )


def test_release_flow_contains_transport_loss_before_and_after_swap() -> None:
    release = (ROOT / "deploy" / "scripts" / "deploy-release.sh").read_text(
        encoding="utf-8"
    )

    assert "interrupt_deployment()" in release
    assert "trap interrupt_deployment HUP INT TERM" in release
    interrupt = release[
        release.index("interrupt_deployment()") : release.index("restart_old_worker()")
    ]
    assert 'if [[ "${SWAPPED}" -eq 1 ]]' in interrupt
    assert "rollback_release" in interrupt
    assert "restart_old_worker" in interrupt


def test_release_flow_has_exact_release_bound_one_time_evidence_key_provisioning() -> None:
    release = (ROOT / "deploy" / "scripts" / "deploy-release.sh").read_text(
        encoding="utf-8"
    )

    assert "provision-evidence-key" in release
    assert "sha=([0-9a-f]{40})" in release
    assert "IFS= read -r PROVISION_KEY" in release
    assert '[[ "${PROVISION_KEY}" =~ ^[0-9a-f]{64}$ ]]' in release
    assert '[[ "${current_release_sha}" == "${provision_sha}" ]]' in release
    assert '[[ "${remote_main_sha}" == "${provision_sha}" ]]' in release
    assert 'install -d -m 755 "${key_directory}"' in release
    assert 'chmod 600 "${EVIDENCE_KEY_PATH}"' in release
    assert 'mv -f -- "${TEMP_KEY}" "${EVIDENCE_KEY_PATH}"' in release
    assert "Deployment evidence key provisioned" in release


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_evidence_key_provisioning_is_atomic_idempotent_and_release_bound(
    tmp_path: Path,
) -> None:
    release_dir = tmp_path / "live"
    release_dir.mkdir()
    sha = "a" * 40
    (release_dir / ".pathlab-release").write_text(f"{sha}\n", encoding="utf-8")
    key_path = tmp_path / "etc" / "deploy-evidence.key"
    lock_path = tmp_path / "deploy.lock"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_flock = fake_bin / "flock"
    fake_flock.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_flock.chmod(0o755)
    fake_python = fake_bin / "python3"
    fake_python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    script = ROOT / "deploy" / "scripts" / "deploy-release.sh"
    first_key = "b" * 64
    second_key = "c" * 64

    common = f"""
export PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY=1
export PATHLAB_DEPLOY_TEST_REMOTE_MAIN_SHA={sha}
export PATH='{_bash_path(fake_bin)}':$PATH
source '{_bash_path(script)}'
LIVE_DIR='{_bash_path(release_dir)}'
LOCK_FILE='{_bash_path(lock_path)}'
EVIDENCE_KEY_PATH='{_bash_path(key_path)}'
"""
    success = subprocess.run(
        [
            str(BASH),
            "-lc",
            common
            + f"provision_evidence_key {sha} {first_key}\n"
            + f"provision_evidence_key {sha} {first_key}\n",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert success.returncode == 0, success.stderr
    assert key_path.read_text(encoding="utf-8") == first_key
    if os.name != "nt":
        assert key_path.stat().st_mode & 0o777 == 0o600

    conflict = subprocess.run(
        [str(BASH), "-lc", common + f"provision_evidence_key {sha} {second_key}\n"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert conflict.returncode != 0
    assert "different deployment evidence key" in conflict.stderr
    assert key_path.read_text(encoding="utf-8") == first_key

    wrong_release = tmp_path / "wrong-live"
    wrong_release.mkdir()
    (wrong_release / ".pathlab-release").write_text(f"{'d' * 40}\n", encoding="utf-8")
    wrong_key_path = tmp_path / "wrong-etc" / "deploy-evidence.key"
    mismatch_script = common.replace(
        f"LIVE_DIR='{_bash_path(release_dir)}'", f"LIVE_DIR='{_bash_path(wrong_release)}'"
    ).replace(
        f"EVIDENCE_KEY_PATH='{_bash_path(key_path)}'",
        f"EVIDENCE_KEY_PATH='{_bash_path(wrong_key_path)}'",
    )
    mismatch = subprocess.run(
        [str(BASH), "-lc", mismatch_script + f"provision_evidence_key {sha} {first_key}\n"],
        text=True,
        capture_output=True,
        check=False,
    )
    assert mismatch.returncode != 0
    assert "not bound to the live release" in mismatch.stderr
    assert not wrong_key_path.exists()


def test_deploy_workflow_produces_and_transports_authenticated_evidence() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-production.yml").read_text(
        encoding="utf-8"
    )
    bastion = (ROOT / "deploy" / "scripts" / "deploy-via-bastion.sh").read_text(encoding="utf-8")
    assert "build_deploy_evidence.py" in workflow
    assert "request-summarized-usages" in workflow
    assert "browser" in workflow
    assert "PATHLAB_DEPLOY_EVIDENCE_KEY" in workflow
    assert "evidence=${EVIDENCE_B64}" in bastion
    assert "signature=${PATHLAB_DEPLOY_EVIDENCE_SIGNATURE}" in bastion
    assert 'REMOTE_REQUEST="provision-evidence-key sha=${TARGET_SHA}"' in bastion
    assert "printf '%s\\n' \"${PATHLAB_DEPLOY_EVIDENCE_KEY}\" | \"${TARGET_SSH[@]}\"" in bastion
    assert "provision-evidence-key sha=${TARGET_SHA} key=" not in bastion
    assert '"lifecycle-state" == `ACTIVE`' in bastion
    assert '"lifecycle-state" == `CREATING`' in bastion
    assert '"lifecycle-state" == `DELETING`' in bastion
    assert workflow.index("Remove temporary cloud credentials") < workflow.index(
        "Record deployment result"
    )


def _write_bastion_reconcile_fakes(tmp_path: Path) -> tuple[Path, Path, Path]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    inventory = tmp_path / "inventory.json"
    delete_marker = tmp_path / "deleted.txt"
    oci = fake_bin / "oci"
    oci.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == *"bastion session list"* ]]; then
  if [[ -s "${DELETE_MARKER}" ]]; then
    printf '{"data":[]}\n'
  else
    cat "${OCI_INVENTORY}"
  fi
elif [[ "$*" == *"bastion session delete"* ]]; then
  printf '%s\n' "$*" >> "${DELETE_MARKER}"
else
  exit 90
fi
""",
        encoding="utf-8",
    )
    gh = fake_bin / "gh"
    gh.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
printf '{"status":"%s","conclusion":"%s"}\n' "${GH_RUN_STATUS}" "${GH_RUN_CONCLUSION}"
""",
        encoding="utf-8",
    )
    jq = fake_bin / "jq"
    jq.write_text(
        f"""#!/usr/bin/env bash
exec "{_shell_path(Path(sys.executable))}" - "$@" <<'PY'
import json
import sys

args = sys.argv[1:]
query = next((value for value in args if value.startswith(".")), "")
payload = json.loads(open(args[-1], encoding="utf-8").read())
if 'type == "array"' in query:
    raise SystemExit(0 if isinstance(payload.get("data"), list) else 1)
if query == ".status // empty":
    print(payload.get("status", ""))
elif query == ".conclusion // empty":
    print(payload.get("conclusion", ""))
elif "@tsv" in query:
    for item in payload.get("data", []):
        if item.get("lifecycle-state") in ("ACTIVE", "CREATING", "DELETING"):
            print("\\t".join((item["id"], item.get("display-name", ""), item["lifecycle-state"])))
elif "select(.id == $id)" in query:
    wanted = args[args.index("--arg") + 2]
    for item in payload.get("data", []):
        if item.get("id") == wanted:
            print(item.get("lifecycle-state", ""))
PY
""",
        encoding="utf-8",
    )
    oci.chmod(0o755)
    gh.chmod(0o755)
    jq.chmod(0o755)
    return fake_bin, inventory, delete_marker


@pytest.mark.skipif(PORTABLE_BASH is None, reason="Bash is required")
def test_bastion_reconciliation_deletes_only_failed_terminal_owned_sessions(
    tmp_path: Path,
) -> None:
    fake_bin, inventory, delete_marker = _write_bastion_reconcile_fakes(tmp_path)
    inventory.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "id": "ocid1.bastionsession.first",
                        "display-name": "pathlab-capacity-12345-arm",
                        "lifecycle-state": "DELETING",
                    },
                    {
                        "id": "ocid1.bastionsession.second",
                        "display-name": "pathlab-deploy-12345-1780000000",
                        "lifecycle-state": "CREATING",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_shell_path(fake_bin)}:/usr/bin:/bin",
            "PATHLAB_OCI_COMMAND": _shell_path(fake_bin / "oci"),
            "PATHLAB_GH_COMMAND": _shell_path(fake_bin / "gh"),
            "OCI_INVENTORY": _shell_path(inventory),
            "DELETE_MARKER": _shell_path(delete_marker),
            "GH_RUN_STATUS": "completed",
            "GH_RUN_CONCLUSION": "failure",
            "GH_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "example/pathlab",
            "OCI_BASTION_ID": "masked-test-bastion",
        }
    )
    result = subprocess.run(
        [
            str(PORTABLE_BASH),
            str(ROOT / "deploy" / "scripts" / "reconcile-bastion-sessions.sh"),
            "99999",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "Reconciled 2 terminal PathLab Bastion session(s)." in result.stdout
    assert len(delete_marker.read_text(encoding="utf-8").splitlines()) == 2


@pytest.mark.skipif(PORTABLE_BASH is None, reason="Bash is required")
@pytest.mark.parametrize(
    ("display_name", "run_status", "run_conclusion", "failure"),
    [
        ("pathlab-capacity-12345-arm", "in_progress", "", "not terminal"),
        ("operator-maintenance", "completed", "failure", "not owned"),
        ("pathlab-capacity-12345-arm", "completed", "success", "not an approved"),
    ],
)
def test_bastion_reconciliation_fails_closed_for_unsafe_ownership(
    tmp_path: Path,
    display_name: str,
    run_status: str,
    run_conclusion: str,
    failure: str,
) -> None:
    fake_bin, inventory, delete_marker = _write_bastion_reconcile_fakes(tmp_path)
    inventory.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "id": "ocid1.bastionsession.unsafe",
                        "display-name": display_name,
                        "lifecycle-state": "ACTIVE",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_shell_path(fake_bin)}:/usr/bin:/bin",
            "PATHLAB_OCI_COMMAND": _shell_path(fake_bin / "oci"),
            "PATHLAB_GH_COMMAND": _shell_path(fake_bin / "gh"),
            "OCI_INVENTORY": _shell_path(inventory),
            "DELETE_MARKER": _shell_path(delete_marker),
            "GH_RUN_STATUS": run_status,
            "GH_RUN_CONCLUSION": run_conclusion,
            "GH_TOKEN": "test-token",
            "GITHUB_REPOSITORY": "example/pathlab",
            "OCI_BASTION_ID": "masked-test-bastion",
        }
    )
    result = subprocess.run(
        [
            str(PORTABLE_BASH),
            str(ROOT / "deploy" / "scripts" / "reconcile-bastion-sessions.sh"),
            "99999",
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert failure in result.stderr
    assert not delete_marker.exists()


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_watchdog_install_rolls_back_partial_systemd_failure(tmp_path: Path) -> None:
    release = tmp_path / "release"
    unit_source = release / "deploy" / "systemd"
    unit_source.mkdir(parents=True)
    for name in ("service", "timer"):
        (unit_source / f"pathlab-viewer-watchdog.{name}").write_text(
            f"new-{name}\n", encoding="utf-8"
        )
    unit_dir = tmp_path / "units"
    unit_dir.mkdir()
    (tmp_path / "state").mkdir()
    (unit_dir / "pathlab-viewer-watchdog.service").write_text("old-service\n", encoding="utf-8")
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl = fake_bin / "systemctl"
    systemctl.write_text(
        "#!/usr/bin/env bash\nif [[ \"$1 $2\" == 'enable --now' ]]; then exit 42; fi\nexit 0\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_SYSTEMD_UNIT_DIR": _bash_path(unit_dir),
            "PATHLAB_WATCHDOG_STATE_DIR": _bash_path(tmp_path / "state"),
        }
    )
    result = subprocess.run(
        [
            str(BASH),
            str(ROOT / "deploy" / "scripts" / "install-watchdog.sh"),
            "install",
            _bash_path(release),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 42
    assert (unit_dir / "pathlab-viewer-watchdog.service").read_text(
        encoding="utf-8"
    ) == "old-service\n"
    assert not (unit_dir / "pathlab-viewer-watchdog.timer").exists()


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_watchdog_uninstall_propagates_disable_failure_and_restores_units(
    tmp_path: Path,
) -> None:
    release = tmp_path / "release"
    (release / "deploy" / "systemd").mkdir(parents=True)
    unit_dir = tmp_path / "units"
    state_dir = tmp_path / "state"
    fake_bin = tmp_path / "bin"
    unit_dir.mkdir()
    state_dir.mkdir()
    fake_bin.mkdir()
    for name in ("service", "timer"):
        (unit_dir / f"pathlab-viewer-watchdog.{name}").write_text(f"old-{name}\n", encoding="utf-8")
    systemctl = fake_bin / "systemctl"
    failure_marker = tmp_path / "disable-failed"
    systemctl.write_text(
        "#!/usr/bin/env bash\n"
        f"marker='{_bash_path(failure_marker)}'\n"
        'if [[ "$1 $2" == \'disable --now\' && ! -f "$marker" ]]; then '
        'touch "$marker"; exit 42; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    systemctl.chmod(0o755)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_SYSTEMD_UNIT_DIR": _bash_path(unit_dir),
            "PATHLAB_WATCHDOG_STATE_DIR": _bash_path(state_dir),
        }
    )
    result = subprocess.run(
        [
            str(BASH),
            str(ROOT / "deploy" / "scripts" / "install-watchdog.sh"),
            "uninstall",
            _bash_path(release),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 42
    assert (unit_dir / "pathlab-viewer-watchdog.service").read_text(
        encoding="utf-8"
    ) == "old-service\n"
    assert (unit_dir / "pathlab-viewer-watchdog.timer").read_text(encoding="utf-8") == "old-timer\n"


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_release_rollback_restores_previous_tree_behaviorally(tmp_path: Path) -> None:
    live = tmp_path / "live"
    rollback = tmp_path / "rollback"
    live.mkdir()
    rollback.mkdir()
    (live / "candidate").write_text("candidate", encoding="utf-8")
    restore_script = live / "deploy" / "scripts" / "restore-deploy-rollback-database.sh"
    restore_script.parent.mkdir(parents=True)
    restore_marker = tmp_path / "database-restored"
    restore_script.write_text(
        "#!/usr/bin/env bash\n"
        f"touch '{_bash_path(restore_marker)}'\n",
        encoding="utf-8",
    )
    restore_script.chmod(0o755)
    (rollback / "previous").write_text("previous", encoding="utf-8")
    backup = tmp_path / "data" / "backups" / "backup-1"
    backup.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl = fake_bin / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)
    shell = (
        "set -Eeuo pipefail; export PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY=1; "
        'source "$1"; LIVE_DIR="$2"; ROLLBACK_DIR="$3"; SWAPPED=1; '
        'BACKUP_PATH="$4"; DATA_DIR="$5"; BACKUP_DIR="$6"; '
        "WATCHDOG_CHANGED=0; OLD_WORKER_STOPPED=0; OLD_SERVICES_STOPPED=0; "
        "rollback_release"
    )
    env = os.environ.copy()
    env["PATH"] = f"{_bash_path(fake_bin)}:{env['PATH']}"
    result = subprocess.run(
        [
            str(BASH),
            "-c",
            shell,
            "rollback-test",
            _bash_path(ROOT / "deploy" / "scripts" / "deploy-release.sh"),
            _bash_path(live),
            _bash_path(rollback),
            _bash_path(backup),
            _bash_path(tmp_path / "data"),
            _bash_path(tmp_path / "data" / "backups"),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert restore_marker.exists()
    assert (live / "previous").read_text(encoding="utf-8") == "previous"
    failed = list(tmp_path.glob("live.failed-*"))
    assert len(failed) == 1
    assert (failed[0] / "candidate").read_text(encoding="utf-8") == "candidate"


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_release_rollback_fails_closed_when_database_restore_fails(tmp_path: Path) -> None:
    live = tmp_path / "live"
    rollback = tmp_path / "rollback"
    restore_script = live / "deploy" / "scripts" / "restore-deploy-rollback-database.sh"
    restore_script.parent.mkdir(parents=True)
    restore_script.write_text("#!/usr/bin/env bash\nexit 42\n", encoding="utf-8")
    restore_script.chmod(0o755)
    rollback.mkdir()
    (live / "candidate").write_text("candidate", encoding="utf-8")
    (rollback / "previous").write_text("previous", encoding="utf-8")
    backup = tmp_path / "data" / "backups" / "backup-1"
    backup.mkdir(parents=True)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl = fake_bin / "systemctl"
    systemctl.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    systemctl.chmod(0o755)
    shell = (
        "set -Eeuo pipefail; export PATHLAB_DEPLOY_RELEASE_LIBRARY_ONLY=1; "
        'source "$1"; LIVE_DIR="$2"; ROLLBACK_DIR="$3"; SWAPPED=1; '
        'BACKUP_PATH="$4"; DATA_DIR="$5"; BACKUP_DIR="$6"; '
        "WATCHDOG_CHANGED=0; OLD_WORKER_STOPPED=0; OLD_SERVICES_STOPPED=0; "
        "rollback_release"
    )
    env = os.environ.copy()
    env["PATH"] = f"{_bash_path(fake_bin)}:{env['PATH']}"
    result = subprocess.run(
        [
            str(BASH),
            "-c",
            shell,
            "rollback-test",
            _bash_path(ROOT / "deploy" / "scripts" / "deploy-release.sh"),
            _bash_path(live),
            _bash_path(rollback),
            _bash_path(backup),
            _bash_path(tmp_path / "data"),
            _bash_path(tmp_path / "data" / "backups"),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert "candidate release retained for schema compatibility" in result.stderr
    assert (live / "candidate").read_text(encoding="utf-8") == "candidate"
    assert (rollback / "previous").read_text(encoding="utf-8") == "previous"


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_capacity_shell_contains_failed_restoration(tmp_path: Path) -> None:
    compose_dir = tmp_path / "deploy"
    runtime_dir = compose_dir / "runtime"
    fake_bin = tmp_path / "bin"
    compose_dir.mkdir()
    runtime_dir.mkdir()
    fake_bin.mkdir()
    env_file = compose_dir / ".env"
    env_file.write_text("PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n", encoding="utf-8")
    decision = runtime_dir / "pathlab-capacity-run-789.json"
    decision_signature = Path(f"{decision}.sig")
    command = fake_bin / "run-load"
    command.write_text(
        f"#!/usr/bin/env bash\nprintf '{{}}' > '{_bash_path(decision)}'\n"
        f"printf '%064d' 0 > '{_bash_path(decision_signature)}'\n",
        encoding="utf-8",
    )
    python = fake_bin / "python3"
    python.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \" $* \" == *' capacity-decision '* ]]; then echo 1200; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        f"log='{_bash_path(tmp_path / 'docker.log')}'\n"
        'printf \'%s\\n\' "$*" >> "$log"\n'
        "if [[ \" $* \" == *' compose up '* ]]; then\n"
        f"  count_file='{_bash_path(tmp_path / 'up-count')}'\n"
        '  count=0; [[ -f "$count_file" ]] && count=$(cat "$count_file")\n'
        '  count=$((count + 1)); printf \'%s\' "$count" > "$count_file"\n'
        "  [[ $count -gt 1 ]] && exit 9\n"
        "fi\n"
        "if [[ \" $* \" == *' compose ps '* ]]; then printf 'api\\nclassroom\\n'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    date = fake_bin / "date"
    date.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \"$1\" == '+%H' ]]; then echo 02; "
        "elif [[ \"$1\" == '+%s' ]]; then echo 1786649400; "
        'else /usr/bin/date "$@"; fi\n',
        encoding="utf-8",
    )
    for executable in (command, python, docker, date):
        executable.chmod(0o755)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_CAPACITY_TEST_MODE": "1",
            "PATHLAB_CAPACITY_TEST_ICT_HOUR": "02",
            "PATHLAB_CAPACITY_ENV_FILE": _bash_path(env_file),
            "PATHLAB_COMPOSE_DIR": _bash_path(compose_dir),
            "PATHLAB_CAPACITY_RUNTIME_DIR": _bash_path(runtime_dir),
            "PATHLAB_CAPACITY_DECISION_FILE": _bash_path(decision),
            "PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE": _bash_path(decision_signature),
            "PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE": _bash_path(evidence),
            "PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE": "a" * 64,
            "PATHLAB_CAPACITY_CANDIDATE_SHA": "b" * 40,
            "PATHLAB_CAPACITY_RUN_ID": "run-789",
            "PATHLAB_CAPACITY_NONCE": "nonce-run-789",
            "PATHLAB_PYTHON": _bash_path(python),
        }
    )
    result = subprocess.run(
        [
            str(BASH),
            str(ROOT / "deploy" / "scripts" / "with-capacity-override.sh"),
            _bash_path(command),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 1
    assert env_file.read_text(encoding="utf-8") == "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n"
    assert "compose stop api classroom" in (tmp_path / "docker.log").read_text(encoding="utf-8")


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
@pytest.mark.parametrize(("signal", "expected"), [("INT", 130), ("TERM", 143)])
def test_capacity_shell_restores_on_signals(tmp_path: Path, signal: str, expected: int) -> None:
    compose_dir = tmp_path / "deploy"
    runtime_dir = compose_dir / "runtime"
    fake_bin = tmp_path / "bin"
    compose_dir.mkdir()
    runtime_dir.mkdir()
    fake_bin.mkdir()
    env_file = compose_dir / ".env"
    env_file.write_text("PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n", encoding="utf-8")
    command = fake_bin / "signal-load"
    command.write_text(
        f'#!/usr/bin/env bash\nkill -s {signal} "$PPID"\nsleep 1\n',
        encoding="utf-8",
    )
    python = fake_bin / "python3"
    python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \" $* \" == *' compose ps '* ]]; then printf 'api\\nclassroom\\n'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    for executable in (command, python, docker):
        executable.chmod(0o755)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    decision = runtime_dir / "pathlab-capacity-run-signal.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_CAPACITY_TEST_MODE": "1",
            "PATHLAB_CAPACITY_TEST_ICT_HOUR": "02",
            "PATHLAB_CAPACITY_ENV_FILE": _bash_path(env_file),
            "PATHLAB_COMPOSE_DIR": _bash_path(compose_dir),
            "PATHLAB_CAPACITY_RUNTIME_DIR": _bash_path(runtime_dir),
            "PATHLAB_CAPACITY_DECISION_FILE": _bash_path(decision),
            "PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE": _bash_path(Path(f"{decision}.sig")),
            "PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE": _bash_path(evidence),
            "PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE": "a" * 64,
            "PATHLAB_CAPACITY_CANDIDATE_SHA": "b" * 40,
            "PATHLAB_CAPACITY_RUN_ID": "run-signal",
            "PATHLAB_CAPACITY_NONCE": "nonce-run-signal",
            "PATHLAB_PYTHON": _bash_path(python),
        }
    )
    result = subprocess.run(
        [
            str(BASH),
            str(ROOT / "deploy" / "scripts" / "with-capacity-override.sh"),
            _bash_path(command),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected
    assert env_file.read_text(encoding="utf-8") == (
        "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n"
        "PATHLAB_ANNOTATIONS_ENABLED=false\n"
    )


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_capacity_shell_refuses_0459_before_raising_limit(tmp_path: Path) -> None:
    compose_dir = tmp_path / "deploy"
    runtime_dir = compose_dir / "runtime"
    fake_bin = tmp_path / "bin"
    compose_dir.mkdir()
    runtime_dir.mkdir()
    fake_bin.mkdir()
    env_file = compose_dir / ".env"
    env_file.write_text("PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n", encoding="utf-8")
    python = fake_bin / "python3"
    python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    command = fake_bin / "must-not-run"
    marker = tmp_path / "ran"
    command.write_text(f"#!/usr/bin/env bash\ntouch '{_bash_path(marker)}'\n", encoding="utf-8")
    python.chmod(0o755)
    command.chmod(0o755)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    decision = runtime_dir / "pathlab-capacity-run-late.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_CAPACITY_TEST_MODE": "1",
            "PATHLAB_CAPACITY_TEST_ICT_HOUR": "04",
            "PATHLAB_CAPACITY_TEST_ICT_SECONDS": "17940",
            "PATHLAB_CAPACITY_ENV_FILE": _bash_path(env_file),
            "PATHLAB_COMPOSE_DIR": _bash_path(compose_dir),
            "PATHLAB_CAPACITY_RUNTIME_DIR": _bash_path(runtime_dir),
            "PATHLAB_CAPACITY_DECISION_FILE": _bash_path(decision),
            "PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE": _bash_path(Path(f"{decision}.sig")),
            "PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE": _bash_path(evidence),
            "PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE": "a" * 64,
            "PATHLAB_CAPACITY_CANDIDATE_SHA": "b" * 40,
            "PATHLAB_CAPACITY_RUN_ID": "run-late",
            "PATHLAB_CAPACITY_NONCE": "nonce-run-late",
            "PATHLAB_PYTHON": _bash_path(python),
        }
    )
    result = subprocess.run(
        [
            str(BASH),
            str(ROOT / "deploy" / "scripts" / "with-capacity-override.sh"),
            _bash_path(command),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 2
    assert "two hours before the authorized hard stop" in result.stderr
    assert env_file.read_text(encoding="utf-8") == "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n"
    assert not marker.exists()


@pytest.mark.skipif(not BASH.exists(), reason="Git Bash is required")
def test_capacity_shell_terminates_overrun_and_restores_limit(tmp_path: Path) -> None:
    compose_dir = tmp_path / "deploy"
    runtime_dir = compose_dir / "runtime"
    fake_bin = tmp_path / "bin"
    compose_dir.mkdir()
    runtime_dir.mkdir()
    fake_bin.mkdir()
    env_file = compose_dir / ".env"
    env_file.write_text("PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n", encoding="utf-8")
    started = tmp_path / "started"
    terminated = tmp_path / "terminated"
    command = fake_bin / "overrun-load"
    command.write_text(
        "#!/usr/bin/env bash\n"
        f"touch '{_bash_path(started)}'\n"
        f"trap \"touch '{_bash_path(terminated)}'\" TERM\n"
        "while :; do sleep 1; done\n",
        encoding="utf-8",
    )
    python = fake_bin / "python3"
    python.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    date = fake_bin / "date"
    date.write_text("#!/usr/bin/env bash\nprintf '1700000000\\n'\n", encoding="utf-8")
    docker = fake_bin / "docker"
    docker.write_text(
        "#!/usr/bin/env bash\n"
        "if [[ \" $* \" == *' compose ps '* ]]; then printf 'api\\nclassroom\\n'; fi\n"
        "exit 0\n",
        encoding="utf-8",
    )
    for executable in (command, python, date, docker):
        executable.chmod(0o755)
    evidence = tmp_path / "evidence.json"
    evidence.write_text("{}", encoding="utf-8")
    decision = runtime_dir / "pathlab-capacity-run-overrun.json"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{_bash_path(fake_bin)}:{env['PATH']}",
            "PATHLAB_CAPACITY_TEST_MODE": "1",
            "PATHLAB_CAPACITY_TEST_ICT_HOUR": "02",
            "PATHLAB_CAPACITY_TEST_ICT_SECONDS": "7200",
            "PATHLAB_CAPACITY_TEST_REQUIRED_RUNTIME_SECONDS": "1",
            "PATHLAB_CAPACITY_TEST_LAUNCH_SECONDS_UNTIL_END": "5",
            "PATHLAB_CAPACITY_TEST_KILL_AFTER_SECONDS": "1",
            "PATHLAB_CAPACITY_TEST_DEADLINE_SAFETY_SECONDS": "1",
            "PATHLAB_CAPACITY_RESTORE_NOT_AFTER": str(int(time.time()) + 30),
            "PATHLAB_CAPACITY_ENV_FILE": _bash_path(env_file),
            "PATHLAB_COMPOSE_DIR": _bash_path(compose_dir),
            "PATHLAB_CAPACITY_RUNTIME_DIR": _bash_path(runtime_dir),
            "PATHLAB_CAPACITY_DECISION_FILE": _bash_path(decision),
            "PATHLAB_CAPACITY_DECISION_SIGNATURE_FILE": _bash_path(Path(f"{decision}.sig")),
            "PATHLAB_CAPACITY_PREFLIGHT_EVIDENCE": _bash_path(evidence),
            "PATHLAB_CAPACITY_PREFLIGHT_SIGNATURE": "a" * 64,
            "PATHLAB_CAPACITY_CANDIDATE_SHA": "b" * 40,
            "PATHLAB_CAPACITY_RUN_ID": "run-overrun",
            "PATHLAB_CAPACITY_NONCE": "nonce-run-overrun",
            "PATHLAB_PYTHON": _bash_path(python),
        }
    )
    started_at = time.monotonic()
    result = subprocess.run(
        [
            str(BASH),
            str(ROOT / "deploy" / "scripts" / "with-capacity-override.sh"),
            _bash_path(command),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    elapsed = time.monotonic() - started_at
    assert result.returncode in {124, 137}
    assert elapsed < 6
    assert started.exists()
    assert terminated.exists()
    assert env_file.read_text(encoding="utf-8") == (
        "PATHLAB_CLASSROOM_MAX_PARTICIPANTS=300\n"
        "PATHLAB_ANNOTATIONS_ENABLED=false\n"
    )
