"""Explicit affine initialization followed by a genuine residual engine.

Only temporary images are warped. Stored maps always map original moving
level-zero coordinates to original reference level-zero coordinates.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any, cast

import cv2
import numpy as np
from PIL import Image

from . import alignment_engines as engines
from .alignment import AlignmentRejected, compose_transforms


class RecipeEngine:
    def __init__(self, name: str):
        self.name = name

    def available(self) -> tuple[bool, str | None]:
        for stage in engines.RECIPE_STAGES[self.name]:
            available, reason = engines.get_engine(stage).available()
            if not available:
                return False, f"{self.name}: {reason}"
        return True, None

    def register(
        self, inputs: engines.EngineInput, progress: engines.Progress
    ) -> engines.EngineRun:
        started = time.monotonic()
        settings = inputs.settings or {}
        total_budget = min(600.0, float(settings.get("timeoutSeconds", 600)))
        if total_budget <= 0:
            raise AlignmentRejected("registration exceeded the pair timeout")
        stages = engines.RECIPE_STAGES[self.name]
        receipts: list[dict[str, Any]] = []
        stage_settings = settings.get("stages", {})
        crop_provenance = {
            key: settings[key] for key in ("referenceCropped", "movingCropped") if key in settings
        }
        calibration: dict[str, list[float]] = {}
        for key in ("referenceMicronsPerPixel", "movingMicronsPerPixel"):
            if key in settings:
                value = np.asarray(settings[key], dtype=float)
                if value.shape != (2,) or not np.isfinite(value).all() or np.any(value <= 0):
                    raise AlignmentRejected("invalid per-axis recipe calibration")
                calibration[key] = [float(v) for v in value]

        def run(stage: str, stage_inputs: engines.EngineInput) -> engines.EngineRun:
            remaining = total_budget - (time.monotonic() - started)
            if remaining <= 0:
                raise AlignmentRejected("registration exceeded the pair timeout")
            values = {
                **stage_settings.get(stage, {}),
                **calibration,
                **crop_provenance,
                "timeoutSeconds": remaining,
                "maximumDimension": 2048,
            }
            if receipts and "referenceMicronsPerPixel" in calibration:
                # The residual's moving image has already been warped into
                # reference pixels. Caller moving calibration cannot survive it.
                values["referenceMicronsPerPixel"] = calibration["referenceMicronsPerPixel"]
                values["movingMicronsPerPixel"] = calibration["referenceMicronsPerPixel"]
            if receipts and "referenceCropped" in crop_provenance:
                values["movingCropped"] = crop_provenance["referenceCropped"]
            if stage == engines.ENGINE_VALIS and self.name == "valis-rigid-wsireg":
                values["rigidOnly"] = True
            stage_directory = inputs.workspace / f"stage-{len(receipts)}"
            stage_directory.mkdir(parents=True, exist_ok=True)
            stage_inputs = replace(stage_inputs, workspace=stage_directory, settings=values)
            progress({"stage": f"recipe-{stage}", "progress": 20 + len(receipts) * 35})
            result = engines.get_engine(stage).register(stage_inputs, progress)
            if time.monotonic() - started > total_budget:
                raise AlignmentRejected("registration exceeded the pair timeout")
            receipts.append(
                {
                    "engine": stage,
                    "buildVersion": engines.ENGINE_VERSIONS[stage],
                    "settingsDigest": engines.settings_digest(stage, values),
                    "runtimeSeconds": result.runtime_seconds,
                    "status": result.registration.get("status"),
                    "coordinateFrame": "level-zero-reference",
                }
            )
            return result

        seed = run(stages[0], inputs).registration
        initial = np.asarray(seed.get("movingToReference"), dtype=np.float64)
        if (
            initial.shape != (2, 3)
            or not np.isfinite(initial).all()
            or (abs(np.linalg.det(initial[:, :2])) < 1e-8)
            or seed.get("status") not in ("ready", "approximate")
        ):
            raise AlignmentRejected("recipe initializer has no invertible coordinate map")
        initializer_bytes = json.dumps(seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        if len(initializer_bytes) > engines.MAX_INITIALIZER_ARTIFACT_BYTES:
            raise AlignmentRejected("initializer provenance exceeds its size ceiling")
        initializer_artifact = inputs.workspace / engines.INITIALIZER_ARTIFACT_NAME
        initializer_artifact.write_bytes(initializer_bytes)
        initializer_descriptor = {
            "name": engines.INITIALIZER_ARTIFACT_NAME,
            "sha256": engines._hash_file(initializer_artifact),
        }
        if inputs.artifact_dir is not None:
            # Persist before the residual runs: hard supervisor termination
            # cannot execute this process's finally/temporary cleanup blocks.
            engines._copy_initializer_provenance(
                inputs.workspace, inputs.artifact_dir, initializer_descriptor
            )
        reference = inputs.reference.copy()
        reference.thumbnail((2048, 2048))
        # Convert level-zero initializer into input-image -> bounded reference-image pixels.
        ref_scale = np.diag(
            [
                reference.width / inputs.reference_full_size[0],
                reference.height / inputs.reference_full_size[1],
            ]
        )
        mov_scale = np.diag(
            [
                inputs.moving_full_size[0] / inputs.moving.width,
                inputs.moving_full_size[1] / inputs.moving.height,
            ]
        )
        image_initial = np.zeros((2, 3))
        image_initial[:, :2] = ref_scale @ initial[:, :2] @ mov_scale
        image_initial[:, 2] = ref_scale @ initial[:, 2]
        warped = cv2.warpAffine(
            np.asarray(inputs.moving.convert("RGB")),
            image_initial,
            reference.size,
            borderValue=(255, 255, 255),
        )
        residual = run(
            stages[1],
            replace(
                inputs,
                reference=reference,
                moving=Image.fromarray(warped),
                moving_full_size=inputs.reference_full_size,
            ),
        ).registration
        if residual.get("status") not in ("ready", "approximate"):
            raise AlignmentRejected("recipe residual has no supported map")
        inverse = cv2.invertAffineTransform(initial)

        def original(points: Any) -> list[list[float]]:
            array = np.asarray(points, dtype=np.float64)
            return cast(list[list[float]], (array @ inverse[:, :2].T + inverse[:, 2]).tolist())

        def cells(key: str) -> list[dict[str, Any]]:
            result = []
            for cell in residual.get(key) or []:
                moving = np.asarray(original(cell["moving"]))
                # Refuse original-frame extrapolation introduced by initializer padding.
                if np.any(moving < 0) or np.any(moving >= np.asarray(inputs.moving_full_size)):
                    continue
                result.append({**cell, "moving": moving.tolist(), "provenance": self.name})
            return result

        local = cells("triangles")
        overview = cells("overviewTriangles")
        if not local and not overview:
            raise AlignmentRejected("recipe has no supported original-frame cells")
        support_cells = local + overview

        def support(side: str) -> list[float]:
            vertices = np.asarray([point for cell in support_cells for point in cell[side]])
            low, high = vertices.min(axis=0), vertices.max(axis=0)
            return [float(low[0]), float(low[1]), float(high[0]), float(high[1])]

        payload = {
            **residual,
            "engine": self.name,
            "engineVersion": engines.ENGINE_VERSIONS[self.name],
            "movingToReference": compose_transforms(
                residual["movingToReference"], initial.tolist()
            ),
            "triangles": local,
            "overviewTriangles": overview,
            "movingSupport": support("moving"),
            "referenceSupport": support("reference"),
            "controlPoints": [
                {**p, "moving": original([p["moving"]])[0]}
                for p in residual.get("controlPoints") or []
            ],
            "supportPolygons": {
                "moving": [c["moving"] for c in local],
                "reference": [c["reference"] for c in local],
            },
            "recipeStages": receipts,
            "initializerArtifact": initializer_descriptor,
            "recipeFrames": {
                "initialMovingToReference": initial.tolist(),
                "residualFrame": "warped-moving-in-reference-level-zero",
                "referenceImageToFullScale": [
                    inputs.reference_full_size[0] / reference.width,
                    inputs.reference_full_size[1] / reference.height,
                ],
                "movingImageToFullScale": [
                    inputs.moving_full_size[0] / inputs.moving.width,
                    inputs.moving_full_size[1] / inputs.moving.height,
                ],
                "cropOrigin": [0, 0],
                "maximumDimension": 2048,
                "pairCalibration": calibration,
                "initializerKind": "affine-overview-in-level-zero-frame",
                "initializerSupportAppliedToWarp": False,
            },
        }
        if not local:
            payload["status"] = "approximate"
        artifact = inputs.workspace / "recipe-map.json"
        artifact.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
        return engines.EngineRun(
            payload, artifact, engines._hash_file(artifact), time.monotonic() - started
        )
