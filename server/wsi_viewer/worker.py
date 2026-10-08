import hashlib
import json
import logging
import math
import multiprocessing
import os
import queue
import shutil
import signal
import sqlite3
import stat
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict
from collections.abc import Callable
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import cv2
from PIL import Image
from sqlalchemy import CursorResult, case, delete, func, or_, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql import Select

from .alignment import (
    AlignmentRejected,
    register_pair,
    rescale_registration,
)
from .alignment_calibration import metadata_frame_digest, normalized_microns_per_pixel
from .alignment_engines import (
    ENGINE_NATIVE,
    ENGINE_NATIVE_OVERVIEW,
    ENGINE_VALIS,
    ENGINE_VERSIONS,
    merge_component_maps,
    run_engine,
    settings_digest,
)
from .alignment_fast import PREPARATION_VERSION, PreparationCache, register_prepared
from .alignment_geometry import (
    derivative_sampling_geometry,
    original_frame_registration,
    validate_sampling_geometry,
)
from .alignment_policy import VALIDATION_POLICY, case_ids_conflict, current_registration
from .alignment_processes import AlignmentContainmentLost
from .alignment_processes import LinuxAlignmentGroup as _LinuxAlignmentGroup
from .alignment_pyramid import (
    _candidate_component_pairs,
    component_bounds,
    read_region,
    refine_supported_patches,
    register_components,
)
from .alignment_regions import slide_version
from .alignment_resources import EngineResourceUnavailable
from .alignment_windows import WindowsAlignmentJob as _WindowsAlignmentJob
from .config import Settings
from .conversion import configure_libvips, generate_dzi
from .database import session_factory
from .desktop_sync import record_sync_event, revision_for
from .domain import SlideState
from .models import (
    AuditEvent,
    ComparisonRegistrationCandidate,
    ComparisonRegistrationRevision,
    ComparisonSet,
    DesktopPairing,
    Job,
    Slide,
)
from .ome import OmeError, validate_ome_tiff
from .runtime_protection import protection_snapshot
from .stack_service import activate_ready_slide_memberships, remove_slide_from_stacks
from .storage import StorageLayout
from .worker_health import HeartbeatWriter

JOB_POLL_INTERVAL_SECONDS = 2.0
_preparation_cache = PreparationCache()
_preview_maps: OrderedDict[tuple[Any, ...], dict[str, Any]] = OrderedDict()
_preview_map_bytes = 0
_worker_startup_seconds: float | None = None
STALE_RECOVERY_INTERVAL_SECONDS = 60.0
TUS_CLEANUP_INTERVAL_SECONDS = 30.0 * 60.0
STORAGE_CAPACITY_CHECK_INTERVAL_SECONDS = 60.0
PAIRING_CLEANUP_INTERVAL_SECONDS = 60.0
PAIRING_CLEANUP_BATCH_SIZE = 1000
STORAGE_CAPACITY_THRESHOLDS = (70, 80, 90)
LOGGER = logging.getLogger(__name__)


def _candidate_validation_state(
    registration: dict[str, Any], engine: str, source_version: str, anchor_version: str
) -> str:
    candidate = {
        **registration,
        "provenance": "automatic",
        "engine": engine,
        "engineVersion": ENGINE_VERSIONS[engine],
        "settingsDigest": settings_digest(engine, registration.get("engineSettings") or {}),
        "sourceVersion": source_version,
        "anchorVersion": anchor_version,
    }
    current = current_registration(
        candidate, source_version=source_version, anchor_version=anchor_version
    )
    return "engineering_passed" if current and current.get("status") == "ready" else "rejected"


def _registration_quality(registration: dict[str, Any] | None) -> tuple[int, float, int]:
    """Rank navigation evidence without treating an approximate map as anatomy."""
    registration = current_registration(registration)
    if not registration or registration.get("status") == "stale":
        return (0, 0.0, 0)
    provenance = str(registration.get("provenance") or "")
    status = str(registration.get("status") or "")
    evidence = registration.get("evidence") or {}
    overview_count = len(registration.get("overviewTriangles") or [])
    triangle_count = len(registration.get("triangles") or [])
    confidence = float(registration.get("confidence") or 0.0)
    if provenance.startswith("manual"):
        tier = 100
    elif status == "ready" and triangle_count:
        tier = 80
    elif (
        status == "approximate"
        and overview_count
        and evidence.get("source") == "bounded-pyramid-whole-slide-structure"
    ):
        tier = 60
    elif (
        status == "approximate"
        and overview_count
        and evidence.get("componentOrderPreserved") is True
    ):
        tier = 50
    elif status == "approximate" and overview_count:
        tier = 20
    elif status == "rejected":
        tier = 5
    else:
        tier = 10
    return (tier, confidence, triangle_count or overview_count)


def _best_compatible_registration(
    database: OrmSession,
    *,
    comparison: ComparisonSet,
    slide: Slide,
    reference: Slide,
) -> dict[str, Any] | None:
    if case_ids_conflict(slide.case_id, reference.case_id):
        return None
    candidates: list[dict[str, Any]] = []
    current = comparison.registrations.get(slide.id)
    if (
        current
        and current.get("sourceVersion") == slide.sha256
        and current.get("anchorVersion") == reference.sha256
        and current.get("anchorSlideId", reference.id) == reference.id
    ):
        candidates.append(current)
    revisions = database.scalars(
        select(ComparisonRegistrationRevision).where(
            ComparisonRegistrationRevision.comparison_set_id == comparison.id,
            ComparisonRegistrationRevision.slide_id == slide.id,
            ComparisonRegistrationRevision.source_version == slide.sha256,
            ComparisonRegistrationRevision.anchor_slide_id == reference.id,
        )
    ).all()
    for revision in revisions:
        registration = revision.registration
        if registration.get("anchorVersion") != reference.sha256:
            continue
        candidates.append(registration)
    candidates = [
        value
        for item in candidates
        if (
            value := current_registration(
                item,
                source_metadata=slide.slide_metadata or {},
                anchor_metadata=reference.slide_metadata or {},
                source_snapshot_version=slide_version(slide) if not slide.sha256 else None,
                anchor_snapshot_version=slide_version(reference) if not reference.sha256 else None,
            )
        )
        and value.get("status") in {"ready", "approximate"}
    ]
    return max(candidates, key=_registration_quality, default=None)


def _with_overview_fallback(
    primary: dict[str, Any], secondary: dict[str, Any] | None
) -> dict[str, Any]:
    """Keep a qualified coarse mesh without replacing stronger local evidence."""
    if str(primary.get("provenance", "")).startswith("manual") or not secondary:
        return primary
    fallback = secondary.get("overviewFallback") or secondary
    if (
        fallback.get("status") != "approximate"
        or not fallback.get("overviewTriangles")
        or (fallback.get("evidence") or {}).get("source") != "bounded-sparse-overview"
        or any(
            not primary.get(key) or primary.get(key) != fallback.get(key)
            for key in ("sourceVersion", "anchorVersion", "anchorSlideId")
        )
        or (current_registration(fallback) or {}).get("status") != "approximate"
    ):
        return primary
    if primary.get("overviewTriangles") == fallback.get("overviewTriangles"):
        result = deepcopy(primary)
        result.pop("overviewFallback", None)
        return result
    result = deepcopy(primary)
    result["overviewFallback"] = deepcopy(fallback)
    result["overviewFallback"].pop("overviewFallback", None)
    return result


def _next_job_statement(
    *,
    now: datetime,
    postgres: bool,
    include_kinds: frozenset[str] | None = None,
    exclude_kinds: frozenset[str] | None = None,
) -> Select[tuple[Job]]:
    statement = (
        select(Job)
        .where(
            Job.status.in_({"queued", "retry_wait"}),
            or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= now),
        )
        .order_by(
            case(
                ((Job.kind == "align") & (Job.checkpoint["phase"].as_string() == "preview"), 0),
                (Job.kind.in_({"align", "align_benchmark"}), 2),
                else_=1,
            ),
            Job.created_at,
        )
        .limit(1)
    )
    if include_kinds:
        statement = statement.where(Job.kind.in_(include_kinds))
    if exclude_kinds:
        statement = statement.where(Job.kind.not_in(exclude_kinds))
    return statement.with_for_update(skip_locked=True) if postgres else statement


