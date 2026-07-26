import copy
import csv
import io
import math
import re
import uuid
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictFloat,
    StrictInt,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session as OrmSession

from .models import Annotation, AnnotationLayer, AnnotationRevision, AuditEvent, Slide

MAX_ACTIVE_ANNOTATIONS = 25_000
MAX_LAYERS_PER_SLIDE = 100
MAX_VERTICES_PER_SHAPE = 8_192
MAX_VERTICES_PER_IMPORT = 250_000
MAX_BATCH_OPERATIONS = 50
MAX_REVISIONS = 25
TOMBSTONE_DAYS = 30
MAX_PURGE_PER_WRITE = 100

_HTML_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_CONTROL_CHARACTER = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class AnnotationError(ValueError):
    def __init__(
        self,
        code: str,
        *,
        status_code: int = 422,
        detail: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}


def _plain_text(value: str) -> str:
    if _CONTROL_CHARACTER.search(value) or _HTML_TAG.search(value):
        raise ValueError("plain text is required")
    return value


class AnnotationModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        allow_inf_nan=False,
    )


StrictFiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]


class Point(AnnotationModel):
    x: StrictFiniteFloat
    y: StrictFiniteFloat


class PointGeometry(AnnotationModel):
    type: Literal["point"]
    x: StrictFiniteFloat
    y: StrictFiniteFloat


class PolylineGeometry(AnnotationModel):
    type: Literal["polyline"]
    points: list[Point] = Field(min_length=2, max_length=MAX_VERTICES_PER_SHAPE)


class AngleGeometry(AnnotationModel):
    type: Literal["angle"]
    points: list[Point] = Field(min_length=3, max_length=3)


class RectangleGeometry(AnnotationModel):
    type: Literal["rectangle"]
    x: StrictFiniteFloat
    y: StrictFiniteFloat
    width: StrictFiniteFloat = Field(gt=0)
    height: StrictFiniteFloat = Field(gt=0)


class EllipseGeometry(AnnotationModel):
    type: Literal["ellipse"]
    cx: StrictFiniteFloat
    cy: StrictFiniteFloat
    rx: StrictFiniteFloat = Field(gt=0)
    ry: StrictFiniteFloat = Field(gt=0)


class PolygonGeometry(AnnotationModel):
    type: Literal["polygon"]
    points: list[Point] = Field(min_length=3, max_length=MAX_VERTICES_PER_SHAPE)


class TextGeometry(AnnotationModel):
    type: Literal["text"]
    x: StrictFiniteFloat
    y: StrictFiniteFloat
    text: str = Field(min_length=1, max_length=2_000)

    _validate_text = field_validator("text")(_plain_text)


AnnotationGeometry = Annotated[
    PointGeometry
    | PolylineGeometry
    | AngleGeometry
    | RectangleGeometry
    | EllipseGeometry
    | PolygonGeometry
    | TextGeometry,
    Field(discriminator="type"),
]
GEOMETRY_ADAPTER: TypeAdapter[AnnotationGeometry] = TypeAdapter(AnnotationGeometry)


class AnnotationStyle(AnnotationModel):
    stroke_color: str = Field(
        default="#c43d3d",
        alias="strokeColor",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    fill_color: str = Field(
        default="#c43d3d",
        alias="fillColor",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    stroke_width: FiniteFloat = Field(default=2, alias="strokeWidth", ge=0.25, le=64)
    opacity: FiniteFloat = Field(default=0.35, ge=0, le=1)
    label_visible: bool = Field(default=True, alias="labelVisible")


class AnnotationMetadata(AnnotationModel):
    title: str = Field(default="", max_length=200)
    classification: str = Field(default="", max_length=120)
    tags: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=4_000)

    @field_validator("title", "classification", "notes")
    @classmethod
    def validate_plain_text(cls, value: str) -> str:
        return _plain_text(value)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, tags: list[str]) -> list[str]:
        for tag in tags:
            if not tag or len(tag) > 80:
                raise ValueError("tags must contain 1 to 80 characters")
            _plain_text(tag)
        return tags


class AnnotationItemInput(AnnotationModel):
    id: UUID
    layer_id: UUID = Field(alias="layerId")
    geometry: AnnotationGeometry
    style: AnnotationStyle = Field(default_factory=AnnotationStyle)
    metadata: AnnotationMetadata = Field(default_factory=AnnotationMetadata)


class CreateOperation(AnnotationModel):
    type: Literal["create"]
    item: AnnotationItemInput


class UpdateOperation(AnnotationModel):
    type: Literal["update"]
    id: UUID
    version: StrictInt = Field(ge=1)
    layer_id: UUID | None = Field(default=None, alias="layerId")
    geometry: AnnotationGeometry | None = None
    style: AnnotationStyle | None = None
    metadata: AnnotationMetadata | None = None

    @model_validator(mode="after")
    def require_change(self) -> "UpdateOperation":
        if all(
            value is None
            for value in (self.layer_id, self.geometry, self.style, self.metadata)
        ):
            raise ValueError("update requires at least one changed field")
        return self


class DeleteOperation(AnnotationModel):
    type: Literal["delete"]
    id: UUID
    version: StrictInt = Field(ge=1)


class RestoreOperation(AnnotationModel):
    type: Literal["restore"]
    id: UUID
    version: StrictInt = Field(ge=1)


AnnotationOperation = Annotated[
    CreateOperation | UpdateOperation | DeleteOperation | RestoreOperation,
    Field(discriminator="type"),
]


