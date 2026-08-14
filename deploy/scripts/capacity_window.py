"""Fail-closed wall-clock bounds for the production capacity workflow."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "tests" / "load"))

from distributed_certification import ICT, build_plan, validate_plan  # noqa: E402

ARM_RUNWAY_SECONDS = 240
DECISION_SECONDS = 180
RESTORATION_SECONDS = 900
POSTFLIGHT_SECONDS = 300
AGGREGATE_SECONDS = 180
MINIMUM_SAFETY_MARGIN_SECONDS = 150
FAIL_SAFE_RECOVERY_SECONDS = 270


class WindowError(ValueError):
    """Raised when a plan or phase falls outside the protected wall clock."""


def _load_plan(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise WindowError("capacity plan must contain an object")
    validate_plan(value)
    return value


def describe(plan: dict[str, object]) -> dict[str, int]:
    """Return exact phase deadlines after validating the immutable schedule."""
    start_epoch_ms = plan.get("startEpochMs")
    stages = plan.get("stages")
    if not isinstance(start_epoch_ms, int) or not isinstance(stages, list) or not stages:
        raise WindowError("capacity plan schedule is incomplete")
    start = datetime.fromtimestamp(start_epoch_ms / 1_000, ICT)
    if (start.hour, start.minute, start.second, start.microsecond) != (2, 9, 0, 0):
        raise WindowError("capacity admission must start at exactly 02:09 ICT")

    expected = build_plan(
        run_id=str(plan.get("runId", "")),
        workflow_sha=str(plan.get("workflowSha", "")),
        browser_ci_run_id=plan.get("browserCiRunId", 0),  # type: ignore[arg-type]
        start_epoch_ms=start_epoch_ms,
        now_epoch_ms=start_epoch_ms - 120_000,
    )
    if plan != expected:
        raise WindowError("capacity plan does not match the protected stage schedule")

    final_stage = stages[-1]
    if not isinstance(final_stage, dict):
        raise WindowError("capacity final stage is invalid")
    final_transition_ms = final_stage.get("transitionEndEpochMs")
    if not isinstance(final_transition_ms, int) or final_transition_ms % 1_000:
        raise WindowError("capacity final transition must use whole seconds")

    mutation_start = int(start.replace(hour=2, minute=0, second=0, microsecond=0).timestamp())
    window_end = int(start.replace(hour=5, minute=0, second=0, microsecond=0).timestamp())
    final_transition = final_transition_ms // 1_000
    result = {
        "mutationStartEpoch": mutation_start,
        "armNotAfterEpoch": mutation_start + ARM_RUNWAY_SECONDS,
        "admissionStartEpoch": start_epoch_ms // 1_000,
        "finalTransitionEpoch": final_transition,
        "decisionDeadlineEpoch": final_transition + DECISION_SECONDS,
        "cleanupExecutionDeadlineEpoch": (
            final_transition + RESTORATION_SECONDS - FAIL_SAFE_RECOVERY_SECONDS
        ),
        "restorationDeadlineEpoch": final_transition + RESTORATION_SECONDS,
        "postflightDeadlineEpoch": final_transition + RESTORATION_SECONDS + POSTFLIGHT_SECONDS,
        "workflowCutoffEpoch": (
            final_transition + RESTORATION_SECONDS + POSTFLIGHT_SECONDS + AGGREGATE_SECONDS
        ),
        "windowEndEpoch": window_end,
        "safetyMarginSeconds": (
            window_end
            - final_transition
            - RESTORATION_SECONDS
            - POSTFLIGHT_SECONDS
            - AGGREGATE_SECONDS
        ),
    }
    if result["admissionStartEpoch"] - result["armNotAfterEpoch"] < 300:
        raise WindowError("capacity runners require five minutes after the arm deadline")
    if result["safetyMarginSeconds"] < MINIMUM_SAFETY_MARGIN_SECONDS:
        raise WindowError("capacity workflow does not retain the required safety margin")
    return result


def remaining_seconds(plan: dict[str, object], phase: str, now_epoch: int) -> int:
    bounds = describe(plan)
    deadlines = {
        "arm": bounds["armNotAfterEpoch"],
        "decision": bounds["decisionDeadlineEpoch"],
        "cleanup": bounds["cleanupExecutionDeadlineEpoch"],
        "postflight": bounds["postflightDeadlineEpoch"],
        "aggregate": bounds["workflowCutoffEpoch"],
    }
    if phase not in deadlines:
        raise WindowError("capacity phase is invalid")
    if phase in {"arm", "cleanup"} and now_epoch < bounds["mutationStartEpoch"]:
        raise WindowError("production mutation cannot start before 02:00 ICT")
    remaining = deadlines[phase] - now_epoch
    if remaining <= 0:
        raise WindowError(f"capacity {phase} deadline has elapsed")
    return remaining


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("describe")
    remaining_parser = subparsers.add_parser("remaining")
    remaining_parser.add_argument(
        "--phase", required=True, choices=("arm", "decision", "cleanup", "postflight", "aggregate")
    )
    remaining_parser.add_argument("--now-epoch", type=int)
    args = parser.parse_args()

    try:
        plan = _load_plan(args.plan)
        if args.command == "describe":
            print(json.dumps(describe(plan), sort_keys=True))
            return
        if args.now_epoch is not None and os.environ.get("PATHLAB_CAPACITY_TEST_MODE") != "true":
            raise WindowError("clock overrides require capacity test mode")
        now_epoch = int(time.time()) if args.now_epoch is None else args.now_epoch
        print(remaining_seconds(plan, args.phase, now_epoch))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.error(str(exc))


if __name__ == "__main__":
    main()
