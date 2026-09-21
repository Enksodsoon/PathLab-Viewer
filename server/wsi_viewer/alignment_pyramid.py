"""Bounded component reads and registration using existing DZI tiles."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .alignment import (
    AlignmentRejected,
    RegistrationResult,
    _mask_seed,
    _registration_triangles,
    _structure,
    register_pair,
    rescale_registration,
)


@dataclass(frozen=True)
class _ComponentMap:
    transform: list[list[float]]
    overview_cells: list[dict[str, Any]]
    verified_cells: list[dict[str, Any]]
    supported_cells: list[dict[str, Any]]
    intensity_score: float
    overlap: float
    flow_control_count: int
    flow_cycle_p95: float
    patch_ncc_median: float
    patch_discrimination_median: float
    layout_score: float = 0.0
    feature_inliers: int = 0
    feature_spread: float = 0.0

    @property
    def feature_identity_score(self) -> float:
        """Bounded KAZE support used only to distinguish component candidates."""
        return min(1.0, self.feature_inliers / 50.0) * math.sqrt(
            max(0.0, min(1.0, self.feature_spread))
        )

    @property
    def identity_score(self) -> float:
        if not self.flow_control_count:
            return 0.0
        verified_ratio = len(self.verified_cells) / self.flow_control_count
        return (
            verified_ratio
            + 0.5 * max(0.0, self.patch_ncc_median)
            + 0.5 * max(0.0, self.patch_discrimination_median)
            + 0.25 * self.feature_identity_score
        )


def _layout_consistency(
    transform: list[list[float]],
    reference_boxes: list[tuple[int, int, int, int]],
    moving_boxes: list[tuple[int, int, int, int]],
    reference_size: tuple[int, int],
) -> float:
    """Score whether one component map also preserves the slide fragment layout.

    This is assignment evidence, not an anatomical match.  Only the largest
    common number of fragments participate so small stain-specific debris does
    not penalize a serial section.  A symmetric nearest-neighbour distance
    penalizes transforms that align one core while moving the remaining cores
    to blank or unrelated locations.
    """
    count = min(len(reference_boxes), len(moving_boxes), 4)
    if count < 2:
        return 0.0

    def centers(boxes: list[tuple[int, int, int, int]]) -> np.ndarray:
        return np.asarray(
            [
                [(left + right) / 2, (top + bottom) / 2]
                for left, top, right, bottom in boxes[:count]
            ],
            dtype=np.float64,
        )

    reference_centers = centers(reference_boxes)
    moving_centers = centers(moving_boxes)
    affine = np.asarray(transform, dtype=np.float64)
    projected = moving_centers @ affine[:, :2].T + affine[:, 2]
    distances = np.linalg.norm(
        projected[:, None, :] - reference_centers[None, :, :], axis=2
    )
    symmetric_error = (
        float(np.mean(np.min(distances, axis=1)))
        + float(np.mean(np.min(distances, axis=0)))
    ) / 2
    diagonal = max(1.0, math.hypot(*reference_size))
    return float(math.exp(-symmetric_error / (0.1 * diagonal)))


def _component_identity_is_clear(
    candidate: _ComponentMap, alternatives: list[_ComponentMap]
) -> bool:
    """Require internal evidence, with layout used only as a conservative tie-breaker."""
    if not alternatives:
        return True
    alternative_score = max(item.identity_score for item in alternatives)
    if (
        candidate.identity_score >= alternative_score * 1.25
        and candidate.identity_score - alternative_score >= 0.12
    ):
        return True
    alternative_layout = max(item.layout_score for item in alternatives)
    return (
        candidate.layout_score >= 0.75
        and candidate.layout_score - alternative_layout >= 0.35
        and candidate.identity_score >= alternative_score * 1.12
        and candidate.identity_score - alternative_score >= 0.04
    )


def _candidate_component_pairs(
    reference_overview: Image.Image,
    moving_overview: Image.Image,
    reference_boxes: list[tuple[int, int, int, int]],
    moving_boxes: list[tuple[int, int, int, int]],
    reference_size: tuple[int, int],
    moving_size: tuple[int, int],
) -> tuple[list[tuple[int, int]], set[tuple[int, int]]]:
    """Pair fragments using the whole-slide layout without claiming anatomy."""
    _, reference_mask = _structure(np.asarray(reference_overview.convert("RGB")))
    _, moving_mask = _structure(np.asarray(moving_overview.convert("RGB")))
    seed, seed_overlap = _mask_seed(reference_mask, moving_mask)
    reference_scale = np.asarray(
        [
            reference_overview.width / reference_size[0],
            reference_overview.height / reference_size[1],
        ]
    )
    moving_scale = np.asarray(
        [moving_overview.width / moving_size[0], moving_overview.height / moving_size[1]]
    )
    reference_centers = (
        np.asarray(
            [
                [(left + right) / 2, (top + bottom) / 2]
                for left, top, right, bottom in reference_boxes
            ]
        )
        * reference_scale
    )
    moving_centers = (
        np.asarray(
            [[(left + right) / 2, (top + bottom) / 2] for left, top, right, bottom in moving_boxes]
        )
        * moving_scale
    )
    projected = cv2.transform(moving_centers.astype(np.float32)[:, None, :], seed)[:, 0, :]
    distances = np.linalg.norm(projected[:, None, :] - reference_centers[None, :, :], axis=2)
    pairs: list[tuple[int, int]] = []
    layout_resolved: set[tuple[int, int]] = set()
    diagonal = max(1.0, math.hypot(reference_overview.width, reference_overview.height))
    for moving_index in range(len(moving_boxes)):
        reference_index = int(np.argmin(distances[moving_index]))
        if int(np.argmin(distances[:, reference_index])) != moving_index:
            continue
        pair = (moving_index, reference_index)
        pairs.append(pair)
        ordered = np.sort(distances[moving_index])
        best = float(ordered[0]) / diagonal
        margin = float(ordered[1] - ordered[0]) / diagonal if len(ordered) > 1 else 0.0
        if (
            len(reference_boxes) >= 2
            and len(moving_boxes) >= 2
            and seed_overlap >= 0.2
            and 0.005 < best <= 0.08
            and margin >= 0.12
        ):
            layout_resolved.add(pair)
    return pairs, layout_resolved


def _approximate_component_map(
    reference: Image.Image,
    moving: Image.Image,
    reference_frame: tuple[int, int, int],
    moving_frame: tuple[int, int, int],
) -> _ComponentMap | None:
    """Fit stain-independent component shape and return explicitly approximate cells."""
    reference_rgb = np.asarray(reference.convert("RGB"))
    moving_rgb = np.asarray(moving.convert("RGB"))

    def cropped_structure(image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        # Whole-slide segmentation rejects edge-touching components to suppress
        # scanner borders. A deliberately cropped component can validly touch
        # its crop edge, so surround it with known white context first.
        rgb = np.asarray(image.convert("RGB"))
        padding = max(24, min(rgb.shape[:2]) // 40)
        padded = np.pad(
            rgb,
            ((padding, padding), (padding, padding), (0, 0)),
            mode="constant",
            constant_values=255,
        )
        structure, mask = _structure(padded)
        return (
            structure[padding:-padding, padding:-padding],
            mask[padding:-padding, padding:-padding],
        )

    reference_structure, reference_mask = cropped_structure(reference)
    moving_structure, moving_mask = cropped_structure(moving)
    seed, initial_overlap = _mask_seed(reference_mask, moving_mask)
    inverse_seed = cv2.invertAffineTransform(seed).astype(np.float32)
    try:
        score = 0.0
        for sigma in (12.0, 6.0, 3.0):
            fixed = cv2.GaussianBlur(reference_structure, (0, 0), sigma).astype(np.float32) / 255
            floating = cv2.GaussianBlur(moving_structure, (0, 0), sigma).astype(np.float32) / 255
            score, inverse_seed = cv2.findTransformECC(  # type: ignore[call-overload]
                fixed,
                floating,
                inverse_seed,
                cv2.MOTION_AFFINE,
                (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 80, 1e-5),
                None,
                5,
            )
    except cv2.error:
        return None
    transform = cv2.invertAffineTransform(inverse_seed)
    determinant = float(np.linalg.det(transform[:, :2]))
    warped_mask = cv2.warpAffine(
        moving_mask, transform, (reference_mask.shape[1], reference_mask.shape[0])
    )
    intersection = int(np.count_nonzero((warped_mask > 0) & (reference_mask > 0)))
    total_tissue = int(np.count_nonzero(warped_mask)) + int(np.count_nonzero(reference_mask))
    overlap = 2 * intersection / max(1, total_tissue)
    if score < 0.78 or overlap < max(0.62, initial_overlap * 0.85) or not 0.25 <= determinant <= 4:
        return None

    feature_inliers, feature_spread = _feature_identity_evidence(
        reference_rgb,
        reference_mask,
        moving_rgb,
        moving_mask,
        transform,
    )

    controls, flow_cycle_p95 = _flow_refined_controls(
        reference_structure,
        reference_mask,
        moving_structure,
        moving_mask,
        transform,
    )
    provenance = "approximate-structural-flow"
    if len(controls) < 12:
        # Build small cells only inside the corresponding tissue component.
        # These improve overview navigation but remain separate from anatomical evidence.
        spacing = max(48, min(moving_mask.shape) // 8)
        controls = []
        for y in range(spacing // 2, moving_mask.shape[0], spacing):
            for x in range(spacing // 2, moving_mask.shape[1], spacing):
                if not moving_mask[y, x]:
                    continue
                target = transform[:, :2] @ np.asarray([x, y]) + transform[:, 2]
                tx, ty = int(round(target[0])), int(round(target[1]))
                if not (
                    0 <= tx < reference_mask.shape[1]
                    and 0 <= ty < reference_mask.shape[0]
                ):
                    continue
                if not reference_mask[ty, tx]:
                    continue
                controls.append(
                    {
                        "moving": [float(x), float(y)],
                        "reference": [float(target[0]), float(target[1])],
                        "errorPixels": 0.0,
                    }
                )
        provenance = "approximate-intensity-shape"
        flow_cycle_p95 = -1.0
    cells = _registration_triangles(
        controls,
        moving_mask=moving_mask,
        reference_mask=reference_mask,
    )
    if not cells:
        return None
    verified_cells, patch_ncc_median, patch_discrimination_median = (
        _flow_cell_evidence(cells, reference_structure, moving_structure)
        if provenance == "approximate-structural-flow"
        else ([], -1.0, -1.0)
    )
    supported_cells = _expand_verified_support(cells, verified_cells)
    rx, ry, reference_divisor = reference_frame
    mx, my, moving_divisor = moving_frame
    linear = (
        np.diag([reference_divisor, reference_divisor])
        @ transform[:, :2]
        @ np.diag([1 / moving_divisor, 1 / moving_divisor])
    )
    offset = (
        np.asarray([rx, ry]) + reference_divisor * transform[:, 2] - linear @ np.asarray([mx, my])
    )
    full_transform = np.column_stack([linear, offset])
    overview_cells: list[dict[str, Any]] = []
    full_verified_cells: list[dict[str, Any]] = []
    full_supported_cells: list[dict[str, Any]] = []
    for cell in cells:
        overview_cells.append(
            {
                "moving": [
                    [mx + moving_divisor * x, my + moving_divisor * y] for x, y in cell["moving"]
                ],
                "reference": [
                    [rx + reference_divisor * x, ry + reference_divisor * y]
                    for x, y in cell["reference"]
                ],
                "provenance": provenance,
            }
        )
    for cell in verified_cells:
        full_verified_cells.append(
            {
                "moving": [
                    [mx + moving_divisor * x, my + moving_divisor * y] for x, y in cell["moving"]
                ],
                "reference": [
                    [rx + reference_divisor * x, ry + reference_divisor * y]
                    for x, y in cell["reference"]
                ],
                "maxResidualPixels": cell.get("maxResidualPixels", flow_cycle_p95),
                "provenance": "structural-flow-patch",
            }
        )
    verified_ids = {id(item) for item in verified_cells}
    for cell in supported_cells:
        full_supported_cells.append(
            {
                "moving": [
                    [mx + moving_divisor * x, my + moving_divisor * y]
                    for x, y in cell["moving"]
                ],
                "reference": [
                    [rx + reference_divisor * x, ry + reference_divisor * y]
                    for x, y in cell["reference"]
                ],
                "maxResidualPixels": cell.get("maxResidualPixels", flow_cycle_p95),
                "provenance": (
                    "structural-flow-patch"
                    if id(cell) in verified_ids
                    else "structural-flow-neighbor"
                ),
            }
        )
    return _ComponentMap(
        transform=full_transform.tolist(),
        overview_cells=overview_cells,
        verified_cells=full_verified_cells,
        supported_cells=full_supported_cells,
        intensity_score=float(score),
        overlap=float(overlap),
        flow_control_count=(
            len(controls) if provenance == "approximate-structural-flow" else 0
        ),
        flow_cycle_p95=flow_cycle_p95,
        patch_ncc_median=patch_ncc_median,
        patch_discrimination_median=patch_discrimination_median,
        feature_inliers=feature_inliers,
        feature_spread=feature_spread,
    )


def _gradient_feature(structure: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(structure, (0, 0), 1.5)
    horizontal = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    vertical = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(horizontal, vertical)
    normalized = cv2.normalize(  # type: ignore[call-overload]
        magnitude, None, 0, 255, cv2.NORM_MINMAX
    )
    return np.asarray(normalized, dtype=np.uint8)


def _optical_density_gray(rgb: np.ndarray) -> np.ndarray:
    """Return a stain-tolerant optical-density image using NumPy and OpenCV only."""
    density = -np.log10(np.clip(rgb.astype(np.float32) / 255.0, 1 / 255, 1))
    gray = np.mean(density, axis=2)
    upper = float(np.percentile(gray, 95))
    return np.asarray(np.clip(gray * 255 / max(upper, 1e-6), 0, 255), dtype=np.uint8)


def _feature_identity_evidence(
    reference_rgb: np.ndarray,
    reference_mask: np.ndarray,
    moving_rgb: np.ndarray,
    moving_mask: np.ndarray,
    moving_to_reference: np.ndarray,
) -> tuple[int, float]:
    """Measure distributed, mutually matched KAZE features after coarse alignment.

    This is candidate-identity evidence, not an anatomical registration map.
    It follows the lightweight optical-density/KAZE strategy used by HISAlign,
    while keeping the default worker free of its Torch, SimpleITK, and
    scikit-image runtime dependencies.
    """
    maximum = 1200

    def bounded(image: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        scale = min(1.0, maximum / max(image.shape[:2]))
        size = (
            max(1, round(image.shape[1] * scale)),
            max(1, round(image.shape[0] * scale)),
        )
        gray = _optical_density_gray(image)
        return (
            cv2.resize(gray, size, interpolation=cv2.INTER_AREA),
            cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST),
            scale,
        )

    reference, reference_small_mask, reference_scale = bounded(
        reference_rgb, reference_mask
    )
    moving, moving_small_mask, moving_scale = bounded(moving_rgb, moving_mask)
    transform = np.asarray(moving_to_reference, dtype=np.float64).copy()
    transform[:, :2] *= reference_scale / moving_scale
    transform[:, 2] *= reference_scale
    warped = cv2.warpAffine(
        moving,
        transform.astype(np.float32),
        (reference.shape[1], reference.shape[0]),
        borderValue=0,
    )
    warped_mask = cv2.warpAffine(
        moving_small_mask,
        transform.astype(np.float32),
        (reference.shape[1], reference.shape[0]),
        flags=cv2.INTER_NEAREST,
    )
    valid = np.asarray(
        (reference_small_mask > 0) & (warped_mask > 0), dtype=np.uint8
    ) * 255
    if cv2.countNonZero(valid) < max(512, valid.size // 200):
        return 0, 0.0

    detector = cv2.KAZE_create()  # type: ignore[attr-defined]
    reference_keypoints, reference_descriptors = detector.detectAndCompute(reference, valid)
    moving_keypoints, moving_descriptors = detector.detectAndCompute(warped, valid)
    if reference_descriptors is None or moving_descriptors is None:
        return 0, 0.0
    if len(reference_descriptors) < 4 or len(moving_descriptors) < 4:
        return 0, 0.0

    matcher = cv2.BFMatcher(cv2.NORM_L2)

    def ratio_matches(first: np.ndarray, second: np.ndarray) -> list[cv2.DMatch]:
        return [
            best
            for best, alternate in matcher.knnMatch(first, second, k=2)
            if best.distance < 0.8 * alternate.distance
        ]

    forward = ratio_matches(reference_descriptors, moving_descriptors)
    reverse = {
        (match.trainIdx, match.queryIdx)
        for match in ratio_matches(moving_descriptors, reference_descriptors)
    }
    mutual = [
        match for match in forward if (match.queryIdx, match.trainIdx) in reverse
    ]
    if len(mutual) < 4:
        return 0, 0.0
    source = np.asarray(
        [reference_keypoints[match.queryIdx].pt for match in mutual], dtype=np.float32
    )
    target = np.asarray(
        [moving_keypoints[match.trainIdx].pt for match in mutual], dtype=np.float32
    )
    _, inlier_mask = cv2.findHomography(source, target, cv2.USAC_MAGSAC, 5.0)
    if inlier_mask is None:
        return 0, 0.0
    inlier_points = source[inlier_mask.ravel() > 0]
    if len(inlier_points) < 4:
        return len(inlier_points), 0.0
    valid_points = cv2.findNonZero(valid)
    if valid_points is None:
        return len(inlier_points), 0.0
    x, y, width, height = cv2.boundingRect(valid_points)
    del x, y
    extent = np.ptp(inlier_points, axis=0)
    spread = float(extent[0] * extent[1] / max(1, width * height))
    return len(inlier_points), min(1.0, spread)


def _flow_cell_evidence(
    cells: list[dict[str, Any]],
    reference_structure: np.ndarray,
    moving_structure: np.ndarray,
) -> tuple[list[dict[str, Any]], float, float]:
    """Withhold an affine-warped patch check from optical-flow estimation.

    A cycle-consistent flow can still follow the wrong repeated texture.  Each
    triangle is therefore tested on gradient patches after applying its local
    affine map, and against four displaced reference patches.  The metrics are
    evidence only: component assignment must also be disambiguated before a
    map can be promoted from approximate navigation.
    """
    reference_feature = _gradient_feature(reference_structure)
    moving_feature = _gradient_feature(moving_structure)
    # A 97 px patch at the bounded component level represents the same
    # mesoscopic field as the 49 px withheld patch at the 2x overview level.
    # This is large enough to compare glands/cores across serial sections
    # without relying on individual nuclei surviving the cut.
    radius = 48
    displacement = 100
    accepted: list[dict[str, Any]] = []
    scores: list[float] = []
    discriminations: list[float] = []

    def correlation(first: np.ndarray, second: np.ndarray) -> float:
        left = first.astype(np.float32) - float(np.mean(first))
        right = second.astype(np.float32) - float(np.mean(second))
        denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
        return float(np.sum(left * right) / denominator) if denominator > 1e-6 else -1.0

    for cell in cells:
        moving = np.asarray(cell["moving"], dtype=np.float32)
        reference = np.asarray(cell["reference"], dtype=np.float32)
        inverse = cv2.invertAffineTransform(cv2.getAffineTransform(moving, reference))
        center_x, center_y = np.rint(np.mean(reference, axis=0)).astype(int)
        if not (
            radius <= center_x < reference_feature.shape[1] - radius
            and radius <= center_y < reference_feature.shape[0] - radius
        ):
            continue
        rows, columns = np.mgrid[
            center_y - radius : center_y + radius + 1,
            center_x - radius : center_x + radius + 1,
        ].astype(np.float32)
        map_x = np.asarray(
            inverse[0, 0] * columns + inverse[0, 1] * rows + inverse[0, 2],
            dtype=np.float32,
        )
        map_y = np.asarray(
            inverse[1, 0] * columns + inverse[1, 1] * rows + inverse[1, 2],
            dtype=np.float32,
        )
        if (
            float(np.min(map_x)) < 0
            or float(np.min(map_y)) < 0
            or float(np.max(map_x)) >= moving_feature.shape[1] - 1
            or float(np.max(map_y)) >= moving_feature.shape[0] - 1
        ):
            continue
        moving_patch = cv2.remap(
            moving_feature,
            map_x,
            map_y,
            cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=0,
        )
        reference_patch = reference_feature[
            center_y - radius : center_y + radius + 1,
            center_x - radius : center_x + radius + 1,
        ]
        score = correlation(moving_patch, reference_patch)
        displaced: list[float] = []
        for delta_x, delta_y in (
            (displacement, 0),
            (-displacement, 0),
            (0, displacement),
            (0, -displacement),
        ):
            displaced_x, displaced_y = center_x + delta_x, center_y + delta_y
            if (
                radius <= displaced_x < reference_feature.shape[1] - radius
                and radius <= displaced_y < reference_feature.shape[0] - radius
            ):
                displaced.append(
                    correlation(
                        moving_patch,
                        reference_feature[
                            displaced_y - radius : displaced_y + radius + 1,
                            displaced_x - radius : displaced_x + radius + 1,
                        ],
                    )
                )
        if not displaced:
            continue
        discrimination = score - float(np.median(displaced))
        scores.append(score)
        discriminations.append(discrimination)
        if score >= 0.18 and discrimination >= 0.12:
            accepted.append(cell)
    return (
        accepted,
        float(np.median(scores)) if scores else -1.0,
        float(np.median(discriminations)) if discriminations else -1.0,
    )


def _expand_verified_support(
    cells: list[dict[str, Any]], verified: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Extend directly verified triangles through continuous low-residual flow.

    Every added cell shares a complete edge with accepted support and comes
    from the same cycle-consistent flow controls. Spatially sparse evidence is
    limited to one ring; distributed evidence may cover its connected tissue
    region without extrapolating across blank gaps.
    """
    if not verified:
        return []

    def vertices(cell: dict[str, Any]) -> set[tuple[int, int]]:
        return {
            (round(float(x) * 1000), round(float(y) * 1000))
            for x, y in cell["moving"]
        }

    accepted_ids = {id(cell) for cell in verified}
    accepted_vertices = [vertices(cell) for cell in verified]
    verified_residuals = [
        float(cell.get("maxResidualPixels", 0.0)) for cell in verified
    ]
    residual_limit = max(4.0, float(np.percentile(verified_residuals, 95)) * 1.25)
    all_points = np.asarray(
        [point for cell in cells for point in cell["moving"]], dtype=np.float64
    )
    verified_points = np.asarray(
        [point for cell in verified for point in cell["moving"]], dtype=np.float64
    )

    def box_area(points: np.ndarray) -> float:
        extent = np.ptp(points, axis=0)
        return float(extent[0] * extent[1])

    spatial_coverage = box_area(verified_points) / max(1.0, box_area(all_points))
    distributed = len(verified) >= 8 and spatial_coverage >= 0.2
    expanded = list(verified)
    remaining = [cell for cell in cells if id(cell) not in accepted_ids]
    while remaining:
        added: list[dict[str, Any]] = []
        for cell in remaining:
            cell_vertices = vertices(cell)
            if float(cell.get("maxResidualPixels", 0.0)) > residual_limit:
                continue
            if any(len(cell_vertices & existing) >= 2 for existing in accepted_vertices):
                added.append(cell)
        if not added:
            break
        expanded.extend(added)
        if not distributed:
            break
        accepted_vertices.extend(vertices(cell) for cell in added)
        added_ids = {id(cell) for cell in added}
        remaining = [cell for cell in remaining if id(cell) not in added_ids]
    return expanded


