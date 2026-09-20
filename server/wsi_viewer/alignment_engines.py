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
    ENGINE_NATIVE: "piecewise-affine-components-v12",
    ENGINE_HISALIGN: "c56d1eb1a295aec00bf34c05e0274e2fd79fdaf5",
    ENGINE_VALIS: "325828c1dec444e6bb672a78e875537436dd3c20",
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


def _sample_coordinate_map(
    *,
    reference_rgb: np.ndarray,
    moving_rgb: np.ndarray,
    map_moving_to_reference: Callable[[np.ndarray], np.ndarray],
    map_reference_to_moving: Callable[[np.ndarray], np.ndarray],
    provenance: str,
    grid_size: int = 25,
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
    warped_mask = cv2.warpAffine(
        moving_mask,
        np.asarray(affine, dtype=np.float32),
        (reference_mask.shape[1], reference_mask.shape[0]),
    )
    intersection = int(np.count_nonzero((warped_mask > 0) & (reference_mask > 0)))
    tissue_dice = 2 * intersection / max(
        1, int(np.count_nonzero(warped_mask)) + int(np.count_nonzero(reference_mask))
    )
    if tissue_dice < 0.68:
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
        try:
            self._prepare_imports()
            __import__("hisalign.registration.non_rigid")
        except Exception as error:
            return False, f"HISAlign runtime import failed: {type(error).__name__}"
        return True, None

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        self._prepare_imports()
        available, reason = self.available()
        if not available:
            raise AlignmentRejected(reason or "HISAlign is unavailable")
        from hisalign.preprocessing import optical_density_gray  # type: ignore[import-untyped]
        from hisalign.registration import (  # type: ignore[import-untyped]
            feature_detectors,
            feature_matcher,
        )
        from hisalign.registration.non_rigid import (  # type: ignore[import-untyped]
            NonRigidRegistrar,
        )
        from hisalign.registration.rigid import RigidRegistrar  # type: ignore[import-untyped]

        started = time.monotonic()
        reference_rgb = np.asarray(inputs.reference.convert("RGB"), dtype=np.uint8)
        moving_rgb = np.asarray(inputs.moving.convert("RGB"), dtype=np.uint8)
        progress({"stage": "hisalign-preprocessing", "progress": 20})
        reference_gray = optical_density_gray(reference_rgb)
        moving_gray = optical_density_gray(moving_rgb)
        height = max(reference_gray.shape[0], moving_gray.shape[0])
        width = max(reference_gray.shape[1], moving_gray.shape[1])

        def pad(image: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
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
        progress({"stage": "hisalign-non-rigid", "progress": 60})
        non_rigid = NonRigidRegistrar(
            ref_img=reference_padded,
            moving_img=moving_padded,
            M=rigid.M,
            ref_name="reference",
            moving_name="moving",
        )
        non_rigid.fit()
        moving_padding_inverse = np.linalg.inv(moving_padding)
        reference_padding_inverse = np.linalg.inv(reference_padding)

        def homogeneous(points: np.ndarray, matrix: np.ndarray) -> np.ndarray:
            values = np.column_stack([points, np.ones(len(points))]) @ matrix.T
            return np.asarray(values[:, :2] / values[:, 2:3], dtype=np.float64)

        def forward(points: np.ndarray) -> np.ndarray:
            padded = homogeneous(points, moving_padding)
            mapped = non_rigid.warp_xy(padded)
            return np.asarray(
                homogeneous(np.asarray(mapped), reference_padding_inverse),
                dtype=np.float64,
            )

        def inverse(points: np.ndarray) -> np.ndarray:
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
        payload["engine"] = self.name
        payload["engineVersion"] = ENGINE_VERSIONS[self.name]
        return EngineRun(payload, artifact, _hash_file(artifact), time.monotonic() - started)


class ValisEngine:
    name = ENGINE_VALIS

    def available(self) -> tuple[bool, str | None]:
        if importlib.util.find_spec("valis") is None:
            return False, "VALIS runtime is not installed in this worker image"
        try:
            __import__("valis.registration")
        except Exception as error:
            return False, f"VALIS runtime import failed: {type(error).__name__}"
        return True, None

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        available, reason = self.available()
        if not available:
            raise AlignmentRejected(reason or "VALIS is unavailable")
        from valis import (  # type: ignore[import-not-found]
            feature_detectors,
            feature_matcher,
            registration,
        )

        started = time.monotonic()
        source = inputs.workspace / "valis-input"
        output = inputs.workspace / "valis-output"
        source.mkdir(parents=True, exist_ok=True)
        reference_path = source / "00-reference.png"
        moving_path = source / "01-moving.png"
        inputs.reference.save(reference_path)
        inputs.moving.save(moving_path)
        progress({"stage": "valis-rigid-and-non-rigid", "progress": 35})
        detector = feature_detectors.KazeFD()
        matcher = feature_matcher.Matcher(feature_detector=detector)
        registrar = registration.Valis(
            str(source),
            str(output),
            reference_img_f=reference_path.name,
            imgs_ordered=True,
            feature_detector_cls=detector,
            matcher=matcher,
            matcher_for_sorting=matcher,
            max_processed_image_dim_px=4096,
            max_non_rigid_registration_dim_px=2048,
        )
        registrar.register()
        moving_slide = registrar.get_slide(moving_path.name)
        reference_slide = registrar.get_slide(reference_path.name)
        if moving_slide is None or reference_slide is None:
            raise AlignmentRejected("VALIS did not expose both registered slides")

        def forward(points: np.ndarray) -> np.ndarray:
            return np.asarray(
                moving_slide.warp_xy_from_to(points, reference_slide), dtype=np.float64
            )

        def inverse(points: np.ndarray) -> np.ndarray:
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
        payload["engine"] = self.name
        payload["engineVersion"] = ENGINE_VERSIONS[self.name]
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
