from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Any

import pytest
import yaml

from scripts.watch_capacity_shards import (
    GitHubApi,
    ShardState,
    WatchdogError,
    cancel_bound_attempt,
    classify_shards,
    monitor,
    require_mutation_gate,
)
from tests.load.build_capacity_terminal_status import JOBS

WORKFLOW = Path(".github/workflows/capacity-certification.yml")
RUN_ID = 33_936_129_541
ATTEMPT = 2


def shard(index: int, conclusion: str | None) -> dict[str, Any]:
    status = "completed" if conclusion is not None else "in_progress"
    return {
        "id": index + 100,
        "name": f"shard ({index})",
        "status": status,
        "conclusion": conclusion,
    }


def watchdog(*, status: str = "in_progress", conclusion: str | None = None) -> dict[str, Any]:
    return {
        "id": 999,
        "name": "Capacity shard failure watchdog",
        "status": status,
        "conclusion": conclusion,
    }


@dataclass
class FakeApi:
    batches: list[Sequence[dict[str, Any]] | Exception]
    run_record: dict[str, Any] = field(
        default_factory=lambda: {
            "id": RUN_ID,
            "run_attempt": ATTEMPT,
            "status": "in_progress",
            "conclusion": None,
        }
    )
    cancelled: list[int] = field(default_factory=list)

    def jobs(self, run_id: int, run_attempt: int) -> list[dict[str, Any]]:
        assert run_id == RUN_ID
        assert run_attempt == ATTEMPT
        value = self.batches.pop(0)
        if isinstance(value, Exception):
            raise value
        return list(value)

    def run(self, run_id: int) -> dict[str, Any]:
        assert run_id == RUN_ID
        return self.run_record

    def cancel(self, run_id: int) -> None:
        self.cancelled.append(run_id)


def test_failed_or_cancelled_shard_requires_cancellation() -> None:
    failed, failure_detail = classify_shards(
        [shard(index, "failure" if index == 2 else None) for index in range(6)]
    )
    cancelled, cancelled_detail = classify_shards(
        [shard(index, "cancelled" if index == 4 else None) for index in range(6)]
    )

    assert failed is ShardState.FAILED
    assert failure_detail == "shard (2) concluded failure"
    assert cancelled is ShardState.FAILED
    assert cancelled_detail == "shard (4) concluded cancelled"


def test_all_six_successes_stop_without_cancelling() -> None:
    api = FakeApi(batches=[[shard(index, "success") for index in range(6)]])

    result = monitor(api, run_id=RUN_ID, run_attempt=ATTEMPT)

    assert result == "success: all capacity shards completed"
    assert api.cancelled == []


def test_pending_shards_are_polled_until_success() -> None:
    clock_value = [0.0]

    def clock() -> float:
        return clock_value[0]

    def sleep(seconds: float) -> None:
        clock_value[0] += seconds

    pending = [shard(index, "success" if index < 5 else None) for index in range(6)]
    complete = [shard(index, "success") for index in range(6)]
    api = FakeApi(batches=[pending, complete])

    result = monitor(
        api,
        run_id=RUN_ID,
        run_attempt=ATTEMPT,
        poll_seconds=15,
        clock=clock,
        sleep=sleep,
    )

    assert result == "success: all capacity shards completed"
    assert clock_value == [15.0]
    assert api.cancelled == []


def test_repeated_api_errors_fail_closed_through_normal_cancellation() -> None:
    api = FakeApi(
        batches=[
            WatchdogError("temporary API error"),
            WatchdogError("temporary API error"),
            WatchdogError("temporary API error"),
        ]
    )

    result = monitor(
        api,
        run_id=RUN_ID,
        run_attempt=ATTEMPT,
        poll_seconds=0.01,
        sleep=lambda _seconds: None,
    )

    assert result == "cancelled: GitHub job state remained unavailable"
    assert api.cancelled == [RUN_ID]


def test_repeated_malformed_job_state_uses_the_same_bounded_cancel_path() -> None:
    malformed = [shard(index, None) for index in range(6)]
    malformed[2]["conclusion"] = "success"
    api = FakeApi(batches=[malformed, malformed, malformed])

    result = monitor(
        api,
        run_id=RUN_ID,
        run_attempt=ATTEMPT,
        poll_seconds=0.01,
        sleep=lambda _seconds: None,
    )

    assert result == "cancelled: GitHub job state remained unavailable"
    assert api.cancelled == [RUN_ID]


