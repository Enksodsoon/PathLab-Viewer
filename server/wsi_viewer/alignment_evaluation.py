from __future__ import annotations

from typing import Any

import numpy as np


def evaluate_landmarks(records: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [record for record in records if record.get("eligible") is True]
    errors = [
        float(record["errorUm"])
        for record in eligible
        if record.get("errorUm") is not None
    ]
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
    )
    return {
        "eligibleLandmarks": len(eligible),
        "evaluatedLandmarks": len(errors),
        "coverage": coverage,
        "medianErrorUm": median,
        "p95ErrorUm": p95,
        "wrongStructureMatches": wrong,
        "qualified": qualified,
    }
