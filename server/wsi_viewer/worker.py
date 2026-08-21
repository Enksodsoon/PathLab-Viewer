import hashlib
import json
import logging
import shutil
import signal
import stat
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .config import Settings
from .conversion import configure_libvips, generate_dzi
from .database import session_factory
from .domain import SlideState
from .models import AuditEvent, Job, Slide
from .ome import OmeError, validate_ome_tiff
from .runtime_protection import protection_snapshot
from .storage import StorageLayout
from .worker_health import HeartbeatWriter

JOB_POLL_INTERVAL_SECONDS = 2.0
STALE_RECOVERY_INTERVAL_SECONDS = 60.0
TUS_CLEANUP_INTERVAL_SECONDS = 30.0 * 60.0
STORAGE_CAPACITY_CHECK_INTERVAL_SECONDS = 60.0
STORAGE_CAPACITY_THRESHOLDS = (70, 80, 90)
LOGGER = logging.getLogger(__name__)


class DiskUsage(Protocol):
    @property
    def total(self) -> int: ...

    @property
    def used(self) -> int: ...

    @property
    def free(self) -> int: ...


class StorageCapacityMonitor:
    def __init__(
        self,
        root: Path,
        *,
        disk_usage: Callable[[Path], DiskUsage] = shutil.disk_usage,
        log: logging.Logger = LOGGER,
    ) -> None:
        self._root = root
        self._disk_usage = disk_usage
        self._log = log
        self._last_threshold = 0

    def check(self) -> None:
        usage = self._disk_usage(self._root)
        total = usage.total
        used = usage.used
        free = usage.free
        utilization = 100.0 if total <= 0 else used * 100.0 / total
        threshold = max(
            (value for value in STORAGE_CAPACITY_THRESHOLDS if utilization >= value),
            default=0,
        )
        if threshold == self._last_threshold:
            return
        payload = {
            "event": "storage_capacity_warning" if threshold else "storage_capacity_recovered",
            "free_bytes": free,
            "threshold_percent": threshold,
            "utilization_percent": round(utilization, 2),
        }
        message = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        if threshold:
            self._log.warning(message)
        elif self._last_threshold:
            self._log.info(message)
        self._last_threshold = threshold


