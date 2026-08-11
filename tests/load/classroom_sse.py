"""Bounded classroom protocol harness. It refuses production unless explicitly allowed."""

import asyncio
import json
import math
import os
import statistics
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


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
    hub_epochs: set[str] = field(default_factory=set)
    churn_attempted: bool = False


@dataclass
class Recorder:
    presenter_sent: dict[int, float] = field(default_factory=dict)
    presenter_received: dict[int, float] = field(default_factory=dict)
    presenter_latencies_ms: list[float] = field(default_factory=list)
    question_sent: dict[str, float] = field(default_factory=dict)
    question_received: dict[str, float] = field(default_factory=dict)
    question_latencies_ms: list[float] = field(default_factory=list)
    control_sent_at: float | None = None
    control_latencies_ms: list[float] = field(default_factory=list)
    tile_latencies_ms: list[float] = field(default_factory=list)
    tile_errors: int = 0

    def presenter_sent_at(self, sequence: int, started: float) -> None:
        self.presenter_sent[sequence] = started
        received = self.presenter_received.pop(sequence, None)
        if received is not None:
            self.presenter_latencies_ms.append((received - started) * 1000)

    def presenter_received_at(self, sequence: int, received: float) -> None:
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
    delay_ms = min(5000, min(4000, 500 * (2 ** min(3, attempt))) + jitter)
    return float(delay_ms) / 1000


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


async def consume_stream(
    participant: Participant,
    session_id: str,
    deadline: float,
    recorder: Recorder,
    churn_at: float | None,
) -> None:
    attempt = 0
    churned = False
    expected_disconnect = False
    while time.monotonic() < deadline:
        try:
            async with asyncio.timeout(max(0, deadline - time.monotonic())):
                async with participant.client.stream(
                    "GET", f"/api/v1/classroom/sessions/{session_id}/events", timeout=None
                ) as stream:
                    stream.raise_for_status()
                    participant.connects += 1
                    participant.connected_at.append(time.monotonic())
                    event_type = ""
                    async for line in stream.aiter_lines():
                        now = time.monotonic()
                        if churn_at and now >= churn_at and not churned:
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
                                recorder.presenter_received_at(sequence, now)
                            elif event_type == "control" and recorder.control_sent_at is not None:
                                recorder.control_latencies_ms.append(
                                    (now - recorder.control_sent_at) * 1000
                                )
                attempt = 0
                expected_disconnect = False
        except TimeoutError:
            return
        except (httpx.HTTPError, json.JSONDecodeError) as error:
            if expected_disconnect:
                expected_disconnect = False
                continue
            # httpx may surface shutdown of an SSE read near the scenario
            # boundary as an incomplete-chunk protocol error. Count it only
            # when enough time remains for the client's bounded reconnect.
            if time.monotonic() + reconnect_delay(participant.participant_id, attempt) < deadline:
                participant.errors.append(type(error).__name__)
        if time.monotonic() < deadline:
            await asyncio.sleep(reconnect_delay(participant.participant_id, attempt))
            attempt += 1


async def consume_teacher(
    client: httpx.AsyncClient,
    session_id: str,
    deadline: float,
    recorder: Recorder,
) -> None:
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
        except TimeoutError:
            return
        except (httpx.HTTPError, json.JSONDecodeError):
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
            recorder.presenter_sent_at(int(response.json()["presenterSequence"]), started)
            index += 1
        except httpx.HTTPError:
            pass
        await asyncio.sleep(max(0, (1 / rate) - (time.monotonic() - started)))


async def request_tiles(
    base_url: str,
    tile_url: str,
    deadline: float,
    sequence: int,
    recorder: Recorder,
) -> None:
    await asyncio.sleep((sequence % 10) / 10)
    async with httpx.AsyncClient(base_url=base_url, timeout=20) as client:
        while time.monotonic() < deadline:
            started = time.monotonic()
            try:
                response = await client.get(tile_url)
                response.raise_for_status()
                recorder.tile_latencies_ms.append((time.monotonic() - started) * 1000)
            except httpx.HTTPError:
                recorder.tile_errors += 1
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