class DiskUsage(Protocol):
    @property
    def total(self) -> int: ...

    @property
    def used(self) -> int: ...

    @property
    def free(self) -> int: ...


class ChildProcess(Protocol):
    @property
    def pid(self) -> int | None: ...

    def is_alive(self) -> bool: ...

    def terminate(self) -> None: ...

    def join(self, timeout: float | None = None) -> None: ...


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
        try:
            before = info.stat()
        except FileNotFoundError:
            continue
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
            remove_slide_from_stacks(database, slide.id)
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
    size = next((node for node in root if node.tag.rsplit("}", 1)[-1] == "Size"), None)
    if size is None:
        raise OSError("DZI dimensions are unavailable")
    full_width, full_height = int(size.attrib["Width"]), int(size.attrib["Height"])
    tile_size = int(root.attrib["TileSize"])
    overlap = int(root.attrib.get("Overlap", "0"))
    image_format = root.attrib["Format"]
    geometry = derivative_sampling_geometry(derivative, (full_width, full_height), maximum=maximum)
    assert geometry is not None
    level = geometry["selectedLevel"]
    width, height = geometry["analysisSize"]
    overview = Image.new("RGB", (width, height), "white")
    tile_root = derivative / "slide_files" / str(level)
    columns, rows = math.ceil(width / tile_size), math.ceil(height / tile_size)
    loaded_tiles = 0
    for row in range(rows):
        for column in range(columns):
            path = tile_root / f"{column}_{row}.{image_format}"
            if not path.exists() and (derivative / ".openslide-source.json").is_file():
                from .alignment_inputs import require_snapshot_tile_capacity
                from .tile_routes import materialize_local_openslide_tile_from_root

                require_snapshot_tile_capacity(derivative)
                path = materialize_local_openslide_tile_from_root(
                    derivative, derivative.name, path.relative_to(derivative).as_posix()
                )
            # Sparse DZI writers omit all-white tiles. The missing tile is
            # background, not a corrupt pyramid and must not force engines
            # back to the low-resolution thumbnail.
            if not path.exists():
                continue
            with Image.open(path) as opened:
                tile = opened.convert("RGB")
            loaded_tiles += 1
            left = overlap if column else 0
            top = overlap if row else 0
            wanted_width = min(tile_size, width - column * tile_size)
            wanted_height = min(tile_size, height - row * tile_size)
            overview.paste(
                tile.crop((left, top, left + wanted_width, top + wanted_height)),
                (column * tile_size, row * tile_size),
            )
    if not loaded_tiles:
        raise FileNotFoundError("No overview tiles exist at the selected DZI level")
    overview.info["alignmentGeometry"] = geometry
    return overview


def _load_alignment_overview(derivative: Path, *, maximum: int = 4096) -> Image.Image:
    """Prefer a bounded pyramid level for every registration engine."""
    from .alignment_inputs import DESCRIPTOR_NAME, load_immutable_overview

    if (derivative / DESCRIPTOR_NAME).exists():
        return load_immutable_overview(derivative)
    try:
        return _load_dzi_overview(derivative, maximum=maximum)
    except (FileNotFoundError, OSError, ET.ParseError):
        descriptor = derivative / "slide.dzi"
        with Image.open(derivative / "thumbnail.jpg") as opened:
            if descriptor.is_file() and max(opened.size) > 4096:
                raise AlignmentRejected(
                    "alignment thumbnail exceeds the bounded overview size"
                ) from None
            image = opened.convert("RGB")
        if descriptor.is_file():
            root = ET.parse(descriptor).getroot()
            size = next((node for node in root if node.tag.rsplit("}", 1)[-1] == "Size"), None)
            if size is None:
                raise AlignmentRejected("sampling DZI dimensions are unavailable") from None
            geometry = derivative_sampling_geometry(
                derivative,
                (int(size.attrib["Width"]), int(size.attrib["Height"])),
                kind="thumbnail-fallback",
            )
            image.info["alignmentGeometry"] = geometry
        return image


def _alignment_child(
    reference_derivative: str,
    moving_derivative: str,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    engine_name: str,
    engine_settings: dict[str, Any] | None,
    artifact_dir: str | None,
    output: Any,
    seed_registration: dict[str, Any] | None = None,
    startup_gate: Any = None,
) -> None:
    # Give every native registration and any JVM it launches one process group
    # so the OCI supervisor can stop the complete tree on timeout/cancellation.
    if not sys.platform.startswith("win"):
        os.setsid()
    if startup_gate is not None and not startup_gate.wait(30):
        return
    _alignment_invocation(
        reference_derivative,
        moving_derivative,
        reference_full_size,
        moving_full_size,
        engine_name,
        engine_settings,
        artifact_dir,
        output,
        seed_registration,
    )


