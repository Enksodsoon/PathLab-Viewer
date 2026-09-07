from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def request(
    method: str, url: str, headers: dict[str, str], payload: dict[str, Any] | None = None
) -> tuple[int, bytes]:
    body = json.dumps(payload).encode() if payload is not None else None
    outgoing = {**headers, **({"Content-Type": "application/json"} if body else {})}
    call = urllib.request.Request(url, data=body, method=method, headers=outgoing)
    try:
        with urllib.request.urlopen(call, timeout=60) as response:  # noqa: S310 - protected input
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify and clean a synthetic Assessment fixture")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--administration-id", required=True)
    parser.add_argument("--phase", required=True, choices=("campaign", "canary"))
    parser.add_argument("--browser-evidence", type=Path)
    parser.add_argument("--campaign-validation", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    headers = {
        "Cookie": os.environ["ASSESSMENT_ADMIN_COOKIE"],
        "X-CSRF-Token": os.environ["ASSESSMENT_ADMIN_CSRF"],
    }
    prefix = f"{args.base_url}/api/v2/admin/assessment/administrations/{args.administration_id}"
    close_status, _ = request("POST", f"{prefix}/close", headers)
    if close_status not in {200, 409}:
        raise RuntimeError(f"close failed with HTTP {close_status}")
    results_status, results_raw = request("GET", f"{prefix}/results?limit=1", headers)
    if results_status != 200:
        raise RuntimeError(f"results failed with HTTP {results_status}")
    results = json.loads(results_raw)
    expected_responses = 500 if args.phase == "campaign" else 1
    aggregate_verified = (
        results.get("summary", {}).get("responses") == expected_responses
        and results.get("individuals", {}).get("total") == expected_responses
    )
    export_status, export_raw = request("GET", f"{prefix}/export.csv", headers)
    export_verified = export_status == 200 and export_raw.count(b"\n") == expected_responses + 1
    purge: dict[str, Any] = {"status": "closed", "remaining": 1}
    while purge.get("status") != "purged":
        purge_status, purge_raw = request("POST", f"{prefix}/purge?batchSize=100", headers)
        if purge_status != 200:
            raise RuntimeError(f"purge failed with HTTP {purge_status}: {purge_raw[:200]!r}")
        purge = json.loads(purge_raw)
    cleanup_status, cleanup_raw = request("POST", f"{prefix}/synthetic-fixture/cleanup", headers)
    if cleanup_status != 200:
        raise RuntimeError(f"fixture cleanup failed with HTTP {cleanup_status}")
    cleanup = json.loads(cleanup_raw)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    validation = {"aggregateVerified": aggregate_verified, "exportVerified": export_verified}
    if args.phase == "campaign":
        (args.output_dir / "campaign-validation.json").write_text(
            json.dumps(validation, indent=2), encoding="utf-8"
        )
        (args.output_dir / "campaign-cleanup.json").write_text(
            json.dumps(cleanup, indent=2), encoding="utf-8"
        )
        return 0 if all(validation.values()) and all(cleanup.values()) else 1
    if args.browser_evidence is None or args.campaign_validation is None:
        raise RuntimeError("canary phase requires browser and campaign evidence")
    browser = json.loads(args.browser_evidence.read_text(encoding="utf-8"))
    campaign_validation = json.loads(args.campaign_validation.read_text(encoding="utf-8"))
    canaries = {**browser, **campaign_validation}
    campaign_cleanup_path = args.campaign_validation.with_name("campaign-cleanup.json")
    campaign_cleanup = json.loads(campaign_cleanup_path.read_text(encoding="utf-8"))
    combined_cleanup = {
        key: cleanup.get(key) is True and campaign_cleanup.get(key) is True for key in cleanup
    }
    (args.output_dir / "canaries.json").write_text(json.dumps(canaries, indent=2), encoding="utf-8")
    (args.output_dir / "cleanup.json").write_text(
        json.dumps(combined_cleanup, indent=2), encoding="utf-8"
    )
    return 0 if all(canaries.values()) and all(combined_cleanup.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
