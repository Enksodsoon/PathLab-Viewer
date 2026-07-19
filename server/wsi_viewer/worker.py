import hashlib
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .conversion import generate_dzi
from .database import create_schema, session_factory
from .domain import SlideState
from .models import Job
from .ome import OmeError, validate_ome_tiff
from .storage import StorageLayout


def recover_stale_jobs(
    factory: sessionmaker[OrmSession], *, stale_after: timedelta = timedelta(minutes=5)
) -> int:
    cutoff = datetime.now(UTC) - stale_after
    with factory() as database:
        jobs = database.scalars(
            select(Job).where(Job.status == "running", Job.heartbeat_at < cutoff)
        ).all()
        for job in jobs:
            job.status = "queued"
            job.heartbeat_at = None
            if job.slide.state in {SlideState.VALIDATING, SlideState.CONVERTING}:
                job.slide.state = SlideState.QUEUED
        database.commit()
        return len(jobs)


def expire_incomplete_uploads(upload_root: Path, *, older_than: timedelta) -> int:
    if not upload_root.exists():
        return 0
    cutoff = datetime.now(UTC).timestamp() - older_than.total_seconds()
    expired = 0
    for info in upload_root.glob("*.info"):
        if info.stat().st_mtime >= cutoff:
            continue
        upload_id = info.name.removesuffix(".info")
        for artifact in (info, upload_root / upload_id, upload_root / f"{upload_id}.lock"):
            if artifact.is_file():
                artifact.unlink()
        expired += 1
    return expired


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_next(factory: sessionmaker[OrmSession], layout: StorageLayout) -> bool:
    with factory() as database:
        job = database.scalar(
            select(Job).where(Job.status == "queued").order_by(Job.created_at).limit(1)
        )
        if job is None:
            return False
        job.status = "running"
        job.attempts += 1
        job.heartbeat_at = datetime.now(UTC)
        slide = job.slide
        if job.kind == "delete":
            remove_slide(layout, slide.id, slide.public_id)
            database.delete(slide)
            database.commit()
            return True
        slide.state = SlideState.VALIDATING
        database.commit()
        paths = layout.for_slide(slide.id)
        try:
            if not paths.original.exists() or paths.original.stat().st_size != slide.source_bytes:
                raise OmeError("UPLOAD_LENGTH_MISMATCH", "Completed upload length does not match")
            slide.sha256 = _sha256(paths.original)
            metadata = validate_ome_tiff(paths.original)
            slide.slide_metadata = {
                "width": metadata.width,
                "height": metadata.height,
                "bitsPerSample": metadata.bits_per_sample,
                "physicalSizeX": metadata.physical_size_x,
                "physicalSizeY": metadata.physical_size_y,
                "physicalSizeUnit": metadata.physical_size_unit,
                "hasIccProfile": metadata.has_icc_profile,
            }
            slide.state = SlideState.CONVERTING
            job.heartbeat_at = datetime.now(UTC)
            database.commit()
            generate_dzi(
                paths.original,
                paths.private_derivative,
                series_index=metadata.series_index,
                bits=metadata.bits_per_sample,
            )
            slide.state = SlideState.READY_PRIVATE
            job.status = "complete"
            job.heartbeat_at = datetime.now(UTC)
            database.commit()
        except Exception as error:
            slide.state = SlideState.FAILED
            slide.error_code = error.code if isinstance(error, OmeError) else "CONVERSION_FAILED"
            slide.error_message = str(error)
            job.status = "failed"
            job.error = str(error)
            database.commit()
        return True


def remove_slide(layout: StorageLayout, slide_id: str, public_id: str) -> None:
    paths = layout.for_slide(slide_id)
    for target in {
        paths.original.parent,
        paths.derivative_staging,
        paths.private_derivative,
        layout.public_for(public_id),
    }:
        if target.exists():
            shutil.rmtree(target)


def main() -> None:
    settings = Settings()
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root, settings.storage_cap_bytes)
    while True:
        recover_stale_jobs(factory, stale_after=timedelta(seconds=settings.worker_stale_seconds))
        expire_incomplete_uploads(settings.tus_internal_upload_dir, older_than=timedelta(hours=24))
        if not process_next(factory, layout):
            time.sleep(1)
