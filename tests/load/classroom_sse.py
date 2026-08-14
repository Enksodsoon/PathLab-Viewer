"""Bounded classroom protocol harness. It refuses production unless explicitly allowed."""

import asyncio
import hashlib
import json
import math
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from distributed_certification import ADMISSION_SECONDS, early_stop_causes

ADMISSION_REQUEST_TIMEOUT_SECONDS = 8
JOIN_STAGGER_SECONDS = 0.01
SSE_READY_RESERVE_SECONDS = 20
ADMISSION_PROCESS_RESERVE_SECONDS = 5


def admission_budget_required_seconds(participants: int) -> float:
    """Bound setup, joins, and SSE readiness inside the planned admission ramp."""
    if not 1 <= participants <= 334:
        raise ValueError("participants must be 1..334")
    admin_setup = 2 * ADMISSION_REQUEST_TIMEOUT_SECONDS
    last_join_starts = (participants - 1) * JOIN_STAGGER_SECONDS
    return (
        admin_setup
        + last_join_starts
        + ADMISSION_REQUEST_TIMEOUT_SECONDS
        + SSE_READY_RESERVE_SECONDS
        + ADMISSION_PROCESS_RESERVE_SECONDS
    )


class HeavyEarlyStop(RuntimeError):
    def __init__(self, causes: list[str]) -> None:
        super().__init__(",".join(causes))
        self.causes = causes


@dataclass
class LocalStateSnapshot:
    hub_epoch: str
    state_version: int
    presenter_sequence: int
    converged_epoch_ms: int


@dataclass
class Participant:
    sequence: int
    client: httpx.AsyncClient
    participant_id: str
    csrf_token: str
    events: dict[str, int] = field(default_factory=dict)
    connects: int = 0
    errors: list[str] = field(default_factory=list)
    last_presenter_sequence: int = 0
    connected_at: list[float] = field(default_factory=list)
    connected_epoch_ms: list[int] = field(default_factory=list)
    local_state_snapshots: list[LocalStateSnapshot] = field(default_factory=list)
    hub_epochs: set[str] = field(default_factory=set)
    churn_attempted: bool = False
    stream_ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    stream_active: bool = False


@dataclass
class Recorder:
    presenter_sent: dict[int, float] = field(default_factory=dict)
    presenter_received: dict[int, float] = field(default_factory=dict)
    presenter_latencies_ms: list[float] = field(default_factory=list)
    presenter_sent_epoch_ms: dict[int, int] = field(default_factory=dict)
    presenter_received_epoch_ms: dict[int, int] = field(default_factory=dict)
    question_sent: dict[str, float] = field(default_factory=dict)
    question_received: dict[str, float] = field(default_factory=dict)
    question_latencies_ms: list[float] = field(default_factory=list)
    control_sent_at: float | None = None
    control_latencies_ms: list[float] = field(default_factory=list)
    tile_latencies_ms: list[float] = field(default_factory=list)
    tile_errors: int = 0
    poster_latencies_ms: list[float] = field(default_factory=list)
    poster_errors: int = 0
    general_latencies_ms: list[float] = field(default_factory=list)
    general_errors: int = 0
    presenter_http_errors: int = 0
    unexpected_sse_disconnects: int = 0

    def presenter_sent_at(self, sequence: int, started: float, epoch_ms: int) -> None:
        if len(self.presenter_sent_epoch_ms) < 128:
            self.presenter_sent_epoch_ms[sequence] = epoch_ms
        self.presenter_sent[sequence] = started
        received = self.presenter_received.pop(sequence, None)
        if received is not None:
            self.presenter_latencies_ms.append((received - started) * 1000)

    def presenter_received_at(self, sequence: int, received: float, epoch_ms: int) -> None:
        if len(self.presenter_received_epoch_ms) < 128:
            self.presenter_received_epoch_ms.setdefault(sequence, epoch_ms)
        started = self.presenter_sent.get(sequence)
        if started is None:
            self.presenter_received[sequence] = received
        else:
            self.presenter_latencies_ms.append((received - started) * 1000)

    def question_sent_at(self, question_id: str, started: float) -> None:
        self.question_sent[question_id] = started
        received = self.question_received.pop(question_id, None)
        if received is not None:
            self.question_latencies_ms.append((received - started) * 1000)

    def question_received_at(self, question_id: str, received: float) -> None:
        started = self.question_sent.get(question_id)
        if started is None:
            self.question_received[question_id] = received
        else:
            self.question_latencies_ms.append((received - started) * 1000)


def remote_target_allowed(base_url: str, environment: dict[str, str]) -> bool:
    """Allow localhost, or an explicitly protected synthetic GitHub Actions run."""
    parsed = urlparse(base_url)
    if parsed.hostname in {"127.0.0.1", "localhost", "host.docker.internal"}:
        return True
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and environment.get("PATHLAB_CLASSROOM_PROTECTED_REMOTE", "").lower() == "true"
        and environment.get("PATHLAB_CLASSROOM_SYNTHETIC_ONLY", "").lower() == "true"
        and environment.get("GITHUB_ACTIONS", "").lower() == "true"
    )


