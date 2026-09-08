"""Collect operator-produced regional measurements through the protected observer."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

MAX_BYTES = 2 * 1024 * 1024
ARTIFACTS = {*(f"shard-{index}.json" for index in range(1, 6)), "observer.json"}


def validate_bundle(
    value: dict[str, Any], *, run_id: str, release_sha: str,
    administration_id: str, public_id: str, start_epoch: int,
) -> dict[str, dict[str, Any]]:
    expected = {
        "runId": run_id, "releaseSha": release_sha,
        "administrationId": administration_id, "startEpoch": start_epoch,
        "publicId": public_id,
        "clientRegion": "southeast-asia",
    }
    if set(value) != {*expected, "artifacts"} or any(
        value.get(key) != item for key, item in expected.items()
    ):
        raise ValueError("regional campaign identity does not match the protected run")
    artifacts = value["artifacts"]
    if not isinstance(artifacts, dict) or set(artifacts) != ARTIFACTS:
        raise ValueError("exactly five shards and one observer artifact are required")
    if any(not isinstance(item, dict) for item in artifacts.values()):
        raise ValueError("regional artifact must be an object")
    for index in range(1, 6):
        shard = artifacts[f"shard-{index}.json"]
        if any(shard.get(key) != item for key, item in {
            "shard": index, "seats": 100, "autosavesPerSeat": 20,
            "reconnectPercent": 10, "holdSeconds": 3600, "exactRelease": release_sha,
            "publicId": public_id, "startEpoch": start_epoch,
        }.items()) or shard.get("diagnosticOnly"):
            raise ValueError("regional shard is not the exact full-hour workload")
    if any(artifacts["observer.json"].get(key) != expected for key, expected in {
        "releaseSha": release_sha, "administrationId": administration_id,
        "startEpoch": start_epoch,
    }.items()):
        raise ValueError("regional observer campaign mismatch")
    # Negative measurements are retained. The normal final evaluator decides every gate.
    return artifacts


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("regional evidence endpoint must not redirect")


def fetch_bundle(url: str, token: str) -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise ValueError("regional endpoint did not return JSON evidence")
            payload = response.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError("regional evidence exceeds the transfer bound")
        value = json.loads(payload)
        if not isinstance(value, dict):
            raise ValueError("regional evidence must be an object")
        return value
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--observer-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--administration-id", required=True)
    parser.add_argument("--public-id", required=True)
    parser.add_argument("--start-epoch", required=True, type=int)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.observer_url)
    if (
        parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password
        or parsed.query or parsed.fragment or not parsed.path.endswith("/sample")
        or not re.fullmatch(r"[1-9][0-9]{0,19}", args.run_id)
        or not re.fullmatch(r"[0-9a-f]{40}", args.release_sha)
    ):
        raise ValueError("protected HTTPS observer and exact run/release identity required")
    url = args.observer_url.removesuffix("/sample") + "/regional/" + args.run_id
    deadline = time.monotonic() + 4800
    while time.monotonic() < deadline:
        value = fetch_bundle(url, os.environ["ASSESSMENT_OBSERVER_TOKEN"])
        if value is not None:
            artifacts = validate_bundle(
                value, run_id=args.run_id, release_sha=args.release_sha,
                administration_id=args.administration_id, start_epoch=args.start_epoch,
                public_id=args.public_id,
            )
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for name, artifact in artifacts.items():
                (args.output_dir / name).write_text(
                    json.dumps(artifact, allow_nan=False), encoding="utf-8",
                )
            provenance = {key: item for key, item in value.items() if key != "artifacts"}
            (args.output_dir / "regional-provenance.json").write_text(
                json.dumps(provenance), encoding="utf-8",
            )
            print("Regional measurements collected; capacity gates remain unevaluated.")
            return 0
        time.sleep(15)
    raise RuntimeError("regional measurements were not supplied before the bounded deadline")


if __name__ == "__main__":
    raise SystemExit(main())
