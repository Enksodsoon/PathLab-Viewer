"""Private, resumable engine benchmark with fit-free evaluation and honest timing."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import subprocess
import time
from collections import Counter
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .alignment import AlignmentRejected
from .alignment_engines import (
    ENGINE_ALIASES,
    ENGINE_VERSIONS,
    SUPPORTED_ENGINES,
    engine_availability,
    engine_resource_availability,
    settings_digest,
)
from .alignment_evaluation import evaluate_landmarks
from .worker import _load_alignment_overview, _run_alignment_bounded

BENCHMARK_VERSION = "pathlab-alignment-benchmark/1"


def _progress_recorder(
    events: list[dict[str, Any]], started: float
) -> Callable[[dict[str, Any]], None]:
    def record(event: dict[str, Any]) -> None:
        events.append({"stage": event.get("stage"), "elapsedSeconds": time.monotonic() - started})

    return record


def _private_output(output: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    if output.is_relative_to(repository):
        checked = subprocess.run(
            ["git", "check-ignore", "-q", str(output)],
            cwd=repository,
            capture_output=True,
            check=False,
        )
        if checked.returncode != 0:
            raise ValueError(
                "private benchmark output must be outside the repository or git-ignored"
            )


def _visual_qa_pair(pair: dict[str, Any], registration: dict[str, Any], output: Path) -> bool:
    """Original images with corresponding mesh outlines; no fit-landmark overlays."""
    try:
        canvas = Image.new("RGB", (1024, 550), "white")
        drawing = ImageDraw.Draw(canvas)
        cells = registration.get("triangles") or registration.get("overviewTriangles") or []
        stride = max(1, (len(cells) + 95) // 96)
        for offset, side, coordinate in ((0, "reference", "reference"), (512, "moving", "moving")):
            image = _load_alignment_overview(Path(pair[side]["path"]))
            image.thumbnail((512, 512))
            canvas.paste(image, (offset, 30))
            sx, sy = image.width / pair[side]["size"][0], image.height / pair[side]["size"][1]
            for cell in cells[::stride]:
                drawing.polygon(
                    [(offset + point[0] * sx, 30 + point[1] * sy) for point in cell[coordinate]],
                    outline=(30, 130, 180),
                )
            drawing.text(
                (offset + 8, 8),
                f"{side}: original pixels; {registration.get('status')}",
                fill=(20, 20, 20),
            )
        output.parent.mkdir(parents=True, exist_ok=True)
        canvas.save(output)
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False


def validate_manifest(manifest: dict[str, Any], *, screening: bool = False) -> None:
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("manifest requires an explicit pairs array")
    counts = Counter(p.get("kind") for p in pairs)
    if screening and (counts["positive"] != 12 or counts["negative"] != 4 or len(pairs) != 16):
        raise ValueError("screening requires exactly 12 positive and 4 negative pairs")
    seen = set()
    for pair in pairs:
        if pair.get("kind") not in {"positive", "negative"}:
            raise ValueError("pair kind must be positive or negative")
        ordered = []
        for side in ("reference", "moving"):
            slide = pair[side]
            path = Path(slide["path"]).resolve()
            size = np.asarray(slide["size"], dtype=float)
            if (
                not path.is_dir()
                or size.shape != (2,)
                or not np.isfinite(size).all()
                or np.any(size <= 0)
            ):
                raise ValueError("each slide needs a derivative directory and positive full size")
            ordered.append(str(path))
        if ordered[0] == ordered[1] or tuple(ordered) in seen:
            raise ValueError("self pairs and duplicate ordered pairs are forbidden")
        seen.add(tuple(ordered))
        if pair["kind"] == "positive" and (
            not isinstance(pair.get("landmarks"), list) or (screening and not pair["landmarks"])
        ):
            raise ValueError("positive pairs require fit-free landmarks")
        if screening and (
            pair.get("landmarksFitFree") is not True
            or pair.get("independentlyReviewed") is not True
        ):
            raise ValueError("screening inputs must be frozen fit-free and independently reviewed")


def _input_digest(slide: dict[str, Any]) -> str:
    root = Path(slide["path"])
    digest = hashlib.sha256()
    # Hash actual registered pixels and geometry, not a user-entered file identity.
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
    digest.update(json.dumps(slide["size"]).encode())
    return digest.hexdigest()


def _runtime_versions() -> dict[str, str]:
    result = {}
    for package in (
        "numpy",
        "opencv-python-headless",
        "opencv-python",
        "Pillow",
        "wsireg",
        "itk-elastix",
        "valis-wsi",
        "hisalign",
        "deeperhistreg",
        "torch",
    ):
        with suppress(importlib.metadata.PackageNotFoundError):
            result[package] = importlib.metadata.version(package)
    return result


def _pair_settings(pair: dict[str, Any], recipe: str, settings: dict[str, Any]) -> dict[str, Any]:
    """Pair options override cohort options; declared image calibration is authoritative."""
    canonical = ENGINE_ALIASES.get(recipe, recipe)
    overrides = pair.get("settings", {})
    aliases = [name for name, value in ENGINE_ALIASES.items() if value == canonical]
    selected = overrides.get(canonical)
    if selected is None:
        selected = next((overrides[name] for name in aliases if name in overrides), {})
    if not isinstance(selected, dict):
        raise ValueError("pair recipe settings must be an object")
    result = {**settings, **selected}
    for side in ("reference", "moving"):
        key = f"{side}MicronsPerPixel"
        value = pair.get(key, pair[side].get("micronsPerPixel", result.get(key)))
        if value is not None:
            calibration = np.asarray(value, dtype=float)
            if (
                calibration.shape != (2,)
                or not np.isfinite(calibration).all()
                or np.any(calibration <= 0)
            ):
                raise ValueError(
                    "pair calibration requires two finite positive microns-per-pixel values"
                )
            result[key] = calibration.tolist()
    return result


def _private_diagnostic(
    output: Path, key: str, exception_type: str, message: str, *, attempt: str = "cold"
) -> None:
    """Retain failure details only in the explicitly private benchmark directory."""
    path = output / "diagnostics" / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    value: dict[str, Any] = {"digest": key, "exceptionType": exception_type, "message": message}
    previous = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    value["attempts"] = [
        *previous.get("attempts", []),
        {
            "attempt": attempt,
            "exceptionType": exception_type,
            "message": message,
        },
    ]
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def pair_digest(
    pair: dict[str, Any],
    recipe: str,
    settings: dict[str, Any],
    *,
    input_digests: list[str] | None = None,
    settings_are_effective: bool = False,
) -> str:
    value = {
        "benchmark": BENCHMARK_VERSION,
        "recipe": ENGINE_ALIASES.get(recipe, recipe),
        "settingsDigest": settings_digest(
            recipe, settings if settings_are_effective else _pair_settings(pair, recipe, settings)
        ),
        "runtime": _runtime_versions(),
        "inputs": input_digests or [_input_digest(pair[s]) for s in ("reference", "moving")],
    }
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def aggregate_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    reports = {}
    for recipe in sorted({row["recipe"] for row in rows}):
        selected = [row for row in rows if row["recipe"] == recipe]
        # Manual maps cannot remove planned positives from automatic coverage.
        automatic = [
            {**row, "registration": {}, "wrongStructure": None}
            if row.get("manualAssistance")
            else row
            for row in selected
        ]
        positive = [row for row in automatic if row["kind"] == "positive"]
        records = [
            {**landmark, "registration": row.get("registration", {})}
            for row in positive
            for landmark in row["landmarks"]
        ]
        report = evaluate_landmarks(records, measure_approximate=True)
        negatives = [row for row in automatic if row["kind"] == "negative"]
        missing_review = sum(type(row.get("wrongStructure")) is not bool for row in negatives)
        # The independent review determines wrong-structure confidence;
        # an engine's arbitrary low self-score cannot cancel that review.
        confident_wrong = sum(row.get("wrongStructure") is True for row in negatives)
        outcomes = Counter(row["outcome"] for row in automatic)
        # Every planned pair must actually run. Missing negatives cannot be assumed safe.
        ready_gate = report["qualified"]
        gate = (
            report["calibratedCoverage"] >= 0.8
            and report["medianErrorUm"] is not None
            and report["medianErrorUm"] <= 50
            and report["p95ErrorUm"] is not None
            and report["p95ErrorUm"] <= 100
            and report["wrongStructureMatches"] == 0
            and report["invalidLandmarks"] == 0
            and bool(negatives)
            and missing_review == 0
            and confident_wrong == 0
            and all(row["outcome"] in {"ok", "rejected"} for row in automatic)
            and all(
                row.get("independentlyReviewed") is True and row.get("landmarksFitFree") is True
                for row in automatic
            )
        )
        timings = [
            row["coldRuntimeSeconds"]
            for row in automatic
            if not row.get("manualAssistance") and row.get("coldRuntimeSeconds") is not None
        ]
        memory = [
            row["peakMemoryBytes"]
            for row in automatic
            if not row.get("manualAssistance") and row.get("peakMemoryBytes") is not None
        ]
        frontend = [
            row["frontendLatencySeconds"]
            for row in automatic
            if not row.get("manualAssistance")
            and row.get("frontendLatencyScope") == "foreground-open-to-sync"
            and row.get("frontendLatencyReviewed") is True
            and row.get("frontendLatencySeconds") is not None
        ]
        manual_records = [
            {**p, "registration": row.get("registration", {})}
            for row in selected
            if row.get("manualAssistance") and row["kind"] == "positive"
            for p in row["landmarks"]
        ]
        report.update(
            qualified=bool(gate),
            readyQualified=bool(ready_gate),
            benchmarkQualified=bool(gate),
            benchmarkSupportMode="measured-original-coordinate-map-without-status-promotion",
            rankingErrorUnit="um"
            if any(p.get("referenceMicronsPerPixel") is not None for p in records)
            else "relative",
            plannedPairs=len(automatic),
            manualOnlyPairs=sum(bool(row.get("manualAssistance")) for row in selected),
            positivePairs=len(positive),
            missingGroundTruthPairs=sum(not row["landmarks"] for row in positive),
            peakMemoryMedianBytes=float(np.median(memory)) if memory else None,
            peakMemoryP95Bytes=float(np.percentile(memory, 95)) if memory else None,
            queueLatencySeconds=None,
            browserLatencySeconds=None,
            negativePairs=len(negatives),
            outcomes=dict(outcomes),
            missingNegativeReviews=missing_review,
            confidentWrongStructurePairs=confident_wrong,
            coldRuntimeP95Seconds=float(np.percentile(timings, 95)) if timings else None,
            timingScope="supervised-child-compute-excludes-queue-browser",
            foregroundP95Seconds=float(np.percentile(frontend, 95)) if frontend else None,
            foregroundEvidenceComplete=len(frontend) == len(automatic) and bool(automatic),
            manualAssistance=evaluate_landmarks(manual_records, measure_approximate=True),
        )
        reports[recipe] = report
    qualified = [(name, report) for name, report in reports.items() if report["qualified"]]
    accurate = sorted(
        qualified,
        key=lambda x: (
            -x[1]["calibratedCoverage"],
            x[1]["p95ErrorUm"],
            x[1]["coldRuntimeP95Seconds"] or float("inf"),
        ),
    )
    fast = sorted(
        (
            x
            for x in qualified
            if x[1]["foregroundEvidenceComplete"] and x[1]["foregroundP95Seconds"] <= 10
        ),
        key=lambda x: x[1]["foregroundP95Seconds"],
    )
    candidates = [
        (name, report)
        for name, report in reports.items()
        if report["eligibleLandmarks"] > 0
        and report["positivePairs"] > 0
        and report["negativePairs"] > 0
        and report["missingNegativeReviews"] == 0
        and all(outcome in {"ok", "rejected"} for outcome in report["outcomes"])
    ]
    candidates.sort(
        key=lambda x: (
            -x[1]["observedCoverage"],
            (x[1]["p95ErrorUm"] if x[1]["rankingErrorUnit"] == "um" else x[1]["p95RelativeError"])
            if (
                x[1]["p95ErrorUm"] if x[1]["rankingErrorUnit"] == "um" else x[1]["p95RelativeError"]
            )
            is not None
            else float("inf"),
            x[1]["coldRuntimeP95Seconds"] or float("inf"),
        )
    )
    return {
        "recipes": reports,
        "finalists": [name for name, _ in candidates[:4]],
        "winners": {
            "fast": fast[0][0] if fast else None,
            "accurate": accurate[0][0] if accurate else None,
        },
        "qualificationGates": {
            "medianErrorUm": 50,
            "p95ErrorUm": 100,
            "coverage": 0.8,
            "confidentWrongStructureMatches": 0,
        },
    }


def run_benchmark(
    manifest: dict[str, Any],
    output: Path,
    recipes: list[str],
    *,
    screening: bool = False,
    resume: bool = True,
    timeout_seconds: int = 600,
    memory_bytes: int = 7 * 1024**3,
    repeat_runs: int = 0,
) -> dict[str, Any]:
    validate_manifest(manifest, screening=screening)
    if not 0 <= repeat_runs <= 5:
        raise ValueError("repeat runs must be between zero and five")
    output = output.resolve()
    _private_output(output)
    output.mkdir(parents=True, exist_ok=True)
    cache_dir = output / "cache"
    cache_dir.mkdir(exist_ok=True)
    availability = engine_availability()
    rows = []
    for pair_index, pair in enumerate(manifest["pairs"]):
        inputs = [_input_digest(pair[side]) for side in ("reference", "moving")]
        for requested in recipes:
            recipe = ENGINE_ALIASES.get(requested, requested)
            if recipe not in SUPPORTED_ENGINES:
                raise ValueError(f"unsupported recipe {requested}")
            settings = manifest.get("settings", {}).get(
                requested, manifest.get("settings", {}).get(recipe, {})
            )
            settings = {
                **_pair_settings(pair, recipe, settings),
                "timeoutSeconds": min(600, timeout_seconds),
            }
            resources_available, resource_reason = engine_resource_availability(recipe, settings)
            key = pair_digest(
                pair, recipe, settings, input_digests=inputs, settings_are_effective=True
            )
            cache = cache_dir / f"{key}.json"
            cached = resume and cache.is_file()
            if cached:
                receipt = json.loads(cache.read_text(encoding="utf-8"))
                if receipt.get("digest") != key:
                    raise ValueError("cache digest does not match request")
            else:
                started = time.monotonic()
                registration: dict[str, Any] = {}
                stage_events: list[dict[str, Any]] = []
                outcome = "ok"
                reason_code = None
                if not availability.get(recipe, {}).get("available") or not resources_available:
                    outcome = "unavailable"
                    reason_code = resource_reason or "optional-runtime-unavailable"
                else:
                    try:
                        registration = _run_alignment_bounded(
                            Path(pair["reference"]["path"]),
                            Path(pair["moving"]["path"]),
                            tuple(pair["reference"]["size"]),
                            tuple(pair["moving"]["size"]),
                            engine_name=recipe,
                            engine_settings=settings,
                            artifact_dir=output / "artifacts" / key,
                            timeout_seconds=min(600, timeout_seconds),
                            memory_bytes=memory_bytes,
                            progress=_progress_recorder(stage_events, started),
                        )
                        if registration.get("status") not in {"ready", "approximate"}:
                            outcome = "rejected"
                            _private_diagnostic(
                                output,
                                key,
                                "RejectedRegistration",
                                str(
                                    registration.get("reason")
                                    or "registration returned unsupported status"
                                ),
                            )
                    except AlignmentRejected as error:
                        outcome = "rejected"
                        reason_code = "registration-or-resource-gate-rejected"
                        _private_diagnostic(output, key, type(error).__name__, str(error))
                    except Exception as error:
                        outcome = "error"
                        reason_code = type(error).__name__
                        _private_diagnostic(output, key, type(error).__name__, str(error))
                # Paths and upstream error messages can contain private slide identities.
                registration = {
                    k: v
                    for k, v in registration.items()
                    if k not in {"artifactPath", "reason", "engineSettings"}
                }
                receipt = {
                    "digest": key,
                    "recipe": recipe,
                    "outcome": outcome,
                    "reasonCode": reason_code,
                    "registration": registration,
                    "coldRuntimeSeconds": time.monotonic() - started
                    if outcome != "unavailable"
                    else None,
                    "admissionSeconds": time.monotonic() - started
                    if outcome == "unavailable"
                    else None,
                    "stageTimings": stage_events,
                    "settingsDigest": settings_digest(recipe, settings),
                    "inputDigests": inputs,
                    "engineBuild": ENGINE_VERSIONS[recipe],
                    "runtimeVersions": _runtime_versions(),
                }
                temporary = cache.with_suffix(".tmp")
                temporary.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
                temporary.replace(cache)
            repeats = list(receipt.get("repeatComputeReceipts", []))
            for _repeat in range(len(repeats), repeat_runs):
                if not availability.get(recipe, {}).get("available") or not resources_available:
                    break
                repeat_started = time.monotonic()
                repeat_payload: dict[str, Any] = {}
                repeat_outcome = "ok"
                try:
                    repeat_payload = _run_alignment_bounded(
                        Path(pair["reference"]["path"]),
                        Path(pair["moving"]["path"]),
                        tuple(pair["reference"]["size"]),
                        tuple(pair["moving"]["size"]),
                        engine_name=recipe,
                        engine_settings=settings,
                        artifact_dir=output / "artifacts" / key / f"repeat-{_repeat}",
                        timeout_seconds=min(600, timeout_seconds),
                        memory_bytes=memory_bytes,
                    )
                    if repeat_payload.get("status") not in {"ready", "approximate"}:
                        repeat_outcome = "rejected"
                        _private_diagnostic(
                            output,
                            key,
                            "RejectedRegistration",
                            str(
                                repeat_payload.get("reason")
                                or "registration returned unsupported status"
                            ),
                            attempt=f"repeat-{_repeat}",
                        )
                except AlignmentRejected as error:
                    repeat_outcome = "rejected"
                    _private_diagnostic(
                        output, key, type(error).__name__, str(error), attempt=f"repeat-{_repeat}"
                    )
                except Exception as error:
                    repeat_outcome = "error"
                    _private_diagnostic(
                        output, key, type(error).__name__, str(error), attempt=f"repeat-{_repeat}"
                    )
                repeats.append(
                    {
                        "runtimeSeconds": time.monotonic() - repeat_started,
                        "outcome": repeat_outcome,
                        "peakMemoryBytes": repeat_payload.get("peakMemoryBytes"),
                        "timingScope": "fresh-supervised-child-repeat-host-filesystem-cache",
                    }
                )
            receipt["repeatComputeReceipts"] = repeats
            receipt["warmWorkerRuntimeSeconds"] = None
            receipt["visualQaPairProduced"] = (
                _visual_qa_pair(pair, receipt["registration"], output / "qa" / f"{key}.png")
                if receipt["outcome"] == "ok"
                else False
            )
            temporary = cache.with_suffix(".tmp")
            temporary.write_text(json.dumps(receipt, sort_keys=True), encoding="utf-8")
            temporary.replace(cache)
            review = pair.get("reviews", {}).get(requested, pair.get("reviews", {}).get(recipe, {}))
            if review.get("registrationDigest") != receipt["digest"]:
                review = {}
            row = {
                **receipt,
                "peakMemoryBytes": receipt.get("registration", {}).get("peakMemoryBytes"),
                "cached": cached,
                "pairIndex": pair_index,
                "kind": pair["kind"],
                "landmarks": [
                    {
                        "referenceSize": pair["reference"]["size"],
                        **(
                            {"referenceMicronsPerPixel": settings["referenceMicronsPerPixel"]}
                            if "referenceMicronsPerPixel" in settings
                            else {}
                        ),
                        **landmark,
                    }
                    for landmark in pair.get("landmarks", [])
                ],
                "manualAssistance": pair.get("manualAssistance") is True,
                "independentlyReviewed": pair.get("independentlyReviewed") is True,
                "landmarksFitFree": pair.get("landmarksFitFree") is True,
                "wrongStructure": review.get("wrongStructure"),
                "frontendLatencySeconds": review.get("frontendLatencySeconds"),
                "frontendLatencyScope": review.get("frontendLatencyScope"),
                "frontendLatencyReviewed": review.get("frontendLatencyReviewed") is True,
            }
            row["landmarkMetrics"] = evaluate_landmarks(
                [
                    {**landmark, "registration": row["registration"]}
                    for landmark in row["landmarks"]
                ],
                measure_approximate=True,
            )
            rows.append(row)
    report = {
        "schema": BENCHMARK_VERSION,
        "screening": screening,
        **aggregate_results(rows),
        "rows": [
            {k: v for k, v in row.items() if k not in {"landmarks", "registration"}} for row in rows
        ],
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True), encoding="utf-8"
    )
    lines = [
        "# Alignment recipe observations",
        "",
        "Compute timing excludes queue and browser.",
        "",
        "| Recipe | Observed | Ready coverage | Median um | P95 um | Qualified |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for recipe, result in report["recipes"].items():
        lines.append(
            f"| {recipe} | {result['observedLandmarks']} | {result['coverage']:.3f} | "
            f"{result['medianErrorUm']} | {result['p95ErrorUm']} | {result['qualified']} |"
        )
    lines.extend(
        [
            "",
            f"Fast: {report['winners']['fast'] or 'unqualified'}",
            f"Accurate: {report['winners']['accurate'] or 'unqualified'}",
            "",
        ]
    )
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return report
