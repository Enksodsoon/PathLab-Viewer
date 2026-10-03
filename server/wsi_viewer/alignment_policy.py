"""Compatibility checks shared by serving and selecting registration revisions."""

from copy import deepcopy
from typing import Any

from .alignment_engines import ENGINE_VERSIONS, settings_digest
from .alignment_fast import PREPARATION_VERSION

VALIDATION_POLICY = "distributed-support-v2"


def case_ids_conflict(source: str | None, anchor: str | None) -> bool:
    """Known different specimens cannot support automatic correspondence."""
    source_id, anchor_id = (value.strip().casefold() for value in (source or "", anchor or ""))
    return bool(source_id and anchor_id and source_id != anchor_id)


def current_registration(
    value: dict[str, Any] | None,
    *,
    source_version: str | None = None,
    anchor_version: str | None = None,
    source_case_id: str | None = None,
    anchor_case_id: str | None = None,
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