def test_attempt_change_refuses_to_cancel_a_rerun() -> None:
    api = FakeApi(
        batches=[],
        run_record={"id": RUN_ID, "run_attempt": ATTEMPT + 1, "status": "in_progress"},
    )

    with pytest.raises(WatchdogError, match="attempt changed"):
        cancel_bound_attempt(api, run_id=RUN_ID, run_attempt=ATTEMPT)

    assert api.cancelled == []


def test_completed_run_is_reported_terminal_without_false_cancellation() -> None:
    jobs = [shard(index, "failure" if index == 1 else None) for index in range(6)]
    api = FakeApi(
        batches=[jobs],
        run_record={"id": RUN_ID, "run_attempt": ATTEMPT, "status": "completed"},
    )

    result = monitor(api, run_id=RUN_ID, run_attempt=ATTEMPT)

    assert result == "terminal: run completed before cancellation: shard (1) concluded failure"
    assert api.cancelled == []


def test_failure_path_cancels_the_bound_current_attempt() -> None:
    jobs = [shard(index, "failure" if index == 0 else None) for index in range(6)]
    api = FakeApi(batches=[jobs])

    result = monitor(api, run_id=RUN_ID, run_attempt=ATTEMPT)

    assert result == "cancelled: shard (0) concluded failure"
    assert api.cancelled == [RUN_ID]


def test_mutation_gate_accepts_six_healthy_shards_and_live_watchdog() -> None:
    jobs = [shard(index, None) for index in range(6)] + [watchdog()]
    api = FakeApi(batches=[jobs])

    require_mutation_gate(api, run_id=RUN_ID, run_attempt=ATTEMPT)

    assert api.cancelled == []


@pytest.mark.parametrize(
    "jobs, message",
    [
        (
            [shard(index, None) for index in range(5)] + [watchdog()],
            "not all shards are visible",
        ),
        (
            [shard(index, None) for index in range(6)]
            + [watchdog(status="completed", conclusion="failure")],
            "watchdog did not succeed",
        ),
        (
            [shard(index, "cancelled" if index == 3 else None) for index in range(6)]
            + [watchdog()],
            "shard \\(3\\) concluded cancelled",
        ),
        (
            [
                {**shard(index, None), "status": "queued"} if index == 2 else shard(index, None)
                for index in range(6)
            ]
            + [watchdog()],
            "a shard has not started",
        ),
        (
            [shard(index, None) for index in range(6)] + [watchdog(status="queued")],
            "watchdog has not started",
        ),
    ],
)
def test_mutation_gate_rejects_missing_or_failed_guards(
    jobs: list[dict[str, Any]], message: str
) -> None:
    api = FakeApi(batches=[jobs])

    with pytest.raises(WatchdogError, match=message):
        require_mutation_gate(api, run_id=RUN_ID, run_attempt=ATTEMPT)


def test_mutation_gate_fails_closed_when_jobs_api_is_unavailable() -> None:
    api = FakeApi(batches=[WatchdogError("jobs API unavailable")])

    with pytest.raises(WatchdogError, match="jobs API unavailable"):
        require_mutation_gate(api, run_id=RUN_ID, run_attempt=ATTEMPT)


def test_mutation_gate_rejects_inconsistent_top_level_run() -> None:
    jobs = [shard(index, None) for index in range(6)] + [watchdog()]
    api = FakeApi(
        batches=[jobs],
        run_record={
            "id": RUN_ID,
            "run_attempt": ATTEMPT,
            "status": "in_progress",
            "conclusion": "success",
        },
    )

    with pytest.raises(WatchdogError, match="in-progress run has a conclusion"):
        require_mutation_gate(api, run_id=RUN_ID, run_attempt=ATTEMPT)


def test_api_redirect_does_not_forward_authorization_to_another_origin() -> None:
    received_authorization: list[str | None] = []

    class TargetHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            received_authorization.append(self.headers.get("Authorization"))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, _format: str, *_args: object) -> None:
            return

    target = ThreadingHTTPServer(("127.0.0.1", 0), TargetHandler)
    target_thread = Thread(target=target.serve_forever, daemon=True)
    target_thread.start()

    target_url = f"http://127.0.0.1:{target.server_port}/capture"

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self.send_response(302)
            self.send_header("Location", target_url)
            self.end_headers()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
    source_thread = Thread(target=source.serve_forever, daemon=True)
    source_thread.start()
    try:
        api = GitHubApi(
            repository="example/viewer",
            token="secret-test-token",
            api_url=f"http://127.0.0.1:{source.server_port}",
        )
        with pytest.raises(WatchdogError, match="HTTP 302"):
            api.run(RUN_ID)
    finally:
        source.shutdown()
        target.shutdown()
        source.server_close()
        target.server_close()
        source_thread.join(timeout=2)
        target_thread.join(timeout=2)

    assert received_authorization == []


