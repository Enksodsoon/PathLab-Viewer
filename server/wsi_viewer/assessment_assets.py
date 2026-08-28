from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from xml.etree import ElementTree

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as OrmSession

from .domain import SlideState
from .models import (
    AssessmentAdministration,
    AssessmentAssetGrant,
    AssessmentVersion,
    PublicationGrant,
    Slide,
)
from .publication import INDIVIDUAL, delivery_version
from .storage import (
    PublicationError,
    StorageLayout,
    publish_assessment_derivative,
    unpublish_assessment_derivative,
)
from .time_support import utc_now

MAX_ASSESSMENT_SLIDES = 50


class AssessmentAssetError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def definition_slide_ids(definition: dict[str, object]) -> list[str]:
    items = definition.get("items")
    if not isinstance(items, list):
        sections = definition.get("sections")
        items = (
            [
                item
                for section in sections
                if isinstance(section, dict)
                for item in section.get("items", [])
            ]
            if isinstance(sections, list)
            else []
        )
    ordered: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        slide_id = item.get("slideId")
        if isinstance(slide_id, str) and slide_id and slide_id not in ordered:
            ordered.append(slide_id)
    return ordered


def _validate_descriptor(root: Path) -> None:
    descriptor = root / "slide.dzi"
    if not descriptor.is_file() or descriptor.stat().st_size > 64 * 1024:
        raise AssessmentAssetError("ASSESSMENT_SLIDE_DELIVERY_MISSING")
    try:
        image = ElementTree.parse(descriptor).getroot()
        tile_size = int(image.attrib["TileSize"])
        tile_format = image.attrib["Format"].casefold()
        size = next(child for child in image if child.tag.rsplit("}", 1)[-1] == "Size")
        width = int(size.attrib["Width"])
        height = int(size.attrib["Height"])
    except (ElementTree.ParseError, KeyError, StopIteration, TypeError, ValueError) as error:
        raise AssessmentAssetError("ASSESSMENT_SLIDE_DESCRIPTOR_INVALID") from error
    if tile_size <= 0 or width <= 0 or height <= 0 or tile_format not in {"jpg", "jpeg"}:
        raise AssessmentAssetError("ASSESSMENT_SLIDE_DESCRIPTOR_INVALID")
    tiles = root / "slide_files"
    if not tiles.is_dir() or not any(tiles.rglob("*.jpeg")) and not any(tiles.rglob("*.jpg")):
        raise AssessmentAssetError("ASSESSMENT_SLIDE_DELIVERY_MISSING")


def _eligible_slide(database: OrmSession, storage: StorageLayout, slide_id: str) -> Slide:
    slide = database.get(Slide, slide_id)
    grant = database.scalar(
        select(PublicationGrant.id).where(
            PublicationGrant.slide_id == slide_id,
            PublicationGrant.source_type == INDIVIDUAL,
            PublicationGrant.source_id == slide_id,
        )
    )
    if (
        slide is None
        or slide.state != SlideState.PUBLISHED
        or slide.privacy_status != "passed"
        or slide.render_mode != "static_dzi"
        or not slide.sha256
        or slide.derivative_file_count <= 0
        or grant is None
    ):
        raise AssessmentAssetError("ASSESSMENT_SLIDE_NOT_ELIGIBLE")
    _validate_descriptor(storage.for_slide(slide.id).private_derivative)
    return slide


def _prewarm(root: Path) -> None:
    descriptor = root / "slide.dzi"
    descriptor.read_bytes()
    tiles = sorted((*root.rglob("*.jpeg"), *root.rglob("*.jpg")))
    for tile in tiles[:1] + tiles[-1:]:
        with tile.open("rb") as handle:
            handle.read(64 * 1024)


def prepare_asset_grants(
    database: OrmSession,
    storage: StorageLayout,
    administration: AssessmentAdministration,
    slide_ids: list[str],
) -> list[AssessmentAssetGrant]:
    if len(slide_ids) > MAX_ASSESSMENT_SLIDES:
        raise AssessmentAssetError("ASSESSMENT_SLIDE_LIMIT")
    slides = [_eligible_slide(database, storage, slide_id) for slide_id in slide_ids]
    database.execute(
        delete(AssessmentAssetGrant).where(
            AssessmentAssetGrant.administration_id == administration.id
        )
    )
    unpublish_assessment_derivative(storage, administration.public_id)
    created: list[AssessmentAssetGrant] = []
    try:
        for slide in slides:
            version = delivery_version(slide)
            target = publish_assessment_derivative(
                storage,
                slide.id,
                administration.public_id,
                slide.public_id,
                version,
            )
            _validate_descriptor(target)
            _prewarm(target)
            relative = f"{administration.public_id}/{slide.public_id}/{version}"
            grant = AssessmentAssetGrant(
                administration_id=administration.id,
                slide_id=slide.id,
                grant_path=relative,
                expires_at=utc_now() + timedelta(seconds=administration.duration_seconds, hours=24),
            )
            database.add(grant)
            created.append(grant)
        database.flush()
    except (OSError, PublicationError, AssessmentAssetError):
        unpublish_assessment_derivative(storage, administration.public_id)
        raise
    return created


def remove_asset_grants(
    database: OrmSession,
    storage: StorageLayout,
    administration: AssessmentAdministration,
) -> None:
    unpublish_assessment_derivative(storage, administration.public_id)
    database.execute(
        delete(AssessmentAssetGrant).where(
            AssessmentAssetGrant.administration_id == administration.id
        )
    )


def grant_manifest(database: OrmSession, administration_id: str) -> dict[str, str]:
    rows = database.execute(
        select(AssessmentAssetGrant.slide_id, AssessmentAssetGrant.grant_path)
        .where(AssessmentAssetGrant.administration_id == administration_id)
        .order_by(AssessmentAssetGrant.slide_id)
    )
    return {slide_id: f"/assessment-assets/{grant_path}/slide.dzi" for slide_id, grant_path in rows}


def assessment_assets_ready(database: OrmSession, storage: StorageLayout) -> bool:
    administrations = database.scalars(
        select(AssessmentAdministration).where(AssessmentAdministration.status == "open")
    ).all()
    root = (storage.root / "delivery" / "assessment").resolve()
    for administration in administrations:
        version = database.get(AssessmentVersion, administration.version_id)
        if version is None:
            return False
        required = set(definition_slide_ids(version.definition))
        grants = database.scalars(
            select(AssessmentAssetGrant).where(
                AssessmentAssetGrant.administration_id == administration.id,
                AssessmentAssetGrant.expires_at > utc_now(),
            )
        ).all()
        if {grant.slide_id for grant in grants} != required:
            return False
        for grant in grants:
            target = (root / grant.grant_path).resolve()
            if not target.is_relative_to(root):
                return False
            try:
                _validate_descriptor(target)
            except AssessmentAssetError:
                return False
    return True
