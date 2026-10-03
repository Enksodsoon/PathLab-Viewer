"""Optional upstream adapters. No method falls back to native registration."""

from __future__ import annotations

import copy
import importlib
import importlib.metadata
import json
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import cv2
import numpy as np
from PIL import Image

from .alignment import AlignmentRejected, rescale_registration
from .alignment_engines import (
    ENGINE_DHR_LEARNED,
    ENGINE_VERSIONS,
    ENGINE_WSIREG,
    EngineInput,
    EngineRun,
    Progress,
    _hash_file,
    _mark_approximate_engine_map,
    _sample_coordinate_map,
)


def _available(packages: tuple[str, ...]) -> tuple[bool, str | None]:
    for package in packages:
        try:
            found = importlib.util.find_spec(package)
        except (ImportError, ValueError):
            found = None
        if found is None:
            return False, f"{package} unavailable: optional runtime is not installed"
    return True, None


def _bounded(inputs: EngineInput) -> tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]:
    images = []
    for image in (inputs.reference, inputs.moving):
        bounded = image.convert("RGB").copy()
        bounded.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
        images.append(np.asarray(bounded))
    return images[0], images[1]


def _finish(
    inputs: EngineInput,
    name: str,
    reference: np.ndarray[Any, Any],
    moving: np.ndarray[Any, Any],
    forward: Any,
    inverse: Any,
    started: float,
    metadata: dict[str, Any],
) -> EngineRun:
    result = _sample_coordinate_map(
        reference_rgb=reference,
        moving_rgb=moving,
        map_moving_to_reference=forward,
        map_reference_to_moving=inverse,
        provenance=name,
        grid_size=49,
        reference_cropped=(inputs.settings or {}).get("referenceCropped") is True,
        moving_cropped=(inputs.settings or {}).get("movingCropped") is True,
    )
    result = rescale_registration(
        result,
        reference_thumbnail_size=(reference.shape[1], reference.shape[0]),
        moving_thumbnail_size=(moving.shape[1], moving.shape[0]),
        reference_full_size=inputs.reference_full_size,
        moving_full_size=inputs.moving_full_size,
    )
    payload = _mark_approximate_engine_map(
        result.as_json(),
        reason="Engine proposal requires independently reviewed anatomical validation",
    )
    payload.update(
        engine=name, engineVersion=ENGINE_VERSIONS[name], engineSettings=inputs.settings or {}
    )
    payload["evidence"].update(metadata)
    payload["evidence"]["originalPixelsPreserved"] = True
    artifact = inputs.workspace / f"{name}-map.json"
    artifact.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    return EngineRun(payload, artifact, _hash_file(artifact), time.monotonic() - started)


def wsireg_pull_transform(tforms: list[dict[str, Any]]) -> Any:
    transforms = importlib.import_module("wsireg.reg_transforms.reg_transform")
    sequences = importlib.import_module("wsireg.reg_transforms.reg_transform_seq")
    # All maps from one upstream register_2d_images_itkelx call form one
    # elastix chain. wsireg reverses their order within this shared group.
    sequence = sequences.RegTransformSeq(
        [transforms.RegTransform(dict(t)) for t in tforms],
        transform_seq_idx=[0] * len(tforms),
    )
    return sequence.composite_transform


def invert_coordinate_pull(
    pull: Callable[[np.ndarray[Any, Any]], np.ndarray[Any, Any]],
    targets: np.ndarray[Any, Any],
    *,
    initial: np.ndarray[Any, Any] | None = None,
) -> np.ndarray[Any, Any]:
    """Bounded Newton inversion of sampled nonlinear pull coordinates.

    No image-sized displacement field is allocated. Positive finite local
    Jacobians and a measured subpixel residual are required for every sample.
    """
    targets = np.asarray(targets, dtype=np.float64)
    if targets.ndim != 2 or targets.shape[1] != 2 or len(targets) > 49 * 49:
        raise AlignmentRejected("nonlinear inverse exceeds the coordinate sample budget")
    points = targets.copy() if initial is None else np.asarray(initial, dtype=np.float64).copy()
    if (
        points.shape != targets.shape
        or not np.isfinite(points).all()
        or not np.isfinite(targets).all()
    ):
        raise AlignmentRejected("nonlinear inverse has invalid initial coordinates")
    epsilon = 0.25
    for _iteration in range(25):
        mapped = np.asarray(pull(points), dtype=np.float64)
        dx = (np.asarray(pull(points + [epsilon, 0])) - mapped) / epsilon
        dy = (np.asarray(pull(points + [0, epsilon])) - mapped) / epsilon
        jacobian = np.stack((dx, dy), axis=2)
        if mapped.shape != points.shape or not np.isfinite(jacobian).all():
            raise AlignmentRejected("nonlinear inverse has invalid Jacobian coordinates")
        determinant = np.linalg.det(jacobian)
        singular = np.linalg.svd(jacobian, compute_uv=False)
        if np.any(determinant <= 1e-5) or np.any(singular[:, 0] / singular[:, -1] > 20):
            raise AlignmentRejected("nonlinear inverse rejected a folded or unstable Jacobian")
        error = mapped - targets
        if np.max(np.linalg.norm(error, axis=1), initial=0) <= 0.025:
            return points
        update = np.linalg.solve(jacobian, error[..., None])[..., 0]
        if not np.isfinite(update).all() or np.any(np.linalg.norm(update, axis=1) > 512):
            raise AlignmentRejected("nonlinear inverse exceeded bounded Newton displacement")
        points -= update
    raise AlignmentRejected("nonlinear inverse did not converge within its bounded iterations")


