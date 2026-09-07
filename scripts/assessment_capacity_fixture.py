from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def call(
    method: str, url: str, headers: dict[str, str], payload: dict[str, Any] | None = None
) -> tuple[int, dict[str, Any]]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={**headers, **({"Content-Type": "application/json"} if data else {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - protected input
            return response.status, json.loads(response.read().decode() or "{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode() or "{}")


def require(status: int, payload: dict[str, Any], expected: set[int]) -> dict[str, Any]:
    if status not in expected:
        raise RuntimeError(f"unexpected HTTP {status}: {payload}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Provision an isolated synthetic Assessment fixture"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--host-observer-url", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--slide-id", required=True)
    parser.add_argument("--seats", type=int, choices=(1, 500), default=500)
    parser.add_argument("--prefix", default="capacity")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    headers = {
        "Cookie": os.environ["ASSESSMENT_ADMIN_COOKIE"],
        "X-CSRF-Token": os.environ["ASSESSMENT_ADMIN_CSRF"],
    }
    observer_headers = {"Authorization": f"Bearer {os.environ['ASSESSMENT_OBSERVER_TOKEN']}"}
    status, deployed = call("GET", args.host_observer_url, observer_headers)
    require(status, deployed, {200})
    if deployed.get("releaseSha") != args.release_sha:
        raise RuntimeError("protected target does not run the requested exact release")
    suffix = hashlib.sha256(f"{args.release_sha}:{args.prefix}".encode()).hexdigest()[:10]
    status, cohort = call(
        "POST",
        f"{args.base_url}/api/v2/admin/assessment/classes",
        headers,
        {"name": f"Assessment {args.prefix} {suffix}"},
    )
    require(status, cohort, {201})
    identifiers = (
        [f"shard-{shard}-student-{seat}" for shard in range(1, 6) for seat in range(1, 101)]
        if args.seats == 500
        else [f"{args.prefix}-student-1"]
    )
    rows = "\n".join(f"{identifier},{identifier}" for identifier in identifiers)
    import_url = f"{args.base_url}/api/v2/admin/assessment/classes/{cohort['id']}/import"
    status, preview = call("POST", f"{import_url}/preview", headers, {"rows": rows})
    require(status, preview, {200})
    status, committed = call(
        "POST",
        f"{import_url}/commit",
        headers,
        {"rows": rows, "checksum": preview["checksum"]},
    )
    require(status, committed, {201})
    document = {
        "title": f"Protected Assessment {args.prefix}",
        "settings": {"shuffleQuestions": False},
        "items": [
            {
                "id": "capacity-item-1",
                "type": "multiple-choice",
                "prompt": "Capacity fixture answer",
                "points": "1",
                "required": True,
                "options": [
                    {"id": "capacity-option-a", "label": "Accepted"},
                    {"id": "capacity-option-b", "label": "Alternative"},
                ],
                "answerKey": {"optionIds": ["capacity-option-a"]},
            },
            {
                "id": "capacity-static-dzi",
                "type": "diagnostic-field",
                "prompt": "Protected real static DZI",
                "points": "1",
                "required": False,
                "slideId": args.slide_id,
                "answerKey": {"regions": [{"kind": "point", "x": 0.5, "y": 0.5}]},
                "scoring": {"pointTolerance": 0.03, "rectangleIou": 0.25},
            },
        ],
    }
    status, draft = call(
        "POST",
        f"{args.base_url}/api/v2/admin/assessment/drafts",
        headers,
        {"title": document["title"], "document": document},
    )
    require(status, draft, {201})
    access_code = os.environ["ASSESSMENT_CAPACITY_ACCESS_CODE"]
    status, publication = call(
        "POST",
        f"{args.base_url}/api/v2/admin/assessment/drafts/{draft['id']}/publish",
        headers,
        {
            "mode": "formative",
            "cohortId": cohort["id"],
            "durationSeconds": 7200,
            "maxAttempts": 1,
            "accessCode": access_code,
            "syntheticFixture": True,
        },
    )
    require(status, publication, {201})
    administration_id = publication["administrationId"]
    prepare_url = (
        f"{args.base_url}/api/v2/admin/assessment/administrations/{administration_id}/prepare"
    )
    deadline = time.monotonic() + 180
    while True:
        status, prepared = call("POST", prepare_url, headers)
        if status == 200:
            break
        if status != 409 or time.monotonic() >= deadline:
            require(status, prepared, {200})
        time.sleep(10)
    status, opened = call("POST", prepare_url.replace("/prepare", "/open"), headers)
    require(status, opened, {200})
    public_id = publication["publicId"]
    status, metadata = call(
        "GET", f"{args.base_url}/api/v2/assessment/administrations/{public_id}", {}
    )
    require(status, metadata, {200})
    tile_path = metadata.get("assets", {}).get(args.slide_id)
    if not tile_path:
        raise RuntimeError("prepared administration did not expose the real static DZI grant")
    output = {
        "administrationId": administration_id,
        "publicId": public_id,
        "tileUrl": urllib.parse.urljoin(f"{args.base_url}/", tile_path.lstrip("/")),
        "identifier": identifiers[0],
        "releaseSha": args.release_sha,
        "seats": args.seats,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
