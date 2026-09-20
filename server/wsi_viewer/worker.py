import hashlib
import json
import logging
import math
import multiprocessing
import os
import queue
import shutil
import signal
import stat
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import cv2
from PIL import Image
from sqlalchemy import CursorResult, delete, or_, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import Select

from .alignment import (
    AlignmentRejected,
    register_pair,
    rescale_registration,
)
from .alignment_pyramid import register_components
from .config import Settings
from .conversion import configure_libvips, generate_dzi
from .database import session_factory
from .domain import SlideState
from .models import (
    AuditEvent,
    ComparisonRegistrationRevision,
    ComparisonSet,
    DesktopPairing,
    Job,
    Slide,
)
from .ome import OmeError, validate_ome_tiff
from .runtime_protection import protection_snapshot
from .storage import StorageLayout
from .worker_health import HeartbeatWriter

JOB_POLL_INTERVAL_SECONDS = 2.0
STALE_RECOVERY_INTERVAL_SECONDS = 60.0
TUS_CLEANUP_INTERVAL_SECONDS = 30.0 * 60.0
STORAGE_CAPACITY_CHECK_INTERVAL_SECONDS = 60.0
PAIRING_CLEANUP_INTERVAL_SECONDS = 60.0
PAIRING_CLEANUP_BATCH_SIZE = 1000
STORAGE_CAPACITY_THRESHOLDS = (70, 80, 90)
LOGGER = logging.getLogger(__name__)


def _next_job_statement(*, now: datetime, postgres: bool) -> Select[tuple[Job]]:
    statement = (
        select(Job)
        .where(
            Job.status.in_({"queued", "retry_wait"}),
            or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= now),
        )
        .order_by(Job.created_at)
        .limit(1)
    )
    return statement.with_for_update(skip_locked=True) if postgres else statement


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
        cleanup_pairings: Callable[[], object] = lambda: None,
        report_capacity: Callable[[], object] = lambda: None,
        background_allowed: Callable[[], bool] = lambda: True,
        shutdown_requested: Callable[[], bool] = lambda: False,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._recover_stale = recover_stale
        self._cleanup_uploads = cleanup_uploads
        self._process_job = process_job
        self._cleanup_pairings = cleanup_pairings
        self._report_capacity = report_capacity
        self._background_allowed = background_allowed
        self._shutdown_requested = shutdown_requested
        self._monotonic = monotonic
        self._next_job_poll = float("-inf")
        self._next_stale_recovery = float("-inf")
        self._next_tus_cleanup = float("-inf")
        self._next_capacity_check = float("-inf")
        self._next_pairing_cleanup = float("-inf")

    def run_due(self) -> float:
        now = self._monotonic()
        if not self._background_allowed():
            self._next_job_poll = now + JOB_POLL_INTERVAL_SECONDS
            self._next_stale_recovery = max(
                self._next_stale_recovery, now + STALE_RECOVERY_INTERVAL_SECONDS
            )
            self._next_tus_cleanup = max(self._next_tus_cleanup, now + TUS_CLEANUP_INTERVAL_SECONDS)
            self._next_pairing_cleanup = max(
                self._next_pairing_cleanup, now + PAIRING_CLEANUP_INTERVAL_SECONDS
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
        if now >= self._next_pairing_cleanup:
            self._cleanup_pairings()
            self._next_pairing_cleanup = now + PAIRING_CLEANUP_INTERVAL_SECONDS
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
                self._next_pairing_cleanup,
            )
            - now,
        )


def background_work_is_allowed(factory: sessionmaker[OrmSession], *, enabled: bool) -> bool:
    if not enabled:
        return True
    with factory() as database:
        snapshot = protection_snapshot(database)
        database.commit()
        return not snapshot.blocks_background_work


def expire_desktop_pairings(
    factory: sessionmaker[OrmSession], *, now: datetime | None = None
) -> int:
    """Remove one bounded batch of expired handshakes, never issued credentials."""
    cutoff = now if now is not None else datetime.now(UTC)
    candidates = (
        select(DesktopPairing.id)
        .where(DesktopPairing.expires_at <= cutoff)
        .order_by(DesktopPairing.expires_at, DesktopPairing.id)
        .limit(PAIRING_CLEANUP_BATCH_SIZE)
    )
    with factory() as database:
        result = cast(
            CursorResult[Any],
            database.execute(
                delete(DesktopPairing)
                .where(
                    DesktopPairing.id.in_(candidates),
                    DesktopPairing.expires_at <= cutoff,
                )
                .execution_options(synchronize_session=False)
            ),
        )
        database.commit()
        return result.rowcount


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
            dialect = database.get_bind().dialect.name
            if dialect == "sqlite":
                database.connection().exec_driver_sql("BEGIN IMMEDIATE")
                slide = database.get(Slide, upload_id)
            else:
                slide = database.get(Slide, upload_id, with_for_update=True)
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


