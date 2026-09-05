#!/usr/bin/env python3
"""Cancel a bound capacity workflow attempt when a shard cannot succeed.

The standard GitHub cancellation endpoint is deliberate: GitHub re-evaluates job
conditions and leaves the workflow's ``always()`` decision, cleanup, and
postflight chain eligible. This process cannot clean production state itself.
If GitHub's API cannot accept the cancellation request, the watchdog exits
nonzero and the independent host/runtime safety controls remain authoritative.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

API_VERSION = "2022-11-28"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_POLL_SECONDS = 30.0
SHARD_NAME = re.compile(r"^shard \((?P<index>[0-9]+)\)$")
WATCHDOG_JOB_NAME = "Capacity shard failure watchdog"
JOB_STATUSES = {"completed", "in_progress", "pending", "queued", "requested", "waiting"}
JOB_CONCLUSIONS = {
    "action_required",
    "cancelled",
    "failure",
    "neutral",
    "skipped",
    "stale",
    "startup_failure",
    "success",
    "timed_out",
}


class WatchdogError(RuntimeError):
    """The watchdog could not safely determine or request terminal state."""


class ShardState(Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"


class CapacityApi(Protocol):
    def jobs(self, run_id: int, run_attempt: int) -> list[dict[str, Any]]: ...

    def run(self, run_id: int) -> dict[str, Any]: ...

    def cancel(self, run_id: int) -> None: ...


class RejectRedirects(urllib.request.HTTPRedirectHandler):
    """Keep the bearer token on the configured API origin."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


@dataclass(frozen=True)
class GitHubApi:
    repository: str
    token: str
    api_url: str = "https://api.github.com"
    timeout_seconds: float = 15.0

    def _request(self, method: str, path: str) -> Any:
        url = f"{self.api_url.rstrip('/')}/{path.lstrip('/')}"
        request = urllib.request.Request(
            url,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": "pathlab-capacity-failure-watchdog",
            },
        )
        opener = urllib.request.build_opener(RejectRedirects())
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            raise WatchdogError(f"GitHub API {method} returned HTTP {exc.code}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise WatchdogError(f"GitHub API {method} request failed") from exc
        if not body:
            return None
        if len(body) > MAX_RESPONSE_BYTES:
            raise WatchdogError(f"GitHub API response exceeded {MAX_RESPONSE_BYTES} bytes")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise WatchdogError(f"GitHub API returned invalid JSON for {path}") from exc

    def _repo_path(self) -> str:
        parts = self.repository.split("/")
        if len(parts) != 2 or not all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts):
            raise WatchdogError("repository must be an owner/name pair")
        return "/".join(urllib.parse.quote(part, safe="") for part in parts)

    def jobs(self, run_id: int, run_attempt: int) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        page = 1
        while True:
            result = self._request(
                "GET",
                f"repos/{self._repo_path()}/actions/runs/{run_id}/attempts/"
                f"{run_attempt}/jobs?per_page=100&page={page}",
            )
            if not isinstance(result, Mapping) or not isinstance(result.get("jobs"), list):
                raise WatchdogError("GitHub jobs response has no jobs array")
            batch = result["jobs"]
            if not all(isinstance(item, dict) for item in batch):
                raise WatchdogError("GitHub jobs response contains a non-object job")
            jobs.extend(batch)
            total = result.get("total_count")
            if not isinstance(total, int) or total < len(jobs):
                raise WatchdogError("GitHub jobs response has an invalid total_count")
            if len(jobs) >= total:
                return jobs
            if not batch:
                raise WatchdogError("GitHub jobs pagination ended before total_count")
            page += 1
            if page > 10:
                raise WatchdogError("GitHub jobs response exceeded the bounded page limit")

    def run(self, run_id: int) -> dict[str, Any]:
        result = self._request("GET", f"repos/{self._repo_path()}/actions/runs/{run_id}")
        if not isinstance(result, dict):
            raise WatchdogError("GitHub run response is not an object")
        return result

    def cancel(self, run_id: int) -> None:
        self._request("POST", f"repos/{self._repo_path()}/actions/runs/{run_id}/cancel")