def stage_credentials(
    plan: dict[str, Any], stage_name: str, manifest: dict[str, Any]
) -> dict[str, str]:
    """Select a stage's disposable session, rejecting reuse across stages."""
    planned = plan.get("stages")
    if not isinstance(planned, list):
        raise ValueError("capacity plan stages are required")
    names = [
        stage["name"]
        for stage in planned
        if isinstance(stage, dict) and isinstance(stage.get("name"), str)
    ]
    if len(names) != len(planned):
        raise ValueError("every planned stage requires a string name")
    if set(manifest) != set(names):
        raise ValueError("every planned stage requires synthetic session credentials")
    sessions: list[str] = []
    join_codes: list[str] = []
    safety_nonces: list[str] = []
    for name in names:
        entry = manifest.get(name)
        if not isinstance(entry, dict) or set(entry) != {
            "sessionId",
            "joinCode",
            "slideId",
            "safetyNonce",
        }:
            raise ValueError(
                "stage credentials require sessionId, joinCode, slideId, and safetyNonce"
            )
        if not all(isinstance(entry[key], str) and entry[key] for key in entry):
            raise ValueError("stage credentials must be non-empty strings")
        sessions.append(entry["sessionId"])
        join_codes.append(entry["joinCode"])
        if len(entry["safetyNonce"]) < 32 or len(entry["safetyNonce"]) > 128:
            raise ValueError("stage safety nonces must contain 32 through 128 characters")
        safety_nonces.append(entry["safetyNonce"])
    if len(set(sessions)) != 1 or len(set(join_codes)) != 1:
        raise ValueError("all stages must reuse one dedicated resettable Classroom")
    if len(set(safety_nonces)) != len(names):
        raise ValueError("each stage requires a unique safety nonce")
    selected = manifest.get(stage_name)
    if not isinstance(selected, dict):
        raise ValueError("requested stage is not in the synthetic manifest")
    return {key: selected[key] for key in ("sessionId", "joinCode", "slideId", "safetyNonce")}


def media_paths_for_participant(manifest: dict[str, Any], sequence: int) -> list[str]:
    """Return descriptor/poster plus a bounded deterministic 80/20 tile batch."""
    descriptor = manifest.get("descriptor")
    poster = manifest.get("poster")
    common = manifest.get("commonTiles")
    random_tiles = manifest.get("randomTiles")
    if (
        not isinstance(descriptor, str)
        or not isinstance(poster, str)
        or not isinstance(common, list)
        or not common
        or not all(isinstance(item, str) for item in common)
        or not isinstance(random_tiles, list)
        or not random_tiles
        or not all(isinstance(item, str) for item in random_tiles)
    ):
        raise ValueError("media manifest requires descriptor, poster, commonTiles, and randomTiles")
    # Every fifth participant explores independently; the other four follow the teacher.
    pool = random_tiles if sequence % 5 == 4 else common
    batch_size = min(4, len(pool))
    start = sequence % len(pool)
    batch = [pool[(start + offset) % len(pool)] for offset in range(batch_size)]
    return [descriptor, poster, *batch]


def discrete_event_names() -> tuple[str, ...]:
    return (
        "question",
        "pin",
        "control-request",
        "control-grant-revoke",
        "pointer",
        "teaching-annotation",
    )


def lost_critical_events(participants: list[Participant], publisher: bool) -> int:
    """Count missing critical broadcasts; non-publisher shards emit none."""
    if not publisher:
        return 0
    expected = {
        "control": 2,
        "pointer-removed": 1,
        "teaching-annotation-added": 1,
        "teaching-annotation-removed": 1,
    }
    return sum(
        max(0, minimum - participant.events.get(event_type, 0))
        for participant in participants
        for event_type, minimum in expected.items()
    )


def publisher_enabled(value: str) -> bool:
    return value.lower() == "true"


def _journey(values: list[float], failures: int = 0) -> dict[str, Any]:
    requests = len(values) + failures
    return {
        "requests": requests,
        "failures": failures,
        "failureRate": round(failures / requests, 6) if requests else 0,
        "latencyMs": summary(values),
    }


def journey_measurements(recorder: Recorder) -> dict[str, dict[str, Any]]:
    journeys = {
        "presenterSse": _journey(recorder.presenter_latencies_ms, recorder.presenter_http_errors),
        "classroomControl": _journey(recorder.control_latencies_ms),
        "generalApi": _journey(recorder.general_latencies_ms, recorder.general_errors),
        "staticTile": _journey(recorder.tile_latencies_ms, recorder.tile_errors),
        "poster": _journey(recorder.poster_latencies_ms, recorder.poster_errors),
        "question": _journey(recorder.question_latencies_ms),
    }
    journeys["presenterSse"]["fanout"] = {
        "sentEpochMs": {str(key): value for key, value in recorder.presenter_sent_epoch_ms.items()},
        "receivedEpochMs": {
            str(key): value for key, value in recorder.presenter_received_epoch_ms.items()
        },
    }
    return journeys


