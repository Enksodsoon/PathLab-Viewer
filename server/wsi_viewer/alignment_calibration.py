"""Declared physical pixel sizes normalized to micrometres, without unit guessing."""

import hashlib
import json
import math
from typing import Any


def normalized_microns_per_pixel(metadata: dict[str, Any]) -> tuple[float, float] | None:
    factors = {
        "um": 1.0,
        "micrometer": 1.0,
        "micrometre": 1.0,
        "micron": 1.0,
        "nm": 0.001,
        "nanometer": 0.001,
        "nanometre": 0.001,
        "mm": 1000.0,
        "millimeter": 1000.0,
        "millimetre": 1000.0,
        "cm": 10000.0,
        "centimeter": 10000.0,
        "centimetre": 10000.0,
        "m": 1000000.0,
        "meter": 1000000.0,
        "metre": 1000000.0,
    }
    values = []
    for axis in ("X", "Y"):
        unit = metadata.get(f"physicalSize{axis}Unit")
        if unit is None:
            unit = metadata.get("physicalSizeUnit")
        if not isinstance(unit, str):
            return None
        unit = unit.strip().casefold().split(".")[-1].replace("µ", "u").replace("μ", "u")
        if unit.endswith("s"):
            unit = unit[:-1]
        factor = factors.get(unit)
        value = metadata.get(f"physicalSize{axis}")
        if factor is None or value is None or isinstance(value, bool):
            return None
        try:
            normalized = float(value) * factor
        except (TypeError, ValueError):
            return None
        if not math.isfinite(normalized) or normalized <= 0:
            return None
        values.append(normalized)
    return values[0], values[1]


def metadata_frame_digest(metadata: dict[str, Any]) -> str:
    """Identity of the original geometry and declared physical calibration."""
    frame = {
        key: metadata.get(key)
        for key in (
            "width",
            "height",
            "physicalSizeX",
            "physicalSizeY",
            "physicalSizeUnit",
            "physicalSizeXUnit",
            "physicalSizeYUnit",
        )
    }
    encoded = json.dumps(frame, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def public_geometry_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Public navigation needs declared geometry/calibration, never arbitrary metadata."""
    if not metadata:
        return None
    fields = (
        "width",
        "height",
        "physicalSizeX",
        "physicalSizeY",
        "physicalSizeUnit",
        "physicalSizeXUnit",
        "physicalSizeYUnit",
    )
    return {key: metadata[key] for key in fields if metadata.get(key) is not None}
