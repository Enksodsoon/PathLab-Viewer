#!/usr/bin/env python3
"""Authenticated run-bound state machine for a detached capacity wrapper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any

SAFE_ID = re.compile(r"^[a-z0-9-]{1,64}$")
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[A-Za-z0-9._-]{8,128}$")
FINAL_LIMITS = {300, 1200, 1500}


class CapacityControlError(ValueError):
    pass


def _state_path(state_dir: Path, run_id: str) -> Path:
    return state_dir / f"pathlab-capacity-{run_id}-control.json"


def _active_path(state_dir: Path) -> Path:
    return state_dir / "pathlab-capacity-active.json"


def _atomic_write(path: Path, value: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if exclusive:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CapacityControlError("capacity control state is missing or invalid") from error
    if not isinstance(value, dict):
        raise CapacityControlError("capacity control state is invalid")
    return value


def _validate_binding(
    state: dict[str, Any], run_id: str, workflow_sha: str, plan_digest: str, nonce: str
) -> None:
    if (
        state.get("runId") != run_id
        or state.get("workflowSha") != workflow_sha
        or state.get("planDigest") != plan_digest
        or state.get("nonceHash") != hashlib.sha256(nonce.encode()).hexdigest()
    ):
        raise CapacityControlError("capacity control binding does not match")


def arm(
    state_dir: Path,
    run_id: str,
    workflow_sha: str,
    plan_digest: str,
    nonce: str,
    deadline_epoch: int,
    *,
    fault_start_epoch: int | None = None,
    fault_end_epoch: int | None = None,
) -> dict[str, Any]:
    if not SAFE_ID.fullmatch(run_id) or not SHA.fullmatch(workflow_sha):
        raise CapacityControlError("capacity run identity is invalid")
    if not DIGEST.fullmatch(plan_digest) or not NONCE.fullmatch(nonce):
        raise CapacityControlError("capacity run binding is invalid")
    if deadline_epoch < int(time.time()) + 120 or deadline_epoch > int(time.time()) + 3 * 3600:
        raise CapacityControlError("capacity deadline is outside the bounded window")
    if (fault_start_epoch is None) != (fault_end_epoch is None):
        raise CapacityControlError("fault recovery window is incomplete")
    if fault_start_epoch is not None:
        assert fault_end_epoch is not None
        if not (int(time.time()) <= fault_start_epoch < fault_end_epoch <= deadline_epoch):
            raise CapacityControlError("fault recovery window is outside the bounded run")
    state_path = _state_path(state_dir, run_id)
    if state_path.exists():
        raise CapacityControlError("capacity run already exists")
    state = {
        "runId": run_id,
        "workflowSha": workflow_sha,
        "planDigest": plan_digest,
        "nonceHash": hashlib.sha256(nonce.encode()).hexdigest(),
        "deadlineEpoch": deadline_epoch,
        "phase": "armed",
        "finalLimit": None,
        "faultStartEpoch": fault_start_epoch,
        "faultEndEpoch": fault_end_epoch,
        "faultConsumed": False,
    }
    active = _active_path(state_dir)
    try:
        _atomic_write(active, {"runId": run_id}, exclusive=True)
    except FileExistsError as error:
        raise CapacityControlError("another capacity run is active") from error
    try:
        _atomic_write(state_path, state, exclusive=True)
    except BaseException:
        active.unlink(missing_ok=True)
        raise
    return state


def consume_fault(
    state_dir: Path, run_id: str, plan_digest: str, *, now_epoch: int | None = None
) -> dict[str, Any]:
    """Atomically consume the sole Classroom fault allowed for this run."""
    state_path = _state_path(state_dir, run_id)
    state = _load(state_path)
    if state.get("runId") != run_id or state.get("planDigest") != plan_digest:
        raise CapacityControlError("fault request binding does not match")
    if state.get("phase") != "armed":
        raise CapacityControlError("fault request is not bound to an armed run")
    now = int(time.time()) if now_epoch is None else now_epoch
    start = state.get("faultStartEpoch")
    end = state.get("faultEndEpoch")
    if not isinstance(start, int) or not isinstance(end, int) or not start <= now <= end:
        raise CapacityControlError("fault request is outside the recovery window")
    claim = state_dir / f"pathlab-capacity-{run_id}-fault-claim"
    try:
        _atomic_write(claim, {"runId": run_id, "consumedAt": now}, exclusive=True)
    except FileExistsError as error:
        raise CapacityControlError("capacity fault was already consumed") from error
    state["faultConsumed"] = True
    state["faultConsumedAt"] = now
    _atomic_write(state_path, state)
    return state


def request_finalize(
    state_dir: Path,
    run_id: str,
    workflow_sha: str,
    plan_digest: str,
    nonce: str,
    evidence_path: Path,
    signature_path: Path,
) -> None:
    state_path = _state_path(state_dir, run_id)
    state = _load(state_path)
    _validate_binding(state, run_id, workflow_sha, plan_digest, nonce)
    if state.get("phase") != "armed":
        raise CapacityControlError("capacity run is not awaiting finalization")
    expected_evidence = state_dir / f"pathlab-capacity-{run_id}-decision.json"
    if evidence_path != expected_evidence or signature_path != Path(f"{expected_evidence}.sig"):
        raise CapacityControlError("capacity decision paths are not run-bound")
    if not evidence_path.is_file() or not signature_path.is_file():
        raise CapacityControlError("capacity decision evidence is missing")
    signature = signature_path.read_text(encoding="utf-8").strip()
    if not DIGEST.fullmatch(signature):
        raise CapacityControlError("capacity decision signature is invalid")
    state["phase"] = "finalizing"
    state["evidencePath"] = str(evidence_path)
    state["signaturePath"] = str(signature_path)
    _atomic_write(state_path, state)


def consume_finalize(
    state_dir: Path, run_id: str, workflow_sha: str, plan_digest: str, nonce: str
) -> dict[str, str]:
    state_path = _state_path(state_dir, run_id)
    state = _load(state_path)
    _validate_binding(state, run_id, workflow_sha, plan_digest, nonce)
    if state.get("phase") != "finalizing":
        raise CapacityControlError("capacity run is not awaiting finalization")
    result = {
        "evidencePath": str(state.pop("evidencePath")),
        "signaturePath": str(state.pop("signaturePath")),
    }
    state["phase"] = "consumed"
    _atomic_write(state_path, state)
    return result


def mark_finished(
    state_dir: Path,
    run_id: str,
    *,
    success: bool,
    final_limit: int | None = None,
    restoration_verified: bool = False,
) -> None:
    state_path = _state_path(state_dir, run_id)
    state = _load(state_path)
    if success:
        if state.get("phase") != "consumed" or final_limit not in FINAL_LIMITS:
            raise CapacityControlError("successful capacity completion lacks a decision")
        state["phase"] = "restored"
        state["finalLimit"] = final_limit
    else:
        state["phase"] = "aborted-restored" if restoration_verified else "restore-failed"
        state["finalLimit"] = None
    _atomic_write(state_path, state)
    active = _load(_active_path(state_dir))
    if active.get("runId") != run_id:
        raise CapacityControlError("active capacity run binding is corrupt")
    if success or restoration_verified:
        _active_path(state_dir).unlink()


def sanitized_status(state_dir: Path, run_id: str) -> dict[str, Any]:
    state = _load(_state_path(state_dir, run_id))
    return {
        name: state.get(name)
        for name in (
            "runId",
            "workflowSha",
            "planDigest",
            "deadlineEpoch",
            "phase",
            "finalLimit",
            "faultConsumed",
        )
    }


def hold_until_finalize(
    state_dir: Path,
    run_id: str,
    workflow_sha: str,
    plan_digest: str,
    nonce: str,
    decision_output: Path,
    signature_output: Path,
) -> None:
    """Block inside Task5's deadline wrapper until a bound decision arrives."""
    while True:
        state = _load(_state_path(state_dir, run_id))
        _validate_binding(state, run_id, workflow_sha, plan_digest, nonce)
        if int(state["deadlineEpoch"]) <= int(time.time()):
            raise CapacityControlError("capacity run reached its absolute deadline")
        if state.get("phase") == "finalizing":
            request = consume_finalize(state_dir, run_id, workflow_sha, plan_digest, nonce)
            shutil.copyfile(request["evidencePath"], decision_output)
            shutil.copyfile(request["signaturePath"], signature_output)
            os.chmod(decision_output, 0o600)
            os.chmod(signature_output, 0o600)
            return
        if state.get("phase") != "armed":
            raise CapacityControlError("capacity run is no longer armed")
        time.sleep(2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run-bound host capacity control")
    parser.add_argument("--state-dir", type=Path, default=Path("/run"))
    subparsers = parser.add_subparsers(dest="command", required=True)
    arm_parser = subparsers.add_parser("arm")
    for target in (arm_parser,):
        target.add_argument("--run-id", required=True)
        target.add_argument("--workflow-sha", required=True)
        target.add_argument("--plan-digest", required=True)
        target.add_argument("--nonce", required=True)
    arm_parser.add_argument("--deadline-epoch", required=True, type=int)
    arm_parser.add_argument("--fault-start-epoch", required=True, type=int)
    arm_parser.add_argument("--fault-end-epoch", required=True, type=int)
    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run-id", required=True)
    finalize_parser = subparsers.add_parser("finalize")
    consume_parser = subparsers.add_parser("hold")
    finish_parser = subparsers.add_parser("finish")
    fault_parser = subparsers.add_parser("fault")
    for target in (finalize_parser, consume_parser):
        target.add_argument("--run-id", required=True)
        target.add_argument("--workflow-sha", required=True)
        target.add_argument("--plan-digest", required=True)
        target.add_argument("--nonce", required=True)
    finalize_parser.add_argument("--evidence", required=True, type=Path)
    finalize_parser.add_argument("--signature", required=True, type=Path)
    consume_parser.add_argument("--decision-output", required=True, type=Path)
    consume_parser.add_argument("--signature-output", required=True, type=Path)
    finish_parser.add_argument("--run-id", required=True)
    finish_parser.add_argument("--success", action="store_true")
    finish_parser.add_argument("--restoration-verified", action="store_true")
    finish_parser.add_argument("--final-limit", type=int)
    fault_parser.add_argument("--run-id", required=True)
    fault_parser.add_argument("--plan-digest", required=True)
    args = parser.parse_args()
    if args.command == "arm":
        arm(
            args.state_dir,
            args.run_id,
            args.workflow_sha,
            args.plan_digest,
            args.nonce,
            args.deadline_epoch,
            fault_start_epoch=args.fault_start_epoch,
            fault_end_epoch=args.fault_end_epoch,
        )
    elif args.command == "status":
        print(json.dumps(sanitized_status(args.state_dir, args.run_id), sort_keys=True))
    elif args.command == "finalize":
        request_finalize(
            args.state_dir,
            args.run_id,
            args.workflow_sha,
            args.plan_digest,
            args.nonce,
            args.evidence,
            args.signature,
        )
    elif args.command == "hold":
        hold_until_finalize(
            args.state_dir,
            args.run_id,
            args.workflow_sha,
            args.plan_digest,
            args.nonce,
            args.decision_output,
            args.signature_output,
        )
    elif args.command == "fault":
        consume_fault(args.state_dir, args.run_id, args.plan_digest)
    else:
        mark_finished(
            args.state_dir,
            args.run_id,
            success=args.success,
            final_limit=args.final_limit,
            restoration_verified=args.restoration_verified,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
