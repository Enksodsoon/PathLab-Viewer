from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from test_prepared_ingest import _package
from wsi_viewer.desktop_finalizer import PreparedIngestFinalizer, desktop_package_path
from wsi_viewer.domain import SlideState
from wsi_viewer.models import (
    AuditEvent,
    Base,
    DesktopCredential,
    DesktopIngest,
    DesktopSyncEvent,
    Slide,
    User,
)
from wsi_viewer.storage import StorageLayout
from wsi_viewer.time_support import utc_now


@pytest.mark.parametrize("deny_cleanup", [True, False])
def test_package_cleanup_cannot_undo_committed_install(
    tmp_path: Path, monkeypatch, caplog, deny_cleanup: bool
) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'finalizer.sqlite3'}")
    Base.metadata.create_all(engine)
    storage = StorageLayout(tmp_path / "data")
    package = desktop_package_path(storage, "synthetic-ingest")
    package.parent.mkdir(parents=True)
    package_sha, manifest_sha = _package(package)
    length = package.stat().st_size
    with Session(engine) as database:
        user = User(username="synthetic-owner", password_hash="unused-synthetic-hash")
        database.add(user)
        database.flush()
        credential = DesktopCredential(
            id="synthetic-credential",
            user_id=user.id,
            device_name="Synthetic device",
            scopes=[],
            expires_at=utc_now() + timedelta(days=1),
        )
        database.add(credential)
        database.flush()
        database.add(
            DesktopIngest(
                id="synthetic-ingest",
                credential_id=credential.id,
                display_name="Synthetic slide",
                artifact_revision_id="artifact-1",
                package_length=length,
                received_bytes=length,
                package_sha256=package_sha,
                manifest_sha256=manifest_sha,
                status="finalizing",
            )
        )
        database.commit()

    unlink = Path.unlink

    def guarded_unlink(path: Path, *args, **kwargs):
        if deny_cleanup and path == package:
            # The failure is injected only after SQLite committed the ready slide.
            with Session(engine) as database:
                ingest = database.get(DesktopIngest, "synthetic-ingest")
                assert ingest is not None and ingest.status == "ready_private"
                assert database.get(Slide, ingest.slide_id).state == SlideState.READY_PRIVATE
            raise PermissionError("SYNTHETIC_ARCHIVE_LOCKED")
        return unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", guarded_unlink)

    def database_dependency() -> Iterator[Session]:
        with Session(engine) as database:
            yield database

    finalizer = PreparedIngestFinalizer(database_dependency, storage)
    finalizer._finalize("synthetic-ingest")
    for _ in range(2):
        finalizer._finalize("synthetic-ingest")
    with Session(engine) as database:
        ingest = database.get(DesktopIngest, "synthetic-ingest")
        assert ingest is not None and ingest.status == "ready_private"
        assert ingest.error_code is None
        slide = database.get(Slide, ingest.slide_id)
        assert slide is not None and slide.state == SlideState.READY_PRIVATE
        installed = storage.for_slide(slide.id).private_derivative
        assert (installed / "slide.dzi").is_file()
        assert (installed / "slide_files" / "0" / "0_0.jpg").is_file()
        assert (installed / "thumbnail.jpg").is_file()
        assert database.scalar(select(func.count()).select_from(Slide)) == 1
        assert database.scalar(select(func.count()).select_from(AuditEvent)) == 1
        assert database.scalar(select(func.count()).select_from(DesktopSyncEvent)) == 1
    assert package.exists() is deny_cleanup
    if deny_cleanup:
        assert "DESKTOP_PREPARED_PACKAGE_CLEANUP_FAILED" in caplog.text
        assert "synthetic-ingest" in caplog.text
    else:
        assert "DESKTOP_PREPARED_PACKAGE_CLEANUP_FAILED" not in caplog.text
    engine.dispose()