def _load_dzi_overview(derivative: Path, *, maximum: int = 4096) -> Image.Image:
    """Assemble one bounded pyramid level without opening the full-resolution WSI."""
    descriptor = derivative / "slide.dzi"
    root = ET.parse(descriptor).getroot()
    namespace = root.tag.partition("}")[0].lstrip("{")
    size = root.find(f"{{{namespace}}}Size")
    if size is None:
        raise OSError("DZI dimensions are unavailable")
    full_width, full_height = int(size.attrib["Width"]), int(size.attrib["Height"])
    tile_size = int(root.attrib["TileSize"])
    overlap = int(root.attrib.get("Overlap", "0"))
    image_format = root.attrib["Format"]
    maximum_level = math.ceil(math.log2(max(full_width, full_height)))
    level = maximum_level
    while level > 0:
        divisor = 2 ** (maximum_level - level)
        if max(math.ceil(full_width / divisor), math.ceil(full_height / divisor)) <= maximum:
            break
        level -= 1
    divisor = 2 ** (maximum_level - level)
    width, height = math.ceil(full_width / divisor), math.ceil(full_height / divisor)
    overview = Image.new("RGB", (width, height), "white")
    tile_root = derivative / "slide_files" / str(level)
    columns, rows = math.ceil(width / tile_size), math.ceil(height / tile_size)
    for row in range(rows):
        for column in range(columns):
            path = tile_root / f"{column}_{row}.{image_format}"
            with Image.open(path) as opened:
                tile = opened.convert("RGB")
            left = overlap if column else 0
            top = overlap if row else 0
            wanted_width = min(tile_size, width - column * tile_size)
            wanted_height = min(tile_size, height - row * tile_size)
            overview.paste(
                tile.crop((left, top, left + wanted_width, top + wanted_height)),
                (column * tile_size, row * tile_size),
            )
    return overview


def _alignment_child(
    reference_derivative: str,
    moving_derivative: str,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    output: Any,
) -> None:
    try:
        cv2.setNumThreads(1)
        cv2.setRNGSeed(0)

        def overview(path: str) -> Image.Image:
            derivative = Path(path)
            try:
                return _load_dzi_overview(derivative)
            except (FileNotFoundError, OSError, ET.ParseError):
                with Image.open(derivative / "thumbnail.jpg") as opened:
                    return opened.convert("RGB")

        reference_image = overview(reference_derivative)
        moving_image = overview(moving_derivative)
        result = None
        overview_error = None
        try:
            result = register_pair(reference_image, moving_image, max_dimension=4096)
            result = rescale_registration(
                result,
                reference_thumbnail_size=reference_image.size,
                moving_thumbnail_size=moving_image.size,
                reference_full_size=reference_full_size,
                moving_full_size=moving_full_size,
            )
        except AlignmentRejected as error:
            overview_error = str(error)
        if result is None or result.status != "ready":
            if all(
                (Path(path) / "slide.dzi").exists()
                for path in (reference_derivative, moving_derivative)
            ):
                try:
                    result = register_components(
                        Path(reference_derivative),
                        Path(moving_derivative),
                        reference_image,
                        moving_image,
                        reference_full_size,
                        moving_full_size,
                        progress=lambda done, total: output.put(
                            {
                                "progress": {
                                    "stage": "high-resolution-components",
                                    "processedComponentPairs": done,
                                    "totalComponentPairs": total,
                                }
                            }
                        ),
                    )
                except AlignmentRejected as error:
                    if result is None:
                        raise
                    result.evidence["componentRefinementReason"] = str(error)
            elif result is None:
                raise AlignmentRejected(overview_error or "No reliable correspondence found")
        assert result is not None
        output.put({"ok": True, "result": result.as_json()})
    except Exception as error:
        output.put({"ok": False, "type": type(error).__name__, "error": str(error)})


