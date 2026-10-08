"""Rescore immutable cold receipts without registration, fitting or status changes.

The new analysis is separate from original scores. Only explicit usable support
cells are measured; viewer viewport gap snaps and affine-only navigation are out
of scope. Public output contains digests and aggregate errors, never coordinates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from report_alignment_campaign import hybrid_comparisons, pair_landmarks, stage_metrics
from wsi_viewer import alignment_evaluation
from wsi_viewer.alignment_engines import MAX_INITIALIZER_ARTIFACT_BYTES
from wsi_viewer.alignment_evaluation import SUPPORT_MAPPING_POLICY, evaluate_landmarks

MAX_RECEIPT_BYTES = 64 * 1024 * 1024


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _read(
    path: Path, bindings: dict[Path, tuple[str, int]], *, max_bytes: int = MAX_RECEIPT_BYTES
) -> bytes:
    if any(parent.is_symlink() or parent.is_junction() for parent in (path, *path.parents)):
        raise ValueError("symlink input is unsupported")
    if path.stat().st_size > max_bytes:
        raise ValueError("input exceeds receipt ceiling")
    with path.open("rb") as source:
        content = source.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("input exceeds receipt ceiling")
    bindings[path] = (_sha(content), max_bytes)
    return content


def rescore(root: Path, manifest_path: Path, expected_manifest_sha: str) -> dict[str, Any]:
    """Bind report order, receipt metadata, map bytes and fit-free GT before scoring."""
    bindings: dict[Path, tuple[str, int]] = {}
    checkout = Path(__file__).resolve().parents[1]
    source_paths = [
        Path(__file__).resolve(),
        Path(__file__).with_name("report_alignment_campaign.py"),
        *(
            checkout / "server/wsi_viewer" / name
            for name in (
                "alignment_evaluation.py",
                "alignment.py",
                "alignment_benchmark.py",
                "alignment_engines.py",
            )
        ),
    ]
    source_hashes = {
        str(path.relative_to(checkout)).replace("\\", "/"): _sha(path.read_bytes())
        for path in source_paths
    }
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=checkout, check=True, capture_output=True, text=True
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=checkout, check=True, capture_output=True
    ).stdout
    manifest_bytes = _read(manifest_path, bindings)
    if _sha(manifest_bytes) != expected_manifest_sha:
        raise ValueError("manifest does not match admitted frozen bytes")
    manifest = json.loads(manifest_bytes)
    report_bytes = _read(root / "report.json", bindings)
    original = json.loads(report_bytes)
    rescored = json.loads(report_bytes)
    rows = []
    by_recipe: dict[str, list[dict[str, Any]]] = {}
    seen = set()
    for index, row in enumerate(original["rows"]):
        digest = row["digest"]
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("unsafe receipt digest")
        pair_index = row["pairIndex"]
        identity = (pair_index, row["recipe"])
        if type(pair_index) is not int or not 0 <= pair_index < len(manifest["pairs"]):
            raise ValueError("invalid frozen pair ordinal")
        if identity in seen:
            raise ValueError("duplicate planned recipe/pair receipt")
        seen.add(identity)
        receipt_bytes = _read(root / "cache" / f"{digest}.json", bindings)
        receipt = json.loads(receipt_bytes)
        for key in (
            "digest",
            "recipe",
            "outcome",
            "settingsDigest",
            "inputDigests",
            "engineBuild",
            "runtimeVersions",
        ):
            if key not in row or receipt.get(key) != row[key]:
                raise ValueError(f"receipt binding differs: {key}")
        pair = manifest["pairs"][pair_index]
        if pair.get("landmarks") and (
            pair.get("independentlyReviewed") is not True
            or pair.get("landmarksFitFree") is not True
        ):
            raise ValueError("ground truth must be independently reviewed and fit-free")
        landmarks = cast(Callable[..., list[dict[str, Any]]], pair_landmarks)(
            pair, manifest, row["recipe"]
        )
        registration = receipt.get("registration") or {}
        if not isinstance(registration, dict):
            raise ValueError("invalid saved map")
        # An error/rejection cannot borrow an accidentally retained partial map.
        scoring_map = registration if row["outcome"] == "ok" else {}
        records = [{**landmark, "registration": scoring_map} for landmark in landmarks]
        metrics = evaluate_landmarks(records, measure_approximate=True)
        strict_metrics = evaluate_landmarks(records)
        by_recipe.setdefault(row["recipe"], []).extend(records)
        rescored["rows"][index]["landmarkMetrics"] = metrics
        stage = None
        descriptor = registration.get("initializerArtifact")
        if row["outcome"] == "ok" and isinstance(descriptor, dict):
            # Only the descriptor-bound initializer is admissible as stage evidence.
            name = descriptor.get("name")
            if not isinstance(name, str) or Path(name).name != name or "/" in name or "\\" in name:
                raise ValueError("unsafe initializer basename")
            sidecar = root / "artifacts" / digest / name
            sidecar_bytes = _read(sidecar, bindings, max_bytes=MAX_INITIALIZER_ARTIFACT_BYTES)
            if _sha(sidecar_bytes) != descriptor.get("sha256"):
                raise ValueError("initializer differs from saved map provenance")
            stage = cast(Callable[..., dict[str, Any] | None], stage_metrics)(
                root, row, pair, manifest
            )
        rows.append(
            {
                "pairIndex": pair_index,
                "recipe": row["recipe"],
                "outcome": row["outcome"],
                "registrationDigest": digest,
                "receiptSha256": _sha(receipt_bytes),
                "coordinateMapSha256": _sha(_canonical(registration)),
                "groundTruthSha256": _sha(_canonical(landmarks)),
                "inputDigests": row["inputDigests"],
                "settingsDigest": row["settingsDigest"],
                "mapStatusUnchanged": registration.get("status"),
                "originalLandmarkMetrics": row.get("landmarkMetrics"),
                "pointwiseMetrics": metrics,
                "strictReadyLocalMetrics": strict_metrics,
                "stageContribution": stage,
                "qualificationEvidence": False,
            }
        )
    aggregate = {
        recipe: evaluate_landmarks(records, measure_approximate=True)
        for recipe, records in by_recipe.items()
    }
    # This analysis supplies measurements, not reviewed promotion or new winners.
    for value in [
        *aggregate.values(),
        *(row["pointwiseMetrics"] for row in rows),
        *(row["strictReadyLocalMetrics"] for row in rows),
    ]:
        value["wrongStructureMatches"] = None
        value["anatomicalReviewScope"] = (
            "map-specific anatomical review not inferred from landmark input flags"
        )
        if value["eligibleLandmarks"] == 0:
            for key in ("coverage", "observedCoverage", "calibratedCoverage"):
                value[key] = None
    comparisons = cast(Callable[..., list[dict[str, Any]]], hybrid_comparisons)(
        rescored, root, manifest
    )
    for path, (expected, max_bytes) in bindings.items():
        if _sha(_read(path, {}, max_bytes=max_bytes)) != expected:
            raise ValueError("original artifact changed during posthoc scoring")
    if any(
        _sha(path.read_bytes()) != source_hashes[str(path.relative_to(checkout)).replace("\\", "/")]
        for path in source_paths
    ):
        raise ValueError("effective analysis source changed during scoring")
    evaluator_path = Path(alignment_evaluation.__file__)
    reporter_path = Path(__file__).with_name("report_alignment_campaign.py")
    return {
        "schema": "pathlab-posthoc-supported-cell-rescoring/1",
        "originalReportSha256": _sha(report_bytes),
        "startupGitHead": head,
        "startupGitDirty": bool(status),
        "startupGitStatusSha256": _sha(status),
        "startupEffectiveSourceHashes": source_hashes,
        "effectiveAnalysisSourceUnchanged": True,
        "codeIdentityScope": (
            "actual module bytes; startup commit alone does not include dirty changes"
        ),
        "frozenManifestSha256": expected_manifest_sha,
        "evaluatorSourceSha256": _sha(evaluator_path.read_bytes()),
        "reporterSourceSha256": _sha(reporter_path.read_bytes()),
        "analysisScriptSha256": _sha(Path(__file__).read_bytes()),
        "supportMappingPolicy": SUPPORT_MAPPING_POLICY,
        "scope": (
            "explicit supported cells only; excludes viewport gap snaps and affine-only navigation"
        ),
        "registrationReruns": 0,
        "fitPerformed": False,
        "statusPromotionPerformed": False,
        "originalArtifactsUnchanged": True,
        "qualificationEvidence": False,
        "cohortScope": "preserved public development screening; not a disjoint final evaluation",
        "recipeMetrics": aggregate,
        "rows": rows,
        "hybridComparisons": comparisons,
        "artifactSetSha256": _sha(_canonical(sorted(digest for digest, _ in bindings.values()))),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("posthoc output must be a new artifact")
    result = rescore(args.directory.resolve(), args.manifest.resolve(), args.manifest_sha256)
    content = json.dumps(result, sort_keys=True, indent=2, allow_nan=False).encode()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        output.write(content)
    print(
        json.dumps(
            {
                "rows": len(result["rows"]),
                "analysisSha256": _sha(content),
                "originalArtifactsUnchanged": True,
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
