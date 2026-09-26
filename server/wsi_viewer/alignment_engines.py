"""Adapters for reproducible open-source slide registration engines.

Engine-specific objects never cross this module boundary.  Every engine is
sampled into the same paired-triangle representation used by the viewer, so a
single triangle correspondence supplies both forward and inverse navigation.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import time
import types
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import cv2
import numpy as np
from PIL import Image

from .alignment import (
    AlignmentRejected,
    RegistrationResult,
    _registration_triangles,
    _structure,
    register_pair,
    rescale_registration,
)

ENGINE_NATIVE = "native-v12"
ENGINE_HISALIGN = "hisalign-0.2.1"
ENGINE_VALIS = "valis-1.2.0"
ENGINE_VERSIONS = {
    ENGINE_NATIVE: "piecewise-affine-components-v14",
    ENGINE_HISALIGN: "c56d1eb1a295aec00bf34c05e0274e2fd79fdaf5",
    ENGINE_VALIS: "325828c1dec444e6bb672a78e875537436dd3c20",
}
ADAPTER_VERSIONS = {
    ENGINE_NATIVE: "pathlab-adapter-v2-high-resolution-components",
    ENGINE_HISALIGN: "pathlab-adapter-v2-distributed-feature-gate",
    ENGINE_VALIS: "pathlab-adapter-v8-adaptive-disk-lightglue",
}
SUPPORTED_ENGINES = frozenset(ENGINE_VERSIONS)


class Progress(Protocol):
    def __call__(self, values: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class EngineInput:
    reference: Image.Image
    moving: Image.Image
    reference_full_size: tuple[int, int]
    moving_full_size: tuple[int, int]
    workspace: Path
    settings: dict[str, Any] | None = None


@dataclass(frozen=True)
class EngineRun:
    registration: dict[str, Any]
    artifact_path: Path | None
    artifact_sha256: str | None
    runtime_seconds: float


class RegistrationEngine(Protocol):
    name: str

    def available(self) -> tuple[bool, str | None]: ...

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun: ...


def engine_availability() -> dict[str, dict[str, str | bool | None]]:
    result: dict[str, dict[str, str | bool | None]] = {}
    for name in SUPPORTED_ENGINES:
        engine = get_engine(name)
        available, reason = engine.available()
        result[name] = {
            "available": available,
            "reason": reason,
            "buildVersion": ENGINE_VERSIONS[name],
        }
    return result


def settings_digest(engine: str, settings: dict[str, Any] | None = None) -> str:
    payload = {
        "engine": engine,
        "buildVersion": ENGINE_VERSIONS[engine],
        "adapterVersion": ADAPTER_VERSIONS[engine],
        "settings": settings or {},
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _affine_from_controls(controls: list[dict[str, Any]]) -> list[list[float]]:
    moving = np.asarray([item["moving"] for item in controls], dtype=np.float32)
    reference = np.asarray([item["reference"] for item in controls], dtype=np.float32)
    matrix, _ = cv2.estimateAffinePartial2D(moving, reference, method=cv2.LMEDS)
    if matrix is None:
        raise AlignmentRejected("engine transform did not yield a stable affine overview")
    values = np.asarray(matrix, dtype=np.float64).round(10)
    return [[float(value) for value in row] for row in values]


def _scanner_frame_candidate(
    reference_rgb: np.ndarray[Any, Any],
    moving_rgb: np.ndarray[Any, Any],
    *,
    maximum: int = 1024,
) -> tuple[np.ndarray[Any, Any], float, float] | None:
    """Return a bounded, stain-independent scanner-frame proposal.

    The proposal is useful as an external engine initializer, not anatomical
    evidence. Callers must still validate the resulting coordinate map.
    """

    def bounded(rgb: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
        height, width = rgb.shape[:2]
        scale = min(1.0, maximum / max(width, height))
        if scale == 1.0:
            return rgb
        return cv2.resize(
            rgb,
            (max(1, round(width * scale)), max(1, round(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

    reference_small = bounded(reference_rgb)
    moving_small = bounded(moving_rgb)
    reference_structure, reference_mask = _structure(reference_small)
    moving_structure, moving_mask = _structure(moving_small)
    forward = np.asarray(
        [
            [reference_mask.shape[1] / moving_mask.shape[1], 0.0, 0.0],
            [0.0, reference_mask.shape[0] / moving_mask.shape[0], 0.0],
        ],
        dtype=np.float32,
    )
    inverse = cv2.invertAffineTransform(forward)
    try:
        score, inverse = cv2.findTransformECC(  # type: ignore[call-overload]
            cv2.GaussianBlur(reference_structure, (0, 0), 4).astype(np.float32) / 255,
            cv2.GaussianBlur(moving_structure, (0, 0), 4).astype(np.float32) / 255,
            inverse,
            cv2.MOTION_TRANSLATION,
            (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6),
            None,
            7,
        )
    except cv2.error:
        return None
    transform: np.ndarray[Any, Any] = cv2.invertAffineTransform(inverse)
    warped_mask: np.ndarray[Any, Any] = cv2.warpAffine(
        moving_mask,
        transform,
        (reference_mask.shape[1], reference_mask.shape[0]),
    )
    intersection = int(np.count_nonzero((warped_mask > 0) & (reference_mask > 0)))
    overlap = (
        2
        * intersection
        / max(
            1,
            int(np.count_nonzero(warped_mask)) + int(np.count_nonzero(reference_mask)),
        )
    )
    if score < 0.45 or overlap < 0.5:
        return None
    reference_scale = np.asarray(
        [
            reference_rgb.shape[1] / reference_small.shape[1],
            reference_rgb.shape[0] / reference_small.shape[0],
        ]
    )
    moving_scale = np.asarray(
        [
            moving_rgb.shape[1] / moving_small.shape[1],
            moving_rgb.shape[0] / moving_small.shape[0],
        ]
    )
    full = np.zeros((2, 3), dtype=np.float64)
    full[:, :2] = np.diag(reference_scale) @ transform[:, :2] @ np.diag(1 / moving_scale)
    full[:, 2] = transform[:, 2] * reference_scale
    return full, float(score), float(overlap)


def _sample_coordinate_map(
    *,
    reference_rgb: np.ndarray[Any, Any],
    moving_rgb: np.ndarray[Any, Any],
    map_moving_to_reference: Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]],
    map_reference_to_moving: Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]],
    provenance: str,
    grid_size: int = 25,
    minimum_tissue_dice: float = 0.68,
) -> RegistrationResult:
    """Sample an upstream dense transform into invertible paired triangles."""
    _, moving_mask = _structure(moving_rgb)
    _, reference_mask = _structure(reference_rgb)
    height, width = moving_mask.shape
    nonzero = cv2.findNonZero(moving_mask)
    if nonzero is None:
        raise AlignmentRejected("engine map has no moving tissue support")
    bx, by, bw, bh = cv2.boundingRect(nonzero)
    xs = np.linspace(bx, bx + bw - 1, grid_size)
    ys = np.linspace(by, by + bh - 1, grid_size)
    moving_points = np.asarray([(x, y) for y in ys for x in xs], dtype=np.float64)
    tissue = (
        moving_mask[
            np.clip(np.rint(moving_points[:, 1]).astype(int), 0, height - 1),
            np.clip(np.rint(moving_points[:, 0]).astype(int), 0, width - 1),
        ]
        > 0
    )
    moving_points = moving_points[tissue]
    if len(moving_points) < 9:
        raise AlignmentRejected(
            f"engine map has insufficient distributed tissue support ({len(moving_points)} samples)"
        )
    reference_points = np.asarray(map_moving_to_reference(moving_points), dtype=np.float64)
    if reference_points.shape != moving_points.shape or not np.isfinite(reference_points).all():
        raise AlignmentRejected("engine returned invalid forward coordinates")
    restored = np.asarray(map_reference_to_moving(reference_points), dtype=np.float64)
    if restored.shape != moving_points.shape or not np.isfinite(restored).all():
        raise AlignmentRejected("engine returned invalid inverse coordinates")
    cycle = np.linalg.norm(restored - moving_points, axis=1)
    inside = (
        (reference_points[:, 0] >= 0)
        & (reference_points[:, 1] >= 0)
        & (reference_points[:, 0] < reference_mask.shape[1])
        & (reference_points[:, 1] < reference_mask.shape[0])
    )
    reference_tissue = np.zeros(len(reference_points), dtype=bool)
    valid_indexes = np.where(inside)[0]
    reference_tissue[valid_indexes] = (
        reference_mask[
            np.rint(reference_points[valid_indexes, 1]).astype(int),
            np.rint(reference_points[valid_indexes, 0]).astype(int),
        ]
        > 0
    )
    accepted = inside & reference_tissue & (cycle <= 0.5)
    if int(np.count_nonzero(accepted)) < 9:
        raise AlignmentRejected(
            "engine map failed tissue support or round-trip validation "
            f"({int(np.count_nonzero(accepted))}/{len(moving_points)} accepted, "
            f"cycle p95 {float(np.percentile(cycle, 95)):.3f}px)"
        )
    moving_points = moving_points[accepted]
    reference_points = reference_points[accepted]
    cycle = cycle[accepted]
    controls = [
        {
            "moving": source.round(4).tolist(),
            "reference": target.round(4).tolist(),
            "errorPixels": round(float(error), 4),
            "provenance": provenance,
        }
        for source, target, error in zip(moving_points, reference_points, cycle, strict=True)
    ]
    affine = _affine_from_controls(controls)
    warped_mask: np.ndarray[Any, Any] = cv2.warpAffine(
        moving_mask,
        np.asarray(affine, dtype=np.float32),
        (reference_mask.shape[1], reference_mask.shape[0]),
    )
    intersection = int(np.count_nonzero((warped_mask > 0) & (reference_mask > 0)))
    tissue_dice = (
        2
        * intersection
        / max(1, int(np.count_nonzero(warped_mask)) + int(np.count_nonzero(reference_mask)))
    )
    if tissue_dice < minimum_tissue_dice:
        raise AlignmentRejected(
            f"engine map failed whole-tissue overlap validation ({tissue_dice:.3f} Dice)"
        )
    triangles = _registration_triangles(
        controls,
        moving_mask=moving_mask,
        reference_mask=reference_mask,
    )
    for triangle in triangles:
        triangle["provenance"] = provenance
    if not triangles:
        raise AlignmentRejected("engine map contains no non-folded supported cells")
    moving_support = cv2.boundingRect(cv2.findNonZero(moving_mask))
    reference_support = cv2.boundingRect(cv2.findNonZero(reference_mask))
    mx, my, mw, mh = moving_support
    rx, ry, rw, rh = reference_support
    cycle_p95 = float(np.percentile(cycle, 95))
    return RegistrationResult(
        status="ready",
        moving_to_reference=affine,
        reference_support=(rx, ry, rx + rw, ry + rh),
        moving_support=(mx, my, mx + mw, my + mh),
        confidence=max(0.0, min(0.99, 1.0 - cycle_p95 / 2.0)),
        inlier_count=len(controls),
        match_count=len(controls),
        median_error_pixels=float(np.median(cycle)),
        control_points=controls,
        triangles=triangles,
        evidence={
            "mode": "matched-regions",
            "engine": provenance,
            "triangleCount": len(triangles),
            "sampledControlCount": len(controls),
            "roundTripP95Pixels": round(cycle_p95, 6),
            "tissueDice": round(tissue_dice, 6),
            "withheldCheck": "engine-cycle-tissue-support-and-overlap",
        },
    )


def _mark_approximate_engine_map(payload: dict[str, Any], *, reason: str) -> dict[str, Any]:
    """Keep a useful whole-slide proposal without claiming local anatomy.

    Dense-flow cycle consistency only proves that an engine can invert its own
    transform. It does not prove that the transform joins corresponding
    anatomy, so maps without distributed matched features are overview-only.
    """
    result = dict(payload)
    result["status"] = "approximate"
    result["reason"] = reason
    result["confidence"] = min(0.49, float(result.get("confidence") or 0.0))
    result["overviewTriangles"] = list(result.get("triangles") or [])
    result["triangles"] = []
    result["controlPoints"] = []
    result["inlierCount"] = 0
    result["supportPolygons"] = {"moving": [], "reference": []}
    evidence = dict(result.get("evidence") or {})
    evidence.update(
        {
            "mode": "approximate-overview",
            "withheldCheck": "insufficient-distributed-anatomical-features",
        }
    )
    result["evidence"] = evidence
    return result


class NativeEngine:
    name = ENGINE_NATIVE

    def available(self) -> tuple[bool, str | None]:
        return True, None

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        started = time.monotonic()
        progress({"stage": "native-registration", "progress": 30})
        result = register_pair(inputs.reference, inputs.moving, max_dimension=4096)
        result = rescale_registration(
            result,
            reference_thumbnail_size=inputs.reference.size,
            moving_thumbnail_size=inputs.moving.size,
            reference_full_size=inputs.reference_full_size,
            moving_full_size=inputs.moving_full_size,
        )
        payload = result.as_json()
        payload["engine"] = self.name
        payload["engineVersion"] = ENGINE_VERSIONS[self.name]
        return EngineRun(payload, None, None, time.monotonic() - started)


class HisAlignEngine:
    name = ENGINE_HISALIGN

    @staticmethod
    def _prepare_imports() -> None:
        # HISAlign imports its optional KFB reader from package __init__ even
        # when registration receives in-memory arrays. The adapter never opens
        # KFB files, so provide only the unused module boundary.
        sys.modules.setdefault("kfbslide", types.ModuleType("kfbslide"))

    def available(self) -> tuple[bool, str | None]:
        if importlib.util.find_spec("hisalign") is None:
            return False, "HISAlign runtime is not installed in this worker image"
        # Discovery must not load models into the API/foreground worker.
        # Import and execution are validated in the isolated registration child.
        return True, None

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        self._prepare_imports()
        available, reason = self.available()
        if not available:
            raise AlignmentRejected(reason or "HISAlign is unavailable")
        optical_density_gray = importlib.import_module(
            "hisalign.preprocessing"
        ).optical_density_gray
        feature_detectors = importlib.import_module("hisalign.registration.feature_detectors")
        feature_matcher = importlib.import_module("hisalign.registration.feature_matcher")
        NonRigidRegistrar = importlib.import_module(
            "hisalign.registration.non_rigid"
        ).NonRigidRegistrar
        RigidRegistrar = importlib.import_module("hisalign.registration.rigid").RigidRegistrar

        started = time.monotonic()
        reference_rgb = np.asarray(inputs.reference.convert("RGB"), dtype=np.uint8)
        moving_rgb = np.asarray(inputs.moving.convert("RGB"), dtype=np.uint8)
        progress({"stage": "hisalign-preprocessing", "progress": 20})
        reference_gray = optical_density_gray(reference_rgb)
        moving_gray = optical_density_gray(moving_rgb)
        height = max(reference_gray.shape[0], moving_gray.shape[0])
        width = max(reference_gray.shape[1], moving_gray.shape[1])

        def pad(image: np.ndarray[Any, Any]) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
            matrix = np.asarray(
                [
                    [1.0, 0.0, (width - image.shape[1]) / 2],
                    [0.0, 1.0, (height - image.shape[0]) / 2],
                    [0.0, 0.0, 1.0],
                ],
                dtype=np.float64,
            )
            return cv2.warpPerspective(image, matrix, (width, height)), matrix

        reference_padded, reference_padding = pad(reference_gray)
        moving_padded, moving_padding = pad(moving_gray)
        detector = feature_detectors.create_feature_detector("kaze", n_levels=3)
        matcher = feature_matcher.Matcher(feature_detector=detector, max_ratio=0.8)
        progress({"stage": "hisalign-rigid", "progress": 40})
        rigid = RigidRegistrar(
            ref_img=reference_padded,
            moving_img=moving_padded,
            ref_name="reference",
            moving_name="moving",
        )
        rigid.fit(feature_detector=detector, matcher=matcher, transform_type="similarity")
        _, reference_mask = _structure(reference_rgb)
        _, moving_mask = _structure(moving_rgb)

        def padded_tissue_dice(matrix: np.ndarray[Any, Any]) -> float:
            reference_padded_mask: np.ndarray[Any, Any] = cv2.warpPerspective(
                reference_mask, reference_padding, (width, height)
            )
            moving_padded_mask = cv2.warpPerspective(moving_mask, moving_padding, (width, height))
            warped: np.ndarray[Any, Any] = cv2.warpPerspective(
                moving_padded_mask,
                matrix,
                (width, height),
            )
            intersection = int(np.count_nonzero((warped > 0) & (reference_padded_mask > 0)))
            return (
                2
                * intersection
                / max(
                    1,
                    int(np.count_nonzero(warped)) + int(np.count_nonzero(reference_padded_mask)),
                )
            )

        feature_dice = padded_tissue_dice(np.asarray(rigid.M))
        initializer = "hisalign-kaze"
        scanner_score = -1.0
        scanner_dice = -1.0
        scanner = _scanner_frame_candidate(reference_rgb, moving_rgb)
        if scanner is not None:
            scanner_transform, scanner_score, _ = scanner
            scanner_homogeneous = np.eye(3, dtype=np.float64)
            scanner_homogeneous[:2] = scanner_transform
            scanner_padded = reference_padding @ scanner_homogeneous @ np.linalg.inv(moving_padding)
            scanner_dice = padded_tissue_dice(scanner_padded)
            if rigid.n_matches < 8 or scanner_dice >= feature_dice + 0.05:
                rigid.M = scanner_padded
                initializer = "scanner-structure"
        progress({"stage": "hisalign-non-rigid", "progress": 60})
        non_rigid = NonRigidRegistrar(
            ref_img=reference_padded,
            moving_img=moving_padded,
            M=rigid.M,
            ref_name="reference",
            moving_name="moving",
        )
        non_rigid.fit()
        reference_matches = np.asarray(
            rigid.matched_kp_ref if rigid.matched_kp_ref is not None else [],
            dtype=np.float64,
        ).reshape((-1, 2))
        moving_matches = np.asarray(
            rigid.matched_kp_moving if rigid.matched_kp_moving is not None else [],
            dtype=np.float64,
        ).reshape((-1, 2))
        feature_spread = 0.0
        feature_residual = float("inf")
        if len(reference_matches) >= 3 and len(moving_matches) == len(reference_matches):
            reference_area = float(
                cv2.contourArea(cv2.convexHull(reference_matches.astype(np.float32)))
            )
            moving_area = float(cv2.contourArea(cv2.convexHull(moving_matches.astype(np.float32))))
            feature_spread = min(reference_area, moving_area) / max(1.0, float(width * height))
            warped_matches = np.asarray(non_rigid.warp_xy(moving_matches), dtype=np.float64)
            feature_residual = float(
                np.median(np.linalg.norm(warped_matches - reference_matches, axis=1))
            )
        feature_residual_limit = 0.02 * float(np.hypot(width, height))
        local_evidence_qualified = bool(
            rigid.n_matches >= 8
            and feature_spread >= 0.08
            and feature_residual <= feature_residual_limit
        )
        moving_padding_inverse = np.linalg.inv(moving_padding)
        reference_padding_inverse = np.linalg.inv(reference_padding)

        def homogeneous(
            points: np.ndarray[Any, Any], matrix: np.ndarray[Any, Any]
        ) -> np.ndarray[Any, Any]:
            values = np.column_stack([points, np.ones(len(points))]) @ matrix.T
            return np.asarray(values[:, :2] / values[:, 2:3], dtype=np.float64)

        def forward(points: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            padded = homogeneous(points, moving_padding)
            mapped = non_rigid.warp_xy(padded)
            return np.asarray(
                homogeneous(np.asarray(mapped), reference_padding_inverse),
                dtype=np.float64,
            )

        def inverse(points: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            padded = homogeneous(points, reference_padding)
            mapped = non_rigid.inverse_warp_xy(padded)
            return np.asarray(
                homogeneous(np.asarray(mapped), moving_padding_inverse),
                dtype=np.float64,
            )

        progress({"stage": "hisalign-coordinate-map", "progress": 75})
        result = _sample_coordinate_map(
            reference_rgb=reference_rgb,
            moving_rgb=moving_rgb,
            map_moving_to_reference=forward,
            map_reference_to_moving=inverse,
            provenance=self.name,
        )
        result = rescale_registration(
            result,
            reference_thumbnail_size=inputs.reference.size,
            moving_thumbnail_size=inputs.moving.size,
            reference_full_size=inputs.reference_full_size,
            moving_full_size=inputs.moving_full_size,
        )
        artifact = inputs.workspace / "hisalign-coordinate-model.npz"
        np.savez_compressed(
            artifact,
            rigid=np.asarray(rigid.M),
            backward_dx=np.asarray(non_rigid.bk_dxdy[0]),
            backward_dy=np.asarray(non_rigid.bk_dxdy[1]),
            forward_dx=np.asarray(non_rigid.fwd_dxdy[0]),
            forward_dy=np.asarray(non_rigid.fwd_dxdy[1]),
        )
        payload = result.as_json()
        if not local_evidence_qualified:
            payload = _mark_approximate_engine_map(
                payload,
                reason=(
                    "HISAlign produced a whole-slide proposal but did not find enough "
                    "spatially distributed anatomical feature matches for local synchronization"
                ),
            )
        payload["engine"] = self.name
        payload["engineVersion"] = ENGINE_VERSIONS[self.name]
        payload["evidence"] = {
            **payload.get("evidence", {}),
            "rigidInitializer": initializer,
            "adapterVersion": ADAPTER_VERSIONS[self.name],
            "hisalignFeatureMatches": int(rigid.n_matches),
            "hisalignFeatureTissueDice": round(feature_dice, 6),
            "hisalignFeatureSpatialSpread": round(feature_spread, 6),
            "hisalignFeatureResidualPixels": (
                round(feature_residual, 6) if np.isfinite(feature_residual) else None
            ),
            "hisalignLocalEvidenceQualified": local_evidence_qualified,
            "scannerStructureScore": round(scanner_score, 6),
            "scannerTissueDice": round(scanner_dice, 6),
        }
        return EngineRun(payload, artifact, _hash_file(artifact), time.monotonic() - started)


class ValisEngine:
    name = ENGINE_VALIS

    def available(self) -> tuple[bool, str | None]:
        if importlib.util.find_spec("valis") is None:
            return False, "VALIS runtime is not installed in this worker image"
        # VALIS import can initialize Torch models and a JVM. Keep that cost
        # inside the bounded child, never in capability polling.
        return True, None

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        available, reason = self.available()
        if not available:
            raise AlignmentRejected(reason or "VALIS is unavailable")
        registration = importlib.import_module("valis.registration")

        started = time.monotonic()
        source = inputs.workspace / "valis-input"
        output = inputs.workspace / "valis-output"
        source.mkdir(parents=True, exist_ok=True)
        reference_path = source / "00-reference.png"
        moving_path = source / "01-moving.png"
        inputs.reference.save(reference_path)
        inputs.moving.save(moving_path)
        progress({"stage": "valis-rigid-and-non-rigid", "progress": 35})
        maximum_dimension = int((inputs.settings or {}).get("maxImageDimension", 896))
        if maximum_dimension not in {768, 896}:
            raise AlignmentRejected("VALIS image dimension must use a qualified profile")
        registrar = registration.Valis(
            str(source),
            str(output),
            reference_img_f=reference_path.name,
            imgs_ordered=True,
            align_to_reference=True,
            # VALIS otherwise promotes its default 1024-pixel reader limit to
            # max_processed_image_dim_px and materializes several 4096-pixel
            # float images during non-rigid registration.  That exceeded the
            # worker's 7 GiB process ceiling for ordinary two-slide stacks.
            # VALIS can expand a rotated rematching canvas to roughly twice
            # this dimension. 896 retains more feature detail than the safe
            # 768 fallback while leaving enough headroom below the 7 GiB child
            # process ceiling on the development pair.
            max_image_dim_px=maximum_dimension,
            max_processed_image_dim_px=maximum_dimension,
            max_non_rigid_registration_dim_px=1024,
        )
        _, _, error_df = registrar.register()
        if error_df is None:
            raise AlignmentRejected("VALIS registration did not produce validation evidence")
        moving_slide = registrar.get_slide(moving_path.name)
        reference_slide = registrar.get_slide(reference_path.name)
        if moving_slide is None or reference_slide is None:
            raise AlignmentRejected("VALIS did not expose both registered slides")

        def forward(points: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            return np.asarray(
                moving_slide.warp_xy_from_to(points, reference_slide), dtype=np.float64
            )

        def inverse(points: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            return np.asarray(
                reference_slide.warp_xy_from_to(points, moving_slide), dtype=np.float64
            )

        progress({"stage": "valis-coordinate-map", "progress": 75})
        result = _sample_coordinate_map(
            reference_rgb=np.asarray(inputs.reference.convert("RGB")),
            moving_rgb=np.asarray(inputs.moving.convert("RGB")),
            map_moving_to_reference=forward,
            map_reference_to_moving=inverse,
            provenance=self.name,
            # Serial sections can have real missing edge tissue, so VALIS is
            # allowed to produce a preview map below the strict whole-outline
            # threshold. Distributed feature evidence below decides whether
            # the result may be called locally aligned.
            minimum_tissue_dice=0.45,
        )
        raw_moving_matches = getattr(moving_slide, "xy_matched_to_prev", None)
        raw_reference_matches = getattr(moving_slide, "xy_in_prev", None)
        moving_matches = np.asarray(
            raw_moving_matches if raw_moving_matches is not None else [],
            dtype=np.float64,
        ).reshape(-1, 2)
        reference_matches = np.asarray(
            raw_reference_matches if raw_reference_matches is not None else [],
            dtype=np.float64,
        ).reshape(-1, 2)
        if len(moving_matches):
            moving_matches *= np.asarray(
                moving_slide.slide_dimensions_wh[0], dtype=np.float64
            ) / np.asarray(moving_slide.processed_img_shape_rc[::-1], dtype=np.float64)
        if len(reference_matches):
            reference_matches *= np.asarray(
                reference_slide.slide_dimensions_wh[0], dtype=np.float64
            ) / np.asarray(reference_slide.processed_img_shape_rc[::-1], dtype=np.float64)
        match_count = min(len(moving_matches), len(reference_matches))
        moving_matches = moving_matches[:match_count]
        reference_matches = reference_matches[:match_count]
        match_spread = 0.0
        if match_count >= 3:
            moving_area = float(cv2.contourArea(cv2.convexHull(moving_matches.astype(np.float32))))
            reference_area = float(
                cv2.contourArea(cv2.convexHull(reference_matches.astype(np.float32)))
            )
            match_spread = min(
                moving_area / max(1.0, float(np.prod(inputs.moving.size))),
                reference_area / max(1.0, float(np.prod(inputs.reference.size))),
            )
        match_residual = float("inf")
        if match_count:
            match_residual = float(
                np.median(
                    np.linalg.norm(
                        forward(moving_matches) - reference_matches,
                        axis=1,
                    )
                )
            )
        valis_non_rigid_rtre = float("inf")
        try:
            error_rows = error_df.to_dict(orient="records")
            moving_names = {moving_path.name, moving_path.stem}
            moving_row = next(
                row
                for row in error_rows
                if str(row.get("from") or "") in moving_names
                or Path(str(row.get("filename") or "")).name == moving_path.name
            )
            raw_rtre = moving_row.get("non_rigid_rTRE")
            if raw_rtre is None or not np.isfinite(float(raw_rtre)):
                raw_rtre = moving_row.get("rigid_rTRE")
            if raw_rtre is not None and np.isfinite(float(raw_rtre)):
                valis_non_rigid_rtre = float(raw_rtre)
        except (StopIteration, TypeError, ValueError):
            pass
        tissue_dice = float(result.evidence.get("tissueDice") or 0.0)
        local_evidence_qualified = bool(
            match_count >= 8
            and match_spread >= 0.08
            and valis_non_rigid_rtre <= 0.02
            and tissue_dice >= 0.45
        )
        result = rescale_registration(
            result,
            reference_thumbnail_size=inputs.reference.size,
            moving_thumbnail_size=inputs.moving.size,
            reference_full_size=inputs.reference_full_size,
            moving_full_size=inputs.moving_full_size,
        )
        artifact = inputs.workspace / "valis-coordinate-map.json"
        artifact.write_text(json.dumps(result.as_json(), separators=(",", ":")))
        payload = result.as_json()
        if not local_evidence_qualified:
            payload = _mark_approximate_engine_map(
                payload,
                reason=(
                    "VALIS produced a whole-slide proposal but did not find enough "
                    "spatially distributed anatomical feature matches for local synchronization"
                ),
            )
        payload["engine"] = self.name
        payload["engineVersion"] = ENGINE_VERSIONS[self.name]
        payload["evidence"] = {
            **payload.get("evidence", {}),
            "adapterVersion": ADAPTER_VERSIONS[self.name],
            "valisImageDimension": maximum_dimension,
            "valisFeatureMatches": match_count,
            "valisFeatureSpatialSpread": round(match_spread, 6),
            "valisFeatureResidualPixels": (
                round(match_residual, 6) if np.isfinite(match_residual) else None
            ),
            "valisNonRigidRTRE": (
                round(valis_non_rigid_rtre, 8) if np.isfinite(valis_non_rigid_rtre) else None
            ),
            "valisLocalEvidenceQualified": local_evidence_qualified,
        }
        return EngineRun(payload, artifact, _hash_file(artifact), time.monotonic() - started)


def get_engine(name: str) -> RegistrationEngine:
    if name == ENGINE_NATIVE:
        return NativeEngine()
    if name == ENGINE_HISALIGN:
        return HisAlignEngine()
    if name == ENGINE_VALIS:
        return ValisEngine()
    raise ValueError(f"Unsupported registration engine: {name}")


def run_engine(
    name: str,
    *,
    reference: Image.Image,
    moving: Image.Image,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    workspace_root: Path | None = None,
    artifact_dir: Path | None = None,
    settings: dict[str, Any] | None = None,
    progress: Progress = lambda _values: None,
) -> EngineRun:
    root = workspace_root or Path(tempfile.gettempdir())
    with tempfile.TemporaryDirectory(prefix=f"pathlab-{name}-", dir=root) as temporary:
        run = get_engine(name).register(
            EngineInput(
                reference=reference,
                moving=moving,
                reference_full_size=reference_full_size,
                moving_full_size=moving_full_size,
                workspace=Path(temporary),
                settings=settings,
            ),
            progress,
        )
        if run.artifact_path is None or artifact_dir is None:
            return run
        artifact_dir.mkdir(parents=True, exist_ok=True)
        destination = artifact_dir / run.artifact_path.name
        temporary_destination = artifact_dir / f".{run.artifact_path.name}.tmp"
        shutil.copyfile(run.artifact_path, temporary_destination)
        temporary_destination.replace(destination)
        return EngineRun(
            run.registration,
            destination,
            run.artifact_sha256,
            run.runtime_seconds,
        )
