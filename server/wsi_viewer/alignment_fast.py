"""Bounded reusable preparation and conservative overview registration.

This path proposes overview geometry, never locally validated anatomy. The
existing high-resolution worker supplies local correspondence separately.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .alignment import (
    AlignmentRejected,
    RegistrationResult,
    _mask_seed,
    _mutual_matches,
    _orb_features,
    _registration_triangles,
    _structure,
    _support,
    rescale_registration,
)

PREPARATION_VERSION = "overview-orb1536-v6-component-fallback"


@dataclass(frozen=True)
class PreparedSlide:
    structure: np.ndarray[Any, Any]
    mask: np.ndarray[Any, Any]
    points: np.ndarray[Any, Any]
    descriptors: np.ndarray[Any, Any] | None
    full_size: tuple[int, int]
    thin_mask: np.ndarray[Any, Any] | None = None
    calibrated: PreparedSlide | None = None

    @property
    def nbytes(self) -> int:
        return sum(
            x.nbytes
            for x in (self.structure, self.mask, self.points, self.descriptors, self.thin_mask)
            if x is not None
        ) + (self.calibrated.nbytes if self.calibrated is not None else 0)


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
        cropped: bool = False,
    ) -> tuple[PreparedSlide, bool]:
        key = (source, full_size, sampling_scale, cropped, PREPARATION_VERSION, cv2.__version__)
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
        rgb = np.asarray(bounded.convert("RGB"))
        corrected = None
        thin_mask: np.ndarray[Any, Any] | None
        try:
            structure, mask = _structure(rgb, cropped=cropped)
        except AlignmentRejected:
            try:
                structure, mask = _structure(rgb, preserve_thin_tissue=True, cropped=cropped)
            except AlignmentRejected:
                # A tinted glass field can flood the fixed white-background mask.
                # Estimate its color from a sparse sample only after both masks fail.
                background = np.percentile(rgb[::8, ::8].reshape(-1, 3), 70, axis=0)
                corrected = np.clip(
                    rgb.astype(np.float32) * (255 / np.maximum(background, 1)), 0, 255
                ).astype(np.uint8)
                structure, mask = _structure(corrected, preserve_thin_tissue=True, cropped=cropped)
            thin_mask = mask
        else:
            # Cache the alternate support once; retain the original detector budget.
            try:
                _, thin_mask = _structure(rgb, preserve_thin_tissue=True, cropped=cropped)
            except AlignmentRejected:
                thin_mask = None
        keys, descriptors = _orb_features(structure, mask, 1536)
        calibrated = None
        if corrected is None and np.count_nonzero(mask) >= mask.size * 0.15:
            # Dense, lightly stained sections can lose most of their tissue at
            # the overview threshold. Retain a second bounded view only for
            # pairs whose unchanged primary registration rejects.
            background = np.percentile(rgb[::8, ::8].reshape(-1, 3), 70, axis=0)
            corrected = np.clip(
                rgb.astype(np.float32) * (255 / np.maximum(background, 1)), 0, 255
            ).astype(np.uint8)
            try:
                calibrated_structure, calibrated_mask = _structure(
                    corrected, preserve_thin_tissue=True, cropped=cropped
                )
                calibrated_keys, calibrated_descriptors = _orb_features(
                    calibrated_structure, calibrated_mask, 1536
                )
                calibrated = PreparedSlide(
                    calibrated_structure,
                    calibrated_mask,
                    np.asarray([p.pt for p in calibrated_keys], dtype=np.float32).reshape(-1, 2),
                    calibrated_descriptors,
                    coordinate_size,
                    calibrated_mask,
                )
            except AlignmentRejected:
                pass
        prepared = PreparedSlide(
            structure,
            mask,
            np.asarray([p.pt for p in keys], dtype=np.float32).reshape(-1, 2),
            descriptors,
            coordinate_size,
            thin_mask,
            calibrated,
        )
        while self.entries and self.bytes_used + prepared.nbytes > self.max_bytes:
            _, removed = self.entries.popitem(last=False)
            self.bytes_used -= removed.nbytes
        if prepared.nbytes <= self.max_bytes:
            self.entries[key] = prepared
            self.bytes_used += prepared.nbytes
        return prepared, False


def register_prepared(reference: PreparedSlide, moving: PreparedSlide) -> RegistrationResult:
    try:
        return _register_prepared(reference, moving, sigma=3)
    except AlignmentRejected as primary_error:
        try:
            return _register_prepared_components(reference, moving)
        except AlignmentRejected:
            pass
        if reference.thin_mask is not None and moving.thin_mask is not None:
            try:
                result = _register_prepared(
                    replace(reference, mask=reference.thin_mask),
                    replace(moving, mask=moving.thin_mask),
                    sigma=5,
                )
                return replace(
                    result, evidence={**result.evidence, "maskMode": "thin-tissue-fallback"}
                )
            except AlignmentRejected:
                pass
        if reference.calibrated is not None or moving.calibrated is not None:
            result = register_prepared(
                reference.calibrated or reference,
                moving.calibrated or moving,
            )
            return replace(result, evidence={**result.evidence, "maskMode": "calibrated-fallback"})
        raise primary_error


def _register_prepared_components(
    reference: PreparedSlide, moving: PreparedSlide
) -> RegistrationResult:
    """Bounded partial-tissue proposals with unchanged correspondence/geometry gates.

    Feature ambiguity between repeated fragments remains a rejection. No cells
    span the dropped fragments, and successful component maps remain approximate.
    """

    def components(prepared: PreparedSlide) -> list[PreparedSlide]:
        count, labels, stats, _ = cv2.connectedComponentsWithStats(prepared.mask)
        order = sorted(range(1, count), key=lambda i: int(stats[i, cv2.CC_STAT_AREA]), reverse=True)
        result = []
        for label in order[:3]:
            if stats[label, cv2.CC_STAT_AREA] < max(256, prepared.mask.size * 0.01):
                continue
            mask = (labels == label).astype(np.uint8) * 255
            xy = np.rint(prepared.points).astype(int)
            keep = (
                (
                    mask[
                        np.clip(xy[:, 1], 0, mask.shape[0] - 1),
                        np.clip(xy[:, 0], 0, mask.shape[1] - 1),
                    ]
                    > 0
                )
                if len(xy)
                else np.zeros(0, bool)
            )
            result.append(
                replace(
                    prepared,
                    mask=mask,
                    structure=np.where(mask > 0, prepared.structure, 0).astype(np.uint8),
                    points=prepared.points[keep],
                    descriptors=prepared.descriptors[keep]
                    if prepared.descriptors is not None
                    else None,
                    thin_mask=None,
                    calibrated=None,
                )
            )
        return result

    fixed = components(reference)
    floating = components(moving)
    if not fixed or not floating or (len(fixed) == len(floating) == 1):
        raise AlignmentRejected("Needs refinement: no partial component proposals")
    accepted = []
    checked = 0
    used = set()
    for source in floating:
        candidates = []
        for index, target in enumerate(fixed):
            checked += 1
            try:
                proposal = _register_prepared(target, source, sigma=3)
            except AlignmentRejected:
                continue
            if proposal.inlier_count >= 10:
                candidates.append((proposal.inlier_count, index, proposal))
        candidates.sort(key=lambda item: item[0], reverse=True)
        if not candidates:
            continue
        best = candidates[0]
        if len(candidates) > 1 and (
            best[0] < candidates[1][0] * 1.35 or best[0] - candidates[1][0] < 3
        ):
            continue
        if best[1] in used:
            continue
        used.add(best[1])
        accepted.append(best[2])
    if not accepted:
        raise AlignmentRejected("Needs refinement: ambiguous partial component correspondence")
    cells = [cell for result in accepted for cell in result.overview_triangles]
    best_map = max(accepted, key=lambda result: result.inlier_count)
    return replace(
        best_map,
        overview_triangles=cells,
        evidence={
            **best_map.evidence,
            "maskMode": "bounded-component-fallback",
            "componentPairsChecked": checked,
            "acceptedComponents": len(accepted),
            "overviewTriangleCount": len(cells),
        },
    )


def _overview_mask_seed(
    reference_mask: np.ndarray[Any, Any], moving_mask: np.ndarray[Any, Any]
) -> np.ndarray[Any, Any]:
    principal, principal_score = _mask_seed(reference_mask, moving_mask)
    reference_y, reference_x = np.nonzero(reference_mask)
    moving_y, moving_x = np.nonzero(moving_mask)
    reference_center = np.array([reference_x.mean(), reference_y.mean()])
    moving_center = np.array([moving_x.mean(), moving_y.mean()])
    scale = np.sqrt(len(reference_x) / len(moving_x))
    candidates = []
    for turns, rotation in enumerate(
        (
            ((1, 0), (0, 1)),
            ((0, -1), (1, 0)),
            ((-1, 0), (0, -1)),
            ((0, 1), (-1, 0)),
        )
    ):
        candidate = np.zeros((2, 3), dtype=np.float32)
        candidate[:, :2] = np.asarray(rotation) * scale
        candidate[:, 2] = reference_center - candidate[:, :2] @ moving_center
        warped = cv2.warpAffine(moving_mask, candidate, reference_mask.shape[::-1])
        intersection = int(np.count_nonzero(np.logical_and(warped, reference_mask)))
        dice = 2 * intersection / max(1, int(np.count_nonzero(warped)) + len(reference_x))
        candidates.append((dice, candidate, turns))
    candidates.sort(key=lambda item: item[0], reverse=True)
    best, second = candidates[:2]
    # Shape is only a coarse hint. Switch orientations only when the scanner
    # quarter-turn is clearly better than both the principal-axis and other turns.
    if (
        best[2] in (1, 3)
        and best[0] >= 0.75
        and best[0] > principal_score + 0.03
        and best[0] > second[0] + 0.015
    ):
        return best[1]
    return principal


def _register_prepared(
    reference: PreparedSlide, moving: PreparedSlide, *, sigma: int
) -> RegistrationResult:
    height, width = reference.mask.shape
    # Pyramid levels can differ; apply scale/shape gates to level-zero pixels.
    reference_to_full = np.diag([reference.full_size[0] / width, reference.full_size[1] / height])
    moving_from_full = np.diag(
        [moving.mask.shape[1] / moving.full_size[0], moving.mask.shape[0] / moving.full_size[1]]
    )
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
                full_linear = reference_to_full @ fitted[:, :2] @ moving_from_full
                scale = np.sqrt(abs(np.linalg.det(full_linear)))
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
        seed = _overview_mask_seed(reference.mask, moving.mask)
        scanner = np.asarray(
            [[width / moving.mask.shape[1], 0, 0], [0, height / moving.mask.shape[0], 0]],
            dtype=np.float32,
        )
        divisor = max(1.0, max(width, height, *moving.mask.shape) / 512)
        fixed = cv2.resize(
            reference.structure,
            (max(1, round(width / divisor)), max(1, round(height / divisor))),
        )
        floating = cv2.resize(
            moving.structure,
            tuple(max(1, round(side / divisor)) for side in moving.structure.shape[::-1]),
        )

        def resize_frame(
            original: np.ndarray[Any, Any], resized: np.ndarray[Any, Any]
        ) -> np.ndarray[Any, Any]:
            sx, sy = resized.shape[1] / original.shape[1], resized.shape[0] / original.shape[0]
            return np.asarray([[sx, 0, (sx - 1) / 2], [0, sy, (sy - 1) / 2], [0, 0, 1]])

        reference_frame = resize_frame(reference.structure, fixed)
        moving_frame = resize_frame(moving.structure, floating)
        fixed = cv2.GaussianBlur(fixed, (0, 0), sigma).astype(np.float32) / 255
        floating = cv2.GaussianBlur(floating, (0, 0), sigma).astype(np.float32) / 255
        candidates = []
        for initial, motion in ((scanner, cv2.MOTION_TRANSLATION), (seed, cv2.MOTION_AFFINE)):
            small_seed = (
                reference_frame @ np.vstack([initial, [0, 0, 1]]) @ np.linalg.inv(moving_frame)
            )
            inverse = cv2.invertAffineTransform(small_seed[:2]).astype(np.float32)
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
            candidate = (
                np.linalg.inv(reference_frame)
                @ np.vstack([cv2.invertAffineTransform(inverse), [0, 0, 1]])
                @ moving_frame
            )[:2]
            singular = np.linalg.svd(
                reference_to_full @ candidate[:, :2] @ moving_from_full, compute_uv=False
            )
            if (
                score < 0.65
                or singular[-1] < 0.5
                or singular[0] > 2
                or singular[0] / singular[-1] > 1.35
            ):
                continue
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
    result = RegistrationResult(
        status="approximate",
        moving_to_reference=transform.tolist(),
        reference_support=_support(reference.mask, 1),
        moving_support=_support(moving.mask, 1),
        confidence=min(0.49, dice / 2),
        inlier_count=inlier_count,
        match_count=len(matches),
        median_error_pixels=-1,
        control_points=controls,
        evidence={
            "mode": "approximate-overview",
            "source": "bounded-sparse-overview",
            "featureMatchCount": inlier_count,
            "triangleCount": 0,
            "tissueDice": round(dice, 6),
            "preparationVersion": PREPARATION_VERSION,
            "withheldCheck": "pending-independent-landmarks",
        },
    )
    result = rescale_registration(
        result,
        reference_thumbnail_size=(width, height),
        moving_thumbnail_size=(moving.mask.shape[1], moving.mask.shape[0]),
        reference_full_size=reference.full_size,
        moving_full_size=moving.full_size,
    )
    cells = _registration_triangles(
        result.control_points,
        moving_mask=moving.mask,
        reference_mask=reference.mask,
        moving_scale=(
            moving.mask.shape[1] / moving.full_size[0],
            moving.mask.shape[0] / moving.full_size[1],
        ),
        reference_scale=(width / reference.full_size[0], height / reference.full_size[1]),
    )
    if not cells:
        raise AlignmentRejected("Needs refinement: no supported overview cells")
    return replace(
        result,
        control_points=[],
        overview_triangles=cells,
        evidence={**result.evidence, "overviewTriangleCount": len(cells)},
    )
