"""Nine serial real API jobs in an explicitly owned disposable stack; no service startup.

Private receipts retain candidate maps. Queue times are observation intervals, never
an inferred exact start. Browser and human-effort measurements remain unmeasured.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from uuid import uuid4

POLICY = "real-api-nine-serial-operational-jobs/1"
RECIPES = (
    "native-overview-v6",
    "valis-1.2.0",
    "wsireg-0.3.10",
    "hisalign-0.2.1",
    "deeperhistreg-classical",
    "deeperhistreg-learned",
    "native-wsireg",
    "valis-rigid-wsireg",
    "native-valis",
)
TERMINAL = {"succeeded", "failed_terminal", "cancelled"}
MAX_RECEIPT_BYTES = 64 * 1024**2


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def _write(path: Path, value: dict[str, Any]) -> None:
    content = json.dumps(value, sort_keys=True, indent=2, allow_nan=False).encode()
    if len(content) > MAX_RECEIPT_BYTES:
        raise ValueError("operational receipt exceeds bound")
    if any(p.is_symlink() or p.is_junction() for p in (path, *path.parents)):
        raise ValueError("linked operational receipt paths are unsupported")
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix(f".{uuid4().hex}.pending")
    with pending.open("xb") as file:
        file.write(content)
        file.flush()
        os.fsync(file.fileno())
    pending.replace(path)


def validate_guard(guard: dict[str, Any], base: str, database: Path, set_id: str) -> None:
    url = urllib.parse.urlsplit(base)
    if (
        url.scheme != "http"
        or url.hostname != "127.0.0.1"
        or not url.port
        or url.port in {8001, 5175}
        or url.path
        or url.query
        or url.fragment
        or url.username
        or url.password
    ):
        raise ValueError("profile requires an owned disposable IPv4 loopback origin")
    root = Path(guard["disposableRoot"])
    if not root.is_absolute() or not database.is_absolute() or not database.is_file():
        raise ValueError("disposable database must already exist")
    if not database.resolve().is_relative_to(root.resolve()):
        raise ValueError("database escapes declared disposable root")
    if any(p.is_symlink() or p.is_junction() for p in (database, *database.parents)):
        raise ValueError("linked database paths are unsupported")
    if (
        guard.get("schema") != POLICY
        or guard.get("ownedDisposable") is not True
        or guard.get("baseUrl") != base
        or guard.get("database") != str(database)
        or guard.get("comparisonSetId") != set_id
    ):
        raise ValueError("disposable stack admission does not match request")
    for key in ("sourceProofSha256", "configurationProofSha256", "serviceOwnershipProofSha256"):
        if not isinstance(guard.get(key), str) or len(guard[key]) != 64:
            raise ValueError("source/configuration/service ownership proof must be bound")
    if guard.get("qualificationScope") != "operational-only-no-anatomical-qualification":
        raise ValueError("operational scope must be explicit")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise ValueError("operational authentication redirects are forbidden")


class Api:
    def __init__(self, base: str, headers: dict[str, str]):
        self.base, self.headers = base, headers
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect)

    def request(self, path: str, body: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            self.base + path,
            headers={**self.headers, "Content-Type": "application/json"},
            data=None if body is None else json.dumps(body).encode(),
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                content = response.read(MAX_RECEIPT_BYTES + 1)
                if len(content) > MAX_RECEIPT_BYTES:
                    raise ValueError("API response exceeds bounded receipt size")
                value = json.loads(content)
                if not isinstance(value, dict):
                    raise ValueError("API response must be an object")
                return response.status, value
        except urllib.error.HTTPError as error:
            return error.code, {"category": "api-request-rejected"}


def jobs(database: Path, set_id: str, recipe: str) -> list[dict[str, Any]]:
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=2) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT id,status,checkpoint,created_at,updated_at,failure_code,resource_limits "
            "FROM jobs WHERE kind='align_benchmark' ORDER BY created_at,id"
        ).fetchall()
    result = []
    for row in rows:
        value = dict(row)
        checkpoint = json.loads(value["checkpoint"] or "{}")
        if checkpoint.get("comparisonSetId") == set_id and checkpoint.get("engine") == recipe:
            value["checkpoint"] = checkpoint
            value["resource_limits"] = json.loads(value["resource_limits"] or "{}")
            result.append(value)
    return result


def _utc() -> str:
    return dt.datetime.now(dt.UTC).isoformat()


def queue_interval(created_at: str, last_queued: str | None, first_nonqueued: str) -> list[float]:
    def parse(value: str) -> dt.datetime:
        parsed = dt.datetime.fromisoformat(value)
        return parsed.replace(tzinfo=dt.UTC) if parsed.tzinfo is None else parsed

    created = parse(created_at)
    lower = 0.0 if last_queued is None else max(0.0, (parse(last_queued) - created).total_seconds())
    upper = max(lower, (parse(first_nonqueued) - created).total_seconds())
    return [lower, upper]


def profile(
    api: Api,
    database: Path,
    set_id: str,
    version: int,
    output: Path,
    admission: dict[str, Any],
    *,
    poll_seconds: float = 0.25,
) -> dict[str, Any]:
    if not 0.1 <= poll_seconds <= 2:
        raise ValueError("poll interval must be bounded0.1..2seconds")
    binding = _digest(admission)
    rows = []
    endpoint = f"/api/v1/admin/comparison-sets/{urllib.parse.quote(set_id, safe='')}"
    for recipe in RECIPES:
        path = output / "private" / f"{recipe}.json"
        if path.exists():
            if path.stat().st_size > MAX_RECEIPT_BYTES:
                raise ValueError("cached operational receipt exceeds bound")
            row = json.loads(path.read_bytes())
            if row.get("admissionDigest") != binding or row.get("recipe") != recipe:
                raise ValueError("cached operational profile binding differs")
            if row.get("completed") is not True:
                raise ValueError(
                    "interrupted request requires explicit existing-job reconciliation"
                )
            rows.append(row)
            continue
        before = {job["id"] for job in jobs(database, set_id, recipe)}
        started = time.monotonic()
        row = {
            "recipe": recipe,
            "admissionDigest": binding,
            "completed": False,
            "preexistingJobIds": sorted(before),
            "requestAdmissionStartedAt": _utc(),
            "requestStartedAt": None,
            "browserApplicationSeconds": None,
            "humanCorrectionEffort": None,
            "anatomicalAccuracy": None,
            "queueSeconds": None,
        }
        _write(path, row)
        request_started = time.monotonic()
        row["requestStartedAt"] = _utc()
        code, ack = api.request(
            endpoint + "/benchmark", {"version": version, "engines": [recipe], "rerun": True}
        )
        row.update(
            apiStatus=code,
            requestAcknowledgedAt=_utc(),
            requestAckSeconds=time.monotonic() - request_started,
        )
        current = [job for job in jobs(database, set_id, recipe) if job["id"] not in before]
        if code != 202:
            if code >= 500:
                row["outcome"] = "api-acknowledgement-uncertain"
                _write(path, row)
                raise RuntimeError(
                    "API server error may have queued a job; stop for reconciliation"
                )
            if current:
                _write(path, row)
                raise RuntimeError("API rejected request but a job exists; stop for reconciliation")
            row.update(completed=True, outcome="api-rejected", candidate=None)
        else:
            if ack.get("queuedCandidates") != 1 or len(current) != 1:
                _write(path, row)
                raise RuntimeError("expected exactly one real queued job")
            job_id = current[0]["id"]
            last_queued = first_nonqueued = None
            while True:
                matches = [job for job in jobs(database, set_id, recipe) if job["id"] == job_id]
                if len(matches) != 1:
                    raise RuntimeError("queued job disappeared")
                job = matches[0]
                observed = _utc()
                if job["status"] == "queued" and first_nonqueued is None:
                    last_queued = observed
                elif (
                    job["status"] in {"running", "checkpointing", *TERMINAL}
                    and first_nonqueued is None
                ):
                    first_nonqueued = observed
                row.update(
                    jobId=job_id,
                    job=job,
                    lastObservedAt=observed,
                    lastQueuedObservationAt=last_queued,
                    firstNonqueuedObservationAt=first_nonqueued,
                    queueObservationIntervalSeconds=(
                        queue_interval(job["created_at"], last_queued, first_nonqueued)
                        if first_nonqueued
                        else None
                    ),
                )
                _write(path, row)
                if job["status"] in TERMINAL:
                    break
                if time.monotonic() - started >= 660:
                    raise RuntimeError("job not terminal within observation budget; no next job")
                time.sleep(poll_seconds)
            terminal_seconds = time.monotonic() - started
            fetch_started = time.monotonic()
            candidate_code, candidates = api.request(endpoint + "/candidates")
            selected = [
                candidate
                for candidate in candidates.get("candidates", [])
                if candidate.get("engine") == recipe and candidate.get("setVersion") == version
            ]
            if len(selected) > 1:
                raise RuntimeError("multiple matching candidates require explicit reconciliation")
            candidate = selected[0] if candidate_code == 200 and selected else None
            row.update(
                completed=True,
                outcome=job["status"],
                terminalObservedAt=observed,
                terminalObservationSeconds=terminal_seconds,
                candidateFetchSeconds=time.monotonic() - fetch_started,
                candidate=candidate,
                candidateDigest=_digest(candidate) if candidate else None,
                candidateFetchStatus=candidate_code,
            )
        _write(path, row)
        rows.append(row)
        _write(
            output / "progress.json",
            {
                "completedRecipes": len(rows),
                "plannedRecipes": 9,
                "currentRecipe": recipe,
                "policy": POLICY,
            },
        )
    report = {
        "schema": POLICY,
        "admissionDigest": binding,
        "admission": admission,
        "comparisonSetId": set_id,
        "setVersion": version,
        "baseUrl": api.base,
        "plannedRecipes": 9,
        "completedRecipes": len(rows),
        "rows": rows,
        "qualified": False,
        "methodScope": "API-configured-defaults; distinct from scientific campaign settings",
        "queueScope": "observed interval; first nonqueued may already be terminal",
        "pollSeconds": poll_seconds,
        "humanCorrectionEffort": None,
    }
    _write(output / "operational-queue.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--guard", type=Path, required=True)
    parser.add_argument("--comparison-set-id", required=True)
    parser.add_argument("--version", type=int, required=True)
    parser.add_argument("--auth-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    guard = json.loads(args.guard.read_bytes())
    validate_guard(guard, args.base_url, args.database, args.comparison_set_id)
    if guard.get("setVersion") != args.version:
        raise ValueError("comparison version differs from admission")
    if guard.get("outputDirectory") != str(args.output_dir) or not args.output_dir.is_absolute():
        raise ValueError("output must match the admitted private directory")
    if any(p.is_symlink() or p.is_junction() for p in (args.output_dir, *args.output_dir.parents)):
        raise ValueError("linked output directories are unsupported")
    if args.auth_file.is_symlink() or args.auth_file.stat().st_size > 64 * 1024:
        raise ValueError("private authentication admission is unsupported")
    headers = json.loads(args.auth_file.read_bytes())
    if not isinstance(headers, dict) or any(
        key.lower() not in {"cookie", "x-csrf-token"} or not isinstance(value, str)
        for key, value in headers.items()
    ):
        raise ValueError("authentication file only accepts fixture cookie and CSRF headers")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock = args.output_dir / "controller-active.lock"
    with lock.open("x", encoding="utf-8") as file:
        file.write(str(os.getpid()))
    try:
        report = profile(
            Api(args.base_url, headers),
            args.database,
            args.comparison_set_id,
            args.version,
            args.output_dir,
            guard,
        )
    finally:
        if lock.read_text() != str(os.getpid()):
            raise RuntimeError("operational controller ownership changed")
        lock.unlink()
    print(json.dumps({"completedRecipes": report["completedRecipes"], "qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
