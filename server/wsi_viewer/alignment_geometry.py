"""Explicit sampled pixel frames and bounded original-coordinate support."""

from __future__ import annotations

import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import numpy as np

from .alignment import AlignmentRejected


def derivative_sampling_geometry(
    derivative: Path,
    source_size: tuple[int, int],
    *,
    maximum: int = 4096,
    kind: str | None = None,
) -> dict[str, Any] | None:
    """Read deterministic live geometry without decoding or materializing tiles."""
    from .alignment_inputs import DESCRIPTOR_NAME, immutable_descriptor

    if (derivative / DESCRIPTOR_NAME).exists() and kind != "dzi-pyramid":
        return cast(
            dict[str, Any], immutable_descriptor(derivative, source_size=source_size)["geometry"]
        )
    descriptor = derivative / "slide.dzi"
    if not descriptor.is_file():
        return None
    if kind == "thumbnail-fallback":
        from PIL import Image

        with Image.open(derivative / "thumbnail.jpg") as image:
            analysis = list(image.size)
        return validate_sampling_geometry(
            {
                "schema": "pathlab-sampling-frame/1",
                "kind": kind,
                "sourceSize": list(source_size),
                "analysisSize": analysis,
                "coordinateFrameSize": list(source_size),
                "samplingScale": [source_size[0] / analysis[0], source_size[1] / analysis[1]],
                "cropOrigin": [0, 0],
            },
            source_size=source_size,
        )
    root = ET.parse(descriptor).getroot()
    size = next((node for node in root if node.tag.rsplit("}", 1)[-1] == "Size"), None)
    if size is None:
        raise AlignmentRejected("sampling DZI dimensions are unavailable")
    width, height = int(size.attrib["Width"]), int(size.attrib["Height"])
    maximum_level = math.ceil(math.log2(max(width, height)))
    level, divisor = maximum_level, 1
    while level > 0 and max(math.ceil(width / divisor), math.ceil(height / divisor)) > maximum:
        level -= 1
        divisor *= 2
    analysis = [math.ceil(width / divisor), math.ceil(height / divisor)]
    return validate_sampling_geometry(
        {
            "schema": "pathlab-sampling-frame/1",
            "kind": "dzi-pyramid",
            "sourceSize": [width, height],
            "analysisSize": analysis,
            "coordinateFrameSize": [analysis[0] * divisor, analysis[1] * divisor],
            "samplingScale": [divisor, divisor],
            "cropOrigin": [0, 0],
            "pyramidDivisor": divisor,
            "selectedLevel": level,
        },
        source_size=source_size,
    )