async def monitor_heavy_safety(
    admin: httpx.AsyncClient,
    recorder: Recorder,
    participants: list[Participant],
    deadline: float,
    stage_name: str,
) -> None:
    latency_breach_started: float | None = None
    limits = {
        "presenterSse": 250,
        "classroomControl": 500,
        "generalApi": 500,
        "staticTile": 500,
        "poster": 1500,
        "question": 2000,
    }
    while time.monotonic() < deadline:
        await asyncio.sleep(min(5, max(0, deadline - time.monotonic())))
        metrics = (await get_with_retry(admin, "/api/v1/admin/classroom/metrics")).json()
        host_causes = metrics.get("capacitySafetyStopCauses", [])
        if (
            host_causes
            and metrics.get("capacitySafetyStopStage") == stage_name
            and metrics.get("capacitySafetyStopPlanDigest")
            == os.environ.get("PATHLAB_CLASSROOM_PLAN_DIGEST")
            and metrics.get("capacitySafetyStopNonceDigest")
            == hashlib.sha256(
                os.environ.get("PATHLAB_CLASSROOM_SAFETY_NONCE", "").encode()
            ).hexdigest()
        ):
            if not isinstance(host_causes, list) or any(
                cause not in {"cpu-sustained", "memory"} for cause in host_causes
            ):
                raise RuntimeError("invalid host safety-stop signal")
            raise HeavyEarlyStop([str(cause) for cause in host_causes])
        journeys = journey_measurements(recorder)
        latency_ratio = max(
            (journeys[name]["latencyMs"]["p95"] / limit if journeys[name]["requests"] else 0)
            for name, limit in limits.items()
        )
        now = time.monotonic()
        latency_breach_started = (latency_breach_started or now) if latency_ratio > 2 else None
        attempts = sum(item["requests"] for item in journeys.values()) + sum(
            len(participant.errors) for participant in participants
        )
        failures = sum(item["failures"] for item in journeys.values()) + sum(
            len(participant.errors) for participant in participants
        )
        causes = early_stop_causes(
            {
                "queueDepth": int(metrics.get("queueMaxDepth", 0)),
                "queueCapacity": int(metrics.get("queueCapacity", 0)),
                "eventLoopP99Ms": float(metrics.get("eventLoopP99Ms", 0)),
                "failureRate": failures / attempts if attempts else 0,
                "poolTimeouts": int(metrics.get("poolTimeouts", 0)),
                "sqliteLockErrors": int(metrics.get("sqliteLockErrors", 0)),
                "latencyRatio": latency_ratio,
                "latencyBreachSeconds": now - latency_breach_started
                if latency_breach_started
                else 0,
            }
        )
        if causes:
            raise HeavyEarlyStop(causes)


def record_sse_disconnect(recorder: Recorder, *, expected: bool, reconnect_possible: bool) -> None:
    if not expected and reconnect_possible:
        recorder.unexpected_sse_disconnects += 1


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def summary(values: list[float]) -> dict[str, float]:
    return {
        "p50": round(statistics.median(values), 3) if values else 0,
        "p95": round(percentile(values, 0.95), 3),
        "p99": round(percentile(values, 0.99), 3),
    }


def reconnect_delay(participant_id: str, attempt: int) -> float:
    seed = 2166136261
    for value in participant_id.encode():
        seed = ((seed ^ value) * 16777619) & 0xFFFFFFFF
    jitter = seed % 1001
    delay_ms = min(10_000, min(9_000, 500 * (2 ** min(5, attempt))) + jitter)
    return float(delay_ms) / 1000


def recovery_local_state_convergence(
    participants: list[Participant], recovery_ready_epoch_ms: int
) -> tuple[int, float]:
    """Count post-restart canonical snapshots, never mere TCP/SSE connections."""
    if recovery_ready_epoch_ms <= 0:
        return 0, 0
    converged: list[LocalStateSnapshot] = []
    for participant in participants:
        if not participant.local_state_snapshots:
            continue
        initial = participant.local_state_snapshots[0]
        recovered = next(
            (
                item
                for item in participant.local_state_snapshots[1:]
                if item.hub_epoch != initial.hub_epoch
                and item.state_version > initial.state_version
                and item.presenter_sequence > initial.presenter_sequence
            ),
            None,
        )
        if recovered is None or recovered.converged_epoch_ms > recovery_ready_epoch_ms + 30_000:
            continue
        converged.append(recovered)
    seconds = max(
        (max(0, item.converged_epoch_ms - recovery_ready_epoch_ms) / 1_000 for item in converged),
        default=0,
    )
    return len(converged), seconds


async def get_with_retry(
    client: httpx.AsyncClient,
    path: str,
    *,
    attempts: int = 5,
) -> httpx.Response:
    for attempt in range(attempts):
        try:
            response = await client.get(path)
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            if attempt + 1 == attempts:
                raise
            await asyncio.sleep(0.25 * (2**attempt))
    raise RuntimeError("unreachable retry state")


async def probe_general_api(client: httpx.AsyncClient, deadline: float, recorder: Recorder) -> None:
    """Measure the general-service readiness path during the active plateau."""
    while time.monotonic() < deadline:
        started = time.monotonic()
        try:
            response = await client.get("/readyz")
            response.raise_for_status()
            recorder.general_latencies_ms.append((time.monotonic() - started) * 1000)
        except httpx.HTTPError:
            recorder.general_errors += 1
        await asyncio.sleep(5)


