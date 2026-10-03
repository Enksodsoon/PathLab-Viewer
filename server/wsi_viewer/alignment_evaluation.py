from __future__ import annotations

from typing import Any

import numpy as np

from .alignment import AlignmentRejected, map_registration_point


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
            is_approximate = registration.get("status") == "approximate"
            cells = registration.get("triangles") or (
                registration.get("overviewTriangles")
                if measure_approximate and is_approximate
                else []
            )
            if (
                registration.get("status") not in ("ready", "approximate")
                or (is_approximate and not measure_approximate)
                or not cells
            ):
                unsupported += 1
                continue
            mapped = np.asarray(map_registration_point({"triangles": cells}, *moving))
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
