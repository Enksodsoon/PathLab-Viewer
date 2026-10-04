"""Small manual corrections with explicit pixel and tissue support.

These maps are navigation aids, never evidence of anatomical qualification.
The slide pyramids and canonical automatic maps remain unchanged.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .alignment import AlignmentRejected, map_registration_point
from .alignment_calibration import normalized_microns_per_pixel
from .alignment_pyramid import read_region
from .models import Slide


class RegionRejected(ValueError):
    pass


def slide_version(slide: Slide) -> str:
    """Bind content and the original pixel/physical frame to an opaque snapshot.

    Without a checksum, the model's general updated_at is the only persisted
    revision marker. Cosmetic edits conservatively invalidate that fallback;
    pixel changes must advance it. Checksum-bound maps ignore cosmetic edits.
    """
    content = slide.sha256
    if not content:
        timestamp = slide.updated_at
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        content = f"updated:{timestamp.astimezone(UTC).isoformat()}"
    return content_geometry_version(content, slide.slide_metadata or {})


def content_geometry_version(content: str, metadata: dict[str, Any]) -> str:
    def safe(value: Any) -> Any:
        if isinstance(value, float) and not math.isfinite(value):
            return str(value)
        return value

    frame = {
        key: safe(metadata.get(key))
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
    encoded = json.dumps(
        {"schema": "alignment-source/1", "content": content, "frame": frame},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return "alignment:" + hashlib.sha256(encoded).hexdigest()


def validate_anchors(member_ids: list[str], reference_id: str, anchors: dict[str, str]) -> None:
    if any(
        source not in member_ids or target not in member_ids for source, target in anchors.items()
    ):
        raise RegionRejected("ANCHOR_NOT_MEMBER")
    if reference_id in anchors:
        raise RegionRejected("REFERENCE_ANCHOR_INVALID")
    for source in member_ids:
        seen: set[str] = set()
        current = source
        while current != reference_id:
            if current in seen:
                raise RegionRejected("ANCHOR_CYCLE")
            seen.add(current)
            target = anchors.get(current, reference_id)
            if target == current:
                raise RegionRejected("ANCHOR_SELF")
            current = target


def _size(metadata: dict[str, Any]) -> tuple[float, float]:
    try:
        width, height = float(metadata["width"]), float(metadata["height"])
    except (KeyError, TypeError, ValueError) as exc:
        raise RegionRejected("REGION_DIMENSIONS_UNAVAILABLE") from exc
    if not all(math.isfinite(value) and value > 0 for value in (width, height)):
        raise RegionRejected("REGION_DIMENSIONS_UNAVAILABLE")
    return width, height


def _calibration(metadata: dict[str, Any]) -> np.ndarray[Any, Any] | None:
    values = normalized_microns_per_pixel(metadata)
    return np.asarray(values) if values is not None else None


def _local_linear(
    previous: dict[str, Any] | None, point: list[float]
) -> np.ndarray[Any, Any] | None:
    if not previous or previous.get("status") not in {"ready", "approximate"}:
        return None
    cells = (previous.get("triangles") or []) + (previous.get("overviewTriangles") or [])
    fallback = previous.get("overviewFallback") or {}
    cells += fallback.get("overviewTriangles") or []
    for cell in cells:
        registration = {"triangles": [cell]}
        try:
            map_registration_point(registration, *point)
        except (AlignmentRejected, KeyError, ValueError, np.linalg.LinAlgError):
            continue
        source, target = np.asarray(cell["moving"]), np.asarray(cell["reference"])
        if source.shape != (3, 2) or target.shape != (3, 2):
            continue
        try:
            matrix = np.linalg.solve(np.column_stack([source, np.ones(3)]), target).T
        except np.linalg.LinAlgError:
            continue
        linear = matrix[:, :2]
        if np.isfinite(linear).all() and abs(np.linalg.det(linear)) > 1e-8:
            return linear
    return None


def _tissue(
    path: Path, bounds: tuple[int, int, int, int]
) -> tuple[np.ndarray[Any, Any], tuple[int, int, int]]:
    image, frame = read_region(path, bounds, maximum=512)
    rgb = np.asarray(image.convert("RGB"), dtype=np.int16)
    darkest = rgb.min(axis=2)
    chroma = rgb.max(axis=2) - darkest
    mask = ((darkest < 205) | ((darkest < 225) & (chroma > 8))).astype(np.uint8)
    # A conservative margin around glass avoids interpolation onto unsupported pixels.
    return cv2.erode(mask, np.ones((3, 3), np.uint8)), frame


def _polygon_supported(
    points: np.ndarray[Any, Any], mask: np.ndarray[Any, Any], frame: tuple[int, int, int]
) -> bool:
    x, y, divisor = frame
    local = (points - np.asarray([x, y])) / divisor
    if (
        (local < 0).any()
        or (local[:, 0] >= mask.shape[1]).any()
        or (local[:, 1] >= mask.shape[0]).any()
    ):
        return False
    selected = np.zeros_like(mask)
    cv2.fillConvexPoly(selected, np.rint(local).astype(np.int32), 1)
    return bool(selected.any() and np.all(mask[selected != 0] != 0))


def build_region_registration(
    *,
    source_metadata: dict[str, Any],
    target_metadata: dict[str, Any],
    source_bounds: list[float],
    moving_points: list[tuple[float, float]],
    reference_points: list[tuple[float, float]],
    source_path: Path,
    target_path: Path,
    source_version: str,
    target_version: str,
    target_slide_id: str,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_size, target_size = _size(source_metadata), _size(target_metadata)
    bounds = np.asarray(source_bounds, dtype=np.float64)
    if bounds.shape != (4,) or not np.isfinite(bounds).all():
        raise RegionRejected("REGION_BOUNDS_INVALID")
    left, top, width, height = bounds
    if (
        left < 0
        or top < 0
        or width < 2
        or height < 2
        or left + width > source_size[0]
        or top + height > source_size[1]
    ):
        raise RegionRejected("REGION_BOUNDS_INVALID")
    moving, reference = (
        np.asarray(moving_points, dtype=np.float64),
        np.asarray(reference_points, dtype=np.float64),
    )
    if moving.shape != reference.shape or moving.shape not in {(1, 2), (2, 2)}:
        raise RegionRejected("LANDMARK_COUNT_MISMATCH")
    if not np.isfinite(moving).all() or not np.isfinite(reference).all():
        raise RegionRejected("LANDMARK_NONFINITE")
    for points, size in ((moving, source_size), (reference, target_size)):
        if (points < 0).any() or (points >= np.asarray(size)).any():
            raise RegionRejected("LANDMARK_OUTSIDE_SLIDE")
    if (moving < bounds[:2]).any() or (moving > bounds[:2] + bounds[2:]).any():
        raise RegionRejected("LANDMARK_OUTSIDE_REGION")
    source_mpp, target_mpp = _calibration(source_metadata), _calibration(target_metadata)
    calibrated = source_mpp is not None and target_mpp is not None
    source_units, target_units = np.ones(2), np.ones(2)
    if source_mpp is not None and target_mpp is not None:
        source_units, target_units = source_mpp, target_mpp
    linear = _local_linear(previous, moving[0].tolist()) if len(moving) == 1 else None
    basis = (
        "compatible-local-map"
        if linear is not None
        else "physical-calibration"
        if calibrated
        else "pixel-identity"
    )
    if len(moving) == 1:
        if linear is None:
            linear = np.diag(source_units / target_units)
    else:
        if (
            np.linalg.norm(moving[1] - moving[0]) < 1
            or np.linalg.norm(reference[1] - reference[0]) < 1
        ):
            raise RegionRejected("LANDMARKS_DEGENERATE")
        a, b = (moving[1] - moving[0]) * source_units, (reference[1] - reference[0]) * target_units
        denominator = float(a @ a)
        real, imaginary = float(a @ b) / denominator, float(a[0] * b[1] - a[1] * b[0]) / denominator
        physical = np.asarray([[real, -imaginary], [imaginary, real]])
        linear = np.diag(1 / target_units) @ physical @ np.diag(source_units)
        basis = "physical-similarity" if calibrated else "pixel-similarity"
    transform = np.column_stack([linear, reference[0] - linear @ moving[0]])
    if not np.isfinite(transform).all() or abs(np.linalg.det(linear)) < 1e-8:
        raise RegionRejected("LANDMARKS_DEGENERATE")
    basis_version = None
    if len(moving) == 1:
        encoded_basis = json.dumps(
            {"schema": "alignment-basis/1", "basis": basis, "linear": linear.tolist()},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        basis_version = "alignment-basis:" + hashlib.sha256(encoded_basis).hexdigest()
    corners = np.asarray(
        [[left, top], [left + width, top], [left + width, top + height], [left, top + height]]
    )
    projected = corners @ linear.T + transform[:, 2]
    target_low = np.maximum(np.floor(projected.min(axis=0)), 0).astype(int)
    target_high = np.minimum(np.ceil(projected.max(axis=0)) + 1, target_size).astype(int)
    if (target_high <= target_low).any():
        raise RegionRejected("REGION_SUPPORT_UNAVAILABLE")
    # Include the upper boundary's raster sample; crop offsets come from read_region's exact frame.
    source_high = np.minimum(np.ceil(bounds[:2] + bounds[2:]) + 1, source_size).astype(int)
    source_mask, source_frame = _tissue(
        source_path, (math.floor(left), math.floor(top), *source_high)
    )
    target_mask, target_frame = _tissue(target_path, (*target_low, *target_high))
    triangles: list[dict[str, Any]] = []
    xs, ys = np.linspace(left, left + width, 17), np.linspace(top, top + height, 17)
    for x0, x1 in zip(xs[:-1], xs[1:], strict=True):
        for y0, y1 in zip(ys[:-1], ys[1:], strict=True):
            cell = np.asarray([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
            mapped = cell @ linear.T + transform[:, 2]
            if not _polygon_supported(cell, source_mask, source_frame) or not _polygon_supported(
                mapped, target_mask, target_frame
            ):
                continue
            for indices in ([0, 1, 2], [0, 2, 3]):
                triangles.append(
                    {
                        "moving": cell[indices].tolist(),
                        "reference": mapped[indices].tolist(),
                        "confidence": 0.5,
                        "provenance": "manual-region",
                    }
                )
    if not triangles:
        raise RegionRejected("REGION_SUPPORT_UNAVAILABLE")
    registration = {
        "status": "approximate",
        "provenance": "manual-region",
        "sourceVersion": source_version,
        "anchorVersion": target_version,
        "anchorSlideId": target_slide_id,
        "coordinateReferenceId": target_slide_id,
        "movingToReference": transform.tolist(),
        "triangles": triangles,
        "overviewTriangles": triangles,
        "supportPolygons": {
            "moving": [t["moving"] for t in triangles],
            "reference": [t["reference"] for t in triangles],
        },
        "controlPoints": [
            {
                "moving": s.tolist(),
                "reference": t.tolist(),
                "errorPixels": 0,
                "provenance": "manual-region",
            }
            for s, t in zip(moving, reference, strict=True)
        ],
        "confidence": 0.5,
        "evidence": {
            "mode": "manual-region",
            "basis": basis,
            "calibrated": bool(calibrated),
            "anatomicallyQualified": False,
            **({"basisVersion": basis_version} if basis_version is not None else {}),
        },
    }
    for point in moving:
        try:
            map_registration_point(registration, *point)
        except AlignmentRejected as exc:
            raise RegionRejected("LANDMARK_ON_GLASS") from exc
    return registration
