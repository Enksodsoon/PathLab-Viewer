import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_prepared_ingest import _package
from wsi_viewer import desktop_finalizer
from wsi_viewer.desktop_finalizer import PreparedIngestFinalizer, desktop_package_path
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


def fixture(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'finalizer.sqlite'}", connect_args={"timeout": 0.05}
    )
    Base.metadata.create_all(engine)
    storage = StorageLayout(tmp_path / "data")
    package = desktop_package_path(storage, "ingest")
    package.parent.mkdir(parents=True)
    sha, manifest_sha = _package(package)
    with Session(engine) as database:
        user = User(id="owner", username="synthetic", password_hash="unused")
        database.add(user)
        database.flush()
        database.add(
            DesktopCredential(
                id="credential",
                user_id=user.id,
                device_name="Synthetic",
                scopes=[],
                expires_at=utc_now() + timedelta(days=1),
            )
        )
        database.flush()
        database.add(
            DesktopIngest(
                id="ingest",
                credential_id="credential",
                display_name="Synthetic",
                artifact_revision_id="artifact-1",
                package_length=package.stat().st_size,
                received_bytes=package.stat().st_size,
                package_sha256=sha,
                manifest_sha256=manifest_sha,
                status="finalizing",
            )
        )
        database.commit()
    return engine, storage, package


@pytest.mark.parametrize("committed", [False, True])
def test_ready_commit_fault_reconciles_durable_state_before_cleanup(
    tmp_path: Path, caplog, committed: bool
):
    engine, storage, package = fixture(tmp_path)

    class FaultSession(Session):
        def commit(self):
            ready = any(
                isinstance(item, DesktopIngest) and item.status == "ready_private"
                for item in self.identity_map.values()
            )
            if ready:
                if committed:
                    super().commit()
                raise OperationalError(
                    "COMMIT", {}, RuntimeError("synthetic commit acknowledgment failure")
                )
            return super().commit()

    def dependency() -> Iterator[Session]:
        with FaultSession(engine, expire_on_commit=False) as database:
            yield database

    finalizer = PreparedIngestFinalizer(dependency, storage)
    finalizer._finalize("ingest")
    finalizer._finalize("ingest")
    with Session(engine) as database:
        ingest = database.get(DesktopIngest, "ingest")
        assert ingest.status == ("ready_private" if committed else "failed")
        assert database.scalar(select(func.count()).select_from(Slide)) == int(committed)
        assert database.scalar(select(func.count()).select_from(AuditEvent)) == int(committed)
        assert database.scalar(select(func.count()).select_from(DesktopSyncEvent)) == int(committed)
        assert len(list(storage.root.rglob("slide.dzi"))) == int(committed)
        if committed:
            assert "DESKTOP_PREPARED_COMMIT_ACK_FAILED" in caplog.text
    assert package.exists()
    if not committed:
        with Session(engine) as database:
            ingest = database.get(DesktopIngest, "ingest")
            assert ingest.error_code == "PREPARED_INGEST_FINALIZER_FAILED"
            ingest.status = "finalizing"
            database.commit()

        def retry_dependency() -> Iterator[Session]:
            with Session(engine) as database:
                yield database

        retry = PreparedIngestFinalizer(retry_dependency, storage)
        retry._finalize("ingest")
        retry._finalize("ingest")
        with Session(engine) as database:
            assert database.get(DesktopIngest, "ingest").status == "ready_private"
            assert database.scalar(select(func.count()).select_from(Slide)) == 1
            assert database.scalar(select(func.count()).select_from(AuditEvent)) == 1
            assert database.scalar(select(func.count()).select_from(DesktopSyncEvent)) == 1
        assert not package.exists()
    engine.dispose()


def test_valid_package_extraction_does_not_hold_sqlite_writer(tmp_path: Path, monkeypatch):
    engine, storage, _package_path = fixture(tmp_path)
    entered, release = threading.Event(), threading.Event()
    original = desktop_finalizer.install_prepared_package

    def paused(*args, **kwargs):
        entered.set()
        assert release.wait(5), "test did not release valid-package extraction"
        return original(*args, **kwargs)

    monkeypatch.setattr(desktop_finalizer, "install_prepared_package", paused)

    def dependency() -> Iterator[Session]:
        with Session(engine) as database:
            yield database

    finalizer = PreparedIngestFinalizer(dependency, storage)
    with ThreadPoolExecutor(1) as pool:
        install = pool.submit(finalizer._finalize, "ingest")
        try:
            assert entered.wait(3)
            with Session(engine) as database:
                database.add(User(username="competing-writer", password_hash="unused"))
                database.commit()
        finally:
            release.set()
            install.result(timeout=5)
    with Session(engine) as database:
        assert database.get(DesktopIngest, "ingest").status == "ready_private"
        assert database.scalar(select(User.id).where(User.username == "competing-writer"))
    engine.dispose()
