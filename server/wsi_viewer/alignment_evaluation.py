from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from .alignment import AlignmentRejected

SUPPORT_MAPPING_POLICY = "pointwise-supported-cells/2"


def _map_cells(cells: Any, point: np.ndarray) -> np.ndarray | None:
    """Use explicit finite, invertible cells only; never affine extrapolation."""
    if not isinstance(cells, list):
        return None
    for cell in cells:
        try:
            source = np.asarray(cell["moving"], dtype=float)
            target = np.asarray(cell["reference"], dtype=float)
            if any(
                value.shape != (3, 2) or not np.isfinite(value).all() for value in (source, target)
            ):
                continue
            matrix = np.vstack([source.T, np.ones(3)])
            target_matrix = np.vstack([target.T, np.ones(3)])
            source_det = float(np.linalg.det(matrix))
            target_det = float(np.linalg.det(target_matrix))
            if abs(source_det) <= 1e-12 or target_det / source_det <= 1e-12:
                continue
            weights = np.linalg.solve(matrix, [*point, 1.0])
            if np.isfinite(weights).all() and float(np.min(weights)) >= -1e-7:
                mapped = weights @ target
                if np.isfinite(mapped).all():
                    return mapped
        except (KeyError, TypeError, ValueError, np.linalg.LinAlgError):
            continue
    return None


def map_supported_landmark(
    registration: dict[str, Any], point: np.ndarray, *, measure_approximate: bool = False
) -> tuple[np.ndarray, str]:
    """Match viewer tier priority inside explicit cells, excluding viewport gap snaps.

    Coarse observations never count as ready-local evidence. A fallback must bind
    the same source bytes, anchor bytes and anchor identity; optional frame tokens
    must also agree. No nested fallback or affine-only mapping is admitted.
    """
    if registration.get("status") == "ready":
        mapped = _map_cells(registration.get("triangles"), point)
        if mapped is not None:
            return mapped, "ready-local"
    if measure_approximate and registration.get("status") in ("ready", "approximate"):
        mapped = _map_cells(registration.get("overviewTriangles"), point)
        if mapped is not None:
            return mapped, "own-overview"
        fallback = registration.get("overviewFallback")
        binding_keys = ("sourceVersion", "anchorVersion", "anchorSlideId")
        frame_keys = (
            "sourceFrameVersion",
            "anchorFrameVersion",
            "sourceSnapshotVersion",
            "anchorSnapshotVersion",
            "coordinateReferenceId",
        )
        if (
            isinstance(fallback, dict)
            and fallback.get("status") in ("ready", "approximate")
            and all(
                registration.get(key) is not None and fallback.get(key) == registration[key]
                for key in binding_keys
            )
            and all(
                key not in registration or fallback.get(key) == registration[key]
                for key in frame_keys
            )
        ):
            mapped = _map_cells(fallback.get("overviewTriangles"), point)
            if mapped is not None:
                return mapped, "overview-fallback"
    raise AlignmentRejected("point is outside explicit supported registration cells")


def evaluate_landmarks(
    records: list[dict[str, Any]], *, measure_approximate: bool = False
) -> dict[str, Any]:
    eligible = [record for record in records if record.get("eligible") is True]
    errors: list[float] = []
    relative_errors: list[float] = []
    accepted_errors: list[float] = []
    approximate = 0
    invalid = 0
    unsupported = 0
    tiers: Counter[str] = Counter()
    for record in eligible:
        try:
            if type(record.get("wrongStructure")) is not bool:
                raise ValueError("Missing independently reviewed wrong-structure flag")
            moving = np.asarray(record["movingPoint"], dtype=float)
            reference = np.asarray(record["referencePoint"], dtype=float)
            calibration_value = record.get("referenceMicronsPerPixel")
            calibration = (
                np.asarray(calibration_value, dtype=float)
                if calibration_value is not None
                else None
            )
            if any(
                value.shape != (2,) or not np.isfinite(value).all() for value in (moving, reference)
            ) or (
                calibration is not None
                and (
                    calibration.shape != (2,)
                    or not np.isfinite(calibration).all()
                    or np.any(calibration <= 0)
                )
            ):
                raise ValueError("Invalid landmark coordinates or calibration")
            if calibration is None and not measure_approximate:
                raise ValueError("Missing calibration")
            registration = record["registration"]
            if not isinstance(registration, dict):
                raise ValueError("Missing registration")
            mapped, tier = map_supported_landmark(
                registration, moving, measure_approximate=measure_approximate
            )
            is_approximate = tier != "ready-local"
            if calibration is None:
                size = np.asarray(record["referenceSize"], dtype=float)
                if size.shape != (2,) or not np.isfinite(size).all() or np.any(size <= 0):
                    raise ValueError("Missing relative coordinate frame")
                error = float(np.linalg.norm(mapped - reference) / np.linalg.norm(size))
            else:
                error = float(np.linalg.norm((mapped - reference) * calibration))
            if not np.isfinite(error):
                raise ValueError("Non-finite mapped coordinate")
            if calibration is None:
                relative_errors.append(error)
            else:
                errors.append(error)
                if not is_approximate:
                    accepted_errors.append(error)
            approximate += int(is_approximate)
            tiers[tier] += 1
        except AlignmentRejected:
            unsupported += 1
        except (KeyError, TypeError, ValueError, IndexError):
            invalid += 1
    wrong = sum(bool(record.get("wrongStructure")) for record in eligible)
    coverage = len(accepted_errors) / len(eligible) if eligible else 0.0
    median = float(np.median(errors)) if errors else None
    p95 = float(np.percentile(errors, 95)) if errors else None
    ready_median = float(np.median(accepted_errors)) if accepted_errors else None
    ready_p95 = float(np.percentile(accepted_errors, 95)) if accepted_errors else None
    qualified = bool(
        accepted_errors
        and ready_median is not None
        and ready_p95 is not None
        and ready_median <= 50
        and ready_p95 <= 100
        and coverage >= 0.8
        and wrong == 0
        and invalid == 0
    )
    return {
        "eligibleLandmarks": len(eligible),
        "measurementMethod": "mapped-source-coordinates",
        "supportMappingPolicy": SUPPORT_MAPPING_POLICY,
        "supportMappingScope": "explicit cells only; no affine extrapolation or viewport gap snaps",
        "supportTierCounts": dict(tiers),
        "invalidLandmarks": invalid,
        "unsupportedLandmarks": unsupported,
        "evaluatedLandmarks": len(errors),
        "observedLandmarks": len(errors) + len(relative_errors),
        "approximateLandmarks": approximate,
        "relativeLandmarks": len(relative_errors),
        "medianRelativeError": float(np.median(relative_errors)) if relative_errors else None,
        "p95RelativeError": float(np.percentile(relative_errors, 95)) if relative_errors else None,
        "calibratedCoverage": len(errors) / len(eligible) if eligible else 0.0,
        "coverage": coverage,
        "medianErrorUm": median,
        "p95ErrorUm": p95,
        "readyMedianErrorUm": ready_median,
        "readyP95ErrorUm": ready_p95,
        "observedCoverage": (len(errors) + len(relative_errors)) / len(eligible)
        if eligible
        else 0.0,
        "wrongStructureMatches": wrong,
        "qualified": qualified,
    }
