# SPDX-License-Identifier: Apache-2.0
"""Post-terminal stage scorer: original frames, own cells, no fitting.

Importing this module never imports engines/evaluators or reads campaign artifacts.
The aggregator must first bind manifest, cache, completed invocation and sidecar SHA.
"""

import hashlib
import json
import math
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STAGES = {
    "native-wsireg": "native-overview-v6",
    "native-valis": "native-overview-v6",
    "valis-rigid-wsireg": "valis-1.2.0",
}
METRIC_KEYS = (
    "eligibleLandmarks",
    "observedLandmarks",
    "unsupportedLandmarks",
    "invalidLandmarks",
    "observedCoverage",
    "medianRelativeError",
    "p95RelativeError",
    "supportTierCounts",
    "supportMappingPolicy",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def own_cells(registration):
    """Discard retained/nested fallback maps; never extend support with affine-only maps."""
    if not isinstance(registration, dict):
        return {}
    return {
        key: deepcopy(registration.get(key)) for key in ("status", "triangles", "overviewTriangles")
    }


def original_frame_proof(registration, pair):
    """Warm immutable/DZI inputs require explicit applied geometry on both sides.

    Historical plain-JPEG sidecars lack these fields and need their separately bound
    historical producer proof; this new warm scorer never infers a missing frame.
    """
    from wsi_viewer.alignment_geometry import validate_sampling_geometry

    if (
        not isinstance(registration, dict)
        or registration.get("status") not in {"ready", "approximate"}
        or registration.get("samplingGeometryApplied") is not True
    ):
        return False
    settings = registration.get("engineSettings")
    if not isinstance(settings, dict):
        return False
    geometry = {}
    try:
        for side in ("reference", "moving"):
            geometry[side] = validate_sampling_geometry(
                settings[f"{side}Geometry"], source_size=tuple(pair[side]["size"])
            )
    except (KeyError, TypeError, ValueError):
        return False
    expected = hashlib.sha256(canonical(geometry)).hexdigest()
    if registration.get("samplingGeometryDigest") != expected:
        return False
    # The shared clipper outputs source-bound vertices. Refuse malformed sidecars,
    # without adding new source cells or replacing bad coordinates with an affine.
    for key in ("triangles", "overviewTriangles"):
        cells = registration.get(key) or []
        if not isinstance(cells, list):
            return False
        for cell in cells:
            if not isinstance(cell, dict):
                return False
            for side in ("moving", "reference"):
                vertices = cell.get(side)
                size = pair[side]["size"]
                if not isinstance(vertices, list) or len(vertices) != 3:
                    return False
                for point in vertices:
                    if not isinstance(point, list) or len(point) != 2:
                        return False
                    if any(
                        type(v) not in (int, float) or not math.isfinite(v) or v < 0 or v >= size[i]
                        for i, v in enumerate(point)
                    ):
                        return False
    return True


def affine_on_own_source_cells(initializer):
    """Affine actually applied to warp, restricted to recorded initializer support.

    This is a separate measurement from the engine's possibly piecewise map.
    Target projection may leave the reference image; no point outside the engine's
    recorded source cells becomes supported by this calculation.
    """
    affine = initializer.get("movingToReference")
    if (
        not isinstance(affine, list)
        or len(affine) != 2
        or any(
            not isinstance(row, list)
            or len(row) != 3
            or any(type(v) not in (int, float) or not math.isfinite(v) for v in row)
            for row in affine
        )
    ):
        return None
    projected = own_cells(initializer)
    for key in ("triangles", "overviewTriangles"):
        projected[key] = [
            {
                **cell,
                "reference": [
                    [
                        sum(affine[axis][i] * point[i] for i in range(2)) + affine[axis][2]
                        for axis in range(2)
                    ]
                    for point in cell["moving"]
                ],
            }
            for cell in projected.get(key) or []
        ]
    return projected


def metrics(records):
    from wsi_viewer.alignment_evaluation import evaluate_landmarks

    measured = evaluate_landmarks(records, measure_approximate=True)
    return {key: measured[key] for key in METRIC_KEYS}


def measurement(initializer, final, pair, recipe, *, evaluate=False):
    """No scoring until evaluate=True is explicitly authorized after terminal.

    Caller has already validated the initializer descriptor and atomic input proof.
    Returned maps are private ephemeral inputs, never included in public output.
    """
    empty = {"initializer": {}, "applied": {}}
    result = {
        "status": "unmeasured",
        "reason": "post-terminal-evaluation-not-requested",
        "initializerEngineOutputMetrics": None,
        "appliedAffineOnOwnSupportMetrics": None,
        "finalVsInitializerCommonSupport": None,
        "finalVsAppliedAffineCommonSupport": None,
        "residualFrameAccuracy": None,
        "residualFrameAccuracyReason": "residual-is-warped-reference-frame",
        "wholeInitializerPiecewiseMapAppliedToWarp": False,
        "qualified": False,
    }
    if not evaluate:
        return result, empty
    if not isinstance(initializer, dict):
        result["reason"] = "initializer-artifact-or-descriptor-unavailable"
        return result, empty
    if initializer.get("engine") != STAGES[recipe] or not original_frame_proof(initializer, pair):
        result["reason"] = "initializer-original-frame-or-engine-not-proven"
        return result, empty
    initial = own_cells(initializer)
    applied = affine_on_own_source_cells(initializer)
    records = [{**p, "referenceSize": pair["reference"]["size"]} for p in pair.get("landmarks", [])]
    if any(p.get("referenceMicronsPerPixel") is not None for p in records):
        raise ValueError("calibration needs separately reviewed cohort")
    result.update(
        status="measured",
        reason=None,
        initializerCoordinateFrame="original-moving-to-reference-level-zero",
        initializerEngineOutputMetrics=metrics([{**p, "registration": initial} for p in records]),
        appliedAffineOnOwnSupportMetrics=metrics(
            [{**p, "registration": applied or {}} for p in records]
        ),
    )
    final_proven = (
        isinstance(final, dict)
        and final.get("engine") == recipe
        and original_frame_proof(final, pair)
    )
    if final_proven:
        # Reuse the existing reporter's pointwise evaluator/common-set error logic.
        if __package__:
            from . import report_alignment_campaign as reporter
        else:
            import report_alignment_campaign as reporter
        result["finalVsInitializerCommonSupport"] = reporter.paired_landmark_comparison(
            own_cells(final), initial, records
        )
        result["finalVsAppliedAffineCommonSupport"] = reporter.paired_landmark_comparison(
            own_cells(final), applied, records
        )
    else:
        result["pairedComparisonUnavailableReason"] = "final-map-or-original-frame-unavailable"
    result["pairedDeltaSign"] = "final-minus-initializer / negative-is-lower-error"
    result["scope"] = (
        "same-fit-free-landmarks-and-original-pair; own-supported-cells-only; "
        "no global-affine-extrapolation"
    )
    return result, {"initializer": initial, "applied": applied or {}}
