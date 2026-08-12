from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session as OrmSession

from .desktop_sync import record_sync_event, revision_for
from .domain import SlideState
from .models import AuditEvent, DesktopCredential, DesktopIngest, Slide
from .ome import OmeMetadata, validate_ome_tiff
from .ome_tile_index import OmeTileIndex, OmeTileIndexError, build_ome_tile_index
from .storage import StorageLayout


class OmeIngestError(RuntimeError):
    pass


def _stable_file_sha256(path: Path) -> str:
    before = path.lstat()
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.lstat()
    if (
        before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or getattr(before, "st_ino", None) != getattr(after, "st_ino", None)
    ):
        raise OmeIngestError("OME_DESTINATION_CHANGED_DURING_SHA")
    return digest.hexdigest()


def desktop_ome_path(storage: StorageLayout, ingest_id: str) -> Path:
    return storage.root / "desktop-ingest" / f"{ingest_id}.ome.tif.partial"


def desktop_quarantine_path(storage: StorageLayout, ingest_id: str) -> Path:
    return storage.root / "desktop-ingest" / "quarantine" / f"{ingest_id}.ome.tif.failed"


def serialize_ome_tile_index(
    index: OmeTileIndex, *, jpeg_quality: int | None = None
) -> bytes:
    quality = index.jpeg_quality if jpeg_quality is None else jpeg_quality
    if not 1 <= quality <= 100:
        raise OmeIngestError("OME_JPEG_QUALITY_INVALID")
    document: dict[str, Any] = {
        "schema": "pathlab.ome-tile-index/v1",
        "source": {
            "bytes": index.source_size,
            "mtimeNs": index.source_mtime_ns,
            "sha256": index.source_sha256,
        },
        "width": index.width,
        "height": index.height,
        "tileWidth": index.tile_width,
        "tileHeight": index.tile_height,
        "codec": index.codec,
        "pyramidFactors": list(index.pyramid_factors),
        "standaloneJpeg": index.standalone_jpeg,
        "jpegQuality": quality,
        "qualityProfile": f"ome-dynamic-v1-q{quality}",
        "levels": [],
    }
    levels = document["levels"]
    assert isinstance(levels, list)
    for level in index.levels:
        tables = level.tiles[0].jpeg_tables if level.tiles else None
        levels.append(
            {
                "width": level.width,
                "height": level.height,
                "tilesAcross": level.tiles_across,
                "tilesDown": level.tiles_down,
                "jpegTables": (
                    base64.b64encode(tables).decode("ascii") if tables is not None else None
                ),
                "tiles": [
                    {
                        "offset": tile.offset,
                        "byteCount": tile.byte_count,
                        "standaloneJpeg": tile.standalone_jpeg,
                    }
                    for tile in level.tiles
                ],
            }
        )
    return json.dumps(document, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _write_index_atomic(path: Path, payload: bytes) -> None:
    if len(payload) > 16 * 1024**2:
        raise OmeIngestError("OME_INDEX_TOO_LARGE")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _validate_profile(ingest: DesktopIngest, index: OmeTileIndex) -> None:
    if ingest.ome_profile != "ome-dynamic-v1":
        raise OmeIngestError("OME_PROFILE_UNSUPPORTED")
    if ingest.ome_jpeg_quality != 75 or index.jpeg_quality != 75:
        raise OmeIngestError("OME_JPEG_QUALITY_MISMATCH")
    if ingest.ome_width != index.width or ingest.ome_height != index.height:
        raise OmeIngestError("OME_GEOMETRY_MISMATCH")
    pyramid_factor = 2
    if index.pyramid_factors != tuple(
        pyramid_factor**level for level in range(len(index.levels))
    ):
        raise OmeIngestError("OME_PYRAMID_FACTOR_UNSUPPORTED")
    if index.tile_width != 512 or index.tile_height != 512:
        raise OmeIngestError("OME_TILE_SIZE_UNSUPPORTED")
    # The bounded tile renderer can synthesize exactly one terminal factor-two
    # level from the smallest stored overview. Reject anything more truncated.
    if max(index.levels[-1].width, index.levels[-1].height) > 512 * pyramid_factor**2:
        raise OmeIngestError("OME_PYRAMID_INCOMPLETE")


def _metadata_json(
    ingest: DesktopIngest,
    metadata: OmeMetadata,
    index: OmeTileIndex,
) -> dict[str, Any]:
    return {
        "width": metadata.width,
        "height": metadata.height,
        "physicalSizeX": metadata.physical_size_x,
        "physicalSizeY": metadata.physical_size_y,
        "physicalSizeUnit": metadata.physical_size_unit,
        "artifactRevisionId": ingest.artifact_revision_id,
        "downsample": ingest.ome_downsample,
        "encoding": {
            "profile": ingest.ome_profile,
            "codec": index.codec,
            "tileSize": index.tile_width,
            "pyramidFactors": list(index.pyramid_factors),
            "rawFastPath": index.standalone_jpeg,
            "jpegQuality": ingest.ome_jpeg_quality or 75,
        },
    }


def install_ome_ingest(
    ingest: DesktopIngest,
    source: Path,
    database: OrmSession,
    storage: StorageLayout,
) -> None:
    destination: Path | None = None
    try:
        if source.stat().st_size != ingest.package_length:
            raise OmeIngestError("OME_LENGTH_MISMATCH")
        index = build_ome_tile_index(source, expected_sha256=ingest.package_sha256)
        metadata = validate_ome_tiff(source)
        _validate_profile(ingest, index)
        if (metadata.width, metadata.height) != (index.width, index.height):
            raise OmeIngestError("OME_METADATA_GEOMETRY_MISMATCH")

        slide = Slide(
            display_name=ingest.display_name,
            original_filename=f"{ingest.display_name}.ome.tif",
            source_bytes=ingest.package_length,
            reserved_bytes=0,
            derivative_bytes=0,
            derivative_file_count=0,
            render_mode="ome_dynamic",
            state=SlideState.READY_PRIVATE,
            privacy_status="private",
            sha256=index.source_sha256,
            slide_metadata=_metadata_json(ingest, metadata, index),
        )
        database.add(slide)
        database.flush()
        paths = storage.for_slide(slide.id)
        destination = paths.original
        destination.parent.mkdir(parents=True, exist_ok=False)
        os.replace(source, destination)
        if _stable_file_sha256(destination) != index.source_sha256:
            raise OmeIngestError("OME_PERSISTED_SHA_MISMATCH")
        _write_index_atomic(
            paths.ome_index,
            serialize_ome_tile_index(
                index, jpeg_quality=ingest.ome_jpeg_quality or 75
            ),
        )
        ingest.slide_id = slide.id
        ingest.status = "ready_private"
        ingest.error_code = None
        record_sync_event(database, "slide", slide.id, "upsert", revision_for(slide.updated_at))
        owning_credential = database.get(DesktopCredential, ingest.credential_id)
        if owning_credential is None:
            raise OmeIngestError("DESKTOP_CREDENTIAL_MISSING")
        database.add(
            AuditEvent(
                actor_user_id=owning_credential.user_id,
                action="desktop_ome_ingest.complete",
                target_id=slide.id,
            )
        )
        database.commit()
    except (OSError, OmeTileIndexError, OmeIngestError, ValueError) as error:
        database.rollback()
        quarantine = desktop_quarantine_path(storage, ingest.id)
        quarantine.parent.mkdir(parents=True, exist_ok=True)
        candidate = destination if destination is not None and destination.exists() else source
        if candidate.exists():
            try:
                os.replace(candidate, quarantine)
            except OSError:
                candidate.unlink(missing_ok=True)
        if destination is not None:
            shutil.rmtree(destination.parent, ignore_errors=True)
        failed = database.get(DesktopIngest, ingest.id)
        if failed is not None:
            failed.status = "failed"
            failed.error_code = str(error)[:80] or "OME_INGEST_FAILED"
            database.commit()
