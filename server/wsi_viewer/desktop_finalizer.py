import os
import queue
import shutil
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session as OrmSession

from .desktop_sync import record_sync_event, revision_for
from .domain import SlideState
from .models import AuditEvent, DesktopCredential, DesktopIngest, Slide
from .ome_ingest import (
    desktop_ome_path,
    desktop_quarantine_path,
    install_ome_ingest,
)
from .prepared_ingest import PreparedIngestError, install_prepared_package
from .storage import StorageLayout


def desktop_package_path(storage: StorageLayout, ingest_id: str) -> Path:
    return storage.root / "desktop-ingest" / f"{ingest_id}.plslide.partial"


def desktop_upload_path(storage: StorageLayout, ingest: DesktopIngest) -> Path:
    if ingest.ingest_mode == "ome_dynamic_v1":
        return desktop_ome_path(storage, ingest.id)
    return desktop_package_path(storage, ingest.id)


class PreparedIngestFinalizer:
    def __init__(
        self,
        database_dependency: Callable[[], Iterator[OrmSession]],
        storage: StorageLayout,
    ) -> None:
        self.database_dependency = database_dependency
        self.storage = storage
        self.pending: queue.Queue[str | None] = queue.Queue()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread is not None:
            return
        self.thread = threading.Thread(
            target=self._run,
            name="pathlab-prepared-ingest-finalizer",
            daemon=True,
        )
        self.thread.start()
        self._recover()

    def close(self) -> None:
        if self.thread is None:
            return
        self.pending.put(None)
        self.thread.join(timeout=10)
        self.thread = None

    def enqueue(self, ingest_id: str) -> None:
        self.pending.put(ingest_id)

    def _recover(self) -> None:
        with self._database() as database:
            database.execute(
                update(DesktopIngest)
                .where(DesktopIngest.status == "installing")
                .values(status="finalizing")
            )
            database.commit()
            recovering = list(
                database.scalars(
                    select(DesktopIngest.id).where(DesktopIngest.status == "finalizing")
                )
            )
            for ingest in database.scalars(
                select(DesktopIngest).where(
                    DesktopIngest.status == "failed",
                    DesktopIngest.updated_at
                    < datetime.now(UTC).replace(tzinfo=None)
                    - timedelta(hours=_failed_package_ttl_hours()),
                )
            ):
                desktop_upload_path(self.storage, ingest).unlink(missing_ok=True)
                desktop_quarantine_path(self.storage, ingest.id).unlink(missing_ok=True)
        for ingest_id in recovering:
            self.enqueue(ingest_id)

    def _run(self) -> None:
        while True:
            ingest_id = self.pending.get()
            if ingest_id is None:
                return
            try:
                self._finalize(ingest_id)
            except Exception:
                self._mark_failed(ingest_id, "PREPARED_INGEST_FINALIZER_FAILED")

    def _finalize(self, ingest_id: str) -> None:
        with self._database() as database:
            claimed = database.scalar(
                update(DesktopIngest)
                .where(
                    DesktopIngest.id == ingest_id,
                    DesktopIngest.status == "finalizing",
                )
                .values(status="installing")
                .returning(DesktopIngest.id)
            )
            database.commit()
            if claimed is None:
                return
            ingest = database.get(DesktopIngest, ingest_id)
            if ingest is None:
                return
            package = desktop_upload_path(self.storage, ingest)
            if (
                ingest.received_bytes != ingest.package_length
                or not package.is_file()
                or package.stat().st_size != ingest.package_length
            ):
                ingest.status = "failed"
                ingest.error_code = "PREPARED_PACKAGE_INCOMPLETE"
                database.commit()
                return
            if ingest.ingest_mode == "ome_dynamic_v1":
                install_ome_ingest(ingest, package, database, self.storage)
            else:
                _install(ingest, package, database, self.storage)

    def _mark_failed(self, ingest_id: str, code: str) -> None:
        with self._database() as database:
            ingest = database.get(DesktopIngest, ingest_id)
            if ingest is not None and ingest.status in {"finalizing", "installing"}:
                if ingest.ingest_mode == "ome_dynamic_v1":
                    source = desktop_upload_path(self.storage, ingest)
                    if source.exists():
                        quarantine = desktop_quarantine_path(self.storage, ingest.id)
                        quarantine.parent.mkdir(parents=True, exist_ok=True)
                        try:
                            os.replace(source, quarantine)
                        except OSError:
                            source.unlink(missing_ok=True)
                ingest.status = "failed"
                ingest.error_code = code
                database.commit()

    def _database(self) -> "_DatabaseContext":
        return _DatabaseContext(self.database_dependency)