async def consume_stream(
    participant: Participant,
    session_id: str,
    deadline: list[float],
    recorder: Recorder,
    churn_at: list[float] | None,
    expect_restart: bool = False,
) -> None:
    attempt = 0
    churned = False
    expected_disconnect = False
    restart_disconnect_seen = False
    while time.monotonic() < deadline[0]:
        try:
            async with asyncio.timeout(max(0, deadline[0] - time.monotonic())):
                async with participant.client.stream(
                    "GET", f"/api/v1/classroom/sessions/{session_id}/events", timeout=None
                ) as stream:
                    stream.raise_for_status()
                    participant.connects += 1
                    participant.connected_at.append(time.monotonic())
                    participant.connected_epoch_ms.append(int(time.time() * 1_000))
                    participant.stream_active = True
                    event_type = ""
                    async for line in stream.aiter_lines():
                        now = time.monotonic()
                        if churn_at and now >= churn_at[0] and not churned:
                            churned = True
                            participant.churn_attempted = True
                            expected_disconnect = True
                            break
                        if line.startswith("event:"):
                            event_type = line.removeprefix("event:").strip()
                        elif line.startswith("data:"):
                            payload = json.loads(line.removeprefix("data:").strip())
                            if isinstance(payload.get("hubEpoch"), str):
                                participant.hub_epochs.add(payload["hubEpoch"])
                            if event_type == "stream-ready":
                                state = await get_with_retry(
                                    participant.client,
                                    f"/api/v1/classroom/sessions/{session_id}",
                                )
                                canonical = state.json()
                                state_version = int(canonical["stateVersion"])
                                if state_version < int(payload["stateVersion"]):
                                    raise RuntimeError(
                                        "stream snapshot regressed behind stream-ready"
                                    )
                                participant.local_state_snapshots.append(
                                    LocalStateSnapshot(
                                        hub_epoch=str(payload["hubEpoch"]),
                                        state_version=state_version,
                                        presenter_sequence=int(canonical["presenter"]["sequence"]),
                                        converged_epoch_ms=int(time.time() * 1_000),
                                    )
                                )
                                participant.stream_ready.set()
                            participant.events[event_type] = (
                                participant.events.get(event_type, 0) + 1
                            )
                            if event_type == "presenter":
                                sequence = int(payload["presenterSequence"])
                                if sequence < participant.last_presenter_sequence:
                                    participant.errors.append("presenter_sequence_regressed")
                                participant.last_presenter_sequence = max(
                                    participant.last_presenter_sequence, sequence
                                )
                                recorder.presenter_received_at(
                                    sequence, now, int(time.time() * 1_000)
                                )
                            elif event_type == "control" and recorder.control_sent_at is not None:
                                recorder.control_latencies_ms.append(
                                    (now - recorder.control_sent_at) * 1000
                                )
                    recovery_disconnect = expect_restart and not restart_disconnect_seen
                    if recovery_disconnect:
                        restart_disconnect_seen = True
                        participant.churn_attempted = True
                    record_sse_disconnect(
                        recorder,
                        expected=expected_disconnect or recovery_disconnect,
                        reconnect_possible=(
                            time.monotonic() + reconnect_delay(participant.participant_id, attempt)
                            < deadline[0]
                        ),
                    )
                attempt = 0
                expected_disconnect = False
        except TimeoutError:
            return
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            if expect_restart and not restart_disconnect_seen:
                restart_disconnect_seen = True
                participant.churn_attempted = True
                continue
            if expected_disconnect:
                expected_disconnect = False
                continue
            # httpx may surface shutdown of an SSE read near the scenario
            # boundary as an incomplete-chunk protocol error. Count it only
            # when enough time remains for the client's bounded reconnect.
            if (
                time.monotonic() + reconnect_delay(participant.participant_id, attempt)
                < deadline[0]
            ):
                participant.errors.append(type(error).__name__)
                record_sse_disconnect(recorder, expected=False, reconnect_possible=True)
        finally:
            participant.stream_active = False
        if time.monotonic() < deadline[0]:
            await asyncio.sleep(reconnect_delay(participant.participant_id, attempt))
            attempt += 1


async def consume_teacher(
    client: httpx.AsyncClient,
    session_id: str,
    deadline: float,
    recorder: Recorder,
    expect_restart: bool = False,
) -> None:
    restart_disconnect_seen = False
    while time.monotonic() < deadline:
        try:
            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                async with client.stream(
                    "GET", f"/api/v1/admin/classroom/sessions/{session_id}/events", timeout=None
                ) as stream:
                    stream.raise_for_status()
                    event_type = ""
                    async for line in stream.aiter_lines():
                        if line.startswith("event:"):
                            event_type = line.removeprefix("event:").strip()
                        elif line.startswith("data:") and event_type == "question-added":
                            payload = json.loads(line.removeprefix("data:").strip())
                            recorder.question_received_at(
                                str(payload.get("questionId")), time.monotonic()
                            )
                    recovery_disconnect = expect_restart and not restart_disconnect_seen
                    restart_disconnect_seen = restart_disconnect_seen or recovery_disconnect
                    record_sse_disconnect(
                        recorder,
                        expected=recovery_disconnect,
                        reconnect_possible=time.monotonic() + 0.5 < deadline,
                    )
        except TimeoutError:
            return
        except (httpx.HTTPError, json.JSONDecodeError):
            recovery_disconnect = expect_restart and not restart_disconnect_seen
            restart_disconnect_seen = restart_disconnect_seen or recovery_disconnect
            record_sse_disconnect(
                recorder,
                expected=recovery_disconnect,
                reconnect_possible=time.monotonic() + 0.5 < deadline,
            )
            await asyncio.sleep(0.5)


