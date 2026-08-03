# ruff: noqa: B008

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Response
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
)
from sqlalchemy.orm import Session as OrmSession

from .annotations import (
    AnnotationGeometry,
    AnnotationMetadata,
    AnnotationStyle,
    EllipseGeometry,
    RectangleGeometry,
    slide_bounds,
)
from .models import Slide


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)


class EvidenceRegion(CandidateModel):
    id: UUID
    geometry: AnnotationGeometry
    style: AnnotationStyle = Field(default_factory=AnnotationStyle)
    metadata: AnnotationMetadata = Field(default_factory=AnnotationMetadata)
    probability: StrictFloat | None = Field(default=None, ge=0, le=1)
    uncertainty: StrictFloat | None = Field(default=None, ge=0, le=1)
    abstained: StrictBool = False
    evidence_kind: (
        Literal["similar", "contrast", "prototype", "artifact", "annotation_candidate"]
        | None
    ) = Field(default=None, alias="evidenceKind")
    similarity: StrictFloat | None = Field(default=None, ge=-1, le=1)
    rank: StrictInt | None = Field(default=None, ge=1, le=20)
    cross_stain: StrictBool = Field(default=False, alias="crossStain")
    morphology_tags: list[str] = Field(default_factory=list, alias="morphologyTags", max_length=30)


class CandidateLayerRequest(CandidateModel):
    source_fingerprint_sha256: str = Field(
        alias="sourceFingerprintSha256", pattern=r"^[0-9a-f]{64}$"
    )
    result_manifest_sha256: str = Field(alias="resultManifestSha256", pattern=r"^[0-9a-f]{64}$")
    adapter: Literal["bracs", "wsinfer", "foundation", "monai-label", "morphology"]
    model_id: str = Field(alias="modelId", min_length=1, max_length=200)
    expires_minutes: StrictInt = Field(default=60, alias="expiresMinutes", ge=5, le=240)
    research_only: Literal[True] = Field(alias="researchOnly")
    not_diagnostic: Literal[True] = Field(alias="notDiagnostic")
    review_required: Literal[True] = Field(alias="reviewRequired")
    contains_diagnosis: Literal[False] = Field(default=False, alias="containsDiagnosis")
    regions: list[EvidenceRegion] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_adapter_evidence(self) -> "CandidateLayerRequest":
        if self.adapter == "morphology":
            ranks = [region.rank for region in self.regions]
            if any(
                region.evidence_kind is None
                or region.similarity is None
                or region.rank is None
                for region in self.regions
            ):
                raise ValueError("Morphology regions require evidenceKind, similarity, and rank")
            if ranks != list(range(1, len(self.regions) + 1)):
                raise ValueError("Morphology ranks must be contiguous and deterministic")
        elif any(
            region.probability is None or region.uncertainty is None
            for region in self.regions
        ):
            raise ValueError("Prediction candidates require probability and uncertainty")
        return self


def register_ai_candidate_routes(
    app: FastAPI,
    *,
    database_dependency: Callable[[], Iterator[OrmSession]],
    admin_dependency: Callable[..., Any],
    csrf_dependency: Callable[..., Any],
) -> None:
    # Candidate layers are deliberately process-local. Restarting the Viewer or
    # discarding the candidate removes them; accepted regions use the existing
    # annotation batch API and its audit/version controls.
    store: dict[str, dict[str, Any]] = {}
    app.state.ai_candidate_layers = store

    def clean_expired() -> None:
        now = datetime.now(UTC)
        for candidate_id, value in list(store.items()):
            if datetime.fromisoformat(value["expiresAt"]) <= now:
                store.pop(candidate_id, None)

    def create_candidate(
        slide_id: str,
        payload: CandidateLayerRequest,
        _: Any = Depends(csrf_dependency),
        database: OrmSession = Depends(database_dependency),
    ) -> dict[str, Any]:
        clean_expired()
        slide = database.get(Slide, slide_id)
        if slide is None:
            raise HTTPException(status_code=404, detail={"code": "SLIDE_NOT_FOUND"})
        try:
            width, height = slide_bounds(slide)
        except ValueError as error:
            raise HTTPException(
                status_code=409, detail={"code": "SLIDE_BOUNDS_UNAVAILABLE"}
            ) from error
        for region in payload.regions:
            geometry = region.geometry
            points: list[tuple[float, float]] = []
            if hasattr(geometry, "points"):
                points.extend((point.x, point.y) for point in geometry.points)
            for x_name, y_name in (("x", "y"), ("cx", "cy")):
                if hasattr(geometry, x_name) and hasattr(geometry, y_name):
                    points.append((getattr(geometry, x_name), getattr(geometry, y_name)))
            if isinstance(geometry, RectangleGeometry):
                points.append((geometry.x + geometry.width, geometry.y + geometry.height))
            if isinstance(geometry, EllipseGeometry):
                points.extend(
                    (
                        (geometry.cx - geometry.rx, geometry.cy - geometry.ry),
                        (geometry.cx + geometry.rx, geometry.cy + geometry.ry),
                    )
                )
            if any(x < 0 or y < 0 or x > width or y > height for x, y in points):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "AI_CANDIDATE_COORDINATES_INVALID"},
                )
        candidate_id = str(uuid4())
        now = datetime.now(UTC)
        value = {
            "id": candidate_id,
            "slideId": slide_id,
            **payload.model_dump(by_alias=True, mode="json"),
            "temporary": True,
            "accepted": False,
            "createdAt": now.isoformat(),
            "expiresAt": (now + timedelta(minutes=payload.expires_minutes)).isoformat(),
        }
        store[candidate_id] = value
        return value

    app.add_api_route(
        "/api/v2/admin/ai-candidates/slides/{slide_id}",
        create_candidate,
        methods=["POST"],
        status_code=201,
    )

    def get_candidate(
        slide_id: str,
        candidate_id: str,
        _: Any = Depends(admin_dependency),
    ) -> dict[str, Any]:
        clean_expired()
        value = store.get(candidate_id)
        if value is None or value["slideId"] != slide_id:
            raise HTTPException(status_code=404, detail={"code": "AI_CANDIDATE_NOT_FOUND"})
        return value

    app.add_api_route(
        "/api/v2/admin/ai-candidates/slides/{slide_id}/{candidate_id}",
        get_candidate,
        methods=["GET"],
    )

    def discard_candidate(
        slide_id: str,
        candidate_id: str,
        _: Any = Depends(csrf_dependency),
    ) -> Response:
        value = store.get(candidate_id)
        if value is None or value["slideId"] != slide_id:
            raise HTTPException(status_code=404, detail={"code": "AI_CANDIDATE_NOT_FOUND"})
        store.pop(candidate_id, None)
        return Response(status_code=204)

    app.add_api_route(
        "/api/v2/admin/ai-candidates/slides/{slide_id}/{candidate_id}",
        discard_candidate,
        methods=["DELETE"],
        status_code=204,
    )