async def run() -> int:
    base_url = os.environ.get("PATHLAB_CLASSROOM_BASE_URL", "http://127.0.0.1:8000")
    join_code = os.environ.get("PATHLAB_CLASSROOM_JOIN_CODE", "")
    session_id = os.environ.get("PATHLAB_CLASSROOM_SESSION_ID", "")
    slide_id = os.environ.get("PATHLAB_CLASSROOM_SLIDE_ID", "")
    tile_url = os.environ.get("PATHLAB_CLASSROOM_TILE_URL", "")
    username = os.environ.get("PATHLAB_CLASSROOM_ADMIN_USERNAME", "")
    password = os.environ.get("PATHLAB_CLASSROOM_ADMIN_PASSWORD", "")
    count = int(os.environ.get("PATHLAB_CLASSROOM_PARTICIPANTS", "30"))
    duration = float(os.environ.get("PATHLAB_CLASSROOM_DURATION_SECONDS", "60"))
    rate = float(os.environ.get("PATHLAB_CLASSROOM_PRESENTER_RATE", "2"))
    expect_restart = os.environ.get("PATHLAB_CLASSROOM_EXPECT_RESTART", "false").lower() in {
        "1",
        "true",
        "yes",
    }
    if not any(
        host in base_url for host in ("127.0.0.1", "localhost", "host.docker.internal")
    ):
        raise SystemExit("This classroom harness is restricted to local ephemeral targets")
    if not all((join_code, session_id, slide_id, username, password)):
        raise SystemExit("join code, session, slide, and admin credentials are required")
    if not 1 <= count <= 300 or duration <= 0 or not 0 < rate <= 20:
        raise SystemExit("participants must be 1..300; duration positive; presenter rate 0..20")

    recorder = Recorder()
    started = time.monotonic()
    deadline = started + duration
    admin = httpx.AsyncClient(base_url=base_url, timeout=20)
    login = await admin.post(
        "/api/v1/auth/session", json={"username": username, "password": password}
    )
    login.raise_for_status()
    admin_csrf = login.json()["csrfToken"]
    initial_metrics_response = await admin.get("/api/v1/admin/classroom/metrics")
    initial_metrics_response.raise_for_status()
    initial_metrics = initial_metrics_response.json()

    async def join(sequence: int) -> Participant:
        await asyncio.sleep(sequence * 0.01)
        client = httpx.AsyncClient(base_url=base_url, timeout=20)
        response = await client.post("/api/v1/classroom/join", json={"joinCode": join_code})
        response.raise_for_status()
        payload = response.json()
        return Participant(sequence, client, payload["participant"]["id"], payload["csrfToken"])

    participants = list(await asyncio.gather(*(join(index) for index in range(count))))
    streams = [
        asyncio.create_task(
            consume_stream(
                participant,
                session_id,
                deadline,
                recorder,
                started + duration / 2 if participant.sequence % 10 == 0 else None,
            )
        )
        for participant in participants
    ]
    tasks = [
        *streams,
        asyncio.create_task(consume_teacher(admin, session_id, deadline, recorder)),
        asyncio.create_task(
            publish_presenter(
                admin, session_id, slide_id, admin_csrf, deadline, rate, recorder
            )
        ),
        asyncio.create_task(
            exercise_discrete_events(
                participants, admin, session_id, slide_id, admin_csrf, recorder
            )
        ),
    ]
    if tile_url:
        tasks.extend(
            asyncio.create_task(request_tiles(base_url, tile_url, deadline, index, recorder))
            for index in range(count)
        )
    task_results = await asyncio.gather(*tasks, return_exceptions=True)
    task_errors = [repr(result) for result in task_results if isinstance(result, BaseException)]

    final_state = await get_with_retry(
        admin, f"/api/v1/admin/classroom/sessions/{session_id}"
    )
    final_sequence = int(final_state.json()["presenter"]["sequence"])
    converged = 0
    for participant in participants:
        try:
            state = await get_with_retry(
                participant.client, f"/api/v1/classroom/sessions/{session_id}"
            )
            if int(state.json()["presenter"]["sequence"]) == final_sequence:
                converged += 1
        finally:
            await participant.client.aclose()
    metrics = await get_with_retry(admin, "/api/v1/admin/classroom/metrics")
    server_metrics = metrics.json()
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
        )
    }
    await admin.aclose()
    errors = [error for participant in participants for error in participant.errors]
    reconnect_expected = [item for item in participants if item.churn_attempted]
    successful_reconnects = sum(item.connects >= 2 for item in reconnect_expected)
    reconnect_times = [item.connected_at[1] for item in participants if len(item.connected_at) >= 2]
    control_events = sum(item.events.get("control", 0) for item in participants)
    report: dict[str, Any] = {
        "participants": count,
        "durationSeconds": round(time.monotonic() - started, 3),
        "connectionsOpened": sum(item.connects for item in participants),
        "reconnects": sum(max(0, item.connects - 1) for item in participants),
        "reconnectSuccessRate": round(
            successful_reconnects / len(reconnect_expected), 4
        ),
        "reconnectSpreadMs": round(
            (max(reconnect_times) - min(reconnect_times)) * 1000, 3
        ) if len(reconnect_times) > 1 else 0,
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
        "lostDiscreteEvents": max(0, count * 3 - control_events),
    }
    print(json.dumps(report, indent=2))
    # The producer intentionally permits only one HTTP mutation in flight and
    # keeps one latest pending viewport. Under a 300-stream fanout the response
    # latency, not the cadence ceiling, limits the achieved rate. Require a
    # useful 5 Hz freshness floor while separately reporting end-to-end p95/p99.
    minimum_achieved_rate = min(rate, 5)
    expected_updates = math.floor(
        duration * minimum_achieved_rate * (0.3 if expect_restart else 0.8)
    )
    failed = bool(task_errors) or converged != count or recorder.tile_errors > 0
    failed = failed or any(error == "presenter_sequence_regressed" for error in errors)
    failed = failed or successful_reconnects != len(reconnect_expected)
    failed = failed or len(recorder.presenter_sent) < expected_updates
    failed = failed or (expect_restart and report["distinctHubEpochs"] < 2)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