async def publish_presenter(
    admin: httpx.AsyncClient,
    session_id: str,
    slide_id: str,
    csrf_token: str,
    deadline: float,
    rate: float,
    recorder: Recorder,
) -> None:
    index = 0
    while time.monotonic() < deadline:
        started = time.monotonic()
        started_epoch_ms = int(time.time() * 1_000)
        try:
            response = await admin.post(
                f"/api/v1/admin/classroom/sessions/{session_id}/presenter",
                headers={"X-CSRF-Token": csrf_token},
                json={
                    "slideId": slide_id,
                    "x": 0.2 + (index % 60) / 100,
                    "y": 0.5,
                    "zoom": 2 + (index % 4) / 10,
                },
            )
            response.raise_for_status()
            recorder.presenter_sent_at(
                int(response.json()["presenterSequence"]), started, started_epoch_ms
            )
            index += 1
        except (httpx.HTTPError, KeyError, ValueError, json.JSONDecodeError):
            recorder.presenter_http_errors += 1
        await asyncio.sleep(max(0, (1 / rate) - (time.monotonic() - started)))


async def request_tiles(
    base_url: str,
    media_paths: list[str],
    deadline: float,
    sequence: int,
    recorder: Recorder,
) -> None:
    # Guide transitions spread over at most 250 ms and each client begins with
    # two tile requests in flight; the protected harness never exceeds four.
    await asyncio.sleep((sequence % 251) / 1000)
    async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:
        for path_index, path in enumerate(media_paths[:2]):
            started = time.monotonic()
            try:
                response = await client.get(path)
                response.raise_for_status()
                if path_index == 1:
                    recorder.poster_latencies_ms.append((time.monotonic() - started) * 1000)
            except httpx.HTTPError:
                if path_index == 1:
                    recorder.poster_errors += 1
                else:
                    recorder.tile_errors += 1
        semaphore = asyncio.Semaphore(2)

        async def request_tile(path: str) -> None:
            async with semaphore:
                started = time.monotonic()
                try:
                    response = await client.get(path)
                    response.raise_for_status()
                    recorder.tile_latencies_ms.append((time.monotonic() - started) * 1000)
                except httpx.HTTPError:
                    recorder.tile_errors += 1

        while time.monotonic() < deadline:
            await asyncio.gather(*(request_tile(path) for path in media_paths[2:]))
            await asyncio.sleep(2 + (sequence % 5) / 5)


async def exercise_discrete_events(
    participants: list[Participant],
    admin: httpx.AsyncClient,
    session_id: str,
    slide_id: str,
    admin_csrf: str,
    recorder: Recorder,
) -> None:
    await asyncio.sleep(2)
    for participant in participants[: min(5, len(participants))]:
        started = time.monotonic()
        response = await participant.client.post(
            f"/api/v1/classroom/sessions/{session_id}/questions",
            json={
                "idempotencyKey": f"load-{participant.participant_id}-{time.time_ns()}",
                "slideId": slide_id,
                "text": "Bounded certification question",
                "x": 0.4,
                "y": 0.6,
                "zoom": 3,
                "csrfToken": participant.csrf_token,
            },
        )
        response.raise_for_status()
        recorder.question_sent_at(response.json()["questionId"], started)
    target = participants[0]
    mutation = {"csrfToken": target.csrf_token}
    pin = await target.client.post(
        f"/api/v1/classroom/sessions/{session_id}/pin",
        json={
            "slideId": slide_id,
            "x": 0.35,
            "y": 0.65,
            "zoom": 3,
            **mutation,
        },
    )
    pin.raise_for_status()
    control_request = await target.client.post(
        f"/api/v1/classroom/sessions/{session_id}/control-request", json=mutation
    )
    control_request.raise_for_status()
    pointer = await admin.post(
        f"/api/v1/admin/classroom/sessions/{session_id}/pointer",
        headers={"X-CSRF-Token": admin_csrf},
        json={"slideId": slide_id, "style": "green-arrow", "x": 0.5, "y": 0.5},
    )
    pointer.raise_for_status()
    annotation_id = f"load-mark-{time.time_ns()}"
    annotation = await admin.post(
        f"/api/v1/admin/classroom/sessions/{session_id}/annotations",
        headers={"X-CSRF-Token": admin_csrf},
        json={
            "id": annotation_id,
            "slideId": slide_id,
            "tool": "line",
            "color": "#42b883",
            "width": 4,
            "points": [{"x": 0.25, "y": 0.25}, {"x": 0.75, "y": 0.75}],
        },
    )
    annotation.raise_for_status()
    recorder.control_sent_at = time.monotonic()
    granted = await admin.post(
        f"/api/v1/admin/classroom/sessions/{session_id}/control",
        headers={"X-CSRF-Token": admin_csrf},
        json={"participantId": target.participant_id, "seconds": 15},
    )
    granted.raise_for_status()
    await asyncio.sleep(3)
    recorder.control_sent_at = time.monotonic()
    revoked = await admin.delete(
        f"/api/v1/admin/classroom/sessions/{session_id}/control",
        headers={"X-CSRF-Token": admin_csrf},
    )
    revoked.raise_for_status()
    for method, path, client, payload in (
        (
            "DELETE",
            f"/api/v1/classroom/sessions/{session_id}/pin",
            target.client,
            mutation,
        ),
        (
            "DELETE",
            f"/api/v1/classroom/sessions/{session_id}/control-request",
            target.client,
            mutation,
        ),
        (
            "DELETE",
            f"/api/v1/admin/classroom/sessions/{session_id}/pointer",
            admin,
            None,
        ),
        (
            "DELETE",
            f"/api/v1/admin/classroom/sessions/{session_id}/annotations/{annotation_id}",
            admin,
            None,
        ),
    ):
        headers = {"X-CSRF-Token": admin_csrf} if client is admin else {}
        response = (
            await client.request(method, path, headers=headers, json=payload)
            if payload is not None
            else await client.request(method, path, headers=headers)
        )
        response.raise_for_status()


