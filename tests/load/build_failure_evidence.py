#!/usr/bin/env python3
"""Build aggregate-only evidence-v2 for an explicit NOT CERTIFIED outcome."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import re
from pathlib import Path
from typing import Any

from distributed_certification import validate_plan
from validate_postflight_evidence import validate as validate_postflight


def build(
    plan: dict[str, Any],
    decision: dict[str, Any],
    fixture_preparation: dict[str, Any],
    postflight: dict[str, Any],
) -> dict[str, Any]:
    validate_plan(plan)
    validate_postflight(postflight)
    certification = decision.get("certification")
    if not isinstance(certification, dict):
        raise ValueError("signed decision is missing")
    if any(certification.get(name) != plan[name] for name in ("runId",)):
        raise ValueError("decision is not plan-bound")
    if certification.get("candidateSha") != plan["workflowSha"]:
        raise ValueError("decision SHA is not plan-bound")
    if (
        certification.get("verdict") != "NOT CERTIFIED"
        or certification.get("selectedCapacity") != 300
    ):
        raise ValueError("failure decision must select 300")
    if postflight["finalCapacity"] != 300:
        raise ValueError("postflight did not prove the 300-seat floor")
    if (
        fixture_preparation.get("runId") != plan["runId"]
        or fixture_preparation.get("workflowSha") != plan["workflowSha"]
        or fixture_preparation.get("planDigest") != plan["planDigest"]
    ):
        raise ValueError("fixture preparation evidence is not plan-bound")
    return {
        "schemaVersion": 2,
        "certified": False,
        "certifiedTier": None,
        "verdict": "NOT CERTIFIED",
        "selectedCapacity": 300,
        "runId": plan["runId"],
        "candidateSha": plan["workflowSha"],
        "planDigest": plan["planDigest"],
        "evidenceDigest": certification["evidenceDigest"],
        "postflight": postflight,
        "fixturePreparation": {
            key: fixture_preparation[key]
            for key in (
                "prepared",
                "encrypted",
                "syntheticOnly",
                "identifiersIncluded",
                "endpointsValidated",
            )
        },
        "aggregateOnly": True,
        "syntheticOnly": True,
    }


def verify_decision_signature(
    plan: dict[str, Any], decision: dict[str, Any], signature: str, key: bytes
) -> dict[str, Any]:
    validate_plan(plan)
    payload = json.dumps(decision, sort_keys=True, separators=(",", ":")).encode()
    expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError("capacity decision signature is invalid")
    certification = decision.get("certification")
    if not isinstance(certification, dict):
        raise ValueError("signed decision is missing")
    if (
        certification.get("runId") != plan["runId"]
        or certification.get("candidateSha") != plan["workflowSha"]
    ):
        raise ValueError("signed decision is not plan-bound")
    selected = certification.get("selectedCapacity")
    verdict = certification.get("verdict")
    if selected not in (300, 1200, 1500):
        raise ValueError("signed decision capacity is invalid")
    if (selected == 300) != (verdict == "NOT CERTIFIED"):
        raise ValueError("signed decision route is inconsistent")
    return certification


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", choices=("build", "verify-decision"), default="build")
    for name in (
        "plan",
        "decision",
        "signature",
        "key-file",
        "fixture-preparation",
        "postflight",
        "output-json",
        "output-markdown",
    ):
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args()
    required = ("plan", "decision", "signature", "key_file")
    if any(getattr(args, name) is None for name in required):
        parser.error("plan, decision, signature, and key-file are required")
    plan = json.loads(args.plan.read_text())
    decision = json.loads(args.decision.read_text())
    certification = verify_decision_signature(
        plan,
        decision,
        args.signature.read_text().strip(),
        args.key_file.read_bytes().strip(),
    )
    if args.command == "verify-decision":
        print(
            json.dumps(
                {
                    "selectedCapacity": certification["selectedCapacity"],
                    "verdict": certification["verdict"],
                }
            )
        )
        return
    if any(
        getattr(args, name) is None
        for name in ("fixture_preparation", "postflight", "output_json", "output_markdown")
    ):
        parser.error("postflight, output-json, and output-markdown are required to build evidence")
    report = build(
        plan,
        decision,
        json.loads(args.fixture_preparation.read_text()),
        json.loads(args.postflight.read_text()),
    )
    if re.fullmatch(r"[0-9a-f]{64}", report["evidenceDigest"]) is None:
        raise ValueError("decision evidence digest is invalid")
    args.output_json.write_text(json.dumps(report, indent=2) + "\n")
    args.output_markdown.write_text(
        "# Capacity certification\n\n"
        f"**NOT CERTIFIED** for `{report['candidateSha']}`; capacity restored "
        "to 300 and rollback verified.\n"
    )


if __name__ == "__main__":
    main()
