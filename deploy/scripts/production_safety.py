#!/usr/bin/env python3
"""Authenticated, fail-closed production evidence and capacity decisions."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FINAL_LIMITS = {300, 1200, 1500}
EGRESS_LIMIT_BYTES = 9_000_000_000_000
MAX_EVIDENCE_LIFETIME_SECONDS = 900
EXPECTED_REPOSITORY = "Enksodsoon/PathLab-Viewer"


class GuardFailure(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardFailure(message)


def _mapping(value: object, label: str) -> dict[str, Any]:
    _require(isinstance(value, dict), f"{label} evidence is missing or invalid")
    return cast(dict[str, Any], value)


def _canonical_bytes(evidence: dict[str, Any]) -> bytes:
    return json.dumps(
        evidence, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sign_evidence(evidence: dict[str, Any], key: bytes) -> str:
    _require(len(key) >= 32, "deployment evidence key is too short")
    return hmac.new(key, _canonical_bytes(evidence), hashlib.sha256).hexdigest()


def validate(evidence: dict[str, Any], candidate_sha: str) -> None:
    _require(evidence.get("schemaVersion") == 2, "deployment evidence schema is invalid")
    _require(SHA_PATTERN.fullmatch(candidate_sha) is not None, "candidate SHA is invalid")
    _require(evidence.get("candidateSha") == candidate_sha, "candidate SHA evidence mismatch")
    _require(evidence.get("repository") == EXPECTED_REPOSITORY, "repository evidence mismatch")
    _require(
        isinstance(evidence.get("workflowRunId"), str) and evidence["workflowRunId"].isdigit(),
        "workflow run evidence is invalid",
    )

    for group_name, names in (
        ("ci", {"backend", "browser", "web", "containers"}),
        (
            "security",
            {"repository-and-dependencies", "CodeQL (python)", "CodeQL (javascript-typescript)"},
        ),
    ):
        group = _mapping(evidence.get(group_name), group_name)
        _require(group.get("sha") == candidate_sha, f"{group_name} SHA mismatch")
        checks = _mapping(group.get("required"), f"{group_name}.required")
        _require(set(checks) == names, f"{group_name} required checks are incomplete")
        for name in names:
            check = _mapping(checks[name], f"{group_name}.{name}")
            _require(check.get("conclusion") == "success", f"{group_name} failed")
            _require(
                isinstance(check.get("runId"), int)
                and not isinstance(check["runId"], bool)
                and check["runId"] > 0,
                f"{group_name} run ID is invalid",
            )

    fixtures = _mapping(evidence.get("fixtures"), "fixtures")
    _require(fixtures.get("syntheticOnly") is True, "fixtures are not synthetic-only")
    annotations = _mapping(evidence.get("annotations"), "annotations")
    _require(annotations.get("enabled") is False, "annotations must remain disabled")
    egress = _mapping(evidence.get("egress"), "egress")
    projected = egress.get("projectedMonthlyBytes")
    _require(
        isinstance(projected, int)
        and not isinstance(projected, bool)
        and 0 <= projected < EGRESS_LIMIT_BYTES,
        "projected monthly egress must be below 9 TB",
    )
    cost = _mapping(evidence.get("cost"), "cost")
    _require(cost.get("currency") == "SGD", "cost currency must be SGD")
    amount = cost.get("monthToDate")
    _require(
        isinstance(amount, (int, float)) and not isinstance(amount, bool) and amount == 0,
        "OCI month-to-date cost must be SGD 0",
    )


def validate_signed(
    evidence: dict[str, Any],
    candidate_sha: str,
    signature: str,
    key: bytes,
    *,
    now: int,
    expected_nonce: str,
) -> None:
    _require(DIGEST_PATTERN.fullmatch(signature) is not None, "evidence signature is invalid")
    _require(
        hmac.compare_digest(signature, sign_evidence(evidence, key)),
        "evidence signature verification failed",
    )
    issued = evidence.get("issuedAt")
    expires = evidence.get("expiresAt")
    _require(
        isinstance(issued, int)
        and not isinstance(issued, bool)
        and isinstance(expires, int)
        and not isinstance(expires, bool)
        and issued <= now <= expires
        and 0 < expires - issued <= MAX_EVIDENCE_LIFETIME_SECONDS,
        "deployment evidence is stale or has an invalid lifetime",
    )
    _require(evidence.get("nonce") == expected_nonce, "deployment evidence nonce mismatch")
    validate(evidence, candidate_sha)


def _set_capacity(env_file: Path, limit: int) -> None:
    lines = env_file.read_text(encoding="utf-8").splitlines()
    key = "PATHLAB_CLASSROOM_MAX_PARTICIPANTS="
    output: list[str] = []
    replaced = False
    for line in lines:
        if line.startswith(key):
            if not replaced:
                output.append(f"{key}{limit}")
                replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{key}{limit}")
    temporary = env_file.with_suffix(env_file.suffix + ".tmp")
    temporary.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.chmod(temporary, env_file.stat().st_mode & 0o777)
    temporary.replace(env_file)


def _read_capacity(env_file: Path) -> int:
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("PATHLAB_CLASSROOM_MAX_PARTICIPANTS="):
            value = line.split("=", 1)[1]
            _require(value.isdigit(), "existing Classroom capacity is invalid")
            limit = int(value)
            _require(1 <= limit <= 2000, "existing Classroom capacity is out of range")
            return limit
    return 300


def select_final_capacity(
    certification: dict[str, Any],
    *,
    expected_sha: str,
    expected_run_id: str,
    expected_nonce: str,
    not_before: int,
) -> int:
    _require(certification.get("schemaVersion") == 2, "capacity evidence schema is invalid")
    _require(certification.get("candidateSha") == expected_sha, "capacity SHA mismatch")
    _require(certification.get("runId") == expected_run_id, "capacity run ID mismatch")
    _require(certification.get("nonce") == expected_nonce, "capacity nonce mismatch")
    # An authenticated explicit failure decision may only lower capacity. It
    # deliberately carries no invented timing, preflight, cleanup, or hold proof.
    if certification.get("verdict") == "NOT CERTIFIED":
        _require(certification.get("selectedCapacity") == 300, "failure decision must select 300")
        digest = certification.get("evidenceDigest")
        _require(
            isinstance(digest, str) and DIGEST_PATTERN.fullmatch(digest) is not None,
            "capacity aggregate evidence digest is invalid",
        )
        stages = _mapping(certification.get("strictStages"), "strictStages")
        _require(set(stages) == {"1200", "1500"}, "strict capacity stages are incomplete")
        for name in ("1200", "1500"):
            stage = _mapping(stages[name], f"strictStages.{name}")
            _require(
                stage.get("passed") is False and stage.get("durationSeconds") == 0,
                "failure decision must not claim a strict hold",
            )
        _require(
            certification.get("withinAuthorizedIctWindow") is False,
            "failure decision invented window proof",
        )
        _require(
            certification.get("allPreflightGatesPassed") is False,
            "failure decision invented preflight proof",
        )
        _require(
            certification.get("fixtureCleanupSucceeded") is False,
            "failure decision invented cleanup proof",
        )
        results = _mapping(certification.get("stageResults"), "stageResults")
        _require(
            results.get("certification-1200") == {"durationSeconds": 0, "status": "failed"},
            "failure decision must record the failed strict gate",
        )
        return 300
    started = certification.get("startedAt")
    completed = certification.get("completedAt")
    _require(
        isinstance(started, int)
        and not isinstance(started, bool)
        and isinstance(completed, int)
        and not isinstance(completed, bool)
        and not_before <= started <= completed,
        "capacity evidence timing is invalid or stale",
    )
    assert isinstance(started, int)
    assert isinstance(completed, int)
    authorized_start = certification.get("authorizedWindowStart")
    authorized_end = certification.get("authorizedWindowEnd")
    _require(
        isinstance(authorized_start, int)
        and not isinstance(authorized_start, bool)
        and isinstance(authorized_end, int)
        and not isinstance(authorized_end, bool)
        and authorized_end - authorized_start == 3 * 3600
        and authorized_start <= started <= completed <= authorized_end,
        "capacity run was outside the authorized capacity window",
    )
    _require(
        certification.get("withinAuthorizedIctWindow") is True,
        "capacity window evidence failed",
    )
    _require(
        certification.get("allPreflightGatesPassed") is True,
        "capacity preflight evidence failed",
    )
    fixture_cleanup = certification.get("fixtureCleanupSucceeded")
    if not isinstance(fixture_cleanup, bool):
        raise GuardFailure("capacity fixture cleanup evidence is invalid")
    digest = certification.get("evidenceDigest")
    _require(
        isinstance(digest, str) and DIGEST_PATTERN.fullmatch(digest) is not None,
        "capacity aggregate evidence digest is invalid",
    )
    stages = _mapping(certification.get("strictStages"), "strictStages")
    _require(set(stages) == {"1200", "1500"}, "strict capacity stages are incomplete")
    stage_1200 = _mapping(stages["1200"], "strictStages.1200")
    stage_1500 = _mapping(stages["1500"], "strictStages.1500")
    _require(stage_1200.get("durationSeconds") == 3600, "1200 strict hold is incomplete")
    _require(stage_1500.get("durationSeconds") == 600, "1500 strict hold is incomplete")
    strict_1200 = stage_1200.get("passed")
    strict_1500 = stage_1500.get("passed")
    if not isinstance(strict_1200, bool) or not isinstance(strict_1500, bool):
        raise GuardFailure("strict capacity decisions must be booleans")
    _require(strict_1500 is False or strict_1200 is True, "1500 cannot pass when 1200 failed")
    _require(not strict_1200 or fixture_cleanup, "capacity synthetic fixture cleanup failed")
    stage_results = _mapping(certification.get("stageResults"), "stageResults")
    expected_stages = {
        "smoke-2": 0,
        "smoke-100": 0,
        "boundary-300": 600,
        "boundary-600": 600,
        "boundary-900": 600,
        "certification-1200": 3600,
        "headroom-1500": 600,
        "stress-1750": 300,
        "stress-2000": 300,
        "recovery-1200": 0,
    }
    _require(set(stage_results) == set(expected_stages), "capacity stage results are incomplete")
    for name, duration in expected_stages.items():
        stage = _mapping(stage_results[name], f"stageResults.{name}")
        _require(set(stage) == {"durationSeconds", "status"}, f"{name} result is invalid")
        actual_duration = stage.get("durationSeconds")
        _require(
            isinstance(actual_duration, int)
            and not isinstance(actual_duration, bool)
            and actual_duration >= 0,
            f"{name} duration is incomplete",
        )
        assert isinstance(actual_duration, int)
        allowed = (
            {"passed"}
            if strict_1200 and name.startswith(("smoke-", "boundary-"))
            else {"passed", "failed", "early-stopped", "skipped"}
        )
        _require(stage.get("status") in allowed, f"{name} did not pass its required gate")
        if stage.get("status") == "passed":
            _require(actual_duration >= duration, f"{name} duration is incomplete")
    sentinels = _mapping(certification.get("functionalSentinels"), "functionalSentinels")
    _require(
        set(sentinels)
        == {"uploadConversion", "annotations", "libraryShare", "dynamicViewer", "desktop"}
        and all(isinstance(value, bool) for value in sentinels.values()),
        "functional sentinels are incomplete",
    )
    _require(
        stage_results["certification-1200"].get("status")
        == ("passed" if strict_1200 else "failed"),
        "1200 decision is inconsistent",
    )
    expected_headroom = "passed" if strict_1500 else ("failed" if strict_1200 else "skipped")
    _require(
        stage_results["headroom-1500"].get("status") == expected_headroom,
        "1500 decision is inconsistent",
    )
    _require(
        stage_results["recovery-1200"].get("status") == ("passed" if strict_1200 else "skipped"),
        "recovery decision is inconsistent",
    )
    _require(
        not strict_1200 or all(value is True for value in sentinels.values()),
        "functional sentinels did not pass",
    )
    if strict_1500:
        return 1500
    if strict_1200:
        return 1200
    return 300


@contextmanager
def capacity_override(env_file: Path, temporary_limit: int = 2000) -> Iterator[Any]:
    _require(temporary_limit == 2000, "protected temporary capacity must be 2000")
    prior = _read_capacity(env_file)
    selected: int | None = None

    def restore(final_limit: int) -> None:
        nonlocal selected
        _require(final_limit in FINAL_LIMITS, "final capacity lacks strict evidence tier")
        selected = final_limit

    _set_capacity(env_file, temporary_limit)
    try:
        yield restore
    finally:
        _set_capacity(env_file, selected if selected is not None else prior)


def _load_evidence(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GuardFailure("deployment evidence is missing or invalid") from error
    return _mapping(value, "deployment")


def _load_protected_key(path: Path) -> bytes:
    _require(
        path == Path("/etc/pathlab-viewer/deploy-evidence.key"),
        "evidence key path is invalid",
    )
    try:
        metadata = path.lstat()
    except OSError as error:
        raise GuardFailure("deployment evidence key is unavailable") from error
    _require(not stat.S_ISLNK(metadata.st_mode), "deployment evidence key must not be a symlink")
    _require(metadata.st_uid == 0, "deployment evidence key must be root-owned")
    _require(stat.S_IMODE(metadata.st_mode) == 0o600, "deployment evidence key mode must be 0600")
    return path.read_bytes().strip()


def validate_annotation_activation(evidence: dict[str, Any], signature: str, key: bytes) -> int:
    _require(
        DIGEST_PATTERN.fullmatch(signature) is not None
        and hmac.compare_digest(signature, sign_evidence(evidence, key)),
        "annotation activation signature verification failed",
    )
    certification = _mapping(evidence.get("certification"), "certification")
    candidate_sha = certification.get("candidateSha")
    run_id = certification.get("runId")
    nonce = certification.get("nonce")
    not_before = certification.get("authorizedWindowStart")
    _require(isinstance(candidate_sha, str), "annotation activation SHA is invalid")
    _require(isinstance(run_id, str), "annotation activation run is invalid")
    _require(isinstance(nonce, str), "annotation activation nonce is invalid")
    _require(isinstance(not_before, int), "annotation activation window is invalid")
    selected = select_final_capacity(
        certification,
        expected_sha=candidate_sha,
        expected_run_id=run_id,
        expected_nonce=nonce,
        not_before=not_before,
    )
    sentinels = _mapping(certification.get("functionalSentinels"), "functionalSentinels")
    _require(selected in {1200, 1500}, "annotations require a strict 1200-seat certification")
    _require(sentinels.get("annotations") is True, "annotation sentinel did not pass")
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase", choices=("preflight", "capacity-decision", "annotation-activation")
    )
    parser.add_argument("evidence", type=Path)
    parser.add_argument("candidate_sha", nargs="?")
    parser.add_argument("--signature")
    parser.add_argument("--nonce")
    parser.add_argument("--run-id")
    parser.add_argument("--not-before", type=int)
    parser.add_argument(
        "--key-file", type=Path, default=Path("/etc/pathlab-viewer/deploy-evidence.key")
    )
    args = parser.parse_args()
    try:
        evidence = _load_evidence(args.evidence)
        if args.phase == "annotation-activation":
            _require(args.signature is not None, "annotation activation signature is required")
            print(
                validate_annotation_activation(
                    evidence, args.signature, _load_protected_key(args.key_file)
                )
            )
            return 0
        if args.phase == "capacity-decision":
            _require(args.candidate_sha is not None, "candidate SHA is required")
            _require(args.run_id is not None, "capacity run ID is required")
            _require(args.nonce is not None, "capacity nonce is required")
            _require(args.not_before is not None, "capacity start time is required")
            _require(args.signature is not None, "capacity evidence signature is required")
            _require(
                DIGEST_PATTERN.fullmatch(args.signature) is not None
                and hmac.compare_digest(
                    args.signature,
                    sign_evidence(evidence, _load_protected_key(args.key_file)),
                ),
                "capacity evidence signature verification failed",
            )
            print(
                select_final_capacity(
                    _mapping(evidence.get("certification"), "certification"),
                    expected_sha=args.candidate_sha,
                    expected_run_id=args.run_id,
                    expected_nonce=args.nonce,
                    not_before=args.not_before,
                )
            )
            return 0
        _require(args.candidate_sha is not None, "candidate SHA is required")
        _require(args.signature is not None, "deployment evidence signature is required")
        _require(args.nonce is not None, "deployment evidence nonce is required")
        validate_signed(
            evidence,
            args.candidate_sha,
            args.signature,
            _load_protected_key(args.key_file),
            now=int(datetime.now(UTC).timestamp()),
            expected_nonce=args.nonce,
        )
    except (GuardFailure, ValueError) as error:
        print(f"Deployment guard failed: {error}", file=sys.stderr)
        return 1
    print(f"Deployment preflight guards passed for {args.candidate_sha}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