def _alignment_invocation(
    reference_derivative: str,
    moving_derivative: str,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    engine_name: str,
    engine_settings: dict[str, Any] | None,
    artifact_dir: str | None,
    output: Any,
    seed_registration: dict[str, Any] | None = None,
) -> None:
    """One engine invocation after the enclosing child's containment barrier."""
    try:
        cv2.setNumThreads(1)
        cv2.setRNGSeed(0)

        def overview(path: str) -> Image.Image:
            return _load_alignment_overview(Path(path))

        reference_image = overview(reference_derivative)
        moving_image = overview(moving_derivative)
        original_reference_size, original_moving_size = reference_full_size, moving_full_size
        # Capture exact pyramid geometry before any engine resizes its pixels.
        # Plain JPEG requests retain their existing numerical/settings contract.
        engine_settings = dict(engine_settings or {})
        for side, image, derivative, true_size in (
            ("reference", reference_image, reference_derivative, reference_full_size),
            ("moving", moving_image, moving_derivative, moving_full_size),
        ):
            geometry = image.info.get("alignmentGeometry")
            if geometry is None and (Path(derivative) / "slide.dzi").is_file():
                geometry = {
                    "schema": "pathlab-sampling-frame/1",
                    "kind": "thumbnail-fallback",
                    "sourceSize": list(true_size),
                    "analysisSize": list(image.size),
                    "coordinateFrameSize": list(true_size),
                    "samplingScale": [true_size[0] / image.width, true_size[1] / image.height],
                    "cropOrigin": [0, 0],
                }
            if geometry is not None:
                geometry = validate_sampling_geometry(
                    geometry, source_size=true_size, analysis_size=image.size
                )
                engine_settings[f"{side}Geometry"] = geometry
                frame_size = tuple(geometry["coordinateFrameSize"])
                if side == "reference":
                    reference_full_size = frame_size
                else:
                    moving_full_size = frame_size
        if engine_name == ENGINE_VALIS and all(
            (Path(path) / "slide.dzi").is_file()
            for path in (reference_derivative, moving_derivative)
        ):
            reference_boxes = component_bounds(reference_image, reference_full_size)
            moving_boxes = component_bounds(moving_image, moving_full_size)
            reference_boxes = [
                (
                    left,
                    top,
                    min(right, original_reference_size[0]),
                    min(bottom, original_reference_size[1]),
                )
                for left, top, right, bottom in reference_boxes
            ]
            moving_boxes = [
                (
                    left,
                    top,
                    min(right, original_moving_size[0]),
                    min(bottom, original_moving_size[1]),
                )
                for left, top, right, bottom in moving_boxes
            ]
            if 1 < len(reference_boxes) == len(moving_boxes):
                started = time.monotonic()
                pairs, _ = _candidate_component_pairs(
                    reference_image,
                    moving_image,
                    reference_boxes,
                    moving_boxes,
                    reference_full_size,
                    moving_full_size,
                )
                parts = []
                failures = []
                component_settings_receipts = []
                for index, (moving_index, reference_index) in enumerate(pairs):
                    reference_crop, reference_frame = read_region(
                        Path(reference_derivative), reference_boxes[reference_index], 2048
                    )
                    moving_crop, moving_frame = read_region(
                        Path(moving_derivative), moving_boxes[moving_index], 2048
                    )
                    reference_size = (
                        reference_crop.width * reference_frame[2],
                        reference_crop.height * reference_frame[2],
                    )
                    moving_size = (
                        moving_crop.width * moving_frame[2],
                        moving_crop.height * moving_frame[2],
                    )
                    component_settings = dict(engine_settings)
                    for side, crop, frame, true_size in (
                        ("reference", reference_crop, reference_frame, original_reference_size),
                        ("moving", moving_crop, moving_frame, original_moving_size),
                    ):
                        component_settings[f"{side}Geometry"] = {
                            "schema": "pathlab-sampling-frame/1",
                            "kind": "component-region",
                            "sourceSize": list(true_size),
                            "analysisSize": list(crop.size),
                            "coordinateFrameSize": [crop.width * frame[2], crop.height * frame[2]],
                            "samplingScale": [frame[2], frame[2]],
                            "cropOrigin": list(frame[:2]),
                            "pyramidDivisor": frame[2],
                        }
                    key = hashlib.sha256(
                        repr(
                            (
                                hashlib.sha256(reference_crop.tobytes()).hexdigest(),
                                hashlib.sha256(moving_crop.tobytes()).hexdigest(),
                                reference_crop.mode,
                                moving_crop.mode,
                                reference_frame,
                                moving_frame,
                                reference_size,
                                moving_size,
                                settings_digest(engine_name, component_settings),
                                "ordered-components-v1",
                            )
                        ).encode()
                    ).hexdigest()
                    component_dir = (
                        Path(artifact_dir) / f"component-{key}" if artifact_dir else None
                    )
                    receipt = component_dir / "valis-coordinate-map.json" if component_dir else None
                    try:
                        payload = None
                        if receipt and receipt.is_file():
                            with suppress(OSError, ValueError, TypeError):
                                payload = json.loads(receipt.read_text())
                        if (
                            not isinstance(payload, dict)
                            or payload.get("engineVersion") != ENGINE_VERSIONS[engine_name]
                            or payload.get("status") not in {"ready", "approximate"}
                            or not payload.get("movingToReference")
                            or not (payload.get("triangles") or payload.get("overviewTriangles"))
                        ):
                            run = run_engine(
                                engine_name,
                                reference=reference_crop,
                                moving=moving_crop,
                                reference_full_size=reference_size,
                                moving_full_size=moving_size,
                                artifact_dir=component_dir,
                                settings=component_settings,
                                progress=lambda values: output.put({"progress": values}),
                            )
                            payload = run.registration
                        # run_engine already composed the crop origins into
                        # original coordinates; merging must not apply them twice.
                        parts.append(
                            (
                                payload,
                                (0, 0, reference_frame[2])
                                if payload.get("samplingGeometryApplied") is True
                                else reference_frame,
                                (0, 0, moving_frame[2])
                                if payload.get("samplingGeometryApplied") is True
                                else moving_frame,
                            )
                        )
                        component_settings_receipts.append(
                            payload.get("engineSettings", component_settings)
                        )
                    except AlignmentRejected as error:
                        failures.append(
                            {
                                "movingComponent": moving_index,
                                "referenceComponent": reference_index,
                                "reason": str(error),
                            }
                        )
                    output.put(
                        {
                            "progress": {
                                "stage": "valis-components",
                                "processedComponentPairs": index + 1,
                                "totalComponentPairs": len(pairs),
                            }
                        }
                    )
                payload = merge_component_maps(parts)
                payload["engineSettings"] = {
                    **engine_settings,
                    "componentEffectiveSettings": component_settings_receipts,
                }
                payload["evidence"].update(
                    {
                        "componentOrderPreserved": True,
                        "componentPolicy": "ordered-components-v1",
                        "totalComponentPairs": len(pairs),
                        "acceptedComponentPairs": payload["evidence"]["componentCount"],
                        "componentFailures": failures,
                    }
                )
                if failures:
                    payload["reason"] = (
                        "Partial component coverage; unresolved tissue needs refinement"
                    )
                artifact = (
                    Path(artifact_dir) / "component-coordinate-map.json" if artifact_dir else None
                )
                if artifact:
                    artifact.parent.mkdir(parents=True, exist_ok=True)
                    artifact.write_text(json.dumps(payload))
                output.put(
                    {
                        "ok": True,
                        "result": payload,
                        "artifactPath": str(artifact) if artifact else None,
                        "artifactSha256": hashlib.sha256(artifact.read_bytes()).hexdigest()
                        if artifact
                        else None,
                        "runtimeSeconds": time.monotonic() - started,
                    }
                )
                return
        if engine_name != ENGINE_NATIVE:
            engine_run = run_engine(
                engine_name,
                reference=reference_image,
                moving=moving_image,
                reference_full_size=reference_full_size,
                moving_full_size=moving_full_size,
                artifact_dir=Path(artifact_dir) if artifact_dir else None,
                settings=engine_settings,
                progress=lambda values: output.put({"progress": values}),
            )
            output.put(
                {
                    "ok": True,
                    "result": engine_run.registration,
                    "artifactPath": str(engine_run.artifact_path)
                    if engine_run.artifact_path
                    else None,
                    "artifactSha256": engine_run.artifact_sha256,
                    "runtimeSeconds": engine_run.runtime_seconds,
                }
            )
            return
        if seed_registration and (
            seed_registration.get("overviewTriangles") or seed_registration.get("triangles")
        ):
            refined = refine_supported_patches(
                Path(reference_derivative),
                Path(moving_derivative),
                moving_image,
                reference_full_size,
                moving_full_size,
                seed_registration,
                checkpoint_dir=Path(artifact_dir) / "native-batches" if artifact_dir else None,
                progress=lambda done, total: output.put(
                    {
                        "progress": {
                            "stage": "guided-patches",
                            "processedPatches": done,
                            "totalPatches": total,
                        }
                    }
                ),
            )
            refined = original_frame_registration(refined, engine_settings)
            refined["engineSettings"] = engine_settings
            output.put({"ok": True, "result": refined})
            return
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
                        checkpoint_dir=Path(artifact_dir) / "native-batches"
                        if artifact_dir
                        else None,
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
        payload = original_frame_registration(result.as_json(), engine_settings)
        payload["engineSettings"] = engine_settings
        output.put({"ok": True, "result": payload})
    except Exception as error:
        output.put({"ok": False, "type": type(error).__name__, "error": str(error)})


def _process_rss_bytes(process_id: int, *, peak: bool = False) -> int:
    if not sys.platform.startswith("win"):
        try:
            if peak:
                for line in Path(f"/proc/{process_id}/status").read_text().splitlines():
                    if line.startswith("VmHWM:"):
                        return int(line.split()[1]) * 1024
                return 0
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
        return int(counters.PeakWorkingSetSize if peak else counters.WorkingSetSize)
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _descendant_process_ids(process_id: int) -> set[int]:
    if sys.platform.startswith("win") or process_id <= 0:
        return {process_id} if process_id > 0 else set()
    discovered = {process_id}
    pending = [process_id]
    while pending:
        parent = pending.pop()
        children_file = Path(f"/proc/{parent}/task/{parent}/children")
        try:
            children = {int(value) for value in children_file.read_text().split()}
        except (FileNotFoundError, OSError, ValueError):
            children = set()
        unseen = children - discovered
        discovered.update(unseen)
        pending.extend(unseen)
    return discovered


def _process_tree_rss_bytes(process_id: int) -> int:
    return sum(_process_rss_bytes(pid) for pid in _descendant_process_ids(process_id))


def _terminate_process_tree(
    process: ChildProcess,
    linux_group: _LinuxAlignmentGroup | None = None,
) -> None:
    if linux_group is not None:
        linux_group.close()
        process.join(2)
        return
    if process.pid and not sys.platform.startswith("win"):
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        process.join(2)
        if process.is_alive():
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
    elif process.is_alive():
        process.terminate()
    process.join(2)


