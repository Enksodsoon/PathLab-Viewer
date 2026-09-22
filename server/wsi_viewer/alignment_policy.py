"""Compatibility checks shared by serving and selecting registration revisions."""

from copy import deepcopy
from typing import Any

VALIDATION_POLICY = "distributed-support-v1"


def current_registration(
    value: dict[str, Any] | None,
    *,
    source_version: str | None = None,
    anchor_version: str | None = None,
) -> dict[str, Any] | None:
    if not value:
        return value
    incompatible_source = (
        source_version is not None
        and value.get("sourceVersion") not in {None, source_version}
        or anchor_version is not None
        and value.get("anchorVersion") not in {None, anchor_version}
    )
    if str(value.get("provenance", "")).startswith("manual"):
        incompatible_source |= (
            source_version is not None
            and value.get("sourceVersion") != source_version
            or anchor_version is not None
            and value.get("anchorVersion") != anchor_version
        )
    if not incompatible_source and str(value.get("provenance", "")).startswith("manual"):
        return value
    evidence = value.get("evidence") or {}
    engine = str(value.get("engine") or "")
    legacy = (
        engine.startswith("hisalign")
        and not evidence.get("hisalignLocalEvidenceQualified")
        or engine.startswith("valis")
        and not evidence.get("valisLocalEvidenceQualified")
    )
    if not incompatible_source and (value.get("status") != "ready" or not legacy):
        return value
    result = deepcopy(value)
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
