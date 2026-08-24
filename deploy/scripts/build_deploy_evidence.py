#!/usr/bin/env python3
"""Build short-lived, authenticated deployment evidence from GitHub check-runs."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import Any, cast

CI_NAMES = {"backend", "browser", "web", "containers"}
SECURITY_NAMES = {
    "repository-and-dependencies",
    "CodeQL (python)",
    "CodeQL (javascript-typescript)",
}


class EvidenceBuildFailure(RuntimeError):
    pass


def _load_safety() -> ModuleType:
    path = Path(__file__).with_name("production_safety.py")
    spec = importlib.util.spec_from_file_location("pathlab_production_safety", path)
    if spec is None or spec.loader is None:
        raise EvidenceBuildFailure("production safety module is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect_checks(payload: dict[str, Any], sha: str) -> dict[str, dict[str, object]]:
    runs = payload.get("check_runs")
    if not isinstance(runs, list):
        raise EvidenceBuildFailure("GitHub check-runs payload is invalid")
    selected: dict[str, dict[str, object]] = {}
    expected = CI_NAMES | SECURITY_NAMES
    for raw in runs:
        if not isinstance(raw, dict) or raw.get("name") not in expected:
            continue
        name = cast(str, raw["name"])
        run_id = raw.get("id")
        if (
            raw.get("head_sha") != sha
            or raw.get("status") != "completed"
            or raw.get("conclusion") != "success"
            or not isinstance(run_id, int)
            or isinstance(run_id, bool)
            or run_id <= 0
        ):
            continue
        current = selected.get(name)
        if current is None or cast(int, current["runId"]) < run_id:
            selected[name] = {"conclusion": "success", "runId": run_id}
    missing = expected - set(selected)
    if missing:
        raise EvidenceBuildFailure(f"required successful check-runs are missing: {sorted(missing)}")
    return selected


def build_evidence(
    payload: dict[str, Any],
    *,
    sha: str,
    repository: str,
    workflow_run_id: str,
    nonce: str,
    projected_monthly_egress_bytes: int,
    month_to_date_cost_sgd: float,
    now: int,
) -> dict[str, Any]:
    checks = _collect_checks(payload, sha)
    evidence = {
        "schemaVersion": 2,
        "candidateSha": sha,
        "issuedAt": now,
        "expiresAt": now + 600,
        "nonce": nonce,
        "workflowRunId": workflow_run_id,
        "repository": repository,
        "ci": {"sha": sha, "required": {name: checks[name] for name in CI_NAMES}},
        "security": {
            "sha": sha,
            "required": {name: checks[name] for name in SECURITY_NAMES},
        },
        "fixtures": {"syntheticOnly": True},
        "annotations": {"enabled": False},
        "egress": {"projectedMonthlyBytes": projected_monthly_egress_bytes},
        "cost": {
            "currency": "SGD",
            "monthToDate": month_to_date_cost_sgd,
            "projectedIncremental": 0,
        },
    }
    _load_safety().validate(evidence, sha)
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checks", type=Path, required=True)
    parser.add_argument("--candidate-sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--projected-monthly-egress-bytes", type=int, required=True)
    parser.add_argument("--month-to-date-cost-sgd", type=float, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signature-output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.checks.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise EvidenceBuildFailure("GitHub check-runs payload is invalid")
        evidence = build_evidence(
            payload,
            sha=args.candidate_sha,
            repository=args.repository,
            workflow_run_id=args.workflow_run_id,
            nonce=args.nonce,
            projected_monthly_egress_bytes=args.projected_monthly_egress_bytes,
            month_to_date_cost_sgd=args.month_to_date_cost_sgd,
            now=int(time.time()),
        )
        safety = _load_safety()
        signature = safety.sign_evidence(evidence, args.key_file.read_bytes().strip())
        args.output.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
        args.signature_output.write_text(signature + "\n", encoding="ascii")
    except (EvidenceBuildFailure, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Evidence build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