class WsiregEngine:
    name = ENGINE_WSIREG

    def available(self) -> tuple[bool, str | None]:
        available, reason = _available(("wsireg", "itk", "SimpleITK"))
        if not available:
            return available, reason
        for package, expected in (("wsireg", "0.3.10"), ("itk-elastix", "0.25.4")):
            try:
                actual = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError:
                return False, f"{package} unavailable: missing pinned distribution metadata"
            if actual != expected:
                return False, f"{package} unavailable: expected {expected}, found {actual}"
        return True, None

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        available, reason = self.available()
        if not available:
            raise AlignmentRejected(reason or "wsireg unavailable")
        started = time.monotonic()
        sitk = importlib.import_module("SimpleITK")
        itk = importlib.import_module("itk")
        itk.MultiThreaderBase.SetGlobalDefaultNumberOfThreads(1)
        itk.MultiThreaderBase.SetGlobalMaximumNumberOfThreads(1)
        models = importlib.import_module("wsireg.parameter_maps.reg_model")
        registration = importlib.import_module("wsireg.utils.reg_utils")
        reference, moving = _bounded(inputs)
        settings = inputs.settings or {}
        models_requested = settings.get("models", ["rigid", "affine"])
        if not models_requested or any(
            x not in {"rigid", "affine", "similarity", "nl_reduced"} for x in models_requested
        ):
            raise AlignmentRejected("unsupported wsireg bounded model profile")
        calibration = []
        for key, full_size, rgb in (
            ("referenceMicronsPerPixel", inputs.reference_full_size, reference),
            ("movingMicronsPerPixel", inputs.moving_full_size, moving),
        ):
            value = np.asarray(settings.get(key, [1, 1]), dtype=np.float64)
            if value.shape != (2,) or not np.isfinite(value).all() or np.any(value <= 0):
                raise AlignmentRejected("invalid per-axis wsireg calibration")
            calibration.append(
                value * np.asarray(full_size) / np.asarray([rgb.shape[1], rgb.shape[0]])
            )

        def upstream_image(rgb: np.ndarray[Any, Any], spacing: np.ndarray[Any, Any]) -> Any:
            image = sitk.GetImageFromArray(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32))
            image.SetSpacing(tuple(float(x) for x in spacing))
            # The upstream registration helper accepts a RegImage boundary;
            # provide the two methods/attributes it uses without optional WSI readers.
            wrapper = SimpleNamespace(reg_image=image, mask=None)

            def convert() -> None:
                converted = itk.image_from_array(sitk.GetArrayFromImage(wrapper.reg_image))
                converted.SetSpacing(wrapper.reg_image.GetSpacing())
                wrapper.reg_image = converted

            wrapper.reg_image_sitk_to_itk = convert
            return wrapper

        progress({"stage": "wsireg-elastix", "progress": 30})
        output = inputs.workspace / "elastix"
        output.mkdir(parents=True, exist_ok=True)
        maps = [copy.deepcopy(models.RegModel[x].value) for x in models_requested]
        for params in maps:
            params["MaximumNumberOfIterations"] = [
                str(min(512, int(settings.get("iterations", 256))))
            ]
            params["NumberOfThreads"] = ["1"]
        tforms = registration.register_2d_images_itkelx(
            upstream_image(moving, calibration[1]),
            upstream_image(reference, calibration[0]),
            maps,
            output,
            return_image=False,
        )
        pull = wsireg_pull_transform(tforms)

        def inverse(points: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            return cast(
                np.ndarray[Any, Any],
                (
                    np.asarray([pull.TransformPoint(tuple(p * calibration[0])) for p in points])
                    / calibration[1]
                ),
            )

        nonlinear = any(t["Transform"][0] == "BSplineTransform" for t in tforms)
        linear = [t for t in tforms if t["Transform"][0] != "BSplineTransform"]
        push = wsireg_pull_transform(linear).GetInverse() if linear else None

        def forward(points: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
            initial = (
                np.asarray([push.TransformPoint(tuple(p * calibration[1])) for p in points])
                / calibration[0]
                if push
                else points.copy()
            )
            if nonlinear:
                return invert_coordinate_pull(inverse, points, initial=initial)
            return cast(np.ndarray[Any, Any], initial)

        return _finish(
            inputs,
            self.name,
            reference,
            moving,
            forward,
            inverse,
            started,
            {
                "wsiregModels": models_requested,
                "coordinateDirection": "inverse-elastix-pull",
                "inverseMethod": "bounded-sampled-newton-positive-jacobian"
                if nonlinear
                else "analytic-affine",
                "nonlinearInverseMaximumSamples": 2401 if nonlinear else None,
                "referenceSpacing": calibration[0].tolist(),
                "movingSpacing": calibration[1].tolist(),
                "calibrationUnit": "micrometers"
                if all(
                    settings.get(k) for k in ("referenceMicronsPerPixel", "movingMicronsPerPixel")
                )
                else "relative-pixel-frame",
                "maximumDimension": 2048,
                "cropOrigin": [0, 0],
            },
        )


def theta_pull_to_pixel(theta: np.ndarray[Any, Any], size: tuple[int, int]) -> np.ndarray[Any, Any]:
    """PyTorch align_corners=False: normalized target -> normalized source."""
    width, height = size
    normal = np.asarray(
        [[2 / width, 0, 1 / width - 1], [0, 2 / height, 1 / height - 1], [0, 0, 1.0]]
    )
    matrix = np.eye(3)
    matrix[:2] = np.asarray(theta).reshape(2, 3)
    return np.linalg.inv(normal) @ matrix @ normal


class DeeperHistRegEngine:
    def __init__(self, name: str):
        self.name = name

    def available(self) -> tuple[bool, str | None]:
        return _available(("deeperhistreg", "torch"))

    def register(self, inputs: EngineInput, progress: Progress) -> EngineRun:
        available, reason = self.available()
        if not available:
            raise AlignmentRejected(reason or "DeeperHistReg unavailable")
        started = time.monotonic()
        settings = inputs.settings or {}
        learned = self.name == ENGINE_DHR_LEARNED
        weights: dict[str, str] = {}
        if learned:
            for key in ("superpoint", "superglue"):
                path = Path(str(settings.get(f"{key}WeightsPath", "")))
                digest = settings.get(f"{key}WeightsSha256")
                if not path.is_file() or not digest or _hash_file(path) != digest:
                    raise AlignmentRejected(
                        f"DeeperHistReg learned unavailable: verified {key} "
                        "research weights required"
                    )
                weights[f"{key}_weights_path"] = str(path)
        torch = importlib.import_module("torch")
        torch.set_num_threads(1)
        with suppress(RuntimeError):
            torch.set_num_interop_threads(1)
        method_name = "superpoint_superglue" if learned else "sift_ransac"
        module = importlib.import_module(
            f"deeperhistreg.dhr_registration.dhr_initial_alignment.{method_name}"
        )
        reference, moving = _bounded(inputs)
        width = max(reference.shape[1], moving.shape[1])
        height = max(reference.shape[0], moving.shape[0])

        def tensor(rgb: np.ndarray[Any, Any]) -> Any:
            gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
            padded = np.ones((height, width), dtype=np.float32)
            padded[: gray.shape[0], : gray.shape[1]] = gray
            return torch.from_numpy(padded).unsqueeze(0).unsqueeze(0)

        progress({"stage": f"deeperhistreg-{method_name}", "progress": 30})
        # Genuine upstream feature methods; deliberately no native substitute.
        theta, matches = getattr(module, method_name)(
            tensor(moving),
            tensor(reference),
            {
                "echo": False,
                "show": False,
                "device": "cpu",
                "registration_size": min(1024, max(width, height)),
                "return_num_matches": True,
                "max_keypoints": 3000,
                "transform_type": "affine",
                **weights,
            },
        )
        if int(matches) < 8:
            raise AlignmentRejected("DeeperHistReg returned insufficient feature matches")
        pull = theta_pull_to_pixel(theta.detach().cpu().numpy(), (width, height))
        if not np.isfinite(pull).all() or abs(np.linalg.det(pull)) < 1e-8:
            raise AlignmentRejected("DeeperHistReg returned invalid affine transform")
        push = np.linalg.inv(pull)

        def apply(
            matrix: np.ndarray[Any, Any], points: np.ndarray[Any, Any]
        ) -> np.ndarray[Any, Any]:
            return cast(np.ndarray[Any, Any], points @ matrix[:2, :2].T + matrix[:2, 2])

        return _finish(
            inputs,
            self.name,
            reference,
            moving,
            lambda p: apply(push, p),
            lambda p: apply(pull, p),
            started,
            {
                "deeperHistRegMethod": method_name,
                "featureMatchCount": int(matches),
                "coordinateDirection": "normalized-target-to-source-pull-inverted",
                "researchOnly": learned,
                "maximumDimension": 2048,
                "weightsDigests": {
                    key: settings.get(f"{key}WeightsSha256") for key in ("superpoint", "superglue")
                }
                if learned
                else {},
                "cropOrigin": [0, 0],
                "paddedImageSize": [width, height],
            },
        )
