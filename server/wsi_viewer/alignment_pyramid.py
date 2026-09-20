"""Bounded component reads and registration using existing DZI tiles."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .alignment import (
    AlignmentRejected,
    RegistrationResult,
    _structure,
    register_pair,
    rescale_registration,
)


def read_region(
    path: Path, bounds: tuple[int, int, int, int], maximum: int = 4096
) -> tuple[Image.Image, tuple[int, int, int]]:
    """Read only intersecting tiles. Return pixels and exact pixel-to-slide affine.

    Coordinates follow DZI's integer power-of-two downsample, including at
    odd-sized slide edges; ratios of rounded image dimensions are not used.
    """
    if not 256 <= maximum <= 4096:
        raise ValueError("Region limit must be between 256 and 4096")
    root = ET.parse(path / "slide.dzi").getroot()
    size = next((child for child in root if child.tag.split("}")[-1] == "Size"), None)
    if size is None:
        raise OSError("Missing DZI dimensions")
    width, height = int(size.attrib["Width"]), int(size.attrib["Height"])
    left, top, right, bottom = bounds
    if not (0 <= left < right <= width and 0 <= top < bottom <= height):
        raise ValueError("Region is outside the slide")
    full_level = math.ceil(math.log2(max(width, height)))
    divisor = 1
    while (
        max(
            math.ceil(right / divisor) - left // divisor,
            math.ceil(bottom / divisor) - top // divisor,
        )
        > maximum
    ):
        divisor *= 2
    level = full_level - int(math.log2(divisor))
    x0, y0, x1, y1 = (
        left // divisor,
        top // divisor,
        math.ceil(right / divisor),
        math.ceil(bottom / divisor),
    )
    tile_size, overlap = int(root.attrib["TileSize"]), int(root.attrib.get("Overlap", "0"))
    result = Image.new("RGB", (x1 - x0, y1 - y0), "white")
    for row in range(y0 // tile_size, (y1 - 1) // tile_size + 1):
        for column in range(x0 // tile_size, (x1 - 1) // tile_size + 1):
            with Image.open(
                path / "slide_files" / str(level) / f"{column}_{row}.{root.attrib['Format']}"
            ) as source:
                tile = source.convert("RGB")
            origin_x = column * tile_size - (overlap if column else 0)
            origin_y = row * tile_size - (overlap if row else 0)
            crop_left, crop_top = max(x0, column * tile_size), max(y0, row * tile_size)
            crop_right, crop_bottom = (
                min(x1, (column + 1) * tile_size),
                min(y1, (row + 1) * tile_size),
            )
            result.paste(
                tile.crop(
                    (
                        crop_left - origin_x,
                        crop_top - origin_y,
                        crop_right - origin_x,
                        crop_bottom - origin_y,
                    )
                ),
                (crop_left - x0, crop_top - y0),
            )
    return result, (x0 * divisor, y0 * divisor, divisor)


def component_bounds(
    image: Image.Image, full_size: tuple[int, int]
) -> list[tuple[int, int, int, int]]:
    small = image.copy()
    small.thumbnail((2048, 2048))
    _, mask = _structure(np.asarray(small.convert("RGB")))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    scale_x, scale_y = full_size[0] / small.width, full_size[1] / small.height
    boxes = []
    for index in sorted(range(1, count), key=lambda i: stats[i, 4], reverse=True)[:4]:
        x, y, w, h, _ = (int(value) for value in stats[index])
        boxes.append(
            (
                max(0, int((x - 12) * scale_x)),
                max(0, int((y - 12) * scale_y)),
                min(full_size[0], math.ceil((x + w + 12) * scale_x)),
                min(full_size[1], math.ceil((y + h + 12) * scale_y)),
            )
        )
    return boxes


def register_components(
    reference_path: Path,
    moving_path: Path,
    reference_overview: Image.Image,
    moving_overview: Image.Image,
    reference_size: tuple[int, int],
    moving_size: tuple[int, int],
    progress: Callable[[int, int], None] | None = None,
) -> RegistrationResult:
    reference_boxes = component_bounds(reference_overview, reference_size)
    moving_boxes = component_bounds(moving_overview, moving_size)
    candidates = []
    attempted = 0
    total = len(reference_boxes) * len(moving_boxes)
    for mi, moving_box in enumerate(moving_boxes):
        moving, moving_frame = read_region(moving_path, moving_box)
        for ri, reference_box in enumerate(reference_boxes):
            reference, reference_frame = read_region(reference_path, reference_box)
            try:
                result = register_pair(reference, moving, max_dimension=4096)
                if result.status != "ready" or not result.triangles:
                    continue
                # Convert crop-local cells with the exact DZI sampling interval.
                rx, ry, rs = reference_frame
                mx, my, ms = moving_frame
                scaled = rescale_registration(
                    result,
                    reference_thumbnail_size=reference.size,
                    moving_thumbnail_size=moving.size,
                    reference_full_size=(reference.width * rs, reference.height * rs),
                    moving_full_size=(moving.width * ms, moving.height * ms),
                )

                def translate(points: list[list[float]], dx: int, dy: int) -> list[list[float]]:
                    return [[x + dx, y + dy] for x, y in points]

                controls = [
                    {
                        **point,
                        "moving": translate([point["moving"]], mx, my)[0],
                        "reference": translate([point["reference"]], rx, ry)[0],
                        "provenance": "pyramid-component-feature",
                    }
                    for point in scaled.control_points
                ]
                cells = [
                    {
                        **cell,
                        "moving": translate(cell["moving"], mx, my),
                        "reference": translate(cell["reference"], rx, ry),
                        "provenance": "pyramid-component-feature",
                    }
                    for cell in scaled.triangles
                ]
                transform = np.asarray(scaled.moving_to_reference)
                transform[:, 2] += np.array([rx, ry]) - transform[:, :2] @ np.array([mx, my])
                candidates.append(
                    (
                        mi,
                        ri,
                        replace(
                            scaled,
                            moving_to_reference=transform.tolist(),
                            control_points=controls,
                            triangles=cells,
                        ),
                    )
                )
            except AlignmentRejected:
                pass
            finally:
                attempted += 1
                if progress:
                    progress(attempted, total)
    # Multiple plausible assignments are ambiguous, even if one has more matches.
    accepted = [
        (mi, ri, result)
        for mi, ri, result in candidates
        if sum(other_mi == mi for other_mi, _, _ in candidates) == 1
        and sum(other_ri == ri for _, other_ri, _ in candidates) == 1
    ]
    if not accepted:
        raise AlignmentRejected(
            f"No unambiguous high-resolution component match ({attempted} candidate pairs checked)"
        )
    controls = [point for _, _, result in accepted for point in result.control_points]
    cells = [cell for _, _, result in accepted for cell in result.triangles]

    def support(key: str) -> tuple[float, float, float, float]:
        points = np.asarray([point[key] for point in controls])
        return (
            float(points[:, 0].min()),
            float(points[:, 1].min()),
            float(points[:, 0].max()),
            float(points[:, 1].max()),
        )

    best = max(accepted, key=lambda item: len(item[2].triangles))[2]
    return replace(
        best,
        control_points=controls,
        triangles=cells,
        moving_support=support("moving"),
        reference_support=support("reference"),
        inlier_count=sum(result.inlier_count for _, _, result in accepted),
        match_count=sum(result.match_count for _, _, result in accepted),
        evidence={
            "mode": "matched-regions",
            "featureMatchCount": len(controls),
            "anatomicalMatchCount": 0,
            "triangleCount": len(cells),
            "componentPairsChecked": attempted,
            "acceptedComponents": len(accepted),
            "withheldCheck": "pending-independent-landmarks",
            "source": "bounded-pyramid-components",
        },
    )
