import hashlib
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
import tifffile
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from test_desktop_finalizer_transactions import fixture
from wsi_viewer import desktop_finalizer
from wsi_viewer.models import DesktopIngest
from wsi_viewer.ome_ingest import desktop_ome_path, desktop_quarantine_path


@pytest.mark.parametrize("denied", ["rename", "mkdir"])
def test_outer_ome_installer_failure_preserves_raw_source_on_quarantine_denial(
    tmp_path: Path, monkeypatch, caplog, denied: str,
):
    engine, storage, _ = fixture(tmp_path)
    source = desktop_ome_path(storage, "ingest")
    source.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(
        source, np.zeros((512, 512, 3), dtype=np.uint8), ome=True,
        photometric="rgb", tile=(512, 512), compression="jpeg",
        compressionargs={"level": 75}, metadata={"axes": "YXS"},
    )
    original = source.read_bytes()
    with Session(engine) as database:
        ingest = database.get(DesktopIngest, "ingest")
        ingest.ingest_mode = "ome_dynamic_v1"
        ingest.package_length = ingest.received_bytes = len(original)
        database.commit()

    def dependency() -> Iterator[Session]:
        with Session(engine) as database:
            yield database

    def unexpected_installer(*args):
        raise RuntimeError("synthetic unexpected native installer failure")

    monkeypatch.setattr(desktop_finalizer, "install_ome_ingest", unexpected_installer)
    quarantine = desktop_quarantine_path(storage, "ingest")
    if denied == "rename":
        rename = desktop_finalizer.os.replace

        def denied_rename(candidate, destination):
            if Path(destination) == quarantine:
                raise PermissionError("synthetic quarantine rename denial")
            return rename(candidate, destination)

        monkeypatch.setattr(desktop_finalizer.os, "replace", denied_rename)
    else:
        mkdir = Path.mkdir

        def denied_mkdir(path, *args, **kwargs):
            if path == quarantine.parent:
                raise PermissionError("synthetic quarantine mkdir denial")
            return mkdir(path, *args, **kwargs)

        monkeypatch.setattr(Path, "mkdir", denied_mkdir)
    finalizer = desktop_finalizer.PreparedIngestFinalizer(dependency, storage)
    finalizer.enqueue("ingest")
    finalizer.pending.put(None)
    finalizer._run()
    assert source.is_file()
    assert source.read_bytes() == original
    assert not quarantine.exists()
    with Session(engine) as database:
        ingest = database.get(DesktopIngest, "ingest")
        assert ingest.status == "failed"
        assert ingest.error_code == "PREPARED_INGEST_FINALIZER_FAILED"
    assert "DESKTOP_OME_QUARANTINE_FAILED" in caplog.text
    assert "source retained" in caplog.text


@pytest.mark.parametrize("committed", [False, True])
def test_failure_record_commit_denial_does_not_stop_later_valid_ome_work(
    tmp_path: Path, monkeypatch, caplog, committed: bool,
):
    engine, storage, _ = fixture(tmp_path)
    originals = {}
    with Session(engine) as database:
        for ingest_id in ("ingest", "second"):
            source = desktop_ome_path(storage, ingest_id)
            source.parent.mkdir(parents=True, exist_ok=True)
            tifffile.imwrite(
                source, np.zeros((512, 512, 3), dtype=np.uint8), ome=True,
                photometric="rgb", tile=(512, 512), compression="jpeg",
                compressionargs={"level": 75}, metadata={"axes": "YXS"},
            )
            originals[ingest_id] = source.read_bytes()
            ingest = database.get(DesktopIngest, ingest_id)
            if ingest is None:
                ingest = DesktopIngest(
                    id=ingest_id, credential_id="credential", display_name="Synthetic second",
                    artifact_revision_id="artifact-second", manifest_sha256="f" * 64,
                )
                database.add(ingest)
            ingest.ingest_mode = "ome_dynamic_v1"
            ingest.ome_profile = "ome-dynamic-v1"
            ingest.ome_width = ingest.ome_height = 512
            ingest.ome_downsample = 1.0
            ingest.ome_jpeg_quality = 75
            ingest.status = "finalizing"
            ingest.package_length = ingest.received_bytes = len(originals[ingest_id])
            ingest.package_sha256 = hashlib.sha256(originals[ingest_id]).hexdigest()
        database.commit()

    def dependency() -> Iterator[Session]:
        with Session(engine) as database:
            yield database

    install = desktop_finalizer.install_ome_ingest

    def unexpected_first(ingest, source, database, layout):
        if ingest.id == "ingest":
            raise RuntimeError("synthetic unexpected first native installer failure")
        return install(ingest, source, database, layout)

    monkeypatch.setattr(desktop_finalizer, "install_ome_ingest", unexpected_first)
    commit = Session.commit
    denied = False

    def denied_once(database):
        nonlocal denied
        if not denied and any(
            isinstance(record, DesktopIngest) and record.id == "ingest"
            and record.status == "failed" for record in database.dirty
        ):
            denied = True
            if committed:
                commit(database)
            raise OperationalError("COMMIT", {}, RuntimeError("synthetic failure-record denial"))
        return commit(database)

    monkeypatch.setattr(Session, "commit", denied_once)
    finalizer = desktop_finalizer.PreparedIngestFinalizer(dependency, storage)
    finalizer.enqueue("ingest")
    finalizer.enqueue("second")
    finalizer.pending.put(None)
    finalizer._run()
    assert denied
    assert desktop_ome_path(storage, "ingest").read_bytes() == originals["ingest"]
    with Session(engine) as database:
        first = database.get(DesktopIngest, "ingest")
        second = database.get(DesktopIngest, "second")
        assert first.status == ("failed" if committed else "installing")
        assert first.slide_id is None
        assert first.error_code == ("PREPARED_INGEST_FINALIZER_FAILED" if committed else None)
        assert second.status == "ready_private"
        assert storage.for_slide(second.slide_id).original.read_bytes() == originals["second"]
    assert "DESKTOP_INGEST_FAILURE_RECORD_FAILED" in caplog.text

    if committed:
        # A durable failed mark retains its source without an automatic retry.
        return

    # A later startup recovery resumes the original upload after the one-shot
    # database/installer faults clear, without re-upload or a duplicate slide.
    monkeypatch.setattr(desktop_finalizer, "install_ome_ingest", install)
    finalizer._recover()
    finalizer.pending.put(None)
    finalizer._run()
    with Session(engine) as database:
        first = database.get(DesktopIngest, "ingest")
        second = database.get(DesktopIngest, "second")
        assert first.status == second.status == "ready_private"
        assert first.slide_id != second.slide_id
        assert storage.for_slide(first.slide_id).original.read_bytes() == originals["ingest"]