def _flow_refined_controls(
    reference_structure: np.ndarray,
    reference_mask: np.ndarray,
    moving_structure: np.ndarray,
    moving_mask: np.ndarray,
    moving_to_reference: np.ndarray,
) -> tuple[list[dict[str, Any]], float]:
    """Return bounded, cycle-consistent mesoscopic correspondences.

    The flow operates after the accepted component affine and at half scale to
    suppress cell-level stain differences. It never upgrades a map to accurate
    anatomical registration; it only refines approximate navigation.
    """
    height, width = reference_structure.shape
    warped_structure = cv2.warpAffine(moving_structure, moving_to_reference, (width, height))
    warped_mask = cv2.warpAffine(moving_mask, moving_to_reference, (width, height))
    fixed_feature = _gradient_feature(reference_structure)
    moving_feature = _gradient_feature(warped_structure)
    flow_width, flow_height = max(2, width // 2), max(2, height // 2)
    size = (flow_width, flow_height)
    fixed = cv2.resize(fixed_feature, size, interpolation=cv2.INTER_AREA)
    moving = cv2.resize(moving_feature, size, interpolation=cv2.INTER_AREA)
    valid = cv2.resize(
        ((reference_mask > 0) & (warped_mask > 0)).astype(np.uint8),
        size,
        interpolation=cv2.INTER_NEAREST,
    )
    if int(np.count_nonzero(valid)) < max(512, valid.size // 100):
        return [], -1.0
    algorithm = cv2.DISOpticalFlow_create(  # type: ignore[attr-defined]
        cv2.DISOPTICAL_FLOW_PRESET_MEDIUM
    )
    algorithm.setFinestScale(1)
    algorithm.setPatchSize(16)
    algorithm.setPatchStride(8)
    forward = algorithm.calc(moving, fixed, None)
    reverse = algorithm.calc(fixed, moving, None)
    grid_y, grid_x = np.mgrid[0:flow_height, 0:flow_width].astype(np.float32)
    endpoint_x = grid_x + forward[:, :, 0]
    endpoint_y = grid_y + forward[:, :, 1]
    reverse_x = cv2.remap(
        reverse[:, :, 0],
        endpoint_x,
        endpoint_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=999,
    )
    reverse_y = cv2.remap(
        reverse[:, :, 1],
        endpoint_x,
        endpoint_y,
        cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=999,
    )
    cycle = np.hypot(forward[:, :, 0] + reverse_x, forward[:, :, 1] + reverse_y)
    inverse = cv2.invertAffineTransform(moving_to_reference)
    controls: list[dict[str, Any]] = []
    cycles: list[float] = []
    for y in range(32, flow_height - 32, 32):
        for x in range(32, flow_width - 32, 32):
            if not valid[y, x] or cycle[y, x] > 2.0:
                continue
            dx, dy = (float(value) for value in forward[y, x])
            if math.hypot(dx, dy) > 32.0:
                continue
            endpoint_column, endpoint_row = int(round(x + dx)), int(round(y + dy))
            patch_radius = 12
            if not (
                patch_radius <= endpoint_column < flow_width - patch_radius
                and patch_radius <= endpoint_row < flow_height - patch_radius
            ):
                continue
            moving_patch = moving[
                y - patch_radius : y + patch_radius + 1,
                x - patch_radius : x + patch_radius + 1,
            ]
            fixed_patch = fixed[
                endpoint_row - patch_radius : endpoint_row + patch_radius + 1,
                endpoint_column - patch_radius : endpoint_column + patch_radius + 1,
            ]
            if float(np.std(moving_patch)) < 5.0 or float(np.std(fixed_patch)) < 5.0:
                continue
            reference_x, reference_y = 2 * (x + dx), 2 * (y + dy)
            warped_point = np.asarray([2.0 * x, 2.0 * y])
            moving_point = inverse[:, :2] @ warped_point + inverse[:, 2]
            mx, my = int(round(float(moving_point[0]))), int(round(float(moving_point[1])))
            rx, ry = int(round(reference_x)), int(round(reference_y))
            if not (
                0 <= mx < moving_mask.shape[1]
                and 0 <= my < moving_mask.shape[0]
                and 0 <= rx < reference_mask.shape[1]
                and 0 <= ry < reference_mask.shape[0]
                and moving_mask[my, mx]
                and reference_mask[ry, rx]
            ):
                continue
            error = 2.0 * float(cycle[y, x])
            cycles.append(error)
            controls.append(
                {
                    "moving": [float(moving_point[0]), float(moving_point[1])],
                    "reference": [reference_x, reference_y],
                    "errorPixels": error,
                }
            )
    return controls, float(np.percentile(cycles, 95)) if cycles else -1.0


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
            relative_tile = (
                Path("slide_files") / str(level) / f"{column}_{row}.{root.attrib['Format']}"
            )
            tile_path = path / relative_tile
            if not tile_path.is_file() and (path / ".openslide-source.json").is_file():
                from .tile_routes import materialize_local_openslide_tile_from_root

                tile_path = materialize_local_openslide_tile_from_root(
                    path, path.name, relative_tile.as_posix()
                )
            with Image.open(tile_path) as source:
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
        preferred_pairs, layout_resolved_pairs = _candidate_component_pairs(
            reference_overview,
            moving_overview,
            reference_boxes,
            moving_boxes,
            reference_size,
            moving_size,
        )
        moving_regions = {
            index: read_region(moving_path, bounds)
            for index, bounds in enumerate(moving_boxes)
        }
        reference_regions = {
            index: read_region(reference_path, bounds)
            for index, bounds in enumerate(reference_boxes)
        }
        candidates_by_pair: dict[tuple[int, int], _ComponentMap] = {}
        evaluated_pairs: set[tuple[int, int]] = set()

        def candidate_for(moving_index: int, reference_index: int) -> _ComponentMap | None:
            key = (moving_index, reference_index)
            if key in evaluated_pairs:
                return candidates_by_pair.get(key)
            evaluated_pairs.add(key)
            moving, moving_frame = moving_regions[moving_index]
            reference, reference_frame = reference_regions[reference_index]
            candidate = _approximate_component_map(
                reference, moving, reference_frame, moving_frame
            )
            if candidate:
                candidate = replace(
                    candidate,
                    layout_score=_layout_consistency(
                        candidate.transform,
                        reference_boxes,
                        moving_boxes,
                        reference_size,
                    ),
                )
                candidates_by_pair[key] = candidate
            return candidate

        approximate: list[tuple[int, int, _ComponentMap]] = []
        for moving_index, reference_index in preferred_pairs:
            candidate = candidate_for(moving_index, reference_index)
            if candidate:
                approximate.append((moving_index, reference_index, candidate))
        if approximate:
            overview_cells = [cell for _, _, item in approximate for cell in item.overview_cells]
            moving_points = np.asarray(
                [point for cell in overview_cells for point in cell["moving"]], dtype=np.float64
            )
            reference_points = np.asarray(
                [point for cell in overview_cells for point in cell["reference"]], dtype=np.float64
            )
            approximate_best = max(approximate, key=lambda item: len(item[2].overview_cells))[2]
            qualified: list[_ComponentMap] = []
            ambiguous_components = 0
            identity_checks = 0
            layout_resolved_components = 0
            for moving_index, reference_index, candidate in approximate:
                verified_count = len(candidate.verified_cells)
                verified_ratio = verified_count / max(1, candidate.flow_control_count)
                enough_local_support = verified_count >= 8 or (
                    verified_count >= 6 and verified_ratio >= 0.5
                )
                if not enough_local_support:
                    continue
                identity_checks += 1
                alternative_pairs = {
                    *(
                        (moving_index, other_reference)
                        for other_reference in range(len(reference_boxes))
                    ),
                    *(
                        (other_moving, reference_index)
                        for other_moving in range(len(moving_boxes))
                    ),
                } - {(moving_index, reference_index)}
                for other_moving, other_reference in alternative_pairs:
                    candidate_for(other_moving, other_reference)
                alternatives = [
                    other
                    for (other_moving, other_reference), other in candidates_by_pair.items()
                    if (other_moving, other_reference) != (moving_index, reference_index)
                    and (other_moving == moving_index or other_reference == reference_index)
                    and other.flow_control_count > 0
                ]
                resolved_by_layout = (moving_index, reference_index) in layout_resolved_pairs
                clearly_identified = resolved_by_layout or _component_identity_is_clear(
                    candidate, alternatives
                )
                if clearly_identified:
                    qualified.append(candidate)
                    layout_resolved_components += int(resolved_by_layout)
                else:
                    ambiguous_components += 1
            supported_cells = [
                cell for candidate in qualified for cell in candidate.supported_cells
            ]
            if supported_cells:
                verified_moving = np.asarray(
                    [point for cell in supported_cells for point in cell["moving"]],
                    dtype=np.float64,
                )
                verified_reference = np.asarray(
                    [point for cell in supported_cells for point in cell["reference"]],
                    dtype=np.float64,
                )
                return RegistrationResult(
                    status="ready",
                    moving_to_reference=approximate_best.transform,
                    reference_support=(
                        float(verified_reference[:, 0].min()),
                        float(verified_reference[:, 1].min()),
                        float(verified_reference[:, 0].max()),
                        float(verified_reference[:, 1].max()),
                    ),
                    moving_support=(
                        float(verified_moving[:, 0].min()),
                        float(verified_moving[:, 1].min()),
                        float(verified_moving[:, 0].max()),
                        float(verified_moving[:, 1].max()),
                    ),
                    confidence=min(
                        0.75,
                        0.45 + 0.2 * float(np.mean([item.identity_score for item in qualified])),
                    ),
                    inlier_count=len(supported_cells),
                    match_count=len(supported_cells),
                    median_error_pixels=-1.0,
                    triangles=supported_cells,
                    overview_triangles=overview_cells,
                    evidence={
                        "mode": "matched-regions",
                        "anatomicalMatchCount": 0,
                        "featureMatchCount": 0,
                        "triangleCount": len(supported_cells),
                        "overviewTriangleCount": len(overview_cells),
                        "componentPairsChecked": attempted,
                        "structuralComponentPairsChecked": len(candidates_by_pair),
                        "acceptedStructuralComponents": len(qualified),
                        "layoutResolvedComponents": layout_resolved_components,
                        "ambiguousStructuralComponents": ambiguous_components,
                        "layoutConsistencyMedian": round(
                            float(np.median([item.layout_score for item in qualified])), 4
                        ),
                        "opticalDensityKazeInliers": sum(
                            item.feature_inliers for item in qualified
                        ),
                        "opticalDensityKazeSpreadMedian": round(
                            float(np.median([item.feature_spread for item in qualified])), 4
                        ),
                        "flowControlCount": sum(
                            item.flow_control_count for _, _, item in approximate
                        ),
                        "flowCycleP95": round(
                            max(
                                (
                                    item.flow_cycle_p95
                                    for _, _, item in approximate
                                    if item.flow_cycle_p95 >= 0
                                ),
                                default=-1.0,
                            ),
                            4,
                        ),
                        "verifiedPatchCount": sum(
                            len(item.verified_cells) for item in qualified
                        ),
                        "supportExpansionCount": len(supported_cells)
                        - sum(len(item.verified_cells) for item in qualified),
                        "patchNccMedian": round(
                            float(np.median([item.patch_ncc_median for item in qualified])),
                            4,
                        ),
                        "patchDiscriminationMedian": round(
                            float(
                                np.median(
                                    [item.patch_discrimination_median for item in qualified]
                                )
                            ),
                            4,
                        ),
                        "withheldCheck": "pending-independent-landmarks",
                        "availabilityReason": (
                            "Local structural correspondence passed alternative-fragment checks; "
                            "independent landmark accuracy is pending"
                        ),
                        "source": "bounded-pyramid-component-flow-patch",
                    },
                )
            return RegistrationResult(
                status="approximate",
                moving_to_reference=approximate_best.transform,
                reference_support=(
                    float(reference_points[:, 0].min()),
                    float(reference_points[:, 1].min()),
                    float(reference_points[:, 0].max()),
                    float(reference_points[:, 1].max()),
                ),
                moving_support=(
                    float(moving_points[:, 0].min()),
                    float(moving_points[:, 1].min()),
                    float(moving_points[:, 0].max()),
                    float(moving_points[:, 1].max()),
                ),
                confidence=min(
                    0.49,
                    0.3
                    + 0.1
                    * float(np.mean([item.intensity_score for _, _, item in approximate])),
                ),
                inlier_count=0,
                match_count=0,
                median_error_pixels=-1.0,
                overview_triangles=overview_cells,
                evidence={
                    "mode": "outline-proposal",
                    "anatomicalMatchCount": 0,
                    "featureMatchCount": 0,
                    "triangleCount": 0,
                    "overviewTriangleCount": len(overview_cells),
                    "componentPairsChecked": attempted,
                    "structuralComponentPairsChecked": len(candidates_by_pair),
                    "approximateComponents": len(approximate),
                    "componentIdentityChecks": identity_checks,
                    "ambiguousStructuralComponents": ambiguous_components,
                    "layoutConsistencyMedian": round(
                        float(np.median([item.layout_score for _, _, item in approximate])),
                        4,
                    ),
                    "opticalDensityKazeInliers": sum(
                        item.feature_inliers for _, _, item in approximate
                    ),
                    "opticalDensityKazeSpreadMedian": round(
                        float(
                            np.median(
                                [item.feature_spread for _, _, item in approximate]
                            )
                        ),
                        4,
                    ),
                    "intensityShapeScore": round(
                        float(np.mean([item.intensity_score for _, _, item in approximate])), 6
                    ),
                    "outlineOverlap": round(
                        float(np.mean([item.overlap for _, _, item in approximate])), 6
                    ),
                    "flowControlCount": sum(
                        item.flow_control_count for _, _, item in approximate
                    ),
                    "flowCycleP95": round(
                        max(
                            (
                                item.flow_cycle_p95
                                for _, _, item in approximate
                                if item.flow_cycle_p95 >= 0
                            ),
                            default=-1.0,
                        ),
                        4,
                    ),
                    "verifiedPatchCount": sum(
                        len(item.verified_cells) for _, _, item in approximate
                    ),
                    "patchNccMedian": round(
                        float(
                            np.median(
                                [
                                    item.patch_ncc_median
                                    for _, _, item in approximate
                                    if item.patch_ncc_median >= -0.99
                                ]
                            )
                        ),
                        4,
                    )
                    if any(item.patch_ncc_median >= -0.99 for _, _, item in approximate)
                    else -1.0,
                    "patchDiscriminationMedian": round(
                        float(
                            np.median(
                                [
                                    item.patch_discrimination_median
                                    for _, _, item in approximate
                                    if item.patch_discrimination_median >= -0.99
                                ]
                            )
                        ),
                        4,
                    )
                    if any(
                        item.patch_discrimination_median >= -0.99
                        for _, _, item in approximate
                    )
                    else -1.0,
                    "availabilityReason": "No accepted anatomical feature matches",
                    "source": (
                        "bounded-pyramid-component-flow"
                        if any(item.flow_control_count for _, _, item in approximate)
                        else "bounded-pyramid-component-shape"
                    ),
                },
            )
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