def _process_rss_bytes(process_id: int) -> int:
    if not sys.platform.startswith("win"):
        try:
            pages = int(Path(f"/proc/{process_id}/statm").read_text().split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE")
        except (FileNotFoundError, IndexError, OSError, ValueError):
            return 0
    import ctypes
    from ctypes import wintypes

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    handle = ctypes.windll.kernel32.OpenProcess(0x1000 | 0x0400, False, process_id)
    if not handle:
        return 0
    try:
        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        if not ctypes.windll.psapi.GetProcessMemoryInfo(
            handle, ctypes.byref(counters), counters.cb
        ):
            return 0
        return int(counters.WorkingSetSize)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _run_alignment_bounded(
    reference_derivative: Path,
    moving_derivative: Path,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    *,
    timeout_seconds: int,
    memory_bytes: int,
    heartbeat: Callable[[], None] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    context = multiprocessing.get_context("spawn")
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_alignment_child,
        args=(
            str(reference_derivative),
            str(moving_derivative),
            reference_full_size,
            moving_full_size,
            output,
        ),
        daemon=True,
    )
    process.start()
    started = time.monotonic()
    last_heartbeat = started
    try:
        # Drain the result while the child is alive: Queue's feeder can block
        # child shutdown until a large coordinate map has been consumed.
        while True:
            if heartbeat and time.monotonic() - last_heartbeat >= 10:
                heartbeat()
                last_heartbeat = time.monotonic()
            if time.monotonic() - started > timeout_seconds:
                process.terminate()
                raise AlignmentRejected("registration exceeded the pair timeout")
            if _process_rss_bytes(process.pid or 0) > memory_bytes:
                process.terminate()
                raise AlignmentRejected("registration exceeded the memory ceiling")
            try:
                result = output.get(timeout=0.2)
                if "progress" in result:
                    if progress:
                        progress(result["progress"])
                    continue
                break
            except queue.Empty:
                if not process.is_alive():
                    raise AlignmentRejected("registration process ended without a result") from None
        process.join(2)
        if not result.get("ok"):
            raise AlignmentRejected(result.get("error") or "registration failed")
        return cast(dict[str, Any], result["result"])
    finally:
        if process.is_alive():
            process.terminate()
            process.join(2)
        output.close()


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
        now = datetime.now(UTC)
        if protection_enabled:
            snapshot = protection_snapshot(database, now=now)
            if snapshot.blocks_background_work:
                database.commit()
                return False
        statement = _next_job_statement(
            now=now, postgres=database.get_bind().dialect.name == "postgresql"
        )
        job = database.scalar(statement)
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
        if job.kind == "align":
            checkpoint = dict(job.checkpoint or {})
            comparison = database.get(ComparisonSet, checkpoint.get("comparisonSetId"))
            if comparison is None or slide.id != checkpoint.get("memberId"):
                job.status = "failed_terminal"
                job.failure_code = "ALIGNMENT_TARGET_MISSING"
                job.error = "Comparison set or member is unavailable"
                job.heartbeat_at = None
                job.lease_expires_at = None
                database.commit()
                return True
            expected_version = checkpoint.get("setVersion", comparison.version)
            if comparison.version != expected_version or job.cancellation_requested_at is not None:
                job.status = "cancelled"
                job.failure_code = "ALIGNMENT_STALE"
                job.error = "Comparison changed while registration was queued"
                job.heartbeat_at = None
                job.lease_expires_at = None
                database.commit()
                return True
            primary_reference = database.get(Slide, comparison.reference_slide_id)
            anchor_id = checkpoint.get("anchorSlideId") or comparison.reference_slide_id
            reference = database.get(Slide, anchor_id)
            source_current = (
                reference is not None
                and primary_reference is not None
                and comparison.source_versions.get(reference.id) == reference.sha256
                and comparison.source_versions.get(primary_reference.id) == primary_reference.sha256
                and comparison.source_versions.get(slide.id) == slide.sha256
            )
            if not source_current:
                comparison.status = "failed"
                job.status = "failed_terminal"
                job.failure_code = "ALIGNMENT_SOURCE_CHANGED"
                job.error = "A comparison source changed after the set was created"
                job.heartbeat_at = None
                job.lease_expires_at = None
                database.commit()
                return True
            assert reference is not None
            assert primary_reference is not None
            checkpoint.update({"progress": 10, "stage": "loading-overviews", "processedPatches": 0})
            job.checkpoint = checkpoint
            comparison.status = "running"
            database.commit()
            try:
                reference_derivative = layout.for_slide(reference.id).private_derivative
                moving_derivative = layout.for_slide(slide.id).private_derivative
                checkpoint.update(
                    {"progress": 30, "stage": "matching-structures", "totalPatches": 2}
                )
                job.checkpoint = checkpoint
                job.heartbeat_at = datetime.now(UTC)
                job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                database.commit()
                reference_metadata = reference.slide_metadata or {}
                moving_metadata = slide.slide_metadata or {}
                try:
                    reference_full_size = (
                        int(reference_metadata["width"]),
                        int(reference_metadata["height"]),
                    )
                    moving_full_size = (
                        int(moving_metadata["width"]),
                        int(moving_metadata["height"]),
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise AlignmentRejected(
                        "full slide dimensions unavailable for coordinate mapping"
                    ) from error

                def renew_alignment_lease() -> None:
                    database.refresh(job)
                    database.refresh(comparison)
                    if job.cancellation_requested_at or comparison.version != expected_version:
                        raise AlignmentRejected("registration cancelled or superseded")
                    job.heartbeat_at = datetime.now(UTC)
                    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                    database.commit()

                def record_alignment_progress(values: dict[str, Any]) -> None:
                    renew_alignment_lease()
                    checkpoint.update(values)
                    job.checkpoint = dict(checkpoint)
                    database.commit()

                limits = job.resource_limits or {}
                result_json = _run_alignment_bounded(
                    reference_derivative,
                    moving_derivative,
                    reference_full_size,
                    moving_full_size,
                    timeout_seconds=min(600, int(limits.get("timeoutSeconds", 600))),
                    memory_bytes=min(2 * 1024**3, int(limits.get("memoryBytes", 2 * 1024**3))),
                    heartbeat=renew_alignment_lease,
                    progress=record_alignment_progress,
                )
                checkpoint.update(
                    {"progress": 80, "stage": "building-coordinate-map", "processedPatches": 0}
                )
                job.checkpoint = checkpoint
                confidence = float(result_json["confidence"])
                coordinate_reference_id = reference.id
                # Preserve the direct stain-to-anchor map. Composing its vertices
                # through different anchor cells changes interior geometry and
                # also breaks consumers expecting anchor coordinates.
                database.refresh(comparison)
                database.refresh(job)
                if (
                    comparison.version != expected_version
                    or job.cancellation_requested_at is not None
                ):
                    job.status = "cancelled"
                    job.failure_code = "ALIGNMENT_STALE"
                    job.error = "Stale registration output discarded"
                    job.heartbeat_at = None
                    job.lease_expires_at = None
                    database.commit()
                    return True
                registrations = dict(comparison.registrations)
                registrations[slide.id] = {
                    **result_json,
                    "provenance": "automatic",
                    "sourceVersion": slide.sha256,
                    "referenceVersion": primary_reference.sha256,
                    "anchorSlideId": reference.id,
                    "anchorVersion": reference.sha256,
                    "coordinateReferenceId": coordinate_reference_id,
                }
                comparison.registrations = registrations
                database.add(
                    ComparisonRegistrationRevision(
                        comparison_set_id=comparison.id,
                        slide_id=slide.id,
                        set_version=comparison.version,
                        source_version=slide.sha256,
                        anchor_slide_id=reference.id,
                        algorithm_version="piecewise-affine-components-v9",
                        provenance="automatic",
                        registration=registrations[slide.id],
                    )
                )
                comparison.status = (
                    "ready"
                    if len(registrations) == len(comparison.member_slide_ids) - 1
                    and all(value.get("status") == "ready" for value in registrations.values())
                    else "running"
                    if len(registrations) < len(comparison.member_slide_ids) - 1
                    else "partial"
                )
                job.checkpoint = {**checkpoint, "progress": 100, "stage": "complete"}
                job.output_manifest = {
                    "comparisonSetId": comparison.id,
                    "memberId": slide.id,
                    "confidence": confidence,
                    "inlierCount": result_json["inlierCount"],
                }
                job.status = "succeeded"
            except (AlignmentRejected, FileNotFoundError, OSError) as error:
                database.refresh(comparison)
                database.refresh(job)
                if comparison.version != expected_version or job.cancellation_requested_at:
                    job.status = "cancelled"
                    job.failure_code = "ALIGNMENT_STALE"
                    job.heartbeat_at = None
                    job.lease_expires_at = None
                    database.commit()
                    return True
                registrations = dict(comparison.registrations)
                registrations[slide.id] = {
                    "status": "rejected",
                    "provenance": "automatic",
                    "reason": str(error),
                }
                comparison.registrations = registrations
                comparison.status = (
                    "running"
                    if len(registrations) < len(comparison.member_slide_ids) - 1
                    else "partial"
                )
                job.status = "failed_terminal"
                job.failure_code = "ALIGNMENT_REJECTED"
                job.error = str(error)
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
        cleanup_pairings=lambda: expire_desktop_pairings(factory),
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
