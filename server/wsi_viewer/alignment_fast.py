"""Bounded reusable preparation and conservative overview registration.

This path proposes overview geometry, never locally validated anatomy. The
existing high-resolution worker supplies local correspondence separately.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .alignment import (
    AlignmentRejected,
    RegistrationResult,
    _mask_seed,
    _mutual_matches,
    _registration_triangles,
    _structure,
    _support,
    rescale_registration,
)

PREPARATION_VERSION = "overview-orb1536-v1"


@dataclass(frozen=True)
class PreparedSlide:
    structure: np.ndarray[Any, Any]
    mask: np.ndarray[Any, Any]
    points: np.ndarray[Any, Any]
    descriptors: np.ndarray[Any, Any] | None
    full_size: tuple[int, int]

    @property
    def nbytes(self) -> int:
        return sum(
            x.nbytes
            for x in (self.structure, self.mask, self.points, self.descriptors)
            if x is not None
        )


class PreparationCache:
    """Worker-local byte-bounded LRU; no source pixels leave the worker."""

    def __init__(self, max_bytes: int = 128 * 1024**2):
        self.max_bytes = max_bytes
        self.bytes_used = 0
        self.entries: OrderedDict[tuple[Any, ...], PreparedSlide] = OrderedDict()

    def prepare(
        self,
        source: str,
        image: Image.Image | Callable[[], Image.Image],
        full_size: tuple[int, int],
        *,
        sampling_scale: int | None = None,
    ) -> tuple[PreparedSlide, bool]:
        key = (source, full_size, sampling_scale, PREPARATION_VERSION, cv2.__version__)
        if key in self.entries:
            self.entries.move_to_end(key)
            return self.entries[key], True
        bounded = (image() if callable(image) else image).copy()
        # DZI edge pixels cover a padded power-of-two frame. Using the original
        # width divided by its rounded overview width introduces level-zero drift.
        coordinate_size = (
            (bounded.width * sampling_scale, bounded.height * sampling_scale)
            if sampling_scale
            else full_size
        )
        bounded.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
        structure, mask = _structure(np.asarray(bounded.convert("RGB")))
        # Per-cell quotas keep a large dark fragment from taking every feature.
        detector = cv2.ORB.create(nfeatures=1536, fastThreshold=8)
        keys = detector.detect(structure, mask)
        buckets: dict[tuple[int, int], list[cv2.KeyPoint]] = {}
        height, width = mask.shape
        for point in sorted(keys, key=lambda p: p.response, reverse=True):
            cell = (min(7, int(point.pt[0] * 8 / width)), min(7, int(point.pt[1] * 8 / height)))
            bucket = buckets.setdefault(cell, [])
            if len(bucket) < 24:
                bucket.append(point)
        selected = [p for bucket in buckets.values() for p in bucket]
        keys, descriptors = detector.compute(structure, selected)
        prepared = PreparedSlide(
            structure,
            mask,
            np.asarray([p.pt for p in keys], dtype=np.float32).reshape(-1, 2),
            descriptors,
            coordinate_size,
        )
        while self.entries and self.bytes_used + prepared.nbytes > self.max_bytes:
            _, removed = self.entries.popitem(last=False)
            self.bytes_used -= removed.nbytes
        if prepared.nbytes <= self.max_bytes:
            self.entries[key] = prepared
            self.bytes_used += prepared.nbytes
        return prepared, False


def register_prepared(reference: PreparedSlide, moving: PreparedSlide) -> RegistrationResult:
    height, width = reference.mask.shape
    transform = None
    inlier_count = 0
    matches = []
    if (
        reference.descriptors is not None
        and moving.descriptors is not None
        and min(len(reference.descriptors), len(moving.descriptors)) >= 2
    ):
        matches = _mutual_matches(moving.descriptors, reference.descriptors, 0.72)
        if len(matches) >= 10:
            source = np.asarray([moving.points[m.queryIdx] for m in matches], dtype=np.float32)
            target = np.asarray([reference.points[m.trainIdx] for m in matches], dtype=np.float32)
            fitted, inliers = cv2.estimateAffinePartial2D(
                source,
                target,
                method=cv2.RANSAC,
                ransacReprojThreshold=4,
                maxIters=1500,
                confidence=0.995,
            )
            if fitted is not None and inliers is not None:
                good = inliers.ravel().astype(bool)
                inlier_count = int(good.sum())
                spread = np.ptp(source[good], axis=0) if good.any() else [0, 0]
                scale = np.sqrt(abs(np.linalg.det(np.asarray(fitted[:, :2], dtype=np.float64))))
                if (
                    inlier_count >= 10
                    and inlier_count / len(matches) >= 0.28
                    and spread[0] * spread[1] >= moving.mask.size * 0.01
                    and 0.5 <= scale <= 2
                ):
                    transform = fitted
    if transform is None:
        # Compare scanner and tissue-axis initialization. Neither mask overlap
        # nor scanner position alone is sufficient evidence to publish a map.
        seed, _ = _mask_seed(reference.mask, moving.mask)
        scanner = np.asarray(
            [[width / moving.mask.shape[1], 0, 0], [0, height / moving.mask.shape[0], 0]],
            dtype=np.float32,
        )
        divisor = max(1.0, max(width, height, *moving.mask.shape) / 512)
        fixed = cv2.resize(reference.structure, None, fx=1 / divisor, fy=1 / divisor)
        floating = cv2.resize(moving.structure, None, fx=1 / divisor, fy=1 / divisor)
        fixed = cv2.GaussianBlur(fixed, (0, 0), 3).astype(np.float32) / 255
        floating = cv2.GaussianBlur(floating, (0, 0), 3).astype(np.float32) / 255
        candidates = []
        for initial, motion in ((scanner, cv2.MOTION_TRANSLATION), (seed, cv2.MOTION_AFFINE)):
            small_seed = initial.copy()
            small_seed[:, 2] /= divisor
            inverse = cv2.invertAffineTransform(small_seed).astype(np.float32)
            try:
                score, inverse = cv2.findTransformECC(  # type: ignore[call-overload]
                    fixed,
                    floating,
                    inverse,
                    motion,
                    (cv2.TERM_CRITERIA_COUNT | cv2.TERM_CRITERIA_EPS, 25, 1e-4),
                    None,
                    5,
                )
            except cv2.error:
                continue
            candidate = cv2.invertAffineTransform(inverse)
            singular = np.linalg.svd(candidate[:, :2], compute_uv=False)
            if (
                score < 0.65
                or singular[-1] < 0.5
                or singular[0] > 2
                or singular[0] / singular[-1] > 1.35
            ):
                continue
            candidate[:, 2] *= divisor
            candidates.append((score, candidate))
        if not candidates:
            raise AlignmentRejected("Needs refinement: weak coarse structural correspondence")
        transform = max(candidates, key=lambda item: item[0])[1]
    warped: np.ndarray[Any, Any] = cv2.warpAffine(moving.mask, transform, (width, height))
    dice = (
        2
        * int(np.count_nonzero((warped > 0) & (reference.mask > 0)))
        / max(1, int(np.count_nonzero(warped)) + int(np.count_nonzero(reference.mask)))
    )
    if dice < 0.65 or np.linalg.det(np.asarray(transform[:, :2], dtype=np.float64)) <= 0:
        raise AlignmentRejected("Needs refinement: coarse map has insufficient tissue support")
    controls = []
    # Overview positioning needs a sparse support mesh; detector budget is not
    # a mesh budget. Thousands of cells made Python support checks dominate.
    spacing = max(8, int(np.ceil(np.sqrt(np.count_nonzero(moving.mask) / 192))))
    for y in range(spacing // 2, moving.mask.shape[0], spacing):
        for x in range(spacing // 2, moving.mask.shape[1], spacing):
            if not moving.mask[y, x]:
                continue
            target = transform @ [x, y, 1]
            tx, ty = np.rint(target).astype(int)
            if 0 <= tx < width and 0 <= ty < height and reference.mask[ty, tx]:
                controls.append(
                    {
                        "moving": [float(x), float(y)],
                        "reference": target.tolist(),
                        "errorPixels": 0.0,
                    }
                )
    cells = _registration_triangles(
        controls,
        moving_mask=moving.mask,
        reference_mask=reference.mask,
        moving_scale=1.0,
        reference_scale=1.0,
    )
    if not cells:
        raise AlignmentRejected("Needs refinement: no supported overview cells")
    result = RegistrationResult(
        status="approximate",
        moving_to_reference=transform.tolist(),
        reference_support=_support(reference.mask, 1),
        moving_support=_support(moving.mask, 1),
        confidence=min(0.49, dice / 2),
        inlier_count=inlier_count,
        match_count=len(matches),
        median_error_pixels=-1,
        overview_triangles=cells,
        evidence={
            "mode": "approximate-overview",
            "source": "bounded-sparse-overview",
            "featureMatchCount": inlier_count,
            "triangleCount": 0,
            "overviewTriangleCount": len(cells),
            "tissueDice": round(dice, 6),
            "preparationVersion": PREPARATION_VERSION,
            "withheldCheck": "pending-independent-landmarks",
        },
    )
    return rescale_registration(
        result,
        reference_thumbnail_size=(width, height),
        moving_thumbnail_size=(moving.mask.shape[1], moving.mask.shape[0]),
        reference_full_size=reference.full_size,
        moving_full_size=moving.full_size,
    )
