"""Compatibility checks shared by serving and selecting registration revisions."""

import math
from copy import deepcopy
from typing import Any

from .alignment import AlignmentRejected
from .alignment_calibration import metadata_frame_digest, normalized_microns_per_pixel
from .alignment_engines import ENGINE_VERSIONS, settings_digest
from .alignment_fast import PREPARATION_VERSION
from .alignment_geometry import validate_sampling_geometry

VALIDATION_POLICY = "distributed-support-v2"


def case_ids_conflict(source: str | None, anchor: str | None) -> bool:
    """Known different specimens cannot support automatic correspondence."""
    source_id, anchor_id = (value.strip().casefold() for value in (source or "", anchor or ""))
    return bool(source_id and anchor_id and source_id != anchor_id)


def registration_frame_current(
    value: dict[str, Any],
    *,
    source_metadata: dict[str, Any] | None = None,
    anchor_metadata: dict[str, Any] | None = None,
    source_snapshot_version: str | None = None,
    anchor_snapshot_version: str | None = None,
) -> bool:
    for key, snapshot in (
        ("sourceSnapshotVersion", source_snapshot_version),
        ("anchorSnapshotVersion", anchor_snapshot_version),
    ):
        if snapshot is not None and value.get(key) != snapshot:
            return False
    settings = value.get("engineSettings") or {}
    if not isinstance(settings, dict):
        return False
    for side, token, metadata in (
        ("moving", "sourceFrameVersion", source_metadata),
        ("reference", "anchorFrameVersion", anchor_metadata),
    ):
        if metadata is None:
            continue
        if token in value and value[token] != metadata_frame_digest(metadata):
            return False
        try:
            if f"{side}Geometry" in settings:
                validate_sampling_geometry(
                    settings[f"{side}Geometry"],
                    source_size=(int(metadata["width"]), int(metadata["height"])),
                )
            if f"{side}MicronsPerPixel" in settings:
                recorded = settings[f"{side}MicronsPerPixel"]
                current = normalized_microns_per_pixel(metadata)
                if current is None:
                    if recorded is not None:
                        return False
                elif (
                    not isinstance(recorded, (list, tuple))
                    or len(recorded) != 2
                    or any(type(v) not in (int, float) for v in recorded)
                    or not all(
                        math.isclose(v, actual, rel_tol=0, abs_tol=1e-8)
                        for v, actual in zip(recorded, current, strict=True)
                    )
                ):
                    return False
        except (AlignmentRejected, KeyError, TypeError, ValueError, OverflowError):
            return False
    return True


def current_registration(
    value: dict[str, Any] | None,
    *,
    source_version: str | None = None,
    anchor_version: str | None = None,
    source_case_id: str | None = None,
    anchor_case_id: str | None = None,
    source_metadata: dict[str, Any] | None = None,
    anchor_metadata: dict[str, Any] | None = None,
    source_snapshot_version: str | None = None,
    anchor_snapshot_version: str | None = None,
    input_frame_current: bool = True,
) -> dict[str, Any] | None:
    if not value:
        return value
    if case_ids_conflict(source_case_id, anchor_case_id):
        result = deepcopy(value)
        result.update(
            status="rejected",
            reason="Needs refinement: slides have different case identifiers",
            triangles=[],
            controlPoints=[],
            overviewTriangles=[],
            movingToReference=None,
        )
        result.pop("overviewFallback", None)
        return result
    incompatible_source = (
        source_version is not None
        and value.get("sourceVersion") not in {None, source_version}
        or anchor_version is not None
        and value.get("anchorVersion") not in {None, anchor_version}
    )
    incompatible_source |= not input_frame_current or not registration_frame_current(
        value,
        source_metadata=source_metadata,
        anchor_metadata=anchor_metadata,
        source_snapshot_version=source_snapshot_version,
        anchor_snapshot_version=anchor_snapshot_version,
    )
    if str(value.get("provenance", "")).startswith(("manual", "automatic")):
        incompatible_source |= (
            source_version is not None
            and value.get("sourceVersion") != source_version
            or anchor_version is not None
            and value.get("anchorVersion") != anchor_version
        )
    evidence = value.get("evidence") or {}
    engine = str(value.get("engine") or "")
    incompatible_engine = (
        (str(value.get("provenance", "")).startswith("automatic") and engine not in ENGINE_VERSIONS)
        or engine in ENGINE_VERSIONS
        and (
            value.get("engineVersion") != ENGINE_VERSIONS[engine]
            or value.get("settingsDigest")
            != settings_digest(engine, value.get("engineSettings") or {})
            or evidence.get("phase") == "preview"
            and evidence.get("preparationVersion") != PREPARATION_VERSION
        )
    )
    legacy = (
        engine.startswith("hisalign")
        and not evidence.get("hisalignLocalEvidenceQualified")
        or engine.startswith("valis")
        and not evidence.get("valisLocalEvidenceQualified")
    )
    if (
        not incompatible_source
        and not incompatible_engine
        and (value.get("status") != "ready" or not legacy)
    ):
        fallback = value.get("overviewFallback")
        if fallback:
            compatible = current_registration(
                fallback,
                source_version=value.get("sourceVersion"),
                anchor_version=value.get("anchorVersion"),
                source_metadata=source_metadata,
                anchor_metadata=anchor_metadata,
                source_snapshot_version=source_snapshot_version,
                anchor_snapshot_version=anchor_snapshot_version,
            )
            if (
                not compatible
                or compatible.get("status") != "approximate"
                or compatible.get("anchorSlideId") != value.get("anchorSlideId")
            ):
                result = deepcopy(value)
                result.pop("overviewFallback", None)
                return result
        return value
    result = deepcopy(value)
    result.pop("overviewFallback", None)
    result.update(
        status="stale",
        triangles=[],
        controlPoints=[],
        overviewTriangles=[],
        movingToReference=None,
        reason="Needs refinement: saved engine evidence is obsolete",
    )
    result["evidence"] = {
        **evidence,
        "validationPolicy": VALIDATION_POLICY,
        "requiresRevalidation": True,
    }
    return result
