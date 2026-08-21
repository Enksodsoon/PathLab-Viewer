#!/usr/bin/env python3
"""Create, encrypt, materialize, and reconcile run-owned capacity fixtures."""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import http.cookiejar
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

MAX_RESPONSE_BYTES = 2_000_000
MAX_COMMON_PER_LEVEL = 4
MAX_RANDOM_TOTAL = 256


class FixtureError(RuntimeError):
    pass


class Client:
    def __init__(self, base_url: str) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
            raise FixtureError("capacity base URL must be an HTTPS origin")
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.csrf = ""

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict[str, Any] | None = None,
        synthetic_run: str | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        if not path.startswith("/") or urllib.parse.urlsplit(path).netloc:
            raise FixtureError("fixture request escaped the approved origin")
        headers = {"Accept": "application/json, application/xml, image/jpeg"}
        payload = None
        if body is not None:
            payload = json.dumps(body, separators=(",", ":")).encode()
            headers["Content-Type"] = "application/json"
        if self.csrf and method not in {"GET", "HEAD"}:
            headers["X-CSRF-Token"] = self.csrf
        if synthetic_run is not None:
            headers["X-PathLab-Synthetic-Run"] = synthetic_run
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=payload, headers=headers, method=method
        )
        try:
            with self.opener.open(request, timeout=20) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
                if response.status not in expected:
                    raise FixtureError("capacity fixture endpoint returned an unexpected status")
        except urllib.error.HTTPError as error:
            if error.code in expected:
                raw = error.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise FixtureError(
                        "capacity fixture response exceeded its safety bound"
                    ) from error
                if not raw:
                    return None
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
            detail = error.read(4096).decode("utf-8", "replace")
            raise FixtureError(
                f"capacity fixture request failed ({error.code}): {detail}"
            ) from error
        except OSError as error:
            raise FixtureError("capacity fixture endpoint was unavailable") from error
        if len(raw) > MAX_RESPONSE_BYTES:
            raise FixtureError("capacity fixture response exceeded its safety bound")
        if not raw:
            return None
        content_type = response.headers.get_content_type()
        if content_type == "application/json":
            try:
                return json.loads(raw)
            except json.JSONDecodeError as error:
                raise FixtureError("capacity fixture JSON was malformed") from error
        return raw

    def login(self, username: str, password: str) -> None:
        result = self.request(
            "/api/v1/auth/session",
            method="POST",
            body={"username": username, "password": password},
            expected=(201,),
        )
        token = result.get("csrfToken") if isinstance(result, dict) else None
        if not isinstance(token, str) or len(token) < 32:
            raise FixtureError("capacity fixture login did not return a CSRF token")
        self.csrf = token


def _key(secret: str) -> bytes:
    if len(secret) < 32:
        raise FixtureError("deployment evidence key is too short")
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())


