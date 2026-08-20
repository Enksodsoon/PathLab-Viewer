#!/usr/bin/env python3
"""Sign an explicit 300-seat NOT CERTIFIED decision after strict shard failure."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

from distributed_certification import validate_plan
from validate_sentinel_evidence import validate as validate_sentinels


def build(plan: dict[str, Any], sentinels: dict[str, Any] | None, *, nonce: str) -> dict[str, Any]:
    validate_plan(plan)
    if sentinels is not None:
        validate_sentinels(sentinels, require_cleanup=True)
        for field in ("runId", "workflowSha", "planDigest"):
            if sentinels[field] != plan[field]:
                raise ValueError("sentinel evidence is not plan-bound")
    functional = (
        sentinels["functionalSentinels"]
        if sentinels is not None
        else {
            name: False
            for name in (
                "uploadConversion",
                "annotations",
                "libraryShare",
                "dynamicViewer",
                "desktop",
            )
        }
    )
    results = {
        "smoke-2": {"durationSeconds": 0, "status": "skipped"},
        "smoke-100": {"durationSeconds": 0, "status": "skipped"},
        "boundary-300": {"durationSeconds": 0, "status": "skipped"},
        "boundary-600": {"durationSeconds": 0, "status": "skipped"},
        "boundary-900": {"durationSeconds": 0, "status": "skipped"},
        "certification-1200": {"durationSeconds": 0, "status": "failed"},
        "headroom-1500": {"durationSeconds": 0, "status": "skipped"},
        "stress-1750": {"durationSeconds": 0, "status": "skipped"},
        "stress-2000": {"durationSeconds": 0, "status": "skipped"},
        "recovery-1200": {"durationSeconds": 0, "status": "skipped"},
    }
    digest = hashlib.sha256(
        json.dumps({"plan": plan["planDigest"], "failure": "strict-shard"}, sort_keys=True).encode()
    ).hexdigest()
    return {
        "certification": {
            "schemaVersion": 2,
            "candidateSha": plan["workflowSha"],
            "runId": plan["runId"],
            "nonce": nonce,
            "startedAt": 0,
            "completedAt": 0,
            "authorizedWindowStart": plan["windowStartEpochMs"] // 1_000,
            "authorizedWindowEnd": plan["windowEndEpochMs"] // 1_000,
            "withinAuthorizedIctWindow": False,
            "allPreflightGatesPassed": False,
            "fixtureCleanupSucceeded": False,
            "evidenceDigest": digest,
            "strictStages": {
                "1200": {"durationSeconds": 0, "passed": False},
                "1500": {"durationSeconds": 0, "passed": False},
            },
            "stageResults": results,
            "functionalSentinels": functional,
            "verdict": "NOT CERTIFIED",
            "selectedCapacity": 300,
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--sentinels", type=Path)
    parser.add_argument("--nonce", required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--signature-output", type=Path, required=True)
    args = parser.parse_args()
    sentinels = None
    if args.sentinels is not None and args.sentinels.is_file():
        try:
            candidate = json.loads(args.sentinels.read_text())
            validate_sentinels(candidate, require_cleanup=True)
            sentinels = candidate
        except (ValueError, json.JSONDecodeError):
            sentinels = None
    decision = build(json.loads(args.plan.read_text()), sentinels, nonce=args.nonce)
    payload = json.dumps(decision, sort_keys=True, separators=(",", ":")).encode()
    args.output.write_text(json.dumps(decision, indent=2) + "\n")
    args.signature_output.write_text(
        hmac.new(args.key_file.read_bytes().strip(), payload, hashlib.sha256).hexdigest() + "\n"
    )


if __name__ == "__main__":
    main()
