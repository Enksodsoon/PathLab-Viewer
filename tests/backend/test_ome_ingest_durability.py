import hashlib
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import tifffile
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from wsi_viewer import ome_ingest
from wsi_viewer.models import Base, DesktopCredential, DesktopIngest, Slide, User
from wsi_viewer.storage import StorageLayout


@pytest.mark.parametrize("failure", ["rollback", "acknowledgement", "quarantine", "writer"])
def test_ome_commit_failure_preserves_original_bytes(tmp_path: Path, monkeypatch, caplog, failure):
    engine = create_engine(f"sqlite:///{tmp_path / 'ome.sqlite'}", connect_args={"timeout": 0.2})
    Base.metadata.create_all(engine)
    storage = StorageLayout(tmp_path / "data")
    source = ome_ingest.desktop_ome_path(storage, "ingest")
    source.parent.mkdir(parents=True)
    tifffile.imwrite(
        source,
        np.zeros((512, 512, 3), dtype=np.uint8),
        ome=True,
        photometric="rgb",
        tile=(512, 512),
        compression="jpeg",
        compressionargs={"level": 75},
        metadata={"axes": "YXS"},
    )
    original_bytes = source.read_bytes()
    with Session(engine) as database:
        user = User(username="admin", password_hash="hash")
        database.add(user)
        database.flush()
        database.add(
            DesktopCredential(
                id="credential",
                user_id=user.id,
                device_name="Forge",
                scopes=["desktop:ingest"],
                expires_at=datetime.now(UTC) + timedelta(days=1),
            )
        )
        ingest = DesktopIngest(
            id="ingest",
            credential_id="credential",
            display_name="Synthetic",
            artifact_revision_id="revision",
            package_length=len(original_bytes),
            package_sha256=hashlib.sha256(original_bytes).hexdigest(),
            manifest_sha256="f" * 64,
            ingest_mode="ome_dynamic_v1",
            ome_profile="ome-dynamic-v1",
            ome_width=512,
            ome_height=512,
            ome_downsample=1.0,
            ome_jpeg_quality=75,
            received_bytes=len(original_bytes),
            status="installing",
        )
        database.add(ingest)
        database.commit()
        if failure == "writer":
            entered, release = threading.Event(), threading.Event()
            hash_file = ome_ingest._stable_file_sha256

            def paused_hash(path):
                if path.name == "source.ome.tif":
                    entered.set()
                    assert release.wait(5)
                return hash_file(path)

            monkeypatch.setattr(ome_ingest, "_stable_file_sha256", paused_hash)

            def install():
                with Session(engine) as installer:
                    stored = installer.get(DesktopIngest, "ingest")
                    ome_ingest.install_ome_ingest(stored, source, installer, storage)

            with ThreadPoolExecutor(1) as pool:
                installation = pool.submit(install)
                try:
                    assert entered.wait(3)
                    with Session(engine) as competing:
                        competing.add(User(username="competing-writer", password_hash="unused"))
                        competing.commit()
                finally:
                    release.set()
                    installation.result(timeout=5)
            with Session(engine) as verifier:
                persisted = verifier.get(DesktopIngest, "ingest")
                assert persisted.status == "ready_private"
                assert storage.for_slide(persisted.slide_id).original.read_bytes() == original_bytes
                assert verifier.scalar(select(User.id).where(User.username == "competing-writer"))
            engine.dispose()
            return

        commit = database.commit
        failed_once = False

        def failing_commit():
            nonlocal failed_once
            if not failed_once:
                failed_once = True
                if failure == "acknowledgement":
                    commit()
                raise OperationalError("COMMIT", {}, sqlite3.OperationalError("commit failed"))
            commit()

        monkeypatch.setattr(database, "commit", failing_commit)
        if failure == "quarantine":
            replace = ome_ingest.os.replace

            def failed_quarantine_move(candidate, destination):
                if Path(destination) == ome_ingest.desktop_quarantine_path(storage, "ingest"):
                    raise PermissionError("quarantine unavailable")
                replace(candidate, destination)

            monkeypatch.setattr(ome_ingest.os, "replace", failed_quarantine_move)
        raised = None
        try:
            ome_ingest.install_ome_ingest(ingest, source, database, storage)
        except OperationalError as error:
            raised = error
            database.rollback()

    with Session(engine) as verifier:
        persisted = verifier.get(DesktopIngest, "ingest")
        slides = verifier.scalar(select(func.count()).select_from(Slide))
        if failure == "acknowledgement":
            assert slides == 1 and persisted.status == "ready_private"
            paths = storage.for_slide(persisted.slide_id)
            assert paths.original.read_bytes() == original_bytes
            assert paths.ome_index.is_file()
            assert not ome_ingest.desktop_quarantine_path(storage, "ingest").exists()
        else:
            assert slides == 0 and persisted.status == "failed"
            quarantine = ome_ingest.desktop_quarantine_path(storage, "ingest")
            if failure == "rollback":
                assert quarantine.read_bytes() == original_bytes
                assert not list((storage.root / "originals").iterdir())
            else:
                retained = list((storage.root / "originals").glob("*/source.ome.tif"))
                assert len(retained) == 1 and retained[0].read_bytes() == original_bytes
                assert not list((storage.root / "originals").glob("*/tile-index.json"))
                assert "DESKTOP_OME_QUARANTINE_FAILED" in caplog.text
                assert "source retained" in caplog.text
    assert raised is None
    engine.dispose()