def validate_sampling_geometry(
    value: Any,
    *,
    source_size: tuple[int, int] | None = None,
    analysis_size: tuple[int, int] | None = None,
    frame_size: tuple[int, int] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("schema") != "pathlab-sampling-frame/1":
        raise AlignmentRejected("invalid sampling geometry schema")
    if value.get("kind") not in {
        "dzi-pyramid",
        "immutable-overview",
        "thumbnail-fallback",
        "component-region",
        "resampled-reference",
    }:
        raise AlignmentRejected("invalid sampling geometry kind")
    if set(value) - {
        "schema",
        "kind",
        "sourceSize",
        "analysisSize",
        "coordinateFrameSize",
        "samplingScale",
        "cropOrigin",
        "pyramidDivisor",
        "selectedLevel",
        "snapshotPixelSha256",
        "parentFrameDigest",
    }:
        raise AlignmentRejected("unknown sampling geometry declaration")
    for key in ("sourceSize", "analysisSize", "coordinateFrameSize", "samplingScale", "cropOrigin"):
        vector = value.get(key)
        if not isinstance(vector, (list, tuple)) or len(vector) != 2:
            raise AlignmentRejected("invalid sampling geometry vector")
        if any(type(v) not in (int, float) or not np.isfinite(v) for v in vector):
            raise AlignmentRejected("invalid sampling geometry numeric value")
        if any(v < 0 if key == "cropOrigin" else v <= 0 for v in vector):
            raise AlignmentRejected("invalid sampling geometry extent")
    frame = np.asarray(value["analysisSize"]) * np.asarray(value["samplingScale"])
    if not np.allclose(frame, value["coordinateFrameSize"], rtol=0, atol=1e-8):
        raise AlignmentRejected("inconsistent sampling coordinate frame")
    for key, expected in (
        ("sourceSize", source_size),
        ("analysisSize", analysis_size),
        ("coordinateFrameSize", frame_size),
    ):
        if expected is not None and not np.allclose(value[key], expected, rtol=0, atol=1e-8):
            raise AlignmentRejected("sampling geometry differs from actual input")
    if np.any(np.asarray(value["cropOrigin"]) >= np.asarray(value["sourceSize"])):
        raise AlignmentRejected("sampling origin is outside the original source")
    if "pyramidDivisor" in value:
        divisor = value["pyramidDivisor"]
        if type(divisor) is not int or divisor < 1 or divisor & (divisor - 1):
            raise AlignmentRejected("invalid sampling pyramid divisor")
        if list(value["samplingScale"]) != [divisor, divisor]:
            raise AlignmentRejected("sampling scale differs from pyramid divisor")
    for key in ("snapshotPixelSha256", "parentFrameDigest"):
        if key in value and (
            not isinstance(value[key], str) or re.fullmatch(r"[0-9a-f]{64}", value[key]) is None
        ):
            raise AlignmentRejected("invalid sampling geometry digest")
    if "selectedLevel" in value and (
        type(value["selectedLevel"]) is not int or not 0 <= value["selectedLevel"] <= 63
    ):
        raise AlignmentRejected("invalid sampling pyramid level")
    return deepcopy(value)


def validate_input_geometry(
    settings: dict[str, Any], sizes: dict[str, tuple[int, int]], frames: dict[str, tuple[int, int]]
) -> None:
    for side in ("reference", "moving"):
        if f"{side}Geometry" in settings:
            validate_sampling_geometry(
                settings[f"{side}Geometry"], analysis_size=sizes[side], frame_size=frames[side]
            )


def original_frame_registration(
    payload: dict[str, Any], settings: dict[str, Any]
) -> dict[str, Any]:
    """Shift local crops once and clip paired cells to true source bounds.

    This never extends a supported cell into padded pixels or unobserved tissue.
    JPEG maps without explicit geometry retain their exact existing payload.
    """
    geometry = {
        side: validate_sampling_geometry(settings[f"{side}Geometry"])
        for side in ("reference", "moving")
        if f"{side}Geometry" in settings
    }
    if not geometry:
        return payload
    geometry_digest = hashlib.sha256(
        json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if payload.get("samplingGeometryApplied") is True:
        if payload.get("samplingGeometryDigest") != geometry_digest:
            raise AlignmentRejected("sampling geometry differs from the already applied frame")
        return {**payload, "engineSettings": settings}
    result = deepcopy(payload)
    origins = {
        side: np.asarray(geometry.get(side, {}).get("cropOrigin", [0, 0]), dtype=float)
        for side in ("reference", "moving")
    }

    def points(values: Any, side: str) -> list[list[float]] | None:
        array = np.asarray(values, dtype=float)
        if array.ndim != 2 or array.shape[1] != 2 or not np.isfinite(array).all():
            return None
        array = array + origins[side]
        if side in geometry and (
            np.any(array < 0) or np.any(array >= np.asarray(geometry[side]["sourceSize"]))
        ):
            return None
        return cast(list[list[float]], array.tolist())

    def clipped_cell(cell: dict[str, Any]) -> list[dict[str, Any]]:
        reference = np.asarray(cell["reference"], dtype=float) + origins["reference"]
        moving = np.asarray(cell["moving"], dtype=float) + origins["moving"]
        if reference.shape != (3, 2) or moving.shape != (3, 2):
            raise AlignmentRejected("sampling support requires paired triangular cells")
        polygon = list(np.concatenate((reference, moving), axis=1))
        if not np.isfinite(polygon).all():
            raise AlignmentRejected("sampling support contains invalid coordinates")
        # Clip a single paired polygon: each edge interpolation uses identical
        # barycentric weights in both images, retaining the existing cell map.
        for side, offset in (("reference", 0), ("moving", 2)):
            if side not in geometry:
                continue
            for axis, extent in enumerate(geometry[side]["sourceSize"]):
                for bound, lower in ((0.0, True), (float(extent) - 1e-8, False)):
                    if not polygon:
                        return []
                    clipped = []
                    previous = polygon[-1]
                    previous_inside = (
                        previous[offset + axis] >= bound
                        if lower
                        else previous[offset + axis] <= bound
                    )
                    for current in polygon:
                        current_inside = (
                            current[offset + axis] >= bound
                            if lower
                            else current[offset + axis] <= bound
                        )
                        if current_inside != previous_inside:
                            weight = (bound - previous[offset + axis]) / (
                                current[offset + axis] - previous[offset + axis]
                            )
                            clipped.append(previous + weight * (current - previous))
                        if current_inside:
                            clipped.append(current)
                        previous, previous_inside = current, current_inside
                    polygon = clipped
        cells = []
        for index in range(1, len(polygon) - 1):
            triangle = np.asarray([polygon[0], polygon[index], polygon[index + 1]])
            if any(
                abs(
                    np.linalg.det(
                        np.vstack(
                            (
                                triangle[1, start : start + 2] - triangle[0, start : start + 2],
                                triangle[2, start : start + 2] - triangle[0, start : start + 2],
                            )
                        )
                    )
                )
                < 1e-8
                for start in (0, 2)
            ):
                continue
            cells.append(
                {**cell, "reference": triangle[:, :2].tolist(), "moving": triangle[:, 2:].tolist()}
            )
        return cells

    for key in ("triangles", "overviewTriangles"):
        cells = []
        for cell in payload.get(key) or []:
            cells.extend(clipped_cell(cell))
        result[key] = cells
    cells = result["triangles"] + result["overviewTriangles"]
    if not cells and payload.get("status") in {"ready", "approximate"}:
        raise AlignmentRejected("sampling frame has no supported original-bound cells")
    controls = []
    for control in payload.get("controlPoints") or []:
        reference, moving = (
            points([control["reference"]], "reference"),
            points([control["moving"]], "moving"),
        )
        if reference is not None and moving is not None:
            controls.append({**control, "reference": reference[0], "moving": moving[0]})
    result["controlPoints"] = controls
    for side in ("reference", "moving"):
        if cells:
            vertices = np.asarray([point for cell in cells for point in cell[side]])
            result[f"{side}Support"] = [
                *vertices.min(axis=0).tolist(),
                *vertices.max(axis=0).tolist(),
            ]
    result["supportPolygons"] = {
        side: [cell[side] for cell in result["triangles"]] for side in ("reference", "moving")
    }
    if payload.get("movingToReference") is not None:
        matrix = np.asarray(payload["movingToReference"], dtype=float).copy()
        matrix[:, 2] += origins["reference"] - matrix[:, :2] @ origins["moving"]
        result["movingToReference"] = matrix.tolist()
    result["engineSettings"] = settings
    result["samplingGeometryApplied"] = True
    result["samplingGeometryDigest"] = geometry_digest
    return result