def _load_plan(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FixtureError("capacity plan was unavailable or malformed") from error
    required = {"runId", "workflowSha", "planDigest", "windowEndEpochMs", "stages"}
    if not isinstance(value, dict) or not required.issubset(value):
        raise FixtureError("capacity plan is incomplete")
    if not isinstance(value["stages"], list) or not value["stages"]:
        raise FixtureError("capacity plan has no stages")
    unsigned = {key: item for key, item in value.items() if key != "planDigest"}
    digest = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if not hmac.compare_digest(str(value["planDigest"]), digest):
        raise FixtureError("capacity plan digest is invalid")
    return value


def _tiles(slide: dict[str, Any], run_id: str) -> dict[str, Any]:
    descriptor = slide.get("tileSource")
    width, height = slide.get("width"), slide.get("height")
    tile_size, image_format = slide.get("tileSize"), slide.get("format")
    if (
        not isinstance(descriptor, str)
        or not descriptor.startswith("/tiles/")
        or not descriptor.endswith("/slide.dzi")
        or not all(isinstance(value, int) and value > 0 for value in (width, height, tile_size))
        or image_format not in {"jpg", "jpeg"}
    ):
        raise FixtureError("Classroom slide descriptor is not a supported static DZI")
    root = descriptor.removesuffix("slide.dzi")
    maximum = math.ceil(math.log2(max(width, height)))
    seed = int.from_bytes(hashlib.sha256(run_id.encode()).digest(), "big")
    common: list[str] = []
    random_tiles: list[str] = []
    for level in range(maximum, max(-1, maximum - 3), -1):
        divisor = 2 ** (maximum - level)
        columns = math.ceil(math.ceil(width / divisor) / tile_size)
        rows = math.ceil(math.ceil(height / divisor) / tile_size)
        coordinates = [(x, y) for x in range(columns) for y in range(rows)]
        coordinates.sort(
            key=lambda item: (
                (item[0] - (columns - 1) / 2) ** 2
                + (item[1] - (rows - 1) / 2) ** 2,
                item,
            )
        )
        common.extend(
            f"{root}slide_files/{level}/{x}_{y}.{image_format}"
            for x, y in coordinates[:MAX_COMMON_PER_LEVEL]
        )
        ranked = sorted(
            coordinates,
            key=lambda item: hashlib.sha256(
                f"{seed}:{level}:{item[0]}:{item[1]}".encode()
            ).digest(),
        )
        random_tiles.extend(
            f"{root}slide_files/{level}/{x}_{y}.{image_format}"
            for x, y in ranked[: max(1, MAX_RANDOM_TOTAL // 3)]
        )
    return {
        "descriptor": descriptor,
        "poster": f"{root}thumbnail.jpg",
        "commonTiles": common,
        "randomTiles": random_tiles[:MAX_RANDOM_TOTAL],
    }


def _write_private(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)


def create(args: argparse.Namespace) -> None:
    plan = _load_plan(args.plan)
    run_id = str(plan["runId"])
    if run_id != args.run_id:
        raise FixtureError("fixture run does not match the capacity plan")
    if plan.get("workflowSha") != args.workflow_sha:
        raise FixtureError("fixture release does not match the capacity plan")
    client = Client(args.base_url)
    client.login(args.username, args.password)
    existing = client.request("/api/v1/admin/classroom/sessions")
    sessions = existing.get("sessions") if isinstance(existing, dict) else None
    if not isinstance(sessions, list):
        raise FixtureError("Classroom inventory response is malformed")
    if sessions:
        raise FixtureError("refusing to create fixtures while a Classroom is active")
    created_id: str | None = None
    try:
        created = client.request(
            "/api/v1/admin/classroom/sessions",
            method="POST",
            body={"slideIds": [args.slide_id]},
            synthetic_run=run_id,
            expected=(201,),
        )
        if not isinstance(created, dict) or created.get("syntheticRunId") != run_id:
            raise FixtureError("created Classroom is not bound to this workflow run")
        created_id = str(created.get("id", ""))
        join_code = str(created.get("joinCode", ""))
        slides = created.get("slides")
        if (
            len(created_id) != 36
            or not join_code
            or not isinstance(slides, list)
            or len(slides) != 1
        ):
            raise FixtureError("created Classroom response is incomplete")
        media = _tiles(slides[0], run_id)
        paths = [
            media["descriptor"],
            media["poster"],
            media["commonTiles"][0],
            media["randomTiles"][0],
        ]
        for path in paths:
            client.request(path)
        stages = {
            str(stage["name"]): {
                "sessionId": created_id,
                "joinCode": join_code,
                "slideId": args.slide_id,
                "safetyNonce": hmac.new(
                    args.evidence_key.encode(), f"{run_id}:{stage['name']}".encode(), hashlib.sha256
                ).hexdigest(),
            }
            for stage in plan["stages"]
        }
        now = int(datetime.now(UTC).timestamp())
        bundle = {
            "schemaVersion": 1,
            "runId": run_id,
            "workflowSha": plan["workflowSha"],
            "planDigest": plan["planDigest"],
            "createdAtEpoch": now,
            "expiresAtEpoch": int(plan["windowEndEpochMs"] // 1000) + 3600,
            "classroom": {
                "sessionId": created_id,
                "syntheticRunId": run_id,
                "slideId": args.slide_id,
            },
            "stages": stages,
            "media": media,
            "sentinels": {
                "annotationSlideId": args.slide_id,
                "shareTargetId": args.slide_id,
                "dynamicPublicId": args.public_id,
            },
        }
        plaintext = json.dumps(bundle, separators=(",", ":"), sort_keys=True).encode()
        _write_private(args.output, Fernet(_key(args.evidence_key)).encrypt(plaintext))
    except Exception:
        if created_id is not None:
            with suppress(Exception):
                client.request(
                    f"/api/v1/admin/classroom/sessions/{created_id}",
                    method="DELETE",
                    synthetic_run=run_id,
                    expected=(204,),
                )
        raise


def decrypt_bundle(path: Path, evidence_key: str, run_id: str, workflow_sha: str) -> dict[str, Any]:
    try:
        plaintext = Fernet(_key(evidence_key)).decrypt(path.read_bytes())
        bundle = json.loads(plaintext)
    except (OSError, InvalidToken, json.JSONDecodeError) as error:
        raise FixtureError("private capacity fixture bundle is invalid") from error
    now = int(datetime.now(UTC).timestamp())
    if (
        bundle.get("schemaVersion") != 1
        or bundle.get("runId") != run_id
        or bundle.get("workflowSha") != workflow_sha
        or not isinstance(bundle.get("expiresAtEpoch"), int)
        or now > bundle["expiresAtEpoch"]
    ):
        raise FixtureError("private capacity fixture bundle is stale or cross-run")
    return bundle


def materialize(args: argparse.Namespace) -> None:
    bundle = decrypt_bundle(args.input, args.evidence_key, args.run_id, args.workflow_sha)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in (
        ("stage-manifest.json", bundle["stages"]),
        ("media-manifest.json", bundle["media"]),
        ("sentinels.json", bundle["sentinels"]),
        ("fixture-private.json", bundle),
    ):
        _write_private(
            args.output_dir / name,
            (json.dumps(value, separators=(",", ":"), sort_keys=True) + "\n").encode(),
        )


def cleanup(args: argparse.Namespace) -> None:
    bundle = decrypt_bundle(args.input, args.evidence_key, args.run_id, args.workflow_sha)
    client = Client(args.base_url)
    client.login(args.username, args.password)
    fixture = bundle["classroom"]
    state = client.request(
        f"/api/v1/admin/classroom/sessions/{fixture['sessionId']}", expected=(200, 404)
    )
    missing = (
        isinstance(state, dict)
        and state.get("detail", {}).get("code") == "CLASSROOM_NOT_FOUND"
    )
    if state is None or missing:
        return
    owner = state.get("session", {}).get("syntheticRunId") if isinstance(state, dict) else None
    if not hmac.compare_digest(str(owner or ""), args.run_id):
        raise FixtureError("refusing to remove a Classroom not owned by this workflow run")
    client.request(
        f"/api/v1/admin/classroom/sessions/{fixture['sessionId']}",
        method="DELETE",
        synthetic_run=args.run_id,
        expected=(204,),
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    commands = result.add_subparsers(dest="command", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--evidence-key", required=True)
    common.add_argument("--run-id", required=True)
    create_parser = commands.add_parser("create", parents=[common])
    create_parser.add_argument("--plan", type=Path, required=True)
    create_parser.add_argument("--workflow-sha", required=True)
    create_parser.add_argument("--base-url", required=True)
    create_parser.add_argument("--username", required=True)
    create_parser.add_argument("--password", required=True)
    create_parser.add_argument("--slide-id", required=True)
    create_parser.add_argument("--public-id", required=True)
    create_parser.add_argument("--output", type=Path, required=True)
    create_parser.set_defaults(handler=create)
    materialize_parser = commands.add_parser("materialize", parents=[common])
    materialize_parser.add_argument("--workflow-sha", required=True)
    materialize_parser.add_argument("--input", type=Path, required=True)
    materialize_parser.add_argument("--output-dir", type=Path, required=True)
    materialize_parser.set_defaults(handler=materialize)
    cleanup_parser = commands.add_parser("cleanup", parents=[common])
    cleanup_parser.add_argument("--workflow-sha", required=True)
    cleanup_parser.add_argument("--input", type=Path, required=True)
    cleanup_parser.add_argument("--base-url", required=True)
    cleanup_parser.add_argument("--username", required=True)
    cleanup_parser.add_argument("--password", required=True)
    cleanup_parser.set_defaults(handler=cleanup)
    return result


def main() -> None:
    args = parser().parse_args()
    args.handler(args)


if __name__ == "__main__":
    try:
        main()
    except FixtureError as error:
        raise SystemExit(str(error)) from error