def _run_alignment_bounded(
    reference_derivative: Path,
    moving_derivative: Path,
    reference_full_size: tuple[int, int],
    moving_full_size: tuple[int, int],
    *,
    engine_name: str = ENGINE_NATIVE,
    engine_settings: dict[str, Any] | None = None,
    seed_registration: dict[str, Any] | None = None,
    artifact_dir: Path | None = None,
    timeout_seconds: int,
    memory_bytes: int,
    heartbeat: Callable[[], None] | None = None,
    progress: Callable[[dict[str, Any]], None] | None = None,
    _child_target: Callable[..., None] | None = None,
    _absolute_deadline: float | None = None,
) -> dict[str, Any]:
    timeout_seconds = min(600, timeout_seconds)
    if timeout_seconds <= 0:
        raise AlignmentRejected("registration exceeded the pair timeout")
    if heartbeat:
        heartbeat()
    started = time.monotonic()
    deadline = started + timeout_seconds
    if _absolute_deadline is not None:
        deadline = min(deadline, _absolute_deadline)
    if deadline <= started:
        raise AlignmentRejected("registration exceeded the pair timeout before process startup")
    context = multiprocessing.get_context("spawn")
    startup_gate = context.Event() if sys.platform.startswith(("win", "linux")) else None
    output = context.Queue(maxsize=1)
    process = context.Process(
        target=_child_target or _alignment_child,
        args=(
            str(reference_derivative),
            str(moving_derivative),
            reference_full_size,
            moving_full_size,
            engine_name,
            engine_settings,
            str(artifact_dir) if artifact_dir else None,
            output,
            seed_registration,
            startup_gate,
        ),
        daemon=True,
    )
    process.start()
    last_heartbeat = started
    peak_memory_bytes = 0
    windows_job = None
    linux_group = None
    resource_metrics: dict[str, Any] = {}
    try:
        if startup_gate is not None and sys.platform.startswith("win"):
            try:
                windows_job = _WindowsAlignmentJob(process.pid or 0, memory_bytes)
                resource_metrics = windows_job.metrics()
            except OSError as error:
                raise AlignmentRejected(
                    f"Windows process containment memory ceiling admission failed: {error}"
                ) from error
            startup_gate.set()
        elif startup_gate is not None:
            linux_group = _LinuxAlignmentGroup(process.pid or 0, min(10, timeout_seconds))
            resource_metrics = {
                "processContainment": "linux-owned-session",
                "memoryMeasurementScope": "linux-owned-session-sampled-rss",
                "peakMemoryBytes": 0,
            }
            startup_gate.set()
        # Drain the result while the child is alive: Queue's feeder can block
        # child shutdown until a large coordinate map has been consumed.
        while True:
            if heartbeat and time.monotonic() - last_heartbeat >= 0.5:
                heartbeat()
                last_heartbeat = time.monotonic()
            if time.monotonic() >= deadline:
                _terminate_process_tree(process, linux_group)
                raise AlignmentRejected("registration exceeded the pair timeout")
            if windows_job is not None:
                resource_metrics = windows_job.measure()
                current_memory_bytes = int(resource_metrics["peakMemoryBytes"])
            else:
                current_memory_bytes = (
                    linux_group.resident_bytes()
                    if linux_group is not None
                    else _process_tree_rss_bytes(process.pid or 0)
                )
            peak_memory_bytes = max(peak_memory_bytes, current_memory_bytes)
            if linux_group is not None:
                resource_metrics["peakMemoryBytes"] = peak_memory_bytes
            if current_memory_bytes > memory_bytes:
                _terminate_process_tree(process, linux_group)
                raise AlignmentRejected(
                    "registration exceeded the memory ceiling "
                    f"({current_memory_bytes / 1024**3:.2f} GiB > "
                    f"{memory_bytes / 1024**3:.2f} GiB)"
                )
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
            if result.get("type") == "EngineResourceUnavailable":
                raise EngineResourceUnavailable(
                    result.get("error") or "engine resource unavailable"
                )
            raise AlignmentRejected(result.get("error") or "registration failed")
        payload = cast(dict[str, Any], result["result"])
        if result.get("artifactPath"):
            payload["artifactPath"] = result["artifactPath"]
        if result.get("artifactSha256"):
            payload["artifactSha256"] = result["artifactSha256"]
        if result.get("runtimeSeconds") is not None:
            payload["runtimeSeconds"] = result["runtimeSeconds"]
        payload["peakMemoryBytes"] = peak_memory_bytes
        if windows_job is not None:
            resource_metrics = windows_job.measure()
            payload.update(resource_metrics)
        elif linux_group is not None:
            payload.update(resource_metrics)
        return payload
    except OSError as error:
        platform = "Windows" if sys.platform.startswith("win") else "Linux"
        rejected = AlignmentRejected(f"{platform} process containment accounting failed: {error}")
        cast(Any, rejected).resource_metrics = resource_metrics
        raise rejected from error
    except AlignmentRejected as error:
        cast(Any, error).resource_metrics = resource_metrics
        raise
    finally:
        try:
            try:
                if windows_job is not None:
                    windows_job.close()
                if linux_group is not None:
                    linux_group.close()
            except OSError as error:
                platform = "Windows" if sys.platform.startswith("win") else "Linux"
                raise AlignmentContainmentLost(
                    f"{platform} process containment cleanup could not prove "
                    f"all descendants terminal: {error}",
                    resource_metrics,
                ) from error
            finally:
                if process.is_alive():
                    _terminate_process_tree(process)
                else:
                    process.join(2)
        finally:
            output.close()


class AlignmentPreempted(Exception):
    """Interactive foreground work takes priority over unpublished refinement."""


def _map_bytes(value: Any) -> int:
    """Conservative Python resident size, including containers rather than JSON only."""
    if isinstance(value, dict):
        return sys.getsizeof(value) + sum(_map_bytes(k) + _map_bytes(v) for k, v in value.items())
    if isinstance(value, (list, tuple)):
        return sys.getsizeof(value) + sum(_map_bytes(v) for v in value)
    return sys.getsizeof(value)


def _container_memory() -> dict[str, int]:
    measurements = {}
    for filename, key in (
        ("memory.current", "containerMemoryBytes"),
        ("memory.peak", "containerLifetimePeakMemoryBytes"),
    ):
        with suppress(OSError, ValueError):
            measurements[key] = int((Path("/sys/fs/cgroup") / filename).read_text())
    return measurements


def _alignment_remaining_budget(checkpoint: dict[str, Any], limits: dict[str, Any]) -> float:
    return max(
        0.0,
        min(600.0, float(limits.get("timeoutSeconds", 600)))
        - max(0.0, float(checkpoint.get("computeSecondsUsed", 0))),
    )


def _finish_superseded_alignment(database: OrmSession, comparison: ComparisonSet, job: Job) -> None:
    """End obsolete progress without mutating saved maps or regional revisions."""
    if job.kind == "align_benchmark":
        return
    active = database.scalar(
        select(Job.id)
        .where(
            Job.id != job.id,
            Job.kind == "align",
            Job.status.in_({"queued", "retry_wait", "leased", "running"}),
            Job.checkpoint["comparisonSetId"].as_string() == comparison.id,
            Job.checkpoint["setVersion"].as_integer() == comparison.version,
        )
        .limit(1)
    )
    if active:
        comparison.status = "running"
        return
    members = [
        member for member in comparison.member_slide_ids if member != comparison.reference_slide_id
    ]
    comparison.status = (
        "ready"
        if members
        and all(
            comparison.registrations.get(member, {}).get("status") == "ready" for member in members
        )
        else "partial"
    )


