from __future__ import annotations

from typing import Any

import numpy as np

from .alignment import AlignmentRejected, map_registration_point


def evaluate_landmarks(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [record for record in records if record.get("eligible") is True]
    errors: list[float] = []
    invalid = 0
    unsupported = 0
    for record in eligible:
        try:
            moving = np.asarray(record["movingPoint"], dtype=float)
            reference = np.asarray(record["referencePoint"], dtype=float)
            calibration = np.asarray(record["referenceMicronsPerPixel"], dtype=float)
            if any(
                value.shape != (2,) or not np.isfinite(value).all()
                for value in (moving, reference, calibration)
            ) or np.any(calibration <= 0):
                raise ValueError("Invalid landmark coordinates or calibration")
            registration = record["registration"]
            if not isinstance(registration, dict):
                raise ValueError("Missing registration")
            if registration.get("status") != "ready" or not registration.get("triangles"):
                unsupported += 1
                continue
            mapped = np.asarray(map_registration_point(registration, *moving))
            error = float(np.linalg.norm((mapped - reference) * calibration))
            if not np.isfinite(error):
                raise ValueError("Non-finite mapped coordinate")
            errors.append(error)
        except AlignmentRejected:
            unsupported += 1
        except (KeyError, TypeError, ValueError, IndexError):
            invalid += 1
    wrong = sum(bool(record.get("wrongStructure")) for record in eligible)
    coverage = len(errors) / len(eligible) if eligible else 0.0
    median = float(np.median(errors)) if errors else None
    p95 = float(np.percentile(errors, 95)) if errors else None
    qualified = bool(
        errors
        and median is not None
        and p95 is not None
        and median <= 50
        and p95 <= 100
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
        "coverage": coverage,
        "medianErrorUm": median,
        "p95ErrorUm": p95,
        "wrongStructureMatches": wrong,
        "qualified": qualified,
    }
