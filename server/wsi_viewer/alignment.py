# mypy: ignore-errors
"""Bounded, stain-independent coordinate registration for brightfield slides.

OpenCV's generated stubs do not model several array-returning APIs used here;
runtime shapes are validated and covered by synthetic geometry tests.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    tissue = (density >= 14).astype(np.uint8) * 255
    tissue = cv2.morphologyEx(tissue, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    tissue = cv2.morphologyEx(tissue, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
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


def _coarse_refined_result(
    reference_structure: np.ndarray,
    reference_mask: np.ndarray,
    moving_structure: np.ndarray,
    moving_mask: np.ndarray,
    reference_scale: float,
    moving_scale: float,
) -> RegistrationResult:
    seed, overlap = _mask_seed(reference_mask, moving_mask)
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
        raise AlignmentRejected("no reliable correspondence found")
    candidates = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(
        moving_descriptors, reference_descriptors, k=2
    )
    matches = [
        pair[0]
        for pair in candidates
        if len(pair) == 2 and pair[0].distance < 0.80 * pair[1].distance
    ]
    if len(matches) < 16:
        raise AlignmentRejected("no reliable correspondence found")
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
        raise AlignmentRejected("no reliable correspondence found")
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
        raise AlignmentRejected("no reliable correspondence found")
    projected = cv2.transform(moving_points[inliers, None, :], refinement)[:, 0, :]
    median_error = float(np.median(np.linalg.norm(projected - reference_points[inliers], axis=1)))
    combined = (np.vstack([refinement, [0, 0, 1]]) @ np.vstack([seed, [0, 0, 1]]))[:2]
    full = _full_resolution_transform(combined, moving_scale, reference_scale)
    confidence = min(0.95, 0.35 + 0.30 * overlap + 0.20 * ratio + 0.10 * min(1, inlier_count / 40))
    if confidence < 0.55 or median_error > 4.0:
        raise AlignmentRejected("no reliable correspondence found")
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