def test_workflow_grants_write_only_to_bounded_watchdog_job() -> None:
    loaded = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    watchdog = loaded["jobs"]["failure-watchdog"]
    serialized = "\n".join(str(step) for step in watchdog["steps"])

    assert loaded["permissions"]["actions"] == "read"
    assert watchdog["needs"] == ["arm"]
    assert watchdog["timeout-minutes"] == "178"
    assert watchdog["permissions"] == {"actions": "write", "contents": "read"}
    assert "GITHUB_RUN_ID" in serialized
    assert "GITHUB_RUN_ATTEMPT" in serialized
    assert "--poll-seconds 15" in serialized
    assert "--deadline-seconds 10500" in serialized
    assert "/cancel" in Path("scripts/watch_capacity_shards.py").read_text(encoding="utf-8")
    assert "force-cancel" not in Path("scripts/watch_capacity_shards.py").read_text(
        encoding="utf-8"
    )


def test_watchdog_failure_blocks_promotion_while_cleanup_stays_always() -> None:
    loaded = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    jobs = loaded["jobs"]
    decision_runs = "\n".join(str(step.get("run", "")) for step in jobs["decision"]["steps"])

    assert "failure-watchdog" in jobs["decision"]["needs"]
    assert "failure-watchdog" in JOBS
    assert 'needs.failure-watchdog.result }}" = success' in decision_runs
    assert jobs["cleanup"]["if"].startswith("${{ always()")
    assert jobs["postflight"]["if"].startswith("${{ always()")


def test_scheduled_mutations_have_just_in_time_read_only_gate() -> None:
    sentinels = Path("deploy/scripts/run-capacity-sentinels.sh").read_text(encoding="utf-8")
    fault = Path("deploy/scripts/run-capacity-fault-recovery.sh").read_text(encoding="utf-8")

    sentinel_gate = sentinels.index("watch_capacity_shards.py --gate-mutation")
    assert sentinels.index("sleep") < sentinel_gate < sentinels.index("playwright test")
    assert sentinel_gate < sentinels.index("unset GH_TOKEN") < sentinels.index("playwright test")
    fault_gate = fault.index("watch_capacity_shards.py --gate-mutation")
    assert fault.index("sleep") < fault_gate < fault.index('login="$(curl')
    assert fault_gate < fault.index("unset GH_TOKEN") < fault.index('login="$(curl')
    assert fault_gate < fault.index('"capacity-fault run=${run_id}')
    assert "GH_TOKEN" in sentinels
    assert "GH_TOKEN" in fault


def test_poll_interval_is_bounded_to_thirty_seconds() -> None:
    api = FakeApi(batches=[])
    with pytest.raises(WatchdogError, match="at most 30"):
        monitor(api, run_id=RUN_ID, run_attempt=ATTEMPT, poll_seconds=30.1)


def test_success_returned_after_deadline_requests_normal_cancellation() -> None:
    clock_value = [0.0]

    class SlowApi(FakeApi):
        def jobs(self, run_id: int, run_attempt: int) -> list[dict[str, Any]]:
            result = super().jobs(run_id, run_attempt)
            clock_value[0] = 11.0
            return result

    api = SlowApi(batches=[[shard(index, "success") for index in range(6)]])

    result = monitor(
        api,
        run_id=RUN_ID,
        run_attempt=ATTEMPT,
        deadline_seconds=10,
        clock=lambda: clock_value[0],
    )

    assert result == "cancelled: watchdog deadline reached before shard success"
    assert api.cancelled == [RUN_ID]


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_non_finite_deadline_is_rejected(value: float) -> None:
    api = FakeApi(batches=[])
    with pytest.raises(WatchdogError, match="deadline_seconds"):
        monitor(api, run_id=RUN_ID, run_attempt=ATTEMPT, deadline_seconds=value)