class _DatabaseContext:
    def __init__(
        self, database_dependency: Callable[[], Iterator[OrmSession]]
    ) -> None:
        self.iterator = database_dependency()
        self.database: OrmSession | None = None

    def __enter__(self) -> OrmSession:
        self.database = next(self.iterator)
        return self.database

    def __exit__(self, *_: object) -> None:
        close = getattr(self.iterator, "close", None)
        if close is not None:
            close()


def _install(
    ingest: DesktopIngest,
    package: Path,
    database: OrmSession,
    storage: StorageLayout,
) -> None:
    slide = Slide(
        display_name=ingest.display_name,
        original_filename=f"{ingest.display_name}.plslide",
        source_bytes=ingest.package_length,
        reserved_bytes=0,
        state=SlideState.READY_PRIVATE,
        privacy_status="private",
    )
    database.add(slide)
    database.flush()
    destination = storage.for_slide(slide.id).private_derivative
    try:
        result = install_prepared_package(
            package,
            destination,
            expected_package_sha256=ingest.package_sha256,
            expected_artifact_revision_id=ingest.artifact_revision_id,
            expected_manifest_sha256=ingest.manifest_sha256,
        )
        provenance = result.manifest["provenance"]
        slide_info = result.manifest["slide"]
        if (
            ingest.derivative_bytes is not None
            and ingest.derivative_bytes != result.measurement.derivative_bytes
        ) or (
            ingest.derivative_file_count is not None
            and ingest.derivative_file_count != result.measurement.file_count
        ):
            raise PreparedIngestError("DECLARED_DERIVATIVE_MISMATCH")
        slide.sha256 = ingest.package_sha256
        slide.derivative_bytes = result.measurement.derivative_bytes
        slide.derivative_file_count = result.measurement.file_count
        slide.thumbnail_filename = "thumbnail.jpg"
        slide.slide_metadata = {
            "width": slide_info["width"],
            "height": slide_info["height"],
            "physicalSizeX": provenance["calibration"]["pixelSizeX"],
            "physicalSizeY": provenance["calibration"]["pixelSizeY"],
            "physicalSizeUnit": provenance["calibration"]["unit"],
            "artifactRevisionId": provenance["artifactRevisionId"],
            "manifestSha256": result.manifest_sha256,
            "sourceFingerprint": provenance["sourceFingerprint"],
            "coordinateTransform": provenance["coordinateTransform"],
            "encoding": slide_info.get("encoding"),
        }
        ingest.slide_id = slide.id
        ingest.status = "ready_private"
        ingest.error_code = None
        record_sync_event(database, "slide", slide.id, "upsert", revision_for(slide.updated_at))
        owning_credential = database.get(DesktopCredential, ingest.credential_id)
        if owning_credential is None:
            raise PreparedIngestError("DESKTOP_CREDENTIAL_MISSING")
        database.add(
            AuditEvent(
                actor_user_id=owning_credential.user_id,
                action="desktop_ingest.complete",
                target_id=slide.id,
            )
        )
        database.commit()
        package.unlink(missing_ok=True)
    except (OSError, PreparedIngestError, KeyError, TypeError) as error:
        database.rollback()
        shutil.rmtree(destination, ignore_errors=True)
        failed = database.get(DesktopIngest, ingest.id)
        if failed is not None:
            failed.status = "failed"
            failed.error_code = str(error)[:80] or "PREPARED_INGEST_FAILED"
            database.commit()


def _failed_package_ttl_hours() -> int:
    try:
        value = int(os.getenv("PATHLAB_DESKTOP_FAILED_PACKAGE_TTL_HOURS", "24"))
    except ValueError:
        return 24
    return max(1, min(value, 24 * 30))