def _preview_alignment(
    database: OrmSession,
    layout: StorageLayout,
    job: Job,
    comparison: ComparisonSet,
    reference: Slide,
    moving: Slide,
) -> None:
    """Publish a conservative first pass and enqueue independent refinement."""
    global _preview_map_bytes
    started = time.monotonic()
    checkpoint = dict(job.checkpoint or {})
    expected_sources = (reference.sha256, moving.sha256)
    expected_frames = (
        metadata_frame_digest(reference.slide_metadata or {}),
        metadata_frame_digest(moving.slide_metadata or {}),
    )
    deadline = datetime.fromisoformat(checkpoint["foregroundDeadlineAt"])
    queue_seconds = max(
        0.0, (datetime.now(UTC) - (deadline - timedelta(seconds=10))).total_seconds()
    )
    payload: dict[str, Any]
    hits = 0
    preparation_seconds = 0.0
    pair_hit = False
    effective_settings: dict[str, Any] = {}
    try:
        if case_ids_conflict(moving.case_id, reference.case_id):
            raise AlignmentRejected("Needs refinement: slides have different case identifiers")
        if datetime.now(UTC) >= deadline:
            raise AlignmentRejected("Needs refinement: stack foreground deadline exceeded")
        prepared = []
        versions = []
        for slide in (reference, moving):
            metadata = slide.slide_metadata or {}
            size = (int(metadata["width"]), int(metadata["height"]))
            derivative = layout.for_slide(slide.id).private_derivative
            side = "reference" if slide.id == reference.id else "moving"
            calibration = normalized_microns_per_pixel(metadata)
            if calibration is not None:
                effective_settings[f"{side}MicronsPerPixel"] = list(calibration)

            def load(path: Path = derivative) -> Image.Image:
                return _load_alignment_overview(path, maximum=1024)

            # Source digest plus derivative geometry prevents cross-resolution reuse.
            dzi = derivative / "slide.dzi"
            geometry_key = (
                hashlib.sha256(dzi.read_bytes()).hexdigest() if dzi.is_file() else "thumbnail"
            )
            tick = time.monotonic()
            coordinate_size = size
            overview = None
            if dzi.is_file() or (derivative / "immutable-overview.json").is_file():
                # The actual loader chooses DZI, immutable PNG, or thumbnail.
                # Its frame must be known before choosing the preparation key.
                overview = load()
                geometry = validate_sampling_geometry(
                    overview.info["alignmentGeometry"],
                    source_size=size,
                    analysis_size=overview.size,
                )
                effective_settings[f"{side}Geometry"] = geometry
                coordinate_size = tuple(geometry["coordinateFrameSize"])
                geometry_key += (
                    ":"
                    + hashlib.sha256(
                        json.dumps(geometry, sort_keys=True, separators=(",", ":")).encode()
                        + overview.tobytes()
                    ).hexdigest()
                )
            key = f"{layout.root.resolve()}:{slide.sha256}:{geometry_key}"
            value, hit = _preparation_cache.prepare(key, overview or load, coordinate_size)
            preparation_seconds += time.monotonic() - tick
            prepared.append(value)
            versions.append((key, size))
            hits += int(hit)
        cache_key = (
            *versions,
            PREPARATION_VERSION,
            VALIDATION_POLICY,
            settings_digest(ENGINE_NATIVE_OVERVIEW, effective_settings),
        )
        if cache_key in _preview_maps:
            _preview_maps.move_to_end(cache_key)
            payload = deepcopy(_preview_maps[cache_key])
            pair_hit = True
        else:
            if datetime.now(UTC) >= deadline:
                raise AlignmentRejected("Needs refinement: stack foreground deadline exceeded")
            payload = original_frame_registration(
                register_prepared(*prepared).as_json(), effective_settings
            )
            encoded_bytes = _map_bytes(payload)
            while _preview_maps and _preview_map_bytes + encoded_bytes > 16 * 1024**2:
                _, removed = _preview_maps.popitem(last=False)
                _preview_map_bytes -= _map_bytes(removed)
            if encoded_bytes <= 16 * 1024**2:
                _preview_maps[cache_key] = deepcopy(payload)
                _preview_map_bytes += encoded_bytes
        if datetime.now(UTC) > deadline:
            raise AlignmentRejected("Needs refinement: stack foreground deadline exceeded")
    except (AlignmentRejected, OSError, ValueError, KeyError) as error:
        payload = {
            "status": "needs_refinement",
            "reason": str(error),
            "triangles": [],
            "overviewTriangles": [],
            "movingToReference": None,
        }
    payload.update(
        provenance="automatic",
        sourceVersion=moving.sha256,
        anchorVersion=reference.sha256,
        sourceFrameVersion=expected_frames[1],
        anchorFrameVersion=expected_frames[0],
        anchorSlideId=reference.id,
        coordinateReferenceId=reference.id,
        engine=ENGINE_NATIVE_OVERVIEW,
        engineVersion=ENGINE_VERSIONS[ENGINE_NATIVE_OVERVIEW],
        engineSettings=effective_settings,
        settingsDigest=settings_digest(ENGINE_NATIVE_OVERVIEW, effective_settings),
    )
    payload["evidence"] = {
        **payload.get("evidence", {}),
        "validationPolicy": VALIDATION_POLICY,
        "phase": "preview",
        "preparationVersion": PREPARATION_VERSION,
        "stackAcceptedAt": (deadline - timedelta(seconds=10)).isoformat(),
        "previewPublishedAt": datetime.now(UTC).isoformat(),
        "preparationSeconds": preparation_seconds,
        "computeSeconds": max(0.0, time.monotonic() - started - preparation_seconds),
        "queueSeconds": queue_seconds,
        "preparationCacheHits": hits,
        "pairCacheHit": pair_hit,
        "workerRssBytes": _process_rss_bytes(os.getpid()),
        "workerLifetimePeakRssBytes": _process_rss_bytes(os.getpid(), peak=True),
        "workerStartupSeconds": _worker_startup_seconds,
        **_container_memory(),
    }
    # Reread before publication; edits/cancellation can arrive while OpenCV runs.
    database.refresh(comparison)
    database.refresh(job)
    database.refresh(reference)
    database.refresh(moving)
    if case_ids_conflict(moving.case_id, reference.case_id):
        payload.update(
            status="needs_refinement",
            reason="Needs refinement: slides have different case identifiers",
            triangles=[],
            overviewTriangles=[],
            movingToReference=None,
        )
    if (
        comparison.version != checkpoint["setVersion"]
        or job.cancellation_requested_at
        or comparison.source_versions.get(moving.id) != moving.sha256
        or comparison.source_versions.get(reference.id) != reference.sha256
        or expected_sources != (reference.sha256, moving.sha256)
        or expected_frames
        != (
            metadata_frame_digest(reference.slide_metadata or {}),
            metadata_frame_digest(moving.slide_metadata or {}),
        )
    ):
        job.status = "cancelled"
        job.failure_code = "ALIGNMENT_STALE"
        job.error = "Stale registration output discarded after comparison change"
        _finish_superseded_alignment(database, comparison, job)
    else:
        previous = _best_compatible_registration(
            database, comparison=comparison, slide=moving, reference=reference
        )
        preserved = previous and _registration_quality(previous) > _registration_quality(payload)
        metrics = payload["evidence"]
        if preserved:
            payload = _with_overview_fallback(cast(dict[str, Any], previous), payload)
        comparison.registrations = {**comparison.registrations, moving.id: payload}
        if not preserved or payload != previous:
            database.add(
                ComparisonRegistrationRevision(
                    comparison_set_id=comparison.id,
                    slide_id=moving.id,
                    set_version=comparison.version,
                    source_version=moving.sha256,
                    anchor_slide_id=reference.id,
                    algorithm_version=PREPARATION_VERSION,
                    provenance="automatic",
                    registration=payload,
                )
            )
        key = hashlib.sha256(f"{job.id}:refinement".encode()).hexdigest()
        checkpoint["computeSecondsUsed"] = float(checkpoint.get("computeSecondsUsed", 0)) + max(
            0.0, time.monotonic() - started
        )
        if database.scalar(select(Job.id).where(Job.idempotency_key_hash == key)) is None:
            database.add(
                Job(
                    slide_id=moving.id,
                    kind="align",
                    resource_class="isolated",
                    idempotency_key_hash=key,
                    checkpoint={
                        **checkpoint,
                        "phase": "refinement",
                        "stage": "queued-refinement",
                        "progress": 0,
                        "preserveExisting": True,
                    },
                    resource_limits={
                        "cpuThreads": 1,
                        "memoryBytes": 2 * 1024**3,
                        "timeoutSeconds": 600,
                    },
                )
            )
        comparison.status = "running"
        job.status = "succeeded"
        job.checkpoint = {
            **checkpoint,
            "stage": "preview-complete",
            "progress": 100,
            "resultStatus": payload.get("status"),
            "runtimeSeconds": time.monotonic() - started,
            "queueSeconds": queue_seconds,
            "timings": metrics,
        }
    job.heartbeat_at = None
    job.lease_expires_at = None
    database.commit()