class AnnotationBatchRequest(AnnotationModel):
    mutation_id: UUID = Field(alias="mutationId")
    base_version: StrictInt = Field(alias="baseVersion", ge=0)
    operations: list[AnnotationOperation] = Field(
        min_length=1,
        max_length=MAX_BATCH_OPERATIONS,
    )


class LayerMutationRequest(AnnotationModel):
    mutation_id: UUID = Field(alias="mutationId")
    base_version: StrictInt = Field(alias="baseVersion", ge=0)
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = Field(default=0, alias="sortOrder", ge=0)
    visible: bool = True
    locked: bool = False
    opacity: FiniteFloat = Field(default=1.0, ge=0, le=1)

    _validate_name = field_validator("name")(_plain_text)


class LayerUpdateRequest(AnnotationModel):
    mutation_id: UUID = Field(alias="mutationId")
    base_version: StrictInt = Field(alias="baseVersion", ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    sort_order: int | None = Field(default=None, alias="sortOrder", ge=0)
    visible: bool | None = None
    locked: bool | None = None
    opacity: FiniteFloat | None = Field(default=None, ge=0, le=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "LayerUpdateRequest":
        if all(
            value is None
            for value in (
                self.name,
                self.sort_order,
                self.visible,
                self.locked,
                self.opacity,
            )
        ):
            raise ValueError("layer update requires a changed field")
        return self


class VersionedMutationRequest(AnnotationModel):
    mutation_id: UUID = Field(alias="mutationId")
    base_version: StrictInt = Field(alias="baseVersion", ge=0)


class ItemMutationRequest(VersionedMutationRequest):
    version: StrictInt = Field(ge=1)


class AnnotationLayerRecord(AnnotationModel):
    id: str
    slide_id: str = Field(alias="slideId")
    name: str
    sort_order: int = Field(alias="sortOrder")
    visible: bool
    locked: bool
    opacity: float
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class AnnotationBounds(AnnotationModel):
    min_x: float = Field(alias="minX")
    min_y: float = Field(alias="minY")
    max_x: float = Field(alias="maxX")
    max_y: float = Field(alias="maxY")


class AnnotationItemRecord(AnnotationModel):
    id: str
    layer_id: str = Field(alias="layerId")
    geometry: AnnotationGeometry
    style: AnnotationStyle
    metadata: AnnotationMetadata
    version: int
    deleted_at: datetime | None = Field(alias="deletedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    bounds: AnnotationBounds
    measurements: dict[str, float | str]


class AnnotationItemsPage(AnnotationModel):
    items: list[AnnotationItemRecord]
    total: int
    next_offset: int | None = Field(alias="nextOffset")


class AnnotationSlideBounds(AnnotationModel):
    width: float
    height: float


class AnnotationCalibration(AnnotationModel):
    x: float
    y: float
    unit: str


class AnnotationLimits(AnnotationModel):
    active_annotations: int = Field(alias="activeAnnotations")
    layers: int
    vertices_per_shape: int = Field(alias="verticesPerShape")
    vertices_per_import: int = Field(alias="verticesPerImport")
    batch_operations: int = Field(alias="batchOperations")


class AnnotationManifest(AnnotationModel):
    slide_id: str = Field(alias="slideId")
    version: int
    bounds: AnnotationSlideBounds
    calibration: AnnotationCalibration | None
    active_count: int = Field(alias="activeCount")
    trashed_count: int = Field(alias="trashedCount")
    layers: list[AnnotationLayerRecord]
    limits: AnnotationLimits


class AnnotationMutationResult(AnnotationModel):
    id: str
    operation: Literal["create", "update", "delete", "restore"]
    version: int
    deleted: bool


class AnnotationBatchResult(AnnotationModel):
    mutation_id: UUID = Field(alias="mutationId")
    version: int
    results: list[AnnotationMutationResult]
    purged: int


class AnnotationImportRequest(VersionedMutationRequest):
    format: Literal["pathlab", "geojson"]
    layer_name: str | None = Field(default=None, alias="layerName", max_length=160)
    data: dict[str, Any]

    @field_validator("layer_name")
    @classmethod
    def validate_layer_name(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None


class PathLabSlide(AnnotationModel):
    id: str
    width: FiniteFloat = Field(gt=0)
    height: FiniteFloat = Field(gt=0)
    annotation_version: int = Field(alias="annotationVersion", ge=0)


class PathLabLayer(AnnotationModel):
    id: UUID
    name: str = Field(min_length=1, max_length=160)
    sort_order: int = Field(alias="sortOrder", ge=0)
    visible: bool
    locked: bool
    opacity: FiniteFloat = Field(ge=0, le=1)


class PathLabDocument(AnnotationModel):
    schema_version: Literal["pathlab-annotations/v1"] = Field(alias="schema")
    slide: PathLabSlide
    layers: list[PathLabLayer] = Field(max_length=MAX_LAYERS_PER_SLIDE)
    annotations: list[AnnotationItemInput] = Field(max_length=MAX_ACTIVE_ANNOTATIONS)


class GeoJsonClassification(AnnotationModel):
    name: str = Field(min_length=1, max_length=120)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class GeoJsonProperties(AnnotationModel):
    name: str = Field(default="", max_length=200)
    classification: GeoJsonClassification | None = None
    tags: list[str] = Field(default_factory=list, max_length=50)
    notes: str = Field(default="", max_length=4_000)
    layer_name: str = Field(default="Imported annotations", alias="layerName", max_length=160)
    style: AnnotationStyle = Field(default_factory=AnnotationStyle)
    text: str | None = Field(default=None, max_length=2_000)

    @field_validator("name", "notes", "layer_name")
    @classmethod
    def validate_text_fields(cls, value: str) -> str:
        return _plain_text(value)

    @field_validator("text")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        return _plain_text(value) if value is not None else None


GeoJsonPosition = tuple[StrictFiniteFloat, StrictFiniteFloat]


class GeoJsonPoint(AnnotationModel):
    type: Literal["Point"]
    coordinates: GeoJsonPosition


class GeoJsonLineString(AnnotationModel):
    type: Literal["LineString"]
    coordinates: list[GeoJsonPosition] = Field(min_length=2, max_length=MAX_VERTICES_PER_SHAPE)


class GeoJsonPolygon(AnnotationModel):
    type: Literal["Polygon"]
    coordinates: list[list[GeoJsonPosition]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_outer_ring(self) -> "GeoJsonPolygon":
        ring = self.coordinates[0]
        if len(ring) < 4 or len(ring) > MAX_VERTICES_PER_SHAPE + 1:
            raise ValueError("polygon outer ring has an invalid vertex count")
        if ring[0] != ring[-1]:
            raise ValueError("polygon outer ring must be closed")
        return self


GeoJsonGeometry = Annotated[
    GeoJsonPoint | GeoJsonLineString | GeoJsonPolygon,
    Field(discriminator="type"),
]


class GeoJsonFeature(AnnotationModel):
    type: Literal["Feature"]
    id: str | int | None = None
    geometry: GeoJsonGeometry
    properties: GeoJsonProperties


class GeoJsonFeatureCollection(AnnotationModel):
    type: Literal["FeatureCollection"]
    features: list[GeoJsonFeature] = Field(max_length=MAX_ACTIVE_ANNOTATIONS)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def slide_bounds(slide: Slide) -> tuple[float, float]:
    metadata = slide.slide_metadata or {}
    try:
        width = float(metadata["width"])
        height = float(metadata["height"])
    except (KeyError, TypeError, ValueError) as error:
        raise AnnotationError(
            "ANNOTATION_BOUNDS_UNAVAILABLE",
            status_code=409,
        ) from error
    if not math.isfinite(width) or not math.isfinite(height) or width <= 0 or height <= 0:
        raise AnnotationError("ANNOTATION_BOUNDS_UNAVAILABLE", status_code=409)
    return width, height


def calibration_json(slide: Slide) -> dict[str, Any] | None:
    metadata = slide.slide_metadata or {}
    x = metadata.get("physicalSizeX")
    y = metadata.get("physicalSizeY", x)
    unit = metadata.get("physicalSizeUnit")
    if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
        return None
    if not math.isfinite(float(x)) or not math.isfinite(float(y)) or x <= 0 or y <= 0:
        return None
    if not isinstance(unit, str) or not unit:
        return None
    return {"x": float(x), "y": float(y), "unit": unit}


def _points(geometry: AnnotationGeometry) -> list[Point]:
    if isinstance(geometry, (PolylineGeometry, AngleGeometry, PolygonGeometry)):
        return geometry.points
    if isinstance(geometry, RectangleGeometry):
        return [
            Point(x=geometry.x, y=geometry.y),
            Point(x=geometry.x + geometry.width, y=geometry.y),
            Point(x=geometry.x + geometry.width, y=geometry.y + geometry.height),
            Point(x=geometry.x, y=geometry.y + geometry.height),
        ]
    if isinstance(geometry, EllipseGeometry):
        return [
            Point(x=geometry.cx - geometry.rx, y=geometry.cy - geometry.ry),
            Point(x=geometry.cx + geometry.rx, y=geometry.cy + geometry.ry),
        ]
    return [Point(x=geometry.x, y=geometry.y)]


def geometry_stats(
    geometry: AnnotationGeometry,
) -> tuple[float, float, float, float, int]:
    points = _points(geometry)
    xs = [float(point.x) for point in points]
    ys = [float(point.y) for point in points]
    if isinstance(geometry, (PolylineGeometry, AngleGeometry, PolygonGeometry)):
        vertices = len(geometry.points)
    elif isinstance(geometry, RectangleGeometry):
        vertices = 4
    elif isinstance(geometry, EllipseGeometry):
        vertices = 64
    else:
        vertices = 1
    if vertices > MAX_VERTICES_PER_SHAPE:
        raise AnnotationError("ANNOTATION_VERTEX_LIMIT")
    return min(xs), min(ys), max(xs), max(ys), vertices


def validate_geometry_bounds(geometry: AnnotationGeometry, slide: Slide) -> None:
    min_x, min_y, max_x, max_y, _ = geometry_stats(geometry)
    width, height = slide_bounds(slide)
    if min_x < 0 or min_y < 0 or max_x > width or max_y > height:
        raise AnnotationError("ANNOTATION_OUT_OF_BOUNDS")


def _calibration_scale(slide: Slide) -> tuple[float, float, str, str] | None:
    calibration = calibration_json(slide)
    if calibration is None:
        return None
    normalized = str(calibration["unit"]).strip().casefold().replace("μ", "µ")
    factors = {
        "nm": 0.001,
        "nanometer": 0.001,
        "nanometre": 0.001,
        "µm": 1.0,
        "um": 1.0,
        "micrometer": 1.0,
        "micrometre": 1.0,
        "mm": 1000.0,
        "millimeter": 1000.0,
        "millimetre": 1000.0,
    }
    factor = factors.get(normalized)
    if factor is None:
        return None
    return (
        float(calibration["x"]) * factor,
        float(calibration["y"]) * factor,
        "µm",
        "µm²",
    )


def _distance(first: Point, second: Point, scale_x: float, scale_y: float) -> float:
    return math.hypot(
        (float(second.x) - float(first.x)) * scale_x,
        (float(second.y) - float(first.y)) * scale_y,
    )


def _path_length(
    points: list[Point],
    scale_x: float,
    scale_y: float,
    *,
    closed: bool,
) -> float:
    pairs = list(zip(points, points[1:], strict=False))
    if closed:
        pairs.append((points[-1], points[0]))
    return sum(_distance(first, second, scale_x, scale_y) for first, second in pairs)


def _polygon_area(points: list[Point]) -> float:
    pairs = list(zip(points, points[1:] + points[:1], strict=False))
    return abs(
        sum(
            float(first.x) * float(second.y) - float(second.x) * float(first.y)
            for first, second in pairs
        )
    ) / 2


def measurements(geometry: AnnotationGeometry, slide: Slide) -> dict[str, Any]:
    calibration = _calibration_scale(slide)
    scale_x, scale_y, unit, area_unit = calibration or (1.0, 1.0, "px", "px²")
    if isinstance(geometry, (PointGeometry, TextGeometry)):
        return {
            "x": float(geometry.x) * scale_x,
            "y": float(geometry.y) * scale_y,
            "unit": unit,
        }
    if isinstance(geometry, PolylineGeometry):
        return {
            "length": _path_length(
                geometry.points,
                scale_x,
                scale_y,
                closed=False,
            ),
            "unit": unit,
        }
    if isinstance(geometry, AngleGeometry):
        a, vertex, c = geometry.points
        first = (
            (float(a.x) - float(vertex.x)) * scale_x,
            (float(a.y) - float(vertex.y)) * scale_y,
        )
        second = (
            (float(c.x) - float(vertex.x)) * scale_x,
            (float(c.y) - float(vertex.y)) * scale_y,
        )
        denominator = math.hypot(*first) * math.hypot(*second)
        angle = 0.0
        if denominator:
            cosine = max(
                -1.0,
                min(1.0, (first[0] * second[0] + first[1] * second[1]) / denominator),
            )
            angle = math.degrees(math.acos(cosine))
        return {"angle": angle, "unit": "degrees"}
    if isinstance(geometry, RectangleGeometry):
        return {
            "area": float(geometry.width * geometry.height) * scale_x * scale_y,
            "perimeter": 2
            * (
                float(geometry.width) * scale_x
                + float(geometry.height) * scale_y
            ),
            "unit": unit,
            "areaUnit": area_unit,
        }
    if isinstance(geometry, EllipseGeometry):
        ellipse_a = float(geometry.rx) * scale_x
        ellipse_b = float(geometry.ry) * scale_y
        h = ((ellipse_a - ellipse_b) ** 2) / ((ellipse_a + ellipse_b) ** 2)
        perimeter = math.pi * (ellipse_a + ellipse_b) * (
            1 + (3 * h) / (10 + math.sqrt(4 - 3 * h))
        )
        return {
            "area": math.pi * ellipse_a * ellipse_b,
            "perimeter": perimeter,
            "unit": unit,
            "areaUnit": area_unit,
        }
    return {
        "area": _polygon_area(geometry.points) * scale_x * scale_y,
        "perimeter": _path_length(
            geometry.points,
            scale_x,
            scale_y,
            closed=True,
        ),
        "unit": unit,
        "areaUnit": area_unit,
    }


def layer_json(layer: AnnotationLayer) -> dict[str, Any]:
    return {
        "id": layer.id,
        "slideId": layer.slide_id,
        "name": layer.name,
        "sortOrder": layer.sort_order,
        "visible": layer.visible,
        "locked": layer.locked,
        "opacity": layer.opacity,
        "createdAt": layer.created_at.isoformat(),
        "updatedAt": layer.updated_at.isoformat(),
    }


def annotation_json(annotation: Annotation, slide: Slide) -> dict[str, Any]:
    geometry = GEOMETRY_ADAPTER.validate_python(annotation.geometry)
    return {
        "id": annotation.id,
        "layerId": annotation.layer_id,
        "geometry": geometry.model_dump(by_alias=True, mode="json"),
        "style": AnnotationStyle.model_validate(annotation.style).model_dump(
            by_alias=True,
            mode="json",
        ),
        "metadata": AnnotationMetadata.model_validate(
            annotation.annotation_metadata
        ).model_dump(by_alias=True, mode="json"),
        "version": annotation.version,
        "deletedAt": (
            annotation.deleted_at.isoformat() if annotation.deleted_at else None
        ),
        "createdAt": annotation.created_at.isoformat(),
        "updatedAt": annotation.updated_at.isoformat(),
        "bounds": {
            "minX": annotation.bbox_min_x,
            "minY": annotation.bbox_min_y,
            "maxX": annotation.bbox_max_x,
            "maxY": annotation.bbox_max_y,
        },
        "measurements": measurements(geometry, slide),
    }


def revision_json(revision: AnnotationRevision) -> dict[str, Any]:
    return {
        "id": revision.id,
        "version": revision.version,
        "layerId": revision.layer_id,
        "geometry": revision.geometry,
        "style": revision.style,
        "metadata": revision.annotation_metadata,
        "deletedAt": (
            revision.deleted_at.isoformat() if revision.deleted_at else None
        ),
        "createdAt": revision.created_at.isoformat(),
    }


def _annotation_for_operation(
    database: OrmSession,
    slide_id: str,
    annotation_id: UUID,
) -> Annotation:
    annotation = database.get(Annotation, str(annotation_id))
    if annotation is None or annotation.slide_id != slide_id:
        raise AnnotationError("ANNOTATION_NOT_FOUND", status_code=404)
    return annotation


def _layer_exists(
    database: OrmSession,
    slide_id: str,
    layer_id: UUID | str,
) -> bool:
    layer = database.get(AnnotationLayer, str(layer_id))
    return layer is not None and layer.slide_id == slide_id


def _ensure_version(slide: Slide, base_version: int) -> None:
    if slide.annotation_version != base_version:
        raise AnnotationError(
            "ANNOTATION_CONFLICT",
            status_code=409,
            detail={"currentVersion": slide.annotation_version},
        )


def _record_revision(
    database: OrmSession,
    annotation: Annotation,
) -> None:
    database.add(
        AnnotationRevision(
            annotation_id=annotation.id,
            version=annotation.version,
            layer_id=annotation.layer_id,
            geometry_type=annotation.geometry_type,
            geometry=copy.deepcopy(annotation.geometry),
            style=copy.deepcopy(annotation.style),
            annotation_metadata=copy.deepcopy(annotation.annotation_metadata),
            bbox_min_x=annotation.bbox_min_x,
            bbox_min_y=annotation.bbox_min_y,
            bbox_max_x=annotation.bbox_max_x,
            bbox_max_y=annotation.bbox_max_y,
            vertex_count=annotation.vertex_count,
            mutation_id=annotation.mutation_id,
            deleted_at=annotation.deleted_at,
            purge_after=annotation.purge_after,
            created_at=utcnow(),
        )
    )
    database.flush()
    old = list(
        database.scalars(
            select(AnnotationRevision)
            .where(AnnotationRevision.annotation_id == annotation.id)
            .order_by(
                AnnotationRevision.version.desc(),
                AnnotationRevision.created_at.desc(),
            )
            .offset(MAX_REVISIONS)
        )
    )
    for revision in old:
        database.delete(revision)


def purge_expired_tombstones(database: OrmSession, now: datetime) -> int:
    expired = list(
        database.scalars(
            select(Annotation)
            .where(
                Annotation.deleted_at.is_not(None),
                Annotation.purge_after.is_not(None),
                Annotation.purge_after <= now,
            )
            .order_by(Annotation.purge_after, Annotation.id)
            .limit(MAX_PURGE_PER_WRITE)
        )
    )
    for annotation in expired:
        database.delete(annotation)
    return len(expired)


def apply_batch(
    database: OrmSession,
    slide: Slide,
    payload: AnnotationBatchRequest,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    started = perf_counter()
    _ensure_version(slide, payload.base_version)
    seen: set[str] = set()
    active_count = int(
        database.scalar(
            select(func.count(Annotation.id)).where(
                Annotation.slide_id == slide.id,
                Annotation.deleted_at.is_(None),
            )
        )
        or 0
    )
    prepared: list[tuple[AnnotationOperation, Annotation | None]] = []
    for operation in payload.operations:
        if isinstance(operation, CreateOperation):
            item_id = str(operation.item.id)
            if item_id in seen or database.get(Annotation, item_id) is not None:
                raise AnnotationError("ANNOTATION_CONFLICT", status_code=409)
            seen.add(item_id)
            if not _layer_exists(database, slide.id, operation.item.layer_id):
                raise AnnotationError("ANNOTATION_LAYER_NOT_FOUND", status_code=404)
            validate_geometry_bounds(operation.item.geometry, slide)
            active_count += 1
            prepared.append((operation, None))
            continue
        item_id = str(operation.id)
        if item_id in seen:
            raise AnnotationError("ANNOTATION_CONFLICT", status_code=409)
        seen.add(item_id)
        annotation = _annotation_for_operation(database, slide.id, operation.id)
        if annotation.version != operation.version:
            raise AnnotationError(
                "ANNOTATION_CONFLICT",
                status_code=409,
                detail={"currentVersion": slide.annotation_version},
            )
        if isinstance(operation, UpdateOperation):
            if annotation.deleted_at is not None:
                raise AnnotationError("ANNOTATION_TRASHED", status_code=409)
            if operation.layer_id is not None and not _layer_exists(
                database,
                slide.id,
                operation.layer_id,
            ):
                raise AnnotationError("ANNOTATION_LAYER_NOT_FOUND", status_code=404)
            if operation.geometry is not None:
                validate_geometry_bounds(operation.geometry, slide)
        elif isinstance(operation, DeleteOperation):
            if annotation.deleted_at is not None:
                raise AnnotationError("ANNOTATION_TRASHED", status_code=409)
            active_count -= 1
        elif annotation.deleted_at is None:
            raise AnnotationError("ANNOTATION_NOT_TRASHED", status_code=409)
        else:
            validate_geometry_bounds(
                GEOMETRY_ADAPTER.validate_python(annotation.geometry),
                slide,
            )
            active_count += 1
        prepared.append((operation, annotation))
    if active_count > MAX_ACTIVE_ANNOTATIONS:
        raise AnnotationError("ANNOTATION_ACTIVE_LIMIT")

    now = utcnow()
    purged = purge_expired_tombstones(database, now)
    results: list[dict[str, Any]] = []
    mutation_id = str(payload.mutation_id)
    for operation, current in prepared:
        if isinstance(operation, CreateOperation):
            geometry = operation.item.geometry
            min_x, min_y, max_x, max_y, vertices = geometry_stats(geometry)
            annotation = Annotation(
                id=str(operation.item.id),
                slide_id=slide.id,
                layer_id=str(operation.item.layer_id),
                geometry_type=geometry.type,
                geometry=geometry.model_dump(by_alias=True, mode="json"),
                style=operation.item.style.model_dump(by_alias=True, mode="json"),
                annotation_metadata=operation.item.metadata.model_dump(
                    by_alias=True,
                    mode="json",
                ),
                bbox_min_x=min_x,
                bbox_min_y=min_y,
                bbox_max_x=max_x,
                bbox_max_y=max_y,
                vertex_count=vertices,
                version=1,
                mutation_id=mutation_id,
                created_at=now,
                updated_at=now,
            )
            database.add(annotation)
            results.append(
                {
                    "id": annotation.id,
                    "operation": "create",
                    "version": 1,
                    "deleted": False,
                }
            )
            continue
        assert current is not None
        _record_revision(database, current)
        current.version += 1
        current.mutation_id = mutation_id
        current.updated_at = now
        if isinstance(operation, UpdateOperation):
            if operation.layer_id is not None:
                current.layer_id = str(operation.layer_id)
            if operation.geometry is not None:
                geometry = operation.geometry
                min_x, min_y, max_x, max_y, vertices = geometry_stats(geometry)
                current.geometry_type = geometry.type
                current.geometry = geometry.model_dump(by_alias=True, mode="json")
                current.bbox_min_x = min_x
                current.bbox_min_y = min_y
                current.bbox_max_x = max_x
                current.bbox_max_y = max_y
                current.vertex_count = vertices
            if operation.style is not None:
                current.style = operation.style.model_dump(by_alias=True, mode="json")
            if operation.metadata is not None:
                current.annotation_metadata = operation.metadata.model_dump(
                    by_alias=True,
                    mode="json",
                )
        elif isinstance(operation, DeleteOperation):
            current.deleted_at = now
            current.purge_after = now + timedelta(days=TOMBSTONE_DAYS)
        else:
            current.deleted_at = None
            current.purge_after = None
        results.append(
            {
                "id": current.id,
                "operation": operation.type,
                "version": current.version,
                "deleted": current.deleted_at is not None,
            }
        )

    slide.annotation_version += 1
    database.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="annotation.batch",
            target_id=slide.id,
            detail={
                "mutationId": mutation_id,
                "operationCount": len(payload.operations),
                "durationMs": round((perf_counter() - started) * 1000, 3),
                "result": "success",
                "version": slide.annotation_version,
                "purged": purged,
            },
        )
    )
    database.commit()
    return {
        "mutationId": mutation_id,
        "version": slide.annotation_version,
        "results": results,
        "purged": purged,
    }


def restore_revision(
    database: OrmSession,
    slide: Slide,
    annotation: Annotation,
    revision: AnnotationRevision,
    payload: ItemMutationRequest,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    started = perf_counter()
    _ensure_version(slide, payload.base_version)
    if annotation.slide_id != slide.id or revision.annotation_id != annotation.id:
        raise AnnotationError("ANNOTATION_REVISION_NOT_FOUND", status_code=404)
    if annotation.version != payload.version:
        raise AnnotationError(
            "ANNOTATION_CONFLICT",
            status_code=409,
            detail={"currentVersion": slide.annotation_version},
        )
    if not _layer_exists(database, slide.id, revision.layer_id):
        raise AnnotationError("ANNOTATION_LAYER_NOT_FOUND", status_code=404)
    geometry = GEOMETRY_ADAPTER.validate_python(revision.geometry)
    validate_geometry_bounds(geometry, slide)

    now = utcnow()
    purged = purge_expired_tombstones(database, now)
    _record_revision(database, annotation)
    annotation.version += 1
    annotation.layer_id = revision.layer_id
    annotation.geometry_type = revision.geometry_type
    annotation.geometry = copy.deepcopy(revision.geometry)
    annotation.style = copy.deepcopy(revision.style)
    annotation.annotation_metadata = copy.deepcopy(revision.annotation_metadata)
    annotation.bbox_min_x = revision.bbox_min_x
    annotation.bbox_min_y = revision.bbox_min_y
    annotation.bbox_max_x = revision.bbox_max_x
    annotation.bbox_max_y = revision.bbox_max_y
    annotation.vertex_count = revision.vertex_count
    annotation.mutation_id = str(payload.mutation_id)
    annotation.deleted_at = None
    annotation.purge_after = None
    annotation.updated_at = now
    slide.annotation_version += 1
    database.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="annotation.revision.restore",
            target_id=slide.id,
            detail={
                "mutationId": str(payload.mutation_id),
                "operationCount": 1,
                "durationMs": round((perf_counter() - started) * 1000, 3),
                "result": "success",
                "version": slide.annotation_version,
                "purged": purged,
            },
        )
    )
    database.commit()
    return {
        "version": slide.annotation_version,
        "item": annotation_json(annotation, slide),
        "purged": purged,
    }


def _active_annotations(
    database: OrmSession,
    slide_id: str,
) -> list[Annotation]:
    return list(
        database.scalars(
            select(Annotation)
            .where(
                Annotation.slide_id == slide_id,
                Annotation.deleted_at.is_(None),
            )
            .order_by(Annotation.created_at, Annotation.id)
        )
    )


def export_pathlab(
    database: OrmSession,
    slide: Slide,
) -> dict[str, Any]:
    width, height = slide_bounds(slide)
    layers = list(
        database.scalars(
            select(AnnotationLayer)
            .where(AnnotationLayer.slide_id == slide.id)
            .order_by(AnnotationLayer.sort_order, AnnotationLayer.created_at)
        )
    )
    annotations = _active_annotations(database, slide.id)
    return {
        "schema": "pathlab-annotations/v1",
        "slide": {
            "id": slide.id,
            "width": width,
            "height": height,
            "annotationVersion": slide.annotation_version,
        },
        "layers": [
            {
                "id": layer.id,
                "name": layer.name,
                "sortOrder": layer.sort_order,
                "visible": layer.visible,
                "locked": layer.locked,
                "opacity": layer.opacity,
            }
            for layer in layers
        ],
        "annotations": [
            {
                "id": annotation.id,
                "layerId": annotation.layer_id,
                "geometry": annotation.geometry,
                "style": annotation.style,
                "metadata": annotation.annotation_metadata,
            }
            for annotation in annotations
        ],
    }


def _polygon_coordinates(geometry: AnnotationGeometry) -> list[list[float]]:
    if isinstance(geometry, RectangleGeometry):
        points = _points(geometry)
    elif isinstance(geometry, PolygonGeometry):
        points = geometry.points
    elif isinstance(geometry, EllipseGeometry):
        points = [
            Point(
                x=float(geometry.cx)
                + float(geometry.rx) * math.cos((2 * math.pi * index) / 64),
                y=float(geometry.cy)
                + float(geometry.ry) * math.sin((2 * math.pi * index) / 64),
            )
            for index in range(64)
        ]
    else:
        raise AnnotationError("ANNOTATION_EXPORT_UNSUPPORTED")
    coordinates = [[float(point.x), float(point.y)] for point in points]
    coordinates.append(coordinates[0])
    return coordinates


def export_geojson(
    database: OrmSession,
    slide: Slide,
) -> dict[str, Any]:
    layers = {
        layer.id: layer
        for layer in database.scalars(
            select(AnnotationLayer).where(AnnotationLayer.slide_id == slide.id)
        )
    }
    features: list[dict[str, Any]] = []
    for annotation in _active_annotations(database, slide.id):
        geometry = GEOMETRY_ADAPTER.validate_python(annotation.geometry)
        style = AnnotationStyle.model_validate(annotation.style)
        metadata = AnnotationMetadata.model_validate(annotation.annotation_metadata)
        geo_geometry: dict[str, Any]
        text_value: str | None = None
        if isinstance(geometry, (PointGeometry, TextGeometry)):
            geo_geometry = {
                "type": "Point",
                "coordinates": [float(geometry.x), float(geometry.y)],
            }
            if isinstance(geometry, TextGeometry):
                text_value = geometry.text
        elif isinstance(geometry, (PolylineGeometry, AngleGeometry)):
            geo_geometry = {
                "type": "LineString",
                "coordinates": [
                    [float(point.x), float(point.y)] for point in geometry.points
                ],
            }
        else:
            geo_geometry = {
                "type": "Polygon",
                "coordinates": [_polygon_coordinates(geometry)],
            }
        classification = (
            {
                "name": metadata.classification,
                "color": style.stroke_color,
            }
            if metadata.classification
            else None
        )
        features.append(
            {
                "type": "Feature",
                "id": annotation.id,
                "geometry": geo_geometry,
                "properties": {
                    "name": metadata.title,
                    "classification": classification,
                    "tags": metadata.tags,
                    "notes": metadata.notes,
                    "layerName": layers[annotation.layer_id].name,
                    "style": style.model_dump(by_alias=True, mode="json"),
                    **({"text": text_value} if text_value is not None else {}),
                },
            }
        )
    return {"type": "FeatureCollection", "features": features}


def export_csv(
    database: OrmSession,
    slide: Slide,
) -> str:
    layers = {
        layer.id: layer.name
        for layer in database.scalars(
            select(AnnotationLayer).where(AnnotationLayer.slide_id == slide.id)
        )
    }
    fields = [
        "id",
        "layer",
        "title",
        "type",
        "x",
        "y",
        "length",
        "angle",
        "perimeter",
        "area",
        "unit",
        "areaUnit",
    ]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\r\n")
    writer.writeheader()
    for annotation in _active_annotations(database, slide.id):
        geometry = GEOMETRY_ADAPTER.validate_python(annotation.geometry)
        metadata = AnnotationMetadata.model_validate(annotation.annotation_metadata)
        measured = measurements(geometry, slide)
        writer.writerow(
            {
                "id": annotation.id,
                "layer": layers[annotation.layer_id],
                "title": metadata.title,
                "type": geometry.type,
                **measured,
            }
        )
    return stream.getvalue()


def _geojson_geometry(feature: GeoJsonFeature) -> AnnotationGeometry:
    geometry = feature.geometry
    if isinstance(geometry, GeoJsonPoint):
        if feature.properties.text is not None:
            return TextGeometry(
                type="text",
                x=geometry.coordinates[0],
                y=geometry.coordinates[1],
                text=feature.properties.text,
            )
        return PointGeometry(
            type="point",
            x=geometry.coordinates[0],
            y=geometry.coordinates[1],
        )
    if isinstance(geometry, GeoJsonLineString):
        return PolylineGeometry(
            type="polyline",
            points=[
                Point(x=position[0], y=position[1])
                for position in geometry.coordinates
            ],
        )
    return PolygonGeometry(
        type="polygon",
        points=[
            Point(x=position[0], y=position[1])
            for position in geometry.coordinates[0][:-1]
        ],
    )


def _import_items(
    payload: AnnotationImportRequest,
) -> tuple[str, list[tuple[AnnotationGeometry, AnnotationStyle, AnnotationMetadata]]]:
    try:
        if payload.format == "pathlab":
            pathlab_document = PathLabDocument.model_validate(payload.data)
            default_name = (
                pathlab_document.layers[0].name
                if pathlab_document.layers
                else "Imported annotations"
            )
            return (
                payload.layer_name or default_name,
                [
                    (item.geometry, item.style, item.metadata)
                    for item in pathlab_document.annotations
                ],
            )
        geojson_document = GeoJsonFeatureCollection.model_validate(payload.data)
        default_name = (
            geojson_document.features[0].properties.layer_name
            if geojson_document.features
            else "Imported annotations"
        )
        items = []
        for feature in geojson_document.features:
            classification = (
                feature.properties.classification.name
                if feature.properties.classification
                else ""
            )
            items.append(
                (
                    _geojson_geometry(feature),
                    feature.properties.style,
                    AnnotationMetadata(
                        title=feature.properties.name,
                        classification=classification,
                        tags=feature.properties.tags,
                        notes=feature.properties.notes,
                    ),
                )
            )
        return payload.layer_name or default_name, items
    except ValidationError as error:
        raise AnnotationError("ANNOTATION_IMPORT_INVALID") from error


def import_annotations(
    database: OrmSession,
    slide: Slide,
    payload: AnnotationImportRequest,
    *,
    actor_user_id: str,
) -> dict[str, Any]:
    started = perf_counter()
    _ensure_version(slide, payload.base_version)
    layer_count = int(
        database.scalar(
            select(func.count(AnnotationLayer.id)).where(
                AnnotationLayer.slide_id == slide.id
            )
        )
        or 0
    )
    if layer_count >= MAX_LAYERS_PER_SLIDE:
        raise AnnotationError("ANNOTATION_LAYER_LIMIT")
    layer_name, items = _import_items(payload)
    if not items:
        raise AnnotationError("ANNOTATION_IMPORT_EMPTY")
    active_count = int(
        database.scalar(
            select(func.count(Annotation.id)).where(
                Annotation.slide_id == slide.id,
                Annotation.deleted_at.is_(None),
            )
        )
        or 0
    )
    if active_count + len(items) > MAX_ACTIVE_ANNOTATIONS:
        raise AnnotationError("ANNOTATION_ACTIVE_LIMIT")
    total_vertices = 0
    prepared: list[
        tuple[
            AnnotationGeometry,
            AnnotationStyle,
            AnnotationMetadata,
            tuple[float, float, float, float, int],
        ]
    ] = []
    for geometry, style, metadata in items:
        validate_geometry_bounds(geometry, slide)
        stats = geometry_stats(geometry)
        total_vertices += stats[4]
        if total_vertices > MAX_VERTICES_PER_IMPORT:
            raise AnnotationError("ANNOTATION_IMPORT_VERTEX_LIMIT")
        prepared.append((geometry, style, metadata, stats))

    now = utcnow()
    purged = purge_expired_tombstones(database, now)
    layer = AnnotationLayer(
        slide_id=slide.id,
        name=layer_name.strip(),
        sort_order=layer_count,
        visible=True,
        locked=False,
        opacity=1.0,
        created_at=now,
        updated_at=now,
    )
    database.add(layer)
    database.flush()
    mutation_id = str(payload.mutation_id)
    for geometry, style, metadata, stats in prepared:
        min_x, min_y, max_x, max_y, vertices = stats
        database.add(
            Annotation(
                id=new_uuid(),
                slide_id=slide.id,
                layer_id=layer.id,
                geometry_type=geometry.type,
                geometry=geometry.model_dump(by_alias=True, mode="json"),
                style=style.model_dump(by_alias=True, mode="json"),
                annotation_metadata=metadata.model_dump(by_alias=True, mode="json"),
                bbox_min_x=min_x,
                bbox_min_y=min_y,
                bbox_max_x=max_x,
                bbox_max_y=max_y,
                vertex_count=vertices,
                version=1,
                mutation_id=mutation_id,
                created_at=now,
                updated_at=now,
            )
        )
    slide.annotation_version += 1
    database.add(
        AuditEvent(
            actor_user_id=actor_user_id,
            action="annotation.import",
            target_id=slide.id,
            detail={
                "mutationId": mutation_id,
                "operationCount": len(prepared),
                "durationMs": round((perf_counter() - started) * 1000, 3),
                "result": "success",
                "version": slide.annotation_version,
                "purged": purged,
            },
        )
    )
    database.commit()
    return {
        "version": slide.annotation_version,
        "imported": len(prepared),
        "layer": layer_json(layer),
        "purged": purged,
    }


def new_uuid() -> str:
    return str(uuid.uuid4())
