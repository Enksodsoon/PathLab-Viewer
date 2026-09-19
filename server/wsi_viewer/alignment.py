# mypy: ignore-errors
"""Bounded, stain-independent coordinate registration for brightfield slides.

OpenCV's generated stubs do not model several array-returning APIs used here;
runtime shapes are validated and covered by synthetic geometry tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations
from typing import Any

import cv2
import numpy as np
from PIL import Image


class AlignmentRejected(ValueError):
    """The images do not contain enough evidence for safe synchronization."""


@dataclass(frozen=True)
class RegistrationResult:
    status: str
    moving_to_reference: list[list[float]]
    reference_support: tuple[float, float, float, float]
    moving_support: tuple[float, float, float, float]
    confidence: float
    inlier_count: int
    match_count: int
    median_error_pixels: float

    def as_json(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "movingToReference": self.moving_to_reference,
            "referenceSupport": list(self.reference_support),
            "movingSupport": list(self.moving_support),
            "confidence": self.confidence,
            "inlierCount": self.inlier_count,
            "matchCount": self.match_count,
            "medianErrorPixels": self.median_error_pixels,
        }


def map_point(transform: list[list[float]], x: float, y: float) -> tuple[float, float]:
    matrix = np.asarray(transform, dtype=np.float64)
    if matrix.shape != (2, 3):
        raise ValueError("Alignment transform must be a 2x3 matrix")
    mapped = matrix[:, :2] @ np.array([x, y], dtype=np.float64) + matrix[:, 2]
    return float(mapped[0]), float(mapped[1])


def compose_transforms(outer: list[list[float]], inner: list[list[float]]) -> list[list[float]]:
    """Compose moving-to-anchor and anchor-to-reference affine maps."""
    outer_matrix = np.asarray(outer, dtype=np.float64)
    inner_matrix = np.asarray(inner, dtype=np.float64)
    if outer_matrix.shape != (2, 3) or inner_matrix.shape != (2, 3):
        raise ValueError("Alignment transforms must be 2x3 matrices")
    outer_h = np.vstack([outer_matrix, [0.0, 0.0, 1.0]])
    inner_h = np.vstack([inner_matrix, [0.0, 0.0, 1.0]])
    return (outer_h @ inner_h)[:2].round(10).tolist()


def map_bounds(
    transform: list[list[float]], bounds: tuple[float, float, float, float]
) -> tuple[float, float, float, float]:
    corners = [
        map_point(transform, bounds[0], bounds[1]),
        map_point(transform, bounds[2], bounds[1]),
        map_point(transform, bounds[0], bounds[3]),
        map_point(transform, bounds[2], bounds[3]),
    ]
    return (
        min(point[0] for point in corners),
        min(point[1] for point in corners),
        max(point[0] for point in corners),
        max(point[1] for point in corners),
    )


def rescale_registration(
    result: RegistrationResult,
    *,
    reference_thumbnail_size: tuple[int, int],
    moving_thumbnail_size: tuple[int, int],
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
) -> RegistrationResult:
    sizes = (
        reference_thumbnail_size + moving_thumbnail_size + reference_full_size + moving_full_size
    )
    if any(value <= 0 for value in sizes):
        raise ValueError("Registration image dimensions must be positive")
    reference_scale = np.diag(
        [
            reference_full_size[0] / reference_thumbnail_size[0],
            reference_full_size[1] / reference_thumbnail_size[1],
            1.0,
        ]
    )
    moving_scale = np.diag(
        [
            moving_thumbnail_size[0] / moving_full_size[0],
            moving_thumbnail_size[1] / moving_full_size[1],
            1.0,
        ]
    )
    thumbnail_transform = np.vstack(
        [np.asarray(result.moving_to_reference, dtype=np.float64), [0.0, 0.0, 1.0]]
    )
    transform = (reference_scale @ thumbnail_transform @ moving_scale)[:2]

    def scale_support(
        support: tuple[float, float, float, float],
        thumbnail: tuple[int, int],
        full: tuple[int, int],
    ) -> tuple[float, float, float, float]:
        x_scale, y_scale = full[0] / thumbnail[0], full[1] / thumbnail[1]
        return (
            support[0] * x_scale,
            support[1] * y_scale,
            support[2] * x_scale,
            support[3] * y_scale,
        )

    return RegistrationResult(
        status=result.status,
        moving_to_reference=transform.round(10).tolist(),
        reference_support=scale_support(
            result.reference_support, reference_thumbnail_size, reference_full_size
        ),
        moving_support=scale_support(
            result.moving_support, moving_thumbnail_size, moving_full_size
        ),
        confidence=result.confidence,
        inlier_count=result.inlier_count,
        match_count=result.match_count,
        median_error_pixels=round(
            result.median_error_pixels
            * max(
                reference_full_size[0] / reference_thumbnail_size[0],
                reference_full_size[1] / reference_thumbnail_size[1],
            ),
            4,
        ),
    )


def _bounded_rgb(image: Image.Image, maximum: int) -> tuple[np.ndarray, float]:
    rgb = image.convert("RGB")
    scale = min(1.0, maximum / max(rgb.size))
    if scale < 1.0:
        rgb = rgb.resize(
            (max(1, round(rgb.width * scale)), max(1, round(rgb.height * scale))),
            Image.Resampling.LANCZOS,
        )
    return np.asarray(rgb, dtype=np.uint8), scale


def _structure(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    # Optical-density proxy is invariant to RGB channel order and therefore to
    # many broad stain hue changes while retaining nuclei and tissue edges.
    density = 255 - np.min(rgb, axis=2)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    # Require chroma for lightly stained tissue, while retaining dark silver
    # deposits. This avoids scanner-bed edges and coverslip outlines becoming
    # the dominant structures in sparse biopsy sections.
    tissue = ((density >= 18) & ((hsv[:, :, 1] >= 10) | (gray < 205))).astype(np.uint8) * 255
    tissue = cv2.morphologyEx(tissue, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    tissue = cv2.morphologyEx(tissue, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(tissue)
    cleaned = np.zeros_like(tissue)
    minimum_area = max(150, tissue.size // 5000)
    retained: list[tuple[int, int]] = []
    for index in range(1, component_count):
        x, y, width, height, area = stats[index]
        touches_edge = (
            x <= 1
            or y <= 1
            or x + width >= tissue.shape[1] - 1
            or y + height >= tissue.shape[0] - 1
        )
        if area >= minimum_area and not touches_edge:
            retained.append((int(area), index))
    # Whole-slide tissue may be fragmented, but tiny debris adds ambiguous
    # component permutations without useful anatomical evidence.
    for _, index in sorted(retained, reverse=True)[:6]:
        cleaned[labels == index] = 255
    tissue = cleaned
    if cv2.countNonZero(tissue) < max(512, tissue.size // 500):
        raise AlignmentRejected("insufficient tissue for alignment")
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(density)
    return enhanced, tissue


def _support(mask: np.ndarray, scale: float) -> tuple[float, float, float, float]:
    points = cv2.findNonZero(mask)
    if points is None:
        raise AlignmentRejected("insufficient tissue for alignment")
    x, y, width, height = cv2.boundingRect(points)
    return x / scale, y / scale, (x + width) / scale, (y + height) / scale


def _full_resolution_transform(
    low_resolution: np.ndarray,
    moving_scale: float,
    reference_scale: float,
) -> np.ndarray:
    moving_down = np.array([[moving_scale, 0.0, 0.0], [0.0, moving_scale, 0.0], [0.0, 0.0, 1.0]])
    reference_up = np.array(
        [[1.0 / reference_scale, 0.0, 0.0], [0.0, 1.0 / reference_scale, 0.0], [0, 0, 1]]
    )
    affine = np.vstack([low_resolution, [0.0, 0.0, 1.0]])
    return (reference_up @ affine @ moving_down)[:2]


def _mask_seed(reference_mask: np.ndarray, moving_mask: np.ndarray) -> tuple[np.ndarray, float]:
    def center_angle(mask: np.ndarray) -> tuple[np.ndarray, float, int]:
        y, x = np.nonzero(mask)
        center = np.array([x.mean(), y.mean()])
        vector = np.linalg.eigh(np.cov(np.vstack([x, y])))[1][:, -1]
        return center, float(np.arctan2(vector[1], vector[0])), len(x)

    reference_center, reference_angle, reference_area = center_angle(reference_mask)
    moving_center, moving_angle, moving_area = center_angle(moving_mask)
    scale = float(np.sqrt(reference_area / moving_area))
    best_score = -1.0
    best = np.eye(2, 3, dtype=np.float32)
    for extra in (0.0, np.pi):
        angle = reference_angle - moving_angle + extra
        cosine = float(np.cos(angle) * scale)
        sine = float(np.sin(angle) * scale)
        candidate = np.array([[cosine, -sine, 0.0], [sine, cosine, 0.0]], dtype=np.float32)
        candidate[:, 2] = reference_center - candidate[:, :2] @ moving_center
        warped = cv2.warpAffine(
            moving_mask, candidate, (reference_mask.shape[1], reference_mask.shape[0])
        )
        intersection = np.count_nonzero((warped > 0) & (reference_mask > 0))
        score = (
            2 * intersection / max(1, np.count_nonzero(warped) + np.count_nonzero(reference_mask))
        )
        if score > best_score:
            best_score, best = score, candidate
    return best, best_score


def _component_seed(
    reference_mask: np.ndarray, moving_mask: np.ndarray
) -> tuple[np.ndarray | None, float, float, int]:
    def components(mask: np.ndarray) -> list[tuple[int, np.ndarray]]:
        count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        minimum = max(100, mask.size // 5000)
        values = [
            (int(stats[index, cv2.CC_STAT_AREA]), centers[index])
            for index in range(1, count)
            if stats[index, cv2.CC_STAT_AREA] >= minimum
        ]
        return sorted(values, key=lambda item: item[0], reverse=True)[:4]

    reference_components = components(reference_mask)
    moving_components = components(moving_mask)
    matched_count = min(len(reference_components), len(moving_components), 4)
    if matched_count < 2:
        return None, -1.0, 0.0, matched_count
    scores: list[tuple[float, np.ndarray]] = []
    for reference_subset in combinations(reference_components, matched_count):
        reference_points = np.float32([item[1] for item in reference_subset])
        for moving_subset in combinations(moving_components, matched_count):
            for moving_order in permutations(moving_subset):
                moving_points = np.float32([item[1] for item in moving_order])
                candidate, _ = cv2.estimateAffinePartial2D(
                    moving_points, reference_points, method=cv2.LMEDS
                )
                if candidate is None:
                    continue
                scale = float(np.sqrt(abs(np.linalg.det(candidate[:, :2]))))
                if not 0.3 <= scale <= 3.0:
                    continue
                warped = cv2.warpAffine(
                    moving_mask,
                    candidate,
                    (reference_mask.shape[1], reference_mask.shape[0]),
                )
                intersection = np.count_nonzero((warped > 0) & (reference_mask > 0))
                score = (
                    2
                    * intersection
                    / max(1, np.count_nonzero(warped) + np.count_nonzero(reference_mask))
                )
                scores.append((float(score), candidate.astype(np.float32)))
    if not scores:
        return None, -1.0, 0.0, matched_count
    scores.sort(key=lambda item: item[0], reverse=True)
    second = scores[1][0] if len(scores) > 1 else 0.0
    return scores[0][1], scores[0][0], scores[0][0] - second, matched_count


def _coarse_refined_result(
    reference_structure: np.ndarray,
    reference_mask: np.ndarray,
    moving_structure: np.ndarray,
    moving_mask: np.ndarray,
    reference_scale: float,
    moving_scale: float,
) -> RegistrationResult:
    seed, overlap = _mask_seed(reference_mask, moving_mask)
    component_seed, component_overlap, component_margin, component_count = _component_seed(
        reference_mask, moving_mask
    )
    if component_seed is not None and component_overlap > overlap:
        seed, overlap = component_seed, component_overlap

    def outline_result() -> RegistrationResult:
        # Outline-only acceptance is reserved for multiple independently
        # segmented fragments with a clearly better component assignment.
        # This supports sparse cross-stain sections while rejecting symmetric
        # or repeated-fragment permutations that remain ambiguous.
        if component_overlap < 0.72 or component_margin < 0.05 or component_count < 2:
            raise AlignmentRejected("no reliable correspondence found")
        assert component_seed is not None
        full = _full_resolution_transform(component_seed, moving_scale, reference_scale)
        confidence = min(0.75, 0.45 + 0.25 * component_overlap + component_margin)
        return RegistrationResult(
            status="ready",
            moving_to_reference=full.round(10).tolist(),
            reference_support=_support(reference_mask, reference_scale),
            moving_support=_support(moving_mask, moving_scale),
            confidence=round(confidence, 6),
            inlier_count=component_count,
            match_count=component_count,
            median_error_pixels=0.0,
        )

    if overlap < 0.45:
        raise AlignmentRejected("no reliable correspondence found")
    size = (reference_mask.shape[1], reference_mask.shape[0])
    warped_structure = cv2.warpAffine(moving_structure, seed, size)
    warped_mask = cv2.warpAffine(moving_mask, seed, size)
    detector = cv2.ORB_create(nfeatures=5000, scaleFactor=1.2, nlevels=8, fastThreshold=5)
    reference_keys, reference_descriptors = detector.detectAndCompute(
        reference_structure, reference_mask
    )
    moving_keys, moving_descriptors = detector.detectAndCompute(warped_structure, warped_mask)
    if reference_descriptors is None or moving_descriptors is None:
        return outline_result()
    candidates = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(
        moving_descriptors, reference_descriptors, k=2
    )
    matches = [
        pair[0]
        for pair in candidates
        if len(pair) == 2 and pair[0].distance < 0.80 * pair[1].distance
    ]
    if len(matches) < 16:
        return outline_result()
    moving_points = np.float32([moving_keys[item.queryIdx].pt for item in matches])
    reference_points = np.float32([reference_keys[item.trainIdx].pt for item in matches])
    refinement, inlier_mask = cv2.estimateAffinePartial2D(
        moving_points,
        reference_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=5.0,
        maxIters=5000,
        confidence=0.999,
        refineIters=25,
    )
    if refinement is None or inlier_mask is None:
        return outline_result()
    inliers = inlier_mask.ravel().astype(bool)
    inlier_count = int(np.count_nonzero(inliers))
    ratio = inlier_count / len(matches)
    refined_scale = float(np.sqrt(abs(np.linalg.det(refinement[:, :2]))))
    spatial = cv2.boundingRect(moving_points[inliers].astype(np.float32))
    spatial_coverage = (spatial[2] * spatial[3]) / max(1, moving_mask.size)
    # Serial sections preserve tissue layout better than pixel-identical keypoints.
    # Require independent local anchors after strong outline agreement, while
    # allowing stain and section-depth changes to remove most feature matches.
    if (
        inlier_count < 3
        or ratio < 0.07
        or not 0.65 <= refined_scale <= 1.5
        or spatial_coverage < 0.002
    ):
        return outline_result()
    projected = cv2.transform(moving_points[inliers, None, :], refinement)[:, 0, :]
    median_error = float(np.median(np.linalg.norm(projected - reference_points[inliers], axis=1)))
    combined = (np.vstack([refinement, [0, 0, 1]]) @ np.vstack([seed, [0, 0, 1]]))[:2]
    full = _full_resolution_transform(combined, moving_scale, reference_scale)
    confidence = min(0.95, 0.35 + 0.30 * overlap + 0.20 * ratio + 0.10 * min(1, inlier_count / 40))
    if confidence < 0.55 or median_error > 4.0:
        return outline_result()
    return RegistrationResult(
        status="ready",
        moving_to_reference=full.round(10).tolist(),
        reference_support=_support(reference_mask, reference_scale),
        moving_support=_support(moving_mask, moving_scale),
        confidence=round(confidence, 6),
        inlier_count=inlier_count,
        match_count=len(matches),
        median_error_pixels=round(median_error / reference_scale, 4),
    )


def register_pair(
    reference: Image.Image,
    moving: Image.Image,
    *,
    max_dimension: int = 2048,
) -> RegistrationResult:
    if max_dimension < 256 or max_dimension > 4096:
        raise ValueError("max_dimension must be between 256 and 4096")
    reference_rgb, reference_scale = _bounded_rgb(reference, max_dimension)
    moving_rgb, moving_scale = _bounded_rgb(moving, max_dimension)
    reference_structure, reference_mask = _structure(reference_rgb)
    moving_structure, moving_mask = _structure(moving_rgb)

    detector = cv2.ORB_create(nfeatures=5000, scaleFactor=1.2, nlevels=8, fastThreshold=8)
    reference_keys, reference_descriptors = detector.detectAndCompute(
        reference_structure, reference_mask
    )
    moving_keys, moving_descriptors = detector.detectAndCompute(moving_structure, moving_mask)
    if reference_descriptors is None or moving_descriptors is None:
        return _coarse_refined_result(
            reference_structure,
            reference_mask,
            moving_structure,
            moving_mask,
            reference_scale,
            moving_scale,
        )

    matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
    candidates = matcher.knnMatch(moving_descriptors, reference_descriptors, k=2)
    matches = [
        pair[0]
        for pair in candidates
        if len(pair) == 2 and pair[0].distance < 0.72 * pair[1].distance
    ]
    if len(matches) < 10:
        return _coarse_refined_result(
            reference_structure,
            reference_mask,
            moving_structure,
            moving_mask,
            reference_scale,
            moving_scale,
        )

    moving_points = np.float32([moving_keys[item.queryIdx].pt for item in matches])
    reference_points = np.float32([reference_keys[item.trainIdx].pt for item in matches])
    transform, inlier_mask = cv2.estimateAffinePartial2D(
        moving_points,
        reference_points,
        method=cv2.RANSAC,
        ransacReprojThreshold=5.0,
        maxIters=5000,
        confidence=0.999,
        refineIters=25,
    )
    if transform is None or inlier_mask is None:
        return _coarse_refined_result(
            reference_structure,
            reference_mask,
            moving_structure,
            moving_mask,
            reference_scale,
            moving_scale,
        )
    inliers = inlier_mask.ravel().astype(bool)
    inlier_count = int(np.count_nonzero(inliers))
    ratio = inlier_count / len(matches)
    linear = transform[:, :2]
    scale = float(np.sqrt(abs(np.linalg.det(linear))))
    projected = cv2.transform(moving_points[inliers, None, :], transform)[:, 0, :]
    errors = np.linalg.norm(projected - reference_points[inliers], axis=1)
    median_error = float(np.median(errors)) if errors.size else float("inf")
    spatial = (
        cv2.boundingRect(moving_points[inliers].astype(np.float32))
        if inlier_count
        else (0, 0, 0, 0)
    )
    coverage = (spatial[2] * spatial[3]) / max(1, moving_mask.shape[0] * moving_mask.shape[1])
    confidence = min(
        1.0,
        0.45 * ratio + 0.35 * min(1.0, inlier_count / 40) + 0.20 * min(1.0, coverage / 0.08),
    )
    if (
        inlier_count < 10
        or ratio < 0.28
        or not 0.5 <= scale <= 2.0
        or median_error > 4.0
        or coverage < 0.01
        or confidence < 0.55
    ):
        return _coarse_refined_result(
            reference_structure,
            reference_mask,
            moving_structure,
            moving_mask,
            reference_scale,
            moving_scale,
        )

    full = _full_resolution_transform(transform, moving_scale, reference_scale)
    return RegistrationResult(
        status="ready",
        moving_to_reference=full.round(10).tolist(),
        reference_support=_support(reference_mask, reference_scale),
        moving_support=_support(moving_mask, moving_scale),
        confidence=round(confidence, 6),
        inlier_count=inlier_count,
        match_count=len(matches),
        median_error_pixels=round(median_error / reference_scale, 4),
    )
