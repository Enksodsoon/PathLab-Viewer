#!/usr/bin/env python3
"""Bounded component-local recovery for the PathLab production stack."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

COMPONENTS = {
    "api": "http://127.0.0.1:8000/livez",
    "classroom": "http://127.0.0.1:8001/livez",
    "tile-service": "http://127.0.0.1:8090/readyz",
}
FAILURES_BEFORE_RESTART = 3
RESTART_LIMIT = 3
RESTART_WINDOW_SECONDS = 600
DIAGNOSTIC_LIMIT = 131_072

Runner = Callable[..., tuple[int, str]]
Clock = Callable[[], int | float]
Journal = Callable[[dict[str, object]], None]


class WatchdogStateError(RuntimeError):
    pass


def _default_state() -> dict[str, object]:
    return {
        "version": 1,
        "restartActions": [],
        "components": {component: {"consecutiveFailures": 0} for component in COMPONENTS},
    }


def _load_state(path: Path) -> dict[str, object]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _default_state()
    except (OSError, json.JSONDecodeError) as error:
        raise WatchdogStateError("watchdog state cannot be read safely") from error
    if not isinstance(state, dict) or state.get("version") != 1:
        raise WatchdogStateError("watchdog state has an invalid structure")
    components = state.get("components")
    if not isinstance(components, dict) or set(components) != set(COMPONENTS):
        raise WatchdogStateError("watchdog component state is incomplete")
    for value in components.values():
        if not isinstance(value, dict):
            raise WatchdogStateError("watchdog component state is invalid")
        failures = value.get("consecutiveFailures")
        if not isinstance(failures, int) or isinstance(failures, bool) or failures < 0:
            raise WatchdogStateError("watchdog failure count is invalid")
    actions = state.get("restartActions")
    if not isinstance(actions, list):
        raise WatchdogStateError("watchdog restart history is invalid")
    for action in actions:
        if not isinstance(action, dict) or set(action) != {"at", "component", "outcome"}:
            raise WatchdogStateError("watchdog restart action is invalid")
        if (
            not isinstance(action["at"], int)
            or isinstance(action["at"], bool)
            or action["at"] < 0
            or action["component"] not in COMPONENTS
            or action["outcome"] not in {"reserved", "succeeded", "failed"}
        ):
            raise WatchdogStateError("watchdog restart action is invalid")
    return state


def _save_state(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def _run(command: list[str], *, timeout: int, capture: bool = False) -> tuple[int, str]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return 124, f"timed out after {error.timeout} seconds"
    output = (result.stdout + result.stderr)[:DIAGNOSTIC_LIMIT] if capture else ""
    return result.returncode, output


def _journal(event: dict[str, object]) -> None:
    print(json.dumps({"source": "pathlab-component-watchdog", **event}, sort_keys=True))


def _component_state(state: dict[str, object], component: str) -> dict[str, object]:
    components = state["components"]
    assert isinstance(components, dict)
    value = components[component]
    assert isinstance(value, dict)
    return value


def _capture_diagnostics(
    state_dir: Path, compose_dir: Path, component: str, now: int, runner: Runner
) -> Path:
    sections: list[str] = []
    identity_command = ["docker", "compose", "ps", "-q", component]
    identity_code, identity_output = runner(identity_command, timeout=5, capture=True)
    sections.append(
        f"$ {' '.join(identity_command)}\nexit={identity_code}\n"
        f"{identity_output[:DIAGNOSTIC_LIMIT]}"
    )
    commands: list[list[str]] = []
    container_id = identity_output.strip().splitlines()[0] if identity_code == 0 else ""
    if container_id:
        commands.append(
            [
                "docker",
                "inspect",
                "--format",
                "status={{.State.Status}} running={{.State.Running}} "
                "paused={{.State.Paused}} restarting={{.State.Restarting}} "
                "oomKilled={{.State.OOMKilled}} exitCode={{.State.ExitCode}} "
                "startedAt={{.State.StartedAt}} finishedAt={{.State.FinishedAt}} "
                "{{if .State.Health}}health={{.State.Health.Status}}{{end}} "
                "memory={{.HostConfig.Memory}} "
                "nanoCpus={{.HostConfig.NanoCpus}} restarts={{.RestartCount}}",
                container_id,
            ]
        )
    for command in commands:
        code, output = runner(command, timeout=5, capture=True)
        sections.append(f"$ {' '.join(command)}\nexit={code}\n{output[:DIAGNOSTIC_LIMIT]}")
    diagnostics = state_dir / f"diagnostic-{component}-{now}.log"
    diagnostics.write_text("\n\n".join(sections)[:DIAGNOSTIC_LIMIT], encoding="utf-8")
    os.chmod(diagnostics, 0o600)
    return diagnostics


def run_cycle(
    state_dir: Path,
    compose_dir: Path,
    runner: Runner = _run,
    clock: Clock = time.time,
    journal: Journal = _journal,
) -> None:
    """Probe all guarded components once and perform bounded local recovery."""
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = int(clock())
    state_path = state_dir / "state.json"
    state = _load_state(state_path)

    previous_dir = Path.cwd()
    try:
        os.chdir(compose_dir)
        for component, url in COMPONENTS.items():
            component_state = _component_state(state, component)
            code, _ = runner(
                [
                    "docker",
                    "compose",
                    "exec",
                    "-T",
                    component,
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "5",
                    url,
                ],
                timeout=7,
                capture=False,
            )
            raw_failures = component_state.get("consecutiveFailures", 0)
            if not isinstance(raw_failures, int) or isinstance(raw_failures, bool):
                raise WatchdogStateError("watchdog failure count is invalid")
            failures = raw_failures
            if code == 0:
                if failures:
                    journal({"component": component, "decision": "recovered", "failures": failures})
                component_state["consecutiveFailures"] = 0
                journal({"component": component, "decision": "probe-healthy"})
                continue

            failures += 1
            component_state["consecutiveFailures"] = failures
            journal({"component": component, "decision": "probe-failed", "failures": failures})
            if failures < FAILURES_BEFORE_RESTART:
                continue

            diagnostic = _capture_diagnostics(state_dir, compose_dir, component, now, runner)
            journal(
                {
                    "component": component,
                    "decision": "diagnostics-captured",
                    "path": str(diagnostic),
                }
            )
            raw_actions = state.get("restartActions", [])
            if not isinstance(raw_actions, list):
                raise WatchdogStateError("watchdog restart history is invalid")
            actions = [
                action
                for action in raw_actions
                if isinstance(action, dict)
                and isinstance(action.get("at"), int)
                and 0 <= now - action["at"] < RESTART_WINDOW_SECONDS
            ]
            state["restartActions"] = actions
            if len(actions) >= RESTART_LIMIT:
                journal(
                    {
                        "component": component,
                        "decision": "restart-refused-anti-flap",
                        "restartsInWindow": len(actions),
                    }
                )
                continue

            reservation = {"at": now, "component": component, "outcome": "reserved"}
            actions.append(reservation)
            state["restartActions"] = actions
            _save_state(state_path, state)
            try:
                restart_code, _ = runner(
                    ["docker", "compose", "restart", component], timeout=90, capture=False
                )
            except Exception:
                _save_state(state_path, state)
                raise
            if restart_code == 0:
                reservation["outcome"] = "succeeded"
                component_state["consecutiveFailures"] = 0
                journal({"component": component, "decision": "restarted"})
            else:
                reservation["outcome"] = "failed"
                journal({"component": component, "decision": "restart-failed"})
            _save_state(state_path, state)
    finally:
        os.chdir(previous_dir)
        _save_state(state_path, state)


def main() -> int:
    state_dir = Path(
        os.environ.get("PATHLAB_WATCHDOG_STATE_DIR", "/var/lib/pathlab-viewer-watchdog")
    )
    compose_dir = Path(os.environ.get("PATHLAB_COMPOSE_DIR", "/opt/pathlab-viewer/deploy"))
    try:
        run_cycle(state_dir, compose_dir)
    except Exception as error:
        _journal({"decision": "watchdog-error", "error": type(error).__name__})
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