async def run() -> int:
    base_url = os.environ.get("PATHLAB_CLASSROOM_BASE_URL", "http://127.0.0.1:8000")
    join_code = os.environ.get("PATHLAB_CLASSROOM_JOIN_CODE", "")
    session_id = os.environ.get("PATHLAB_CLASSROOM_SESSION_ID", "")
    slide_id = os.environ.get("PATHLAB_CLASSROOM_SLIDE_ID", "")
    tile_url = os.environ.get("PATHLAB_CLASSROOM_TILE_URL", "")
    media_manifest_path = os.environ.get("PATHLAB_CLASSROOM_MEDIA_MANIFEST", "")
    username = os.environ.get("PATHLAB_CLASSROOM_ADMIN_USERNAME", "")
    password = os.environ.get("PATHLAB_CLASSROOM_ADMIN_PASSWORD", "")
    count = int(os.environ.get("PATHLAB_CLASSROOM_PARTICIPANTS", "30"))
    global_target = int(os.environ.get("PATHLAB_CLASSROOM_GLOBAL_TARGET", str(count)))
    duration = float(os.environ.get("PATHLAB_CLASSROOM_DURATION_SECONDS", "60"))
    hold_start_epoch_ms = int(os.environ.get("PATHLAB_CLASSROOM_HOLD_START_EPOCH_MS", "0"))
    rate = float(os.environ.get("PATHLAB_CLASSROOM_PRESENTER_RATE", "2"))
    expect_restart = os.environ.get("PATHLAB_CLASSROOM_EXPECT_RESTART", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    publishes_teacher_events = publisher_enabled(
        os.environ.get("PATHLAB_CLASSROOM_PUBLISHER", "true")
    )
    publisher_offset = int(os.environ.get("PATHLAB_CLASSROOM_PUBLISHER_OFFSET_MS", "0")) / 1000
    heavy_stage = os.environ.get("PATHLAB_CLASSROOM_HEAVY_STAGE", "false").lower() == "true"
    if not remote_target_allowed(base_url, dict(os.environ)):
        raise SystemExit(
            "This classroom harness is restricted to local ephemeral targets or "
            "protected synthetic GitHub Actions runs"
        )
    if not all((join_code, session_id, slide_id, username, password)):
        raise SystemExit("join code, session, slide, and admin credentials are required")
    if not 1 <= count <= 334 or duration <= 0 or not 0 < rate <= 20:
        raise SystemExit("participants must be 1..334; duration positive; presenter rate 0..20")
    if admission_budget_required_seconds(count) > ADMISSION_SECONDS:
        raise SystemExit("participant admission budget exceeds the synchronized ramp")
    media_manifest: dict[str, Any] | None = None
    if media_manifest_path:
        loaded = json.loads(Path(media_manifest_path).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise SystemExit("media manifest must be an object")
        # Validate before any participant joins.
        media_paths_for_participant(loaded, 0)
        media_manifest = loaded

    recorder = Recorder()
    admission_started_epoch_ms = int(time.time() * 1_000)
    admin = httpx.AsyncClient(base_url=base_url, timeout=ADMISSION_REQUEST_TIMEOUT_SECONDS)
    login = await asyncio.wait_for(
        admin.post("/api/v1/auth/session", json={"username": username, "password": password}),
        timeout=ADMISSION_REQUEST_TIMEOUT_SECONDS,
    )
    login.raise_for_status()
    admin_csrf = login.json()["csrfToken"]
    initial_metrics_response = await asyncio.wait_for(
        admin.get("/api/v1/admin/classroom/metrics"),
        timeout=ADMISSION_REQUEST_TIMEOUT_SECONDS,
    )
    initial_metrics_response.raise_for_status()
    initial_metrics = initial_metrics_response.json()

    async def join(sequence: int) -> Participant:
        await asyncio.sleep(sequence * JOIN_STAGGER_SECONDS)
        client = httpx.AsyncClient(base_url=base_url, timeout=ADMISSION_REQUEST_TIMEOUT_SECONDS)
        response = await asyncio.wait_for(
            client.post("/api/v1/classroom/join", json={"joinCode": join_code}),
            timeout=ADMISSION_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        return Participant(sequence, client, payload["participant"]["id"], payload["csrfToken"])

    participants = list(await asyncio.gather(*(join(index) for index in range(count))))
    remaining = (
        (hold_start_epoch_ms - int(time.time() * 1_000)) / 1_000 if hold_start_epoch_ms else 0
    )
    if remaining < -1:
        raise RuntimeError("participant admission missed the synchronized hold start")
    stream_deadline = [time.monotonic() + max(0, remaining) + duration]
    churn_at = [time.monotonic() + max(0, remaining) + duration / 2]
    streams = [
        asyncio.create_task(
            consume_stream(
                participant,
                session_id,
                stream_deadline,
                recorder,
                churn_at if participant.sequence % 10 == 0 else None,
                expect_restart,
            )
        )
        for participant in participants
    ]
    try:
        await asyncio.wait_for(
            asyncio.gather(*(participant.stream_ready.wait() for participant in participants)),
            timeout=max(1, remaining),
        )
    except TimeoutError as error:
        for stream in streams:
            stream.cancel()
        await asyncio.gather(*streams, return_exceptions=True)
        raise RuntimeError("not every admitted participant opened SSE before hold") from error
    if hold_start_epoch_ms:
        remaining = (hold_start_epoch_ms - int(time.time() * 1_000)) / 1_000
        if remaining > 0:
            await asyncio.sleep(remaining)
    if not all(participant.stream_active for participant in participants):
        for stream in streams:
            stream.cancel()
        await asyncio.gather(*streams, return_exceptions=True)
        raise RuntimeError("not every admitted participant had active SSE at hold start")
    hold_metrics_response = await admin.get("/api/v1/admin/classroom/metrics")
    hold_metrics_response.raise_for_status()
    hold_metrics = hold_metrics_response.json()
    server_active_at_hold = int(hold_metrics.get("currentSseConnections", 0))
    server_peak_at_hold = int(hold_metrics.get("peakSseConnections", 0))
    if server_active_at_hold < global_target or server_peak_at_hold < global_target:
        for stream in streams:
            stream.cancel()
        await asyncio.gather(*streams, return_exceptions=True)
        raise RuntimeError("global active SSE target was not reached at hold start")
    hold_started_epoch_ms = int(time.time() * 1_000)
    started = time.monotonic()
    deadline = started + duration
    stream_deadline[0] = deadline
    churn_at[0] = started + duration / 2
    tasks = [*streams]
    tasks.append(asyncio.create_task(probe_general_api(admin, deadline, recorder)))
    if publishes_teacher_events:

        async def delayed(coroutine: Any) -> Any:
            await asyncio.sleep(publisher_offset)
            return await coroutine

        tasks.extend(
            [
                asyncio.create_task(
                    delayed(consume_teacher(admin, session_id, deadline, recorder, expect_restart))
                ),
                asyncio.create_task(
                    delayed(
                        publish_presenter(
                            admin, session_id, slide_id, admin_csrf, deadline, rate, recorder
                        )
                    )
                ),
                asyncio.create_task(
                    delayed(
                        exercise_discrete_events(
                            participants, admin, session_id, slide_id, admin_csrf, recorder
                        )
                    )
                ),
            ]
        )
    if media_manifest is not None:
        tasks.extend(
            asyncio.create_task(
                request_tiles(
                    base_url,
                    media_paths_for_participant(media_manifest, index),
                    deadline,
                    index,
                    recorder,
                )
            )
            for index in range(count)
        )
    elif tile_url:
        tasks.extend(
            asyncio.create_task(
                request_tiles(base_url, [tile_url, tile_url, tile_url], deadline, index, recorder)
            )
            for index in range(count)
        )
    if heavy_stage:
        tasks.append(
            asyncio.create_task(
                monitor_heavy_safety(
                    admin,
                    recorder,
                    participants,
                    deadline,
                    os.environ.get("PATHLAB_CLASSROOM_STAGE_NAME", ""),
                )
            )
        )
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    early_causes: list[str] = []
    for task in done:
        task_failure = task.exception() if not task.cancelled() else None
        if isinstance(task_failure, HeavyEarlyStop):
            early_causes.extend(task_failure.causes)
    if early_causes:
        for task in pending:
            task.cancel()
    task_results = [
        *await asyncio.gather(*done, return_exceptions=True),
        *await asyncio.gather(*pending, return_exceptions=True),
    ]
    hold_ended_epoch_ms = int(time.time() * 1_000)
    task_errors = [
        repr(result)
        for result in task_results
        if isinstance(result, BaseException)
        and not isinstance(result, (HeavyEarlyStop, asyncio.CancelledError))
    ]

    final_state = await get_with_retry(admin, f"/api/v1/admin/classroom/sessions/{session_id}")
    final_sequence = int(final_state.json()["presenter"]["sequence"])
    converged = sum(
        participant.last_presenter_sequence == final_sequence for participant in participants
    )
    for participant in participants:
        await participant.client.aclose()
    metrics = await get_with_retry(admin, "/api/v1/admin/classroom/metrics")
    server_metrics = metrics.json()
    recovery_ready_epoch_ms = int(server_metrics.get("recoveryReadyEpochMs", 0))
    recovery_local_converged, recovery_convergence_seconds = (
        recovery_local_state_convergence(participants, recovery_ready_epoch_ms)
        if expect_restart
        else (0, 0)
    )
    metrics_delta = {
        key: (
            int(server_metrics.get(key, 0)) - int(initial_metrics.get(key, 0))
            if int(server_metrics.get(key, 0)) >= int(initial_metrics.get(key, 0))
            else int(server_metrics.get(key, 0))
        )
        for key in (
            "presenterEventsPublished",
            "presenterEventsCoalesced",
            "slowSubscribersDisconnected",
            "queueOverflows",
            "reconnects",
            "presenterPersistenceWrites",
            "poolTimeouts",
            "sqliteLockErrors",
        )
    }
    server_metrics["poolTimeouts"] = metrics_delta["poolTimeouts"]
    server_metrics["sqliteLockErrors"] = metrics_delta["sqliteLockErrors"]
    await admin.aclose()
    errors = [error for participant in participants for error in participant.errors]
    reconnect_expected = (
        participants if expect_restart else [item for item in participants if item.churn_attempted]
    )
    successful_reconnects = sum(item.connects >= 2 for item in reconnect_expected)
    reconnect_times = [item.connected_at[1] for item in participants if len(item.connected_at) >= 2]
    report: dict[str, Any] = {
        "participants": count,
        "durationSeconds": round((hold_ended_epoch_ms - hold_started_epoch_ms) / 1_000, 3),
        "admissionStartedEpochMs": admission_started_epoch_ms,
        "holdStartedEpochMs": hold_started_epoch_ms,
        "holdEndedEpochMs": hold_ended_epoch_ms,
        "connectionsOpened": sum(item.connects for item in participants),
        "activeSseAtHoldStart": sum(item.stream_ready.is_set() for item in participants),
        "serverActiveSseAtHoldStart": server_active_at_hold,
        "serverPeakSseAtHoldStart": server_peak_at_hold,
        "globalTargetUsers": global_target,
        "reconnects": sum(max(0, item.connects - 1) for item in participants),
        "reconnectSuccessRate": round(successful_reconnects / len(reconnect_expected), 4),
        "reconnectSpreadMs": round((max(reconnect_times) - min(reconnect_times)) * 1000, 3)
        if len(reconnect_times) > 1
        else 0,
        "participantErrors": errors,
        "taskErrors": task_errors,
        "presenterLatencyMs": summary(recorder.presenter_latencies_ms),
        "presenterSendSuccesses": len(recorder.presenter_sent),
        "questionLatencyMs": summary(recorder.question_latencies_ms),
        "controlLatencyMs": summary(recorder.control_latencies_ms),
        "tileLatencyMs": summary(recorder.tile_latencies_ms),
        "tileErrors": recorder.tile_errors,
        "finalConvergence": {"converged": converged, "expected": count},
        "serverMetrics": server_metrics,
        "recoveryReadyEpochMs": recovery_ready_epoch_ms,
        "recoveryConvergenceSeconds": round(recovery_convergence_seconds, 3),
        "recoveryLocalConvergence": {
            "converged": recovery_local_converged,
            "expected": count,
        },
        "serverMetricsDelta": metrics_delta,
        "presenterPersistenceWritesPerSecond": round(
            metrics_delta["presenterPersistenceWrites"] / duration, 4
        ),
        "distinctHubEpochs": len(set().union(*(item.hub_epochs for item in participants))),
        "stalePresenterIncidents": sum(
            item.errors.count("presenter_sequence_regressed") for item in participants
        ),
        "eventCounts": {
            name: sum(item.events.get(name, 0) for item in participants)
            for name in ("stream-ready", "presenter", "control", "question-removed")
        },
        "discreteFeaturesExercised": list(discrete_event_names()),
        "journeys": journey_measurements(recorder),
        "lostDiscreteEvents": lost_critical_events(participants, publishes_teacher_events),
        "unexpectedSseDisconnects": recorder.unexpected_sse_disconnects,
        "queueOverflows": metrics_delta["queueOverflows"],
        "earlyStopCauses": sorted(set(early_causes)),
    }
    print(json.dumps(report, indent=2))
    # The producer intentionally permits only one HTTP mutation in flight and
    # keeps one latest pending viewport. Under a 300-stream fanout the response
    # latency, not the cadence ceiling, limits the achieved rate. Require a
    # useful 5 Hz freshness floor while separately reporting end-to-end p95/p99.
    minimum_achieved_rate = min(rate, 5)
    expected_updates = (
        math.floor(duration * minimum_achieved_rate * (0.3 if expect_restart else 0.8))
        if publishes_teacher_events
        else 0
    )
    failed = bool(task_errors) or converged != count or recorder.tile_errors > 0
    failed = failed or recorder.presenter_http_errors > 0
    failed = failed or recorder.unexpected_sse_disconnects > 0
    failed = failed or metrics_delta["queueOverflows"] > 0
    failed = failed or any(error == "presenter_sequence_regressed" for error in errors)
    failed = failed or successful_reconnects != len(reconnect_expected)
    failed = failed or (
        expect_restart
        and (
            recovery_ready_epoch_ms <= 0
            or recovery_local_converged != count
            or recovery_convergence_seconds < 0
            or recovery_convergence_seconds > 30
        )
    )
    failed = failed or len(recorder.presenter_sent) < expected_updates
    failed = failed or (expect_restart and report["distinctHubEpochs"] < 2)
    return 0 if early_causes else (1 if failed else 0)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
