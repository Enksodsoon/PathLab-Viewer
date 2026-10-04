"""Two actual invocations in one contained child; no retained-model claim."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from . import worker
from .alignment import AlignmentRejected
from .alignment_benchmark import _input_digest, _safe_resource_metrics

WARM_PROTOCOL = "same-contained-process-two-invocations/1"
MAX_INVOCATION_BYTES = 64 * 1024 * 1024


def _refuse_links(path: Path) -> None:
    if any(parent.is_symlink() or parent.is_junction() for parent in (path, *path.parents)):
        raise ValueError("warm artifact symlinks/junctions are unsupported")


def _atomic_receipt(path: Path, value: dict[str, Any]) -> None:
    _refuse_links(path)
    content = json.dumps(value, sort_keys=True, allow_nan=False).encode()
    if len(content) > MAX_INVOCATION_BYTES:
        raise ValueError("warm invocation receipt exceeds ceiling")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.pending")
    with temporary.open("xb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)


class _InvocationOutput:
    def __init__(self, parent: Any, ordinal: int) -> None:
        self.parent = parent
        self.ordinal = ordinal
        self.result: dict[str, Any] | None = None

    def put(self, value: dict[str, Any]) -> None:
        if "progress" in value:
            self.parent.put({"progress": {**value["progress"], "invocationOrdinal": self.ordinal}})
        else:
            self.result = value


def _warm_child(
    reference_derivative: str,
    moving_derivative: str,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    engine_name: str,
    engine_settings: dict[str, Any] | None,
    artifact_dir: str | None,
    output: Any,
    seed_registration: dict[str, Any] | None = None,
    startup_gate: Any = None,
) -> None:
    if not sys.platform.startswith("win"):
        os.setsid()
    if startup_gate is not None and not startup_gate.wait(30):
        return
    if artifact_dir is None:
        raise ValueError("warm trial requires private atomic artifact storage")
    requested = dict(engine_settings or {})
    expected_inputs = requested.pop("_warmInputDigests")
    parent_deadline = float(requested.pop("_warmDeadlineMonotonic"))
    parent_started = float(requested.pop("_warmStartedMonotonic", parent_deadline - 600))
    started = time.monotonic()
    deadline = min(parent_deadline, started + 600.0)
    receipts = []
    for ordinal in (1, 2):
        output.put({"progress": {"stage": "warm-input-admission", "invocationOrdinal": ordinal}})
        admission_started = time.monotonic()
        actual_inputs = [
            _input_digest({"path": path, "size": list(size)})
            for path, size in (
                (reference_derivative, reference_full_size),
                (moving_derivative, moving_full_size),
            )
        ]
        admission_seconds = time.monotonic() - admission_started
        remaining = max(0.0, deadline - time.monotonic())
        invocation_started = time.monotonic()
        sink = _InvocationOutput(output, ordinal)
        executed = remaining >= 1 and actual_inputs == expected_inputs
        if executed:
            _atomic_receipt(
                Path(artifact_dir) / f"invocation-{ordinal}-started.json",
                {
                    "invocationOrdinal": ordinal,
                    "childPid": os.getpid(),
                    "verifiedInputDigests": actual_inputs,
                },
            )
            output.put(
                {"progress": {"stage": "warm-invocation-start", "invocationOrdinal": ordinal}}
            )
            # The enclosing supervisor deadline limits BOTH calls, including
            # startup and preparation. Requested method settings remain stable.
            worker._alignment_invocation(
                reference_derivative,
                moving_derivative,
                reference_full_size,
                moving_full_size,
                engine_name,
                requested,
                str(Path(artifact_dir) / f"invocation-{ordinal}"),
                sink,
                seed_registration,
            )
        result = sink.result or {
            "ok": False,
            "type": "AlignmentRejected",
            "error": (
                "warm input admission differs from frozen inputs"
                if actual_inputs != expected_inputs
                else "shared warm-process deadline exhausted before invocation"
            ),
        }
        value = {
            "schema": WARM_PROTOCOL,
            "invocationOrdinal": ordinal,
            "childPid": os.getpid(),
            "processTemperature": "cold" if ordinal == 1 else "warm-python-repeat",
            "decodedInputCacheState": "unverified",
            "retainedModelTemperature": "unverified",
            "hostFilesystemCacheState": "unmeasured",
            "childStartupSeconds": started - parent_started,
            "inputAdmissionSeconds": admission_seconds,
            "verifiedInputDigests": actual_inputs,
            "grantedRemainingBudgetSeconds": remaining,
            "invocationWallSeconds": time.monotonic() - invocation_started,
            "invocationExecuted": executed,
            "requestedSettings": requested,
            "result": result,
        }
        _atomic_receipt(Path(artifact_dir) / f"invocation-{ordinal}.json", value)
        receipts.append(value)
    output.put({"ok": True, "result": {"warmInvocations": receipts, "protocol": WARM_PROTOCOL}})


def run_warm_bounded(
    reference: Path,
    moving: Path,
    reference_size: tuple[int, int],
    moving_size: tuple[int, int],
    *,
    recipe: str,
    settings: dict[str, Any],
    artifact_dir: Path,
    input_digests: list[str],
    absolute_deadline: float | None = None,
    timeout_seconds: int = 600,
    memory_bytes: int = 7 * 1024**3,
) -> dict[str, Any]:
    """Persist a partial first result, but finish containment before returning."""
    if not 0 < timeout_seconds <= 600 or memory_bytes != 7 * 1024**3:
        raise ValueError("warm protocol requires one shared600s/7GiB boundary")
    if any((artifact_dir / f"invocation-{ordinal}.json").exists() for ordinal in (1, 2)):
        raise ValueError("warm attempt artifact directory must be new")
    failure = None
    last_progress: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    started = time.monotonic()
    deadline = (
        min(started + timeout_seconds, absolute_deadline)
        if absolute_deadline is not None
        else started + timeout_seconds
    )

    def progress(value: dict[str, Any]) -> None:
        last_progress.update(value)

    try:
        payload = worker._run_alignment_bounded(
            reference,
            moving,
            reference_size,
            moving_size,
            engine_name=recipe,
            engine_settings={
                **settings,
                "timeoutSeconds": 600,
                "_warmDeadlineMonotonic": deadline,
                "_warmStartedMonotonic": started,
                "_warmInputDigests": input_digests,
            },
            artifact_dir=artifact_dir,
            timeout_seconds=timeout_seconds,
            memory_bytes=memory_bytes,
            _child_target=_warm_child,
            _absolute_deadline=deadline,
            progress=progress,
        )
        metrics = _safe_resource_metrics(payload)
    except AlignmentRejected as error:
        failure = {"type": type(error).__name__, "error": str(error)}
        metrics = _safe_resource_metrics(getattr(error, "resource_metrics", {}))
    # Fatal containment loss is BaseException and MUST escape this function.
    invocations = []
    for ordinal in (1, 2):
        path = artifact_dir / f"invocation-{ordinal}.json"
        _refuse_links(path)
        if path.is_file():
            if path.stat().st_size > MAX_INVOCATION_BYTES:
                raise ValueError("warm invocation receipt exceeds ceiling")
            content = path.read_bytes()
            value = json.loads(content)
            value["artifactSha256"] = hashlib.sha256(content).hexdigest()
        else:
            value = {
                "invocationOrdinal": ordinal,
                "invocationExecuted": None
                if (artifact_dir / f"invocation-{ordinal}-started.json").is_file()
                else False,
                "invocationExecutionPhaseStarted": (
                    artifact_dir / f"invocation-{ordinal}-started.json"
                ).is_file(),
                "result": {"ok": False, "type": "MissingInvocationReceipt"},
                "reason": "shared-supervisor-failure-before-atomic-result",
            }
        invocations.append(value)
    return {
        "schema": WARM_PROTOCOL,
        "plannedInvocations": 2,
        "invocations": invocations,
        "supervisedTotalWallSeconds": time.monotonic() - started,
        "supervisorFailure": failure,
        "resourceMetrics": metrics,
        "terminalContainmentVerified": True,
        "queueSeconds": None,
        "browserApplicationSeconds": None,
        "retainedModelWarmSeconds": None,
        "cleanupSeconds": None,
        "timingScope": (
            "shared supervisor wall includes startup, both calls and terminal cleanup; "
            "invocation wall includes image preparation and engine; queue/browser excluded"
        ),
    }