def classify_shards(
    jobs: Sequence[Mapping[str, Any]], *, expected_shards: int = 6
) -> tuple[ShardState, str]:
    if expected_shards <= 0:
        raise WatchdogError("expected_shards must be positive")
    shards: dict[int, Mapping[str, Any]] = {}
    for job in jobs:
        name = job.get("name")
        match = SHARD_NAME.fullmatch(name) if isinstance(name, str) else None
        if match is None:
            continue
        index = int(match.group("index"))
        if index >= expected_shards:
            raise WatchdogError(f"unexpected shard index {index}")
        if index in shards:
            raise WatchdogError(f"duplicate shard job {index}")
        status = job.get("status")
        conclusion = job.get("conclusion")
        if status not in JOB_STATUSES:
            raise WatchdogError(f"shard ({index}) has an invalid status")
        if conclusion is not None and conclusion not in JOB_CONCLUSIONS:
            raise WatchdogError(f"shard ({index}) has an invalid conclusion")
        if status == "completed" and conclusion is None:
            raise WatchdogError(f"shard ({index}) completed without a conclusion")
        if status != "completed" and conclusion is not None:
            raise WatchdogError(f"shard ({index}) has a premature conclusion")
        shards[index] = job

    for index, job in sorted(shards.items()):
        conclusion = job.get("conclusion")
        if conclusion is not None and conclusion != "success":
            return ShardState.FAILED, f"shard ({index}) concluded {conclusion}"

    if len(shards) == expected_shards and all(
        job.get("conclusion") == "success" for job in shards.values()
    ):
        return ShardState.SUCCESS, "all six shards concluded success"
    return ShardState.PENDING, f"{len(shards)}/{expected_shards} shards visible"


def require_mutation_gate(
    api: CapacityApi, *, run_id: int, run_attempt: int, expected_shards: int = 6
) -> None:
    before = api.run(run_id)
    require_bound_active_run(before, run_id=run_id, run_attempt=run_attempt)
    jobs = api.jobs(run_id, run_attempt)
    state, detail = classify_shards(jobs, expected_shards=expected_shards)
    if state is ShardState.FAILED:
        raise WatchdogError(f"production mutation blocked: {detail}")
    visible_shards = sum(
        isinstance(job.get("name"), str) and SHARD_NAME.fullmatch(job["name"]) is not None
        for job in jobs
    )
    if visible_shards != expected_shards:
        raise WatchdogError("production mutation blocked: not all shards are visible")
    for job in jobs:
        name = job.get("name")
        if not isinstance(name, str) or SHARD_NAME.fullmatch(name) is None:
            continue
        if job.get("status") == "in_progress" and job.get("conclusion") is None:
            continue
        if job.get("status") == "completed" and job.get("conclusion") == "success":
            continue
        raise WatchdogError("production mutation blocked: a shard has not started")

    watchdogs = [job for job in jobs if job.get("name") == WATCHDOG_JOB_NAME]
    if len(watchdogs) != 1:
        raise WatchdogError("production mutation blocked: watchdog job is not uniquely visible")
    watchdog = watchdogs[0]
    status = watchdog.get("status")
    conclusion = watchdog.get("conclusion")
    if status not in JOB_STATUSES or (conclusion is not None and conclusion not in JOB_CONCLUSIONS):
        raise WatchdogError("production mutation blocked: watchdog state is invalid")
    if status == "completed" and conclusion != "success":
        raise WatchdogError("production mutation blocked: watchdog did not succeed")
    if status != "completed" and (status != "in_progress" or conclusion is not None):
        raise WatchdogError("production mutation blocked: watchdog has not started")

    after = api.run(run_id)
    require_bound_active_run(after, run_id=run_id, run_attempt=run_attempt)


def require_bound_active_run(run: Mapping[str, Any], *, run_id: int, run_attempt: int) -> None:
    if run.get("id") != run_id:
        raise WatchdogError("GitHub run id does not match the bound run")
    if run.get("run_attempt") != run_attempt:
        raise WatchdogError("GitHub run attempt changed")
    if run.get("status") != "in_progress":
        raise WatchdogError("GitHub run is not in progress")
    if run.get("conclusion") is not None:
        raise WatchdogError("GitHub in-progress run has a conclusion")