def process_next(
    factory: sessionmaker[OrmSession],
    layout: StorageLayout,
    *,
    shutdown_requested: Callable[[], bool] = lambda: False,
    protection_enabled: bool = False,
    include_kinds: frozenset[str] | None = None,
    exclude_kinds: frozenset[str] | None = None,
    exclusive_alignment: bool | None = None,
) -> bool:
    if shutdown_requested():
        return False
    with factory() as database:
        if shutdown_requested():
            return False
        # ponytail: serialize admission only; shard if claim throughput becomes a measured limit.
        dialect = database.get_bind().dialect.name
        if dialect == "postgresql":
            if not database.scalar(select(func.pg_try_advisory_xact_lock(0x504C41424A4F42))):
                return False
        elif dialect == "sqlite":
            try:
                database.connection().exec_driver_sql("BEGIN IMMEDIATE")
            except OperationalError as error:
                if isinstance(error.orig, sqlite3.OperationalError) and (
                    getattr(error.orig, "sqlite_errorcode", 0) & 0xFF
                ) in {sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED}:
                    return False  # Retry admission on the next worker poll.
                raise
        now = datetime.now(UTC)
        if protection_enabled:
            snapshot = protection_snapshot(database, now=now)
            if snapshot.blocks_background_work:
                database.commit()
                return False
        alignment_kinds = {"align", "align_benchmark"}
        active_statuses = {"leased", "running", "checkpointing"}
        # This check runs inside the serialized claim transaction. A worker of
        # any role must wait for the current alignment's containment cleanup;
        # queued foreground work still remains visible to its preemption loop.
        if (
            database.scalar(
                select(Job.id)
                .where(Job.kind.in_(alignment_kinds), Job.status.in_(active_statuses))
                .limit(1)
            )
            is not None
        ):
            return False
        if exclusive_alignment is True:
            # A queued alignment owns admission priority, but it starts only
            # after ordinary heavy work has drained.
            ordinary_active = database.scalar(
                select(Job.id)
                .where(Job.kind.not_in(alignment_kinds), Job.status.in_(active_statuses))
                .limit(1)
            )
            if ordinary_active is not None:
                return False
        elif exclusive_alignment is False:
            alignment_waiting_or_active = database.scalar(
                select(Job.id)
                .where(
                    Job.kind.in_(alignment_kinds),
                    or_(
                        Job.status.in_(active_statuses),
                        Job.status.in_({"queued", "retry_wait"})
                        & (Job.checkpoint["phase"].as_string() == "preview")
                        & or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= now),
                    ),
                )
                .limit(1)
            )
            if alignment_waiting_or_active is not None:
                return False
        statement = _next_job_statement(
            now=now,
            postgres=database.get_bind().dialect.name == "postgresql",
            include_kinds=include_kinds,
            exclude_kinds=exclude_kinds,
        )
        job = database.scalar(statement)
        if job is None:
            return False
        if (
            exclusive_alignment is True
            and (job.checkpoint or {}).get("phase") != "preview"
            and database.scalar(
                select(Job.id)
                .where(
                    Job.kind.not_in(alignment_kinds),
                    Job.status.in_({"queued", "retry_wait"}),
                    or_(Job.next_attempt_at.is_(None), Job.next_attempt_at <= now),
                )
                .limit(1)
            )
            is not None
        ):
            return False
        job.status = "running"
        job.attempts += 1
        job.heartbeat_at = now
        job.lease_expires_at = now + timedelta(seconds=60)
        slide = job.slide
        if job.kind == "delete":
            if slide is not None:
                job_id = job.id
                checkpoint: dict[str, Any] = {
                    "phase": "delete-files",
                    "slideId": slide.id,
                    "publicId": slide.public_id,
                }
                # Retain this job across the slide's FK cascade so cleanup can resume.
                job.slide = None
                job.checkpoint = checkpoint
                record_sync_event(database, "slide", slide.id, "delete", revision_for(now))
                database.delete(slide)
                try:
                    database.commit()
                except IntegrityError:
                    database.rollback()
                    blocked = database.get(Job, job_id)
                    if blocked is not None:
                        blocked.status = "failed_terminal"
                        blocked.failure_code = "SLIDE_IN_USE"
                        blocked.error = "Slide deletion was rejected by a database reference"
                        blocked.heartbeat_at = None
                        blocked.lease_expires_at = None
                        if blocked.slide is not None:
                            blocked.slide.state = SlideState.FAILED
                            blocked.slide.error_code = "SLIDE_IN_USE"
                        database.commit()
                    return True
            checkpoint = job.checkpoint or {}
            target_id, public_id = checkpoint.get("slideId"), checkpoint.get("publicId")
            if (
                checkpoint.get("phase") != "delete-files"
                or not isinstance(target_id, str)
                or not isinstance(public_id, str)
            ):
                job.status = "failed_terminal"
                job.failure_code = "JOB_TARGET_MISSING"
                job.error = "Delete job has no supported cleanup target"
            else:
                try:
                    remove_slide(layout, target_id, public_id)
                except (OSError, ValueError):
                    job.status = "retry_wait" if job.attempts < 3 else "failed_terminal"
                    job.failure_code = "DELETE_FILES_FAILED"
                    job.error = "Slide file cleanup failed"
                    job.next_attempt_at = now + timedelta(seconds=30)
                else:
                    job.status = "succeeded"
                    job.failure_code = None
                    job.error = None
            job.heartbeat_at = None
            job.lease_expires_at = None
            database.commit()
            return True
        if slide is None:
            job.status = "failed_terminal"
            job.failure_code = "JOB_TARGET_MISSING"
            job.error = "Job has no supported target"
            job.heartbeat_at = None
            job.lease_expires_at = None
            database.commit()
            return True
        database.commit()
        if job.kind in {"align", "align_benchmark"}:
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
            requested_settings: dict[str, Any] = dict(checkpoint.get("engineSettings") or {})
            applied_settings: dict[str, Any] = dict(requested_settings)
            expected_version = checkpoint.get("setVersion", comparison.version)
            if comparison.version != expected_version or job.cancellation_requested_at is not None:
                job.status = "cancelled"
                job.failure_code = "ALIGNMENT_STALE"
                job.error = "Comparison changed while registration was queued"
                job.heartbeat_at = None
                job.lease_expires_at = None
                _finish_superseded_alignment(database, comparison, job)
                database.commit()
                return True
            primary_reference = database.get(Slide, comparison.reference_slide_id)
            anchor_id = checkpoint.get("anchorSlideId") or comparison.reference_slide_id
            reference = database.get(Slide, anchor_id)
            source_current = (
                reference is not None
                and primary_reference is not None
                and bool(reference.sha256)
                and bool(primary_reference.sha256)
                and bool(slide.sha256)
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
            assert reference.sha256 is not None and slide.sha256 is not None
            if checkpoint.get("sourceVersion") not in {None, slide.sha256} or checkpoint.get(
                "anchorVersion"
            ) not in {None, reference.sha256}:
                job.status = "cancelled"
                job.failure_code = "ALIGNMENT_SOURCE_CHANGED"
                job.heartbeat_at = None
                job.lease_expires_at = None
                database.commit()
                return True
            expected_sources = (reference.sha256, slide.sha256)
            if checkpoint.get("phase") == "preview":
                cv2.setNumThreads(1)
                cv2.setRNGSeed(0)
                _preview_alignment(database, layout, job, comparison, reference, slide)
                return True
            checkpoint.update({"progress": 10, "stage": "loading-overviews", "processedPatches": 0})
            job.checkpoint = checkpoint
            if job.kind != "align_benchmark":
                comparison.status = "running"
            database.commit()
            try:
                if case_ids_conflict(slide.case_id, reference.case_id):
                    raise AlignmentRejected(
                        "Needs refinement: slides have different case identifiers"
                    )
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
                expected_metadata_frames = (
                    metadata_frame_digest(reference_metadata),
                    metadata_frame_digest(moving_metadata),
                )
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
                for side, pair_metadata in (
                    ("reference", reference_metadata),
                    ("moving", moving_metadata),
                ):
                    calibration = normalized_microns_per_pixel(pair_metadata)
                    if calibration is not None:
                        applied_settings[f"{side}MicronsPerPixel"] = list(calibration)

                def renew_alignment_lease() -> None:
                    database.refresh(job)
                    database.refresh(comparison)
                    if job.cancellation_requested_at or comparison.version != expected_version:
                        raise AlignmentRejected("registration cancelled or superseded")
                    if database.scalar(
                        select(Job.id)
                        .where(
                            Job.status.in_({"queued", "retry_wait"}),
                            or_(
                                Job.next_attempt_at.is_(None),
                                Job.next_attempt_at <= datetime.now(UTC),
                            ),
                            or_(
                                Job.kind.not_in(alignment_kinds),
                                (Job.kind == "align")
                                & (Job.checkpoint["phase"].as_string() == "preview"),
                            ),
                        )
                        .limit(1)
                    ):
                        raise AlignmentPreempted()
                    job.heartbeat_at = datetime.now(UTC)
                    job.lease_expires_at = datetime.now(UTC) + timedelta(seconds=60)
                    database.commit()

                def record_alignment_progress(values: dict[str, Any]) -> None:
                    renew_alignment_lease()
                    checkpoint.update(values)
                    job.checkpoint = dict(checkpoint)
                    database.commit()

                limits = job.resource_limits or {}
                engine_name = str(checkpoint.get("engine") or ENGINE_NATIVE)
                artifact_dir = (
                    layout.root
                    / "alignment-artifacts"
                    / comparison.id
                    / str(expected_version)
                    / slide.id
                    / engine_name
                    / ENGINE_VERSIONS[engine_name]
                    / settings_digest(engine_name)
                    / f"{reference.sha256}-{slide.sha256}"
                )
                run_options: dict[str, Any] = {
                    "engine_name": engine_name,
                    "engine_settings": applied_settings,
                    "artifact_dir": artifact_dir,
                    "timeout_seconds": min(600, int(limits.get("timeoutSeconds", 600))),
                    "memory_bytes": min(7 * 1024**3, int(limits.get("memoryBytes", 7 * 1024**3))),
                    "heartbeat": renew_alignment_lease,
                    "progress": record_alignment_progress,
                }
                if engine_name == ENGINE_NATIVE:
                    run_options["seed_registration"] = _best_compatible_registration(
                        database, comparison=comparison, slide=slide, reference=reference
                    )

                def run_with_remaining_budget(**options: Any) -> dict[str, Any]:
                    remaining = _alignment_remaining_budget(checkpoint, limits)
                    if remaining <= 0:
                        raise AlignmentRejected("registration exceeded the total pair timeout")
                    options["timeout_seconds"] = remaining
                    run_started = time.monotonic()
                    try:
                        return _run_alignment_bounded(
                            reference_derivative,
                            moving_derivative,
                            reference_full_size,
                            moving_full_size,
                            **options,
                        )
                    finally:
                        checkpoint["computeSecondsUsed"] = float(
                            checkpoint.get("computeSecondsUsed", 0)
                        ) + (time.monotonic() - run_started)
                        job.checkpoint = dict(checkpoint)

                try:
                    result_json = run_with_remaining_budget(**run_options)
                except AlignmentRejected as error:
                    if engine_name != ENGINE_VALIS or "memory ceiling" not in str(error):
                        raise
                    checkpoint.update(
                        {
                            "progress": 36,
                            "stage": "valis-memory-fallback",
                            "fallbackReason": str(error),
                        }
                    )
                    job.checkpoint = dict(checkpoint)
                    database.commit()
                    applied_settings = {**applied_settings, "maxImageDimension": 768}
                    result_json = run_with_remaining_budget(
                        **{**run_options, "engine_settings": applied_settings},
                    )
                    result_json["evidence"] = {
                        **(result_json.get("evidence") or {}),
                        "adaptiveMemoryFallback": True,
                        "fallbackReason": str(error),
                    }
                effective_settings = result_json.get("engineSettings", applied_settings)
                if not isinstance(effective_settings, dict):
                    raise AlignmentRejected("effective engine settings must be an object")
                try:
                    effective_settings = json.loads(json.dumps(effective_settings, allow_nan=False))
                except (TypeError, ValueError) as error:
                    raise AlignmentRejected("invalid effective engine settings") from error
                for side, true_size in (
                    ("reference", reference_full_size),
                    ("moving", moving_full_size),
                ):
                    if f"{side}Geometry" in effective_settings:
                        validate_sampling_geometry(
                            effective_settings[f"{side}Geometry"], source_size=true_size
                        )
                applied_settings = effective_settings
                result_json.update(
                    engineSettings=effective_settings,
                    settingsDigest=settings_digest(engine_name, effective_settings),
                    requestedSettings=requested_settings,
                    requestedSettingsDigest=settings_digest(engine_name, requested_settings),
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
                database.refresh(slide)
                database.refresh(reference)
                if (
                    comparison.version != expected_version
                    or job.cancellation_requested_at is not None
                    or comparison.source_versions.get(slide.id) != slide.sha256
                    or comparison.source_versions.get(reference.id) != reference.sha256
                    or expected_sources != (reference.sha256, slide.sha256)
                    or expected_metadata_frames
                    != (
                        metadata_frame_digest(reference.slide_metadata or {}),
                        metadata_frame_digest(slide.slide_metadata or {}),
                    )
                ):
                    job.status = "cancelled"
                    job.failure_code = "ALIGNMENT_STALE"
                    job.error = "Stale registration output discarded"
                    job.heartbeat_at = None
                    job.lease_expires_at = None
                    _finish_superseded_alignment(database, comparison, job)
                    database.commit()
                    return True
                if job.kind == "align_benchmark":
                    artifact_path = result_json.pop("artifactPath", None)
                    artifact_sha256 = result_json.pop("artifactSha256", None)
                    runtime_seconds = result_json.pop("runtimeSeconds", None)
                    peak_memory_bytes = result_json.pop("peakMemoryBytes", None)
                    evidence = dict(result_json.get("evidence") or {})
                    evidence.update(
                        {
                            "runtimeSeconds": runtime_seconds,
                            "peakMemoryBytes": peak_memory_bytes,
                            "engineBuildVersion": ENGINE_VERSIONS[engine_name],
                        }
                    )
                    for metric in (
                        "memoryMeasurementScope",
                        "peakCommittedMemoryBytes",
                        "committedMemoryLimitBytes",
                        "processContainment",
                        "kernelReportedPeakJobMemoryBytes",
                        "committedMemoryMeasurementScope",
                        "currentPrivateCommittedMemoryBytes",
                        "sampledPeakPrivateCommittedMemoryBytes",
                        "peakContainedProcesses",
                    ):
                        if metric in result_json:
                            evidence[metric] = result_json[metric]
                    database.add(
                        ComparisonRegistrationCandidate(
                            comparison_set_id=comparison.id,
                            slide_id=slide.id,
                            set_version=comparison.version,
                            anchor_slide_id=reference.id,
                            source_version=slide.sha256,
                            anchor_version=reference.sha256,
                            engine=engine_name,
                            engine_version=ENGINE_VERSIONS[engine_name],
                            settings_digest=settings_digest(engine_name, applied_settings),
                            status=str(result_json.get("status", "rejected")),
                            validation_state=_candidate_validation_state(
                                result_json, engine_name, slide.sha256, reference.sha256
                            ),
                            registration={
                                **result_json,
                                "sourceFrameVersion": metadata_frame_digest(
                                    slide.slide_metadata or {}
                                ),
                                "anchorFrameVersion": metadata_frame_digest(
                                    reference.slide_metadata or {}
                                ),
                                "provenance": "automatic-candidate",
                                "anchorSlideId": reference.id,
                                "coordinateReferenceId": reference.id,
                            },
                            evidence=evidence,
                            artifact_path=artifact_path,
                            artifact_sha256=artifact_sha256,
                        )
                    )
                    job.checkpoint = {**checkpoint, "progress": 100, "stage": "complete"}
                    job.output_manifest = {
                        "comparisonSetId": comparison.id,
                        "memberId": slide.id,
                        "engine": engine_name,
                        "candidate": True,
                    }
                    job.status = "succeeded"
                    job.heartbeat_at = None
                    job.lease_expires_at = None
                    database.commit()
                    return True
                registrations = dict(comparison.registrations)
                replacement = {
                    **result_json,
                    "provenance": "automatic",
                    "sourceVersion": slide.sha256,
                    "referenceVersion": primary_reference.sha256,
                    "anchorSlideId": reference.id,
                    "anchorVersion": reference.sha256,
                    "sourceFrameVersion": metadata_frame_digest(slide.slide_metadata or {}),
                    "anchorFrameVersion": metadata_frame_digest(reference.slide_metadata or {}),
                    "coordinateReferenceId": coordinate_reference_id,
                    "engine": engine_name,
                    "engineVersion": ENGINE_VERSIONS[engine_name],
                    "engineSettings": applied_settings,
                    "settingsDigest": settings_digest(engine_name, applied_settings),
                    "evidence": {
                        **result_json.get("evidence", {}),
                        "validationPolicy": VALIDATION_POLICY,
                    },
                }
                preserved = None
                if checkpoint.get("preserveExisting"):
                    existing = _best_compatible_registration(
                        database,
                        comparison=comparison,
                        slide=slide,
                        reference=reference,
                    )
                    if _registration_quality(existing) > _registration_quality(replacement):
                        preserved = _with_overview_fallback(
                            cast(dict[str, Any], existing), replacement
                        )
                    elif existing:
                        replacement = _with_overview_fallback(replacement, existing)
                registrations[slide.id] = preserved or replacement
                comparison.registrations = registrations
                if preserved is None or preserved != existing:
                    database.add(
                        ComparisonRegistrationRevision(
                            comparison_set_id=comparison.id,
                            slide_id=slide.id,
                            set_version=comparison.version,
                            source_version=slide.sha256,
                            anchor_slide_id=reference.id,
                            algorithm_version=ENGINE_VERSIONS[engine_name],
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
                    "confidence": float(registrations[slide.id].get("confidence") or confidence),
                    "inlierCount": int(
                        registrations[slide.id].get("inlierCount") or result_json["inlierCount"]
                    ),
                    "preservedExisting": preserved is not None,
                }
                job.status = "succeeded"
            except AlignmentContainmentLost as error:
                # A durable quarantine blocks all worker roles and replicas.
                # Stale-running-job recovery must not release unknown children.
                database.refresh(job)
                job.status = "checkpointing"
                job.failure_code = "ALIGNMENT_CONTAINMENT_LOST"
                job.error = str(error)
                quarantined_slide_id = job.slide_id
                job.slide = None  # A slide purge must not cascade away quarantine.
                job.checkpoint = {
                    **checkpoint,
                    "stage": "containment-quarantine",
                    "quarantinedSlideId": quarantined_slide_id,
                    "resourceMetrics": error.resource_metrics,
                }
                job.heartbeat_at = None
                job.lease_expires_at = None
                database.commit()
                raise
            except AlignmentPreempted:
                job.status = "queued"
                job.checkpoint = {
                    **checkpoint,
                    "stage": "waiting-for-foreground",
                    "preemptions": int(checkpoint.get("preemptions", 0)) + 1,
                }
            except (AlignmentRejected, FileNotFoundError, OSError) as error:
                database.refresh(comparison)
                database.refresh(job)
                if comparison.version != expected_version or job.cancellation_requested_at:
                    job.status = "cancelled"
                    job.failure_code = "ALIGNMENT_STALE"
                    job.error = "Stale registration output discarded after comparison change"
                    job.heartbeat_at = None
                    job.lease_expires_at = None
                    _finish_superseded_alignment(database, comparison, job)
                    database.commit()
                    return True
                if job.kind == "align_benchmark":
                    engine_name = str(checkpoint.get("engine") or ENGINE_NATIVE)
                    database.add(
                        ComparisonRegistrationCandidate(
                            comparison_set_id=comparison.id,
                            slide_id=slide.id,
                            set_version=comparison.version,
                            anchor_slide_id=str(checkpoint.get("anchorSlideId")),
                            source_version=slide.sha256,
                            anchor_version=(reference.sha256 if reference else None),
                            engine=engine_name,
                            engine_version=ENGINE_VERSIONS[engine_name],
                            settings_digest=settings_digest(engine_name, applied_settings),
                            status="unavailable"
                            if isinstance(error, EngineResourceUnavailable)
                            else "rejected",
                            validation_state="rejected",
                            registration={"engineSettings": applied_settings},
                            evidence={},
                            failure_reason=str(error),
                        )
                    )
                    job.status = "failed_terminal"
                    job.failure_code = (
                        "ALIGNMENT_ENGINE_UNAVAILABLE"
                        if isinstance(error, EngineResourceUnavailable)
                        else "ALIGNMENT_ENGINE_REJECTED"
                    )
                    job.error = str(error)
                    job.heartbeat_at = None
                    job.lease_expires_at = None
                    database.commit()
                    return True
                registrations = dict(comparison.registrations)
                existing = _best_compatible_registration(
                    database, comparison=comparison, slide=slide, reference=reference
                )
                if (
                    checkpoint.get("preserveExisting")
                    or isinstance(error, EngineResourceUnavailable)
                ) and existing:
                    registrations[slide.id] = existing
                else:
                    registrations[slide.id] = {
                        "status": "needs_refinement"
                        if isinstance(error, EngineResourceUnavailable)
                        else "rejected",
                        "provenance": "automatic",
                        "reason": str(error),
                    }
                comparison.registrations = registrations
                comparison.status = (
                    "ready"
                    if len(registrations) == len(comparison.member_slide_ids) - 1
                    and all(value.get("status") == "ready" for value in registrations.values())
                    else "partial"
                )
                job.status = "failed_terminal"
                job.failure_code = (
                    "ALIGNMENT_ENGINE_UNAVAILABLE"
                    if isinstance(error, EngineResourceUnavailable)
                    else "ALIGNMENT_REJECTED"
                )
                job.error = str(error)
            if job.kind == "align" and comparison.version == expected_version:
                if (
                    checkpoint.get("phase") == "refinement"
                    and job.status in {"succeeded", "failed_terminal"}
                    and comparison.registrations.get(slide.id, {}).get("status") != "ready"
                    and Settings().alignment_valis_enabled
                    and _alignment_remaining_budget(checkpoint, job.resource_limits or {}) > 0
                ):
                    fallback_key = hashlib.sha256(f"{job.id}:valis".encode()).hexdigest()
                    if not database.scalar(
                        select(Job.id).where(Job.idempotency_key_hash == fallback_key)
                    ):
                        database.add(
                            Job(
                                slide_id=slide.id,
                                kind="align",
                                resource_class="isolated",
                                idempotency_key_hash=fallback_key,
                                checkpoint={
                                    **checkpoint,
                                    "phase": "fallback",
                                    "engine": ENGINE_VALIS,
                                    "stage": "queued-valis-refinement",
                                    "progress": 0,
                                    "preserveExisting": True,
                                },
                                resource_limits={
                                    "cpuThreads": 1,
                                    "memoryBytes": 7 * 1024**3,
                                    "timeoutSeconds": 600,
                                },
                            )
                        )
                        database.flush()
                pending = database.scalar(
                    select(Job.id)
                    .where(
                        Job.id != job.id,
                        Job.kind == "align",
                        Job.status.in_({"queued", "retry_wait", "leased", "running"}),
                        Job.checkpoint["comparisonSetId"].as_string() == comparison.id,
                        Job.checkpoint["setVersion"].as_integer() == comparison.version,
                    )
                    .limit(1)
                )
                if pending or job.status == "queued":
                    comparison.status = "running"
            job.heartbeat_at = None
            job.lease_expires_at = None
            database.commit()
            return True
        if job.kind == "delete":
            remove_slide(layout, slide.id, slide.public_id)
            remove_slide_from_stacks(database, slide.id)
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
            activate_ready_slide_memberships(database, slide)
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
        layout.individual_delivery_for(public_id),
    }:
        if target.exists():
            shutil.rmtree(target)


def run_worker_loop(scheduler: WorkerScheduler, shutdown: threading.Event) -> None:
    while not shutdown.is_set():
        delay = scheduler.run_due()
        if delay > 0:
            shutdown.wait(delay)


def main() -> None:
    global _worker_startup_seconds
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    alignment_role = settings.service_role == "alignment"
    if not alignment_role:
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
            include_kinds=(frozenset({"align", "align_benchmark"}) if alignment_role else None),
            exclude_kinds=(
                None
                if alignment_role or settings.service_role == "all"
                else frozenset({"align", "align_benchmark"})
            ),
            exclusive_alignment=(
                True if alignment_role else (None if settings.service_role == "all" else False)
            ),
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
    # Linux production measurement includes interpreter and module imports.
    # Unavailable on other hosts rather than reported as zero startup cost.
    if not sys.platform.startswith("win"):
        with suppress(OSError, ValueError, IndexError):
            fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
            start_seconds = int(fields[19]) / os.sysconf("SC_CLK_TCK")
            _worker_startup_seconds = (
                float(Path("/proc/uptime").read_text().split()[0]) - start_seconds
            )
    try:
        run_worker_loop(scheduler, shutdown)
    finally:
        heartbeat.stop()