class WorkerScheduler:
    def __init__(
        self,
        *,
        recover_stale: Callable[[], object],
        cleanup_uploads: Callable[[], object],
        process_job: Callable[[], bool],
        report_capacity: Callable[[], object] = lambda: None,
        background_allowed: Callable[[], bool] = lambda: True,
        shutdown_requested: Callable[[], bool] = lambda: False,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._recover_stale = recover_stale
        self._cleanup_uploads = cleanup_uploads
        self._process_job = process_job
        self._report_capacity = report_capacity
        self._background_allowed = background_allowed
        self._shutdown_requested = shutdown_requested
        self._monotonic = monotonic
        self._next_job_poll = float("-inf")
        self._next_stale_recovery = float("-inf")
        self._next_tus_cleanup = float("-inf")
        self._next_capacity_check = float("-inf")

    def run_due(self) -> float:
        now = self._monotonic()
        if not self._background_allowed():
            self._next_job_poll = now + JOB_POLL_INTERVAL_SECONDS
            self._next_stale_recovery = max(
                self._next_stale_recovery, now + STALE_RECOVERY_INTERVAL_SECONDS
            )
            self._next_tus_cleanup = max(
                self._next_tus_cleanup, now + TUS_CLEANUP_INTERVAL_SECONDS
            )
            return JOB_POLL_INTERVAL_SECONDS
        if now >= self._next_stale_recovery:
            self._recover_stale()
            self._next_stale_recovery = now + STALE_RECOVERY_INTERVAL_SECONDS
        if now >= self._next_tus_cleanup:
            self._cleanup_uploads()
            self._next_tus_cleanup = now + TUS_CLEANUP_INTERVAL_SECONDS
        if now >= self._next_capacity_check:
            self._report_capacity()
            self._next_capacity_check = now + STORAGE_CAPACITY_CHECK_INTERVAL_SECONDS
        if now >= self._next_job_poll:
            if self._shutdown_requested():
                return 0.0
            processed = self._process_job()
            self._next_job_poll = now if processed else now + JOB_POLL_INTERVAL_SECONDS
        return max(
            0.0,
            min(
                self._next_job_poll,
                self._next_stale_recovery,
                self._next_tus_cleanup,
                self._next_capacity_check,
            )
            - now,
        )


def background_work_is_allowed(
    factory: sessionmaker[OrmSession], *, enabled: bool
) -> bool:
    if not enabled:
        return True
    with factory() as database:
        snapshot = protection_snapshot(database)
        database.commit()
        return not snapshot.blocks_background_work


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
            if job.slide is not None and job.slide.state in {
                SlideState.VALIDATING,
                SlideState.CONVERTING,
            }:
                job.slide.state = SlideState.QUEUED
        database.commit()
        return len(jobs)


def _unlink_upload_artifact(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISREG(mode) or stat.S_ISLNK(mode):
        path.unlink()


def expire_incomplete_uploads(
    upload_root: Path,
    *,
    older_than: timedelta,
    factory: sessionmaker[OrmSession] | None = None,
) -> int:
    if not upload_root.exists():
        return 0
    cutoff = datetime.now(UTC).timestamp() - older_than.total_seconds()
    expired = 0
    for info in upload_root.glob("*.info"):
        before = info.stat()
        if before.st_mtime >= cutoff:
            continue
        upload_id = info.name.removesuffix(".info")
        allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        if not upload_id or any(character not in allowed for character in upload_id):
            continue
        artifacts = (upload_root / upload_id, upload_root / f"{upload_id}.lock", info)
        if factory is None:
            for artifact in artifacts:
                _unlink_upload_artifact(artifact)
            expired += 1
            continue
        with factory() as database:
            database.connection().exec_driver_sql("BEGIN IMMEDIATE")
            slide = database.get(Slide, upload_id)
            if slide is None:
                for artifact in artifacts:
                    _unlink_upload_artifact(artifact)
                database.commit()
                expired += 1
                continue
            if slide.state is not SlideState.UPLOADING:
                database.rollback()
                continue
            try:
                current = info.stat()
            except FileNotFoundError:
                database.rollback()
                continue
            unchanged = (
                current.st_mtime_ns == before.st_mtime_ns
                and current.st_size == before.st_size
                and current.st_ino == before.st_ino
            )
            if not unchanged:
                database.rollback()
                continue
            for artifact in artifacts:
                _unlink_upload_artifact(artifact)
            database.add(AuditEvent(action="upload.expired", target_id=slide.id))
            database.delete(slide)
            database.commit()
        expired += 1
    return expired


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def process_next(
    factory: sessionmaker[OrmSession],
    layout: StorageLayout,
    *,
    shutdown_requested: Callable[[], bool] = lambda: False,
    protection_enabled: bool = False,
) -> bool:
    if shutdown_requested():
        return False
    with factory() as database:
        if shutdown_requested():
            return False
        now = datetime.now(UTC).replace(tzinfo=None)
        if protection_enabled:
            snapshot = protection_snapshot(database, now=now)
            if snapshot.blocks_background_work:
                database.commit()
                return False
        job = database.scalar(
            select(Job)
            .where(
                Job.status.in_({"queued", "retry_wait"}),
                or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= now),
            )
            .order_by(Job.created_at)
            .limit(1)
        )
        if job is None:
            return False
        job.status = "running"
        job.attempts += 1
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=60)
        slide = job.slide
        if slide is None:
            job.status = "failed_terminal"
            job.failure_code = "JOB_TARGET_MISSING"
            job.error = "Job has no supported target"
            job.heartbeat_at = None
            job.lease_expires_at = None
            database.commit()
            return True
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
            job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
            database.commit()
            database.refresh(job)
            if job.cancellation_requested_at is not None:
                slide.state = SlideState.QUEUED
                job.status = "blocked_classroom"
                job.heartbeat_at = None
                job.lease_expires_at = None
                database.commit()
                return True
            result = generate_dzi(
                paths.original,
                paths.private_derivative,
                series_index=metadata.series_index,
                bits=metadata.bits_per_sample,
            )
            slide.derivative_bytes = result.derivative_bytes
            slide.derivative_file_count = result.derivative_file_count
            slide.thumbnail_filename = "thumbnail.jpg"
            slide.reserved_bytes = 0
            slide.state = SlideState.READY_PRIVATE
            job.status = "succeeded"
            job.heartbeat_at = None
            job.lease_expires_at = None
            database.commit()
        except Exception as error:
            slide.reserved_bytes = 0
            slide.state = SlideState.FAILED
            slide.error_code = error.code if isinstance(error, OmeError) else "CONVERSION_FAILED"
            slide.error_message = str(error)
            job.status = "failed_terminal"
            job.failure_code = error.code if isinstance(error, OmeError) else "CONVERSION_FAILED"
            job.error = str(error)
            job.heartbeat_at = None
            job.lease_expires_at = None
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


def run_worker_loop(scheduler: WorkerScheduler, shutdown: threading.Event) -> None:
    while not shutdown.is_set():
        delay = scheduler.run_due()
        if delay > 0:
            shutdown.wait(delay)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    configure_libvips(
        concurrency=settings.libvips_concurrency,
        cache_max_mem_bytes=settings.libvips_cache_max_mem_bytes,
        cache_max_files=settings.libvips_cache_max_files,
        cache_max_operations=settings.libvips_cache_max_operations,
    )
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root, settings.storage_cap_bytes)
    capacity_monitor = StorageCapacityMonitor(settings.data_root)
    shutdown = threading.Event()

    def request_shutdown(_: int, __: object) -> None:
        shutdown.set()

    signal.signal(signal.SIGTERM, request_shutdown)
    signal.signal(signal.SIGINT, request_shutdown)
    scheduler = WorkerScheduler(
        recover_stale=lambda: recover_stale_jobs(
            factory, stale_after=timedelta(seconds=settings.worker_stale_seconds)
        ),
        cleanup_uploads=lambda: expire_incomplete_uploads(
            settings.tus_internal_upload_dir,
            older_than=timedelta(hours=24),
            factory=factory,
        ),
        process_job=lambda: process_next(
            factory,
            layout,
            shutdown_requested=shutdown.is_set,
            protection_enabled=settings.classroom_protection_enabled,
        ),
        report_capacity=capacity_monitor.check,
        background_allowed=lambda: background_work_is_allowed(
            factory, enabled=settings.classroom_protection_enabled
        ),
        shutdown_requested=shutdown.is_set,
    )
    heartbeat = HeartbeatWriter(
        settings.worker_heartbeat_path,
        interval_seconds=settings.worker_heartbeat_interval_seconds,
    )
    heartbeat.start()
    try:
        run_worker_loop(scheduler, shutdown)
    finally:
        heartbeat.stop()