def cancel_bound_attempt(api: CapacityApi, *, run_id: int, run_attempt: int) -> bool:
    # GitHub exposes only run-scoped normal cancellation. Rechecking the attempt
    # immediately before POST narrows the unavoidable GET-to-cancel race. GitHub
    # does not expose an attempt-specific cancellation endpoint.
    run = api.run(run_id)
    if run.get("id") != run_id:
        raise WatchdogError("GitHub run id does not match the bound run")
    if run.get("run_attempt") != run_attempt:
        raise WatchdogError("GitHub run attempt changed; refusing to cancel another attempt")
    if run.get("status") not in JOB_STATUSES:
        raise WatchdogError("GitHub run has an invalid status")
    if run.get("status") == "completed":
        return False
    api.cancel(run_id)
    return True


def request_terminal_state(api: CapacityApi, *, run_id: int, run_attempt: int, reason: str) -> str:
    if cancel_bound_attempt(api, run_id=run_id, run_attempt=run_attempt):
        return f"cancelled: {reason}"
    return f"terminal: run completed before cancellation: {reason}"


def monitor(
    api: CapacityApi,
    *,
    run_id: int,
    run_attempt: int,
    expected_shards: int = 6,
    poll_seconds: float = 15.0,
    deadline_seconds: float = 10_500.0,
    max_api_errors: int = 3,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    if not math.isfinite(poll_seconds) or not 0 < poll_seconds <= MAX_POLL_SECONDS:
        raise WatchdogError("poll_seconds must be greater than zero and at most 30")
    if not math.isfinite(deadline_seconds) or deadline_seconds <= 0 or max_api_errors <= 0:
        raise WatchdogError("deadline_seconds and max_api_errors must be positive")

    deadline = clock() + deadline_seconds
    consecutive_errors = 0
    while True:
        if clock() >= deadline:
            return request_terminal_state(
                api,
                run_id=run_id,
                run_attempt=run_attempt,
                reason="watchdog deadline reached before shard success",
            )
        try:
            jobs = api.jobs(run_id, run_attempt)
            state, detail = classify_shards(jobs, expected_shards=expected_shards)
        except WatchdogError as exc:
            consecutive_errors += 1
            print(
                f"watchdog poll failed ({consecutive_errors}/{max_api_errors}): {exc}",
                file=sys.stderr,
                flush=True,
            )
            if consecutive_errors >= max_api_errors:
                return request_terminal_state(
                    api,
                    run_id=run_id,
                    run_attempt=run_attempt,
                    reason="GitHub job state remained unavailable",
                )
        else:
            consecutive_errors = 0
            if clock() >= deadline:
                return request_terminal_state(
                    api,
                    run_id=run_id,
                    run_attempt=run_attempt,
                    reason="watchdog deadline reached before shard success",
                )
            print(f"capacity shard watchdog: {state.value}: {detail}", flush=True)
            if state is ShardState.SUCCESS:
                return "success: all capacity shards completed"
            if state is ShardState.FAILED:
                return request_terminal_state(
                    api,
                    run_id=run_id,
                    run_attempt=run_attempt,
                    reason=detail,
                )

        remaining = deadline - clock()
        if remaining > 0:
            sleep(min(poll_seconds, remaining))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--run-attempt", type=int, required=True)
    parser.add_argument("--expected-shards", type=int, default=6)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--deadline-seconds", type=float, default=10_500.0)
    parser.add_argument("--max-api-errors", type=int, default=3)
    parser.add_argument("--gate-mutation", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("capacity shard watchdog: GH_TOKEN is required", file=sys.stderr)
        return 1
    if args.run_id <= 0 or args.run_attempt <= 0:
        print("capacity shard watchdog: run id and attempt must be positive", file=sys.stderr)
        return 1
    try:
        api = GitHubApi(repository=args.repository, token=token)
        if args.gate_mutation:
            require_mutation_gate(
                api,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                expected_shards=args.expected_shards,
            )
            result = "success: production mutation gate is healthy"
        else:
            result = monitor(
                api,
                run_id=args.run_id,
                run_attempt=args.run_attempt,
                expected_shards=args.expected_shards,
                poll_seconds=args.poll_seconds,
                deadline_seconds=args.deadline_seconds,
                max_api_errors=args.max_api_errors,
            )
    except WatchdogError as exc:
        print(f"capacity shard watchdog failed closed: {exc}", file=sys.stderr)
        return 1
    print(result, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
