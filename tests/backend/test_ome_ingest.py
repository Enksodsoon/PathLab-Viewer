from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.models import DesktopCredential, DesktopIngest, Slide, User
from wsi_viewer.ome_ingest import (
    OmeIngestError,
    _validate_profile,
    desktop_ome_path,
    desktop_quarantine_path,
    install_ome_ingest,
)
from wsi_viewer.ome_tile_index import OmeLevel, OmeTileIndex
from wsi_viewer.storage import StorageLayout


def test_hash_mismatch_fails_closed_into_private_quarantine(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'ome-ingest.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    storage = StorageLayout(settings.data_root)
    with factory() as database:
        user = User(username="admin", password_hash="hash")
        database.add(user)
        database.flush()
        credential = DesktopCredential(
            id="credential",
            user_id=user.id,
            device_name="Forge",
            scopes=["desktop:ingest"],
            expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=1),
        )
        database.add(credential)
        ingest = DesktopIngest(
            credential_id=credential.id,
            display_name="Rejected",
            artifact_revision_id="revision",
            package_length=10,
            package_sha256="f" * 64,
            manifest_sha256="f" * 64,
            ingest_mode="ome_dynamic_v1",
            ome_profile="ome-dynamic-v1",
            ome_width=1,
            ome_height=1,
            ome_downsample=1.5,
            received_bytes=10,
            status="installing",
        )
        database.add(ingest)
        database.commit()
        ingest_id = ingest.id
        source = desktop_ome_path(storage, ingest_id)
        source.parent.mkdir(parents=True)
        source.write_bytes(b"not-an-ome")

        install_ome_ingest(ingest, source, database, storage)

        database.expire_all()
        failed = database.get(DesktopIngest, ingest_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_code == "OME source hash does not match"
        assert database.scalar(select(func.count()).select_from(Slide)) == 0
    assert desktop_quarantine_path(storage, ingest_id).read_bytes() == b"not-an-ome"
    assert not source.exists()


def test_profile_accepts_regular_factor_four_for_seam_aligned_virtual_levels() -> None:
    levels = tuple(
        OmeLevel(width, height, 1, 1, ())
        for width, height in ((4096, 3072), (1024, 768), (256, 192))
    )
    index = OmeTileIndex(
        4096,
        3072,
        512,
        512,
        "jpeg",
        levels,
        (1, 4, 16),
        True,
        1,
        1,
        "a" * 64,
    )
    ingest = SimpleNamespace(
        ome_profile="ome-dynamic-v1", ome_width=4096, ome_height=3072
    )

    _validate_profile(ingest, index)  # type: ignore[arg-type]

    irregular = OmeTileIndex(
        4096,
        3072,
        512,
        512,
        "jpeg",
        levels,
        (1, 4, 8),
        True,
        1,
        1,
        "a" * 64,
    )
    with pytest.raises(OmeIngestError, match="FACTOR_UNSUPPORTED"):
        _validate_profile(ingest, irregular)  # type: ignore[arg-type]
