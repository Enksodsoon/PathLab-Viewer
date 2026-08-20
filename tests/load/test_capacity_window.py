from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from distributed_certification import ICT, build_plan


def _epoch(hour: int, minute: int, second: int = 0) -> int:
    return int(datetime(2026, 8, 15, hour, minute, second, tzinfo=ICT).timestamp())


def _write_plan(path: Path, *, window_hour: int = 2) -> None:
    plan = build_plan(
        run_id="window-proof",
        workflow_sha="b" * 40,
        browser_ci_run_id=42,
        start_epoch_ms=_epoch(window_hour, 9) * 1000,
        window_start_epoch_ms=_epoch(window_hour, 0) * 1000,
        now_epoch_ms=_epoch(window_hour - 1, 50) * 1000,
    )
    path.write_text(json.dumps(plan), encoding="utf-8")


def _run_window_tool(plan: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PATHLAB_CAPACITY_TEST_MODE": "true"}
    return subprocess.run(
        [
            sys.executable,
            "deploy/scripts/capacity_window.py",
            "--plan",
            str(plan),
            *arguments,
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_window_description_proves_every_phase_and_safety_margin(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)

    completed = _run_window_tool(plan_path, "describe")

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {
        "mutationStartEpoch": _epoch(2, 0),
        "armNotAfterEpoch": _epoch(2, 4),
        "admissionStartEpoch": _epoch(2, 9),
        "finalTransitionEpoch": _epoch(4, 34, 30),
        "decisionDeadlineEpoch": _epoch(4, 37, 30),
        "cleanupExecutionDeadlineEpoch": _epoch(4, 45),
        "restorationDeadlineEpoch": _epoch(4, 49, 30),
        "postflightDeadlineEpoch": _epoch(4, 54, 30),
        "workflowCutoffEpoch": _epoch(4, 57, 30),
        "windowEndEpoch": _epoch(5, 0),
        "safetyMarginSeconds": 150,
    }


def test_window_description_supports_an_explicit_custom_ict_window(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path, window_hour=10)

    completed = _run_window_tool(plan_path, "describe")

    assert completed.returncode == 0, completed.stderr
    value = json.loads(completed.stdout)
    assert value["mutationStartEpoch"] == _epoch(10, 0)
    assert value["admissionStartEpoch"] == _epoch(10, 9)
    assert value["windowEndEpoch"] == _epoch(13, 0)
    assert value["workflowCutoffEpoch"] == _epoch(12, 57, 30)
    assert value["safetyMarginSeconds"] == 150


def test_phase_remaining_fails_closed_before_and_after_its_window(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)

    before_mutation = _run_window_tool(
        plan_path, "remaining", "--phase", "arm", "--now-epoch", str(_epoch(1, 59, 59))
    )
    at_mutation = _run_window_tool(
        plan_path, "remaining", "--phase", "arm", "--now-epoch", str(_epoch(2, 0))
    )
    after_arm = _run_window_tool(
        plan_path, "remaining", "--phase", "arm", "--now-epoch", str(_epoch(2, 3, 1))
    )
    cleanup = _run_window_tool(
        plan_path, "remaining", "--phase", "cleanup", "--now-epoch", str(_epoch(4, 40))
    )
    postflight = _run_window_tool(
        plan_path, "remaining", "--phase", "postflight", "--now-epoch", str(_epoch(4, 50))
    )
    aggregate = _run_window_tool(
        plan_path, "remaining", "--phase", "aggregate", "--now-epoch", str(_epoch(4, 55))
    )

    assert before_mutation.returncode != 0
    assert at_mutation.returncode == 0 and at_mutation.stdout.strip() == "240"
    assert after_arm.returncode == 0 and after_arm.stdout.strip() == "59"
    assert cleanup.returncode == 0 and cleanup.stdout.strip() == "300"
    assert postflight.returncode == 0 and postflight.stdout.strip() == "270"
    assert aggregate.returncode == 0 and aggregate.stdout.strip() == "150"


def test_now_override_is_rejected_outside_test_mode(tmp_path: Path) -> None:
    plan_path = tmp_path / "plan.json"
    _write_plan(plan_path)
    env = {key: value for key, value in os.environ.items() if key != "PATHLAB_CAPACITY_TEST_MODE"}

    completed = subprocess.run(
        [
            sys.executable,
            "deploy/scripts/capacity_window.py",
            "--plan",
            str(plan_path),
            "remaining",
            "--phase",
            "arm",
            "--now-epoch",
            str(_epoch(2, 0)),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.returncode != 0
