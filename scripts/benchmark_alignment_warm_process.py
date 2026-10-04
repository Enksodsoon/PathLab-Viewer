"""Separate resumable full16x9 same-process warm trials; never reinterpret old cold runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from wsi_viewer.alignment_benchmark import (
    _pair_settings,
    _private_output,
    _runtime_versions,
    pair_digest,
    validate_manifest,
)
from wsi_viewer.alignment_engines import ENGINE_ALIASES
from wsi_viewer.alignment_warm import WARM_PROTOCOL, _atomic_receipt, run_warm_bounded

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


def _summary(row: dict[str, Any]) -> dict[str, Any]:
    observations = []
    for invocation in row.get("invocations", []):
        result = invocation.get("result", {})
        registration = result.get("result", {}) if result.get("ok") is True else {}
        observations.append(
            {
                key: invocation.get(key)
                for key in (
                    "invocationOrdinal",
                    "childPid",
                    "processTemperature",
                    "retainedModelTemperature",
                    "invocationExecuted",
                    "invocationWallSeconds",
                    "grantedRemainingBudgetSeconds",
                    "artifactSha256",
                    "childStartupSeconds",
                )
            }
            | {
                "outcome": "ok" if result.get("ok") is True else "failed-or-missing",
                "failureType": result.get("type"),
                "mapStatus": registration.get("status"),
                "anatomicalReviewConfirmed": False,
            }
        )
    return {
        **{
            key: row.get(key)
            for key in (
                "pairIndex",
                "recipe",
                "digest",
                "protocol",
                "admissionSeconds",
                "supervisedTotalWallSeconds",
                "terminalContainmentVerified",
                "resourceMetrics",
                "historicalInterruptedAttempts",
            )
        },
        "invocations": observations,
    }


def campaign(
    manifest: dict[str, Any], output: Path, *, frozen_manifest_sha: str, source_head: str
) -> dict[str, Any]:
    validate_manifest(manifest, screening=True)
    _private_output(output.resolve())
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    protocol = {
        "policy": WARM_PROTOCOL,
        "sourceHead": source_head,
        "frozenManifestSha256": frozen_manifest_sha,
        "plannedInvocations": 2,
        "memoryBytes": 7 * 1024**3,
        "sharedTotalSeconds": 600,
        "runtimeIdentity": _runtime_versions(),
    }
    for pair_index, pair in enumerate(manifest["pairs"]):
        for recipe in RECIPES:
            admission_started = time.monotonic()
            inputs = pair.get("inputDigests")
            if (
                not isinstance(inputs, list)
                or len(inputs) != 2
                or any(not isinstance(value, str) or len(value) != 64 for value in inputs)
            ):
                raise ValueError("warm manifest requires two frozen admitted input digests")
            aliases = [key for key, value in ENGINE_ALIASES.items() if value == recipe]
            cohort = manifest.get("settings", {}).get(recipe)
            if cohort is None:
                cohort = next(
                    (
                        manifest.get("settings", {}).get(key)
                        for key in aliases
                        if key in manifest.get("settings", {})
                    ),
                    {},
                )
            settings = {**_pair_settings(pair, recipe, cohort), "timeoutSeconds": 600}
            digest = pair_digest(
                pair,
                recipe,
                settings,
                input_digests=inputs,
                settings_are_effective=True,
                execution_protocol=protocol,
            )
            cache = output / "cache" / f"{digest}.json"
            if cache.is_symlink():
                raise ValueError("warm cache symlink is unsupported")
            if cache.is_file():
                row = json.loads(cache.read_bytes())
                if (
                    row.get("digest") != digest
                    or row.get("protocol") != protocol
                    or row.get("pairIndex") != pair_index
                    or row.get("recipe") != recipe
                    or row.get("inputDigests") != inputs
                    or row.get("requestedSettings") != settings
                ):
                    raise ValueError("warm cached receipt differs from frozen protocol")
            else:
                admission_seconds = time.monotonic() - admission_started
                remaining = int(600 - admission_seconds)
                attempt_root = output / "artifacts" / digest
                attempt_root.mkdir(parents=True, exist_ok=True)
                number = len(list(attempt_root.glob("attempt-*"))) + 1
                artifact_dir = attempt_root / f"attempt-{number:04d}"
                admission_seconds = time.monotonic() - admission_started
                remaining = max(1, int(600 - admission_seconds))
                if remaining > 0:
                    result = run_warm_bounded(
                        Path(pair["reference"]["path"]),
                        Path(pair["moving"]["path"]),
                        tuple(pair["reference"]["size"]),
                        tuple(pair["moving"]["size"]),
                        recipe=recipe,
                        settings=settings,
                        artifact_dir=artifact_dir,
                        timeout_seconds=remaining,
                        input_digests=inputs,
                        absolute_deadline=admission_started + 600,
                    )
                else:
                    result = {
                        "plannedInvocations": 2,
                        "invocations": [
                            {
                                "invocationOrdinal": ordinal,
                                "invocationExecuted": False,
                                "result": {"ok": False, "type": "AdmissionBudgetExhausted"},
                            }
                            for ordinal in (1, 2)
                        ],
                        "supervisorFailure": {"type": "AdmissionBudgetExhausted"},
                        "terminalContainmentVerified": True,
                    }
                row = {
                    "pairIndex": pair_index,
                    "recipe": recipe,
                    "digest": digest,
                    "protocol": protocol,
                    "inputDigests": inputs,
                    "requestedSettings": settings,
                    "admissionSeconds": admission_seconds,
                    "historicalInterruptedAttempts": number - 1,
                    **result,
                }
                _atomic_receipt(cache, row)
            rows.append(_summary(row))
            _atomic_receipt(
                output / "progress.json",
                {
                    "plannedPairRecipes": 144,
                    "completedPairRecipes": len(rows),
                    "plannedInvocations": 288,
                    "currentPairIndex": pair_index,
                    "currentRecipe": recipe,
                    "registrationTemperatureScope": WARM_PROTOCOL,
                },
            )
    report = {
        "schema": WARM_PROTOCOL,
        "rows": rows,
        "plannedPairRecipes": 144,
        "completedPairRecipes": len(rows),
        "plannedInvocations": 288,
        "retainedModelWarmSeconds": None,
        "qualified": False,
        "queueSeconds": None,
        "browserApplicationSeconds": None,
    }
    _atomic_receipt(output / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    checkout = Path(__file__).resolve().parents[1]
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, check=True, text=True, capture_output=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=checkout, check=True, capture_output=True
    ).stdout
    if head != args.expected_head or status:
        raise ValueError("warm campaign requires exact clean reviewed source freeze")
    content = args.manifest.read_bytes()
    if hashlib.sha256(content).hexdigest() != args.manifest_sha256:
        raise ValueError("warm manifest differs from frozen admission")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    lock = args.output_dir / "controller-active.lock"
    with lock.open("x", encoding="utf-8") as owner:
        owner.write(str(os.getpid()))
    try:
        report = campaign(
            json.loads(content),
            args.output_dir,
            frozen_manifest_sha=args.manifest_sha256,
            source_head=head,
        )
    finally:
        if lock.read_text() != str(os.getpid()):
            raise RuntimeError("warm controller lock ownership changed")
        lock.unlink()
    print(json.dumps({"completedPairRecipes": len(report["rows"]), "qualified": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
