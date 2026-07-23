from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select, text
from wsi_viewer.config import Settings
from wsi_viewer.database import create_schema, session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Job, Slide
from wsi_viewer.storage import (
    InsufficientStorage,
    PublicationError,
    StorageLayout,
    admission_required,
    publish_derivative,
    unpublish_derivative,
)
from wsi_viewer.storage_accounting import (
    reconcile_storage,
    reserve_new_slide,
    reserve_retry,
)


def test_upload_admission_reserves_conversion_and_safety_headroom() -> None:
    gib = 1024**3
    assert admission_required(5 * gib) == 25 * gib


def test_storage_rejects_when_disk_or_app_cap_is_too_small(tmp_path: Path) -> None:
    layout = StorageLayout(tmp_path, cap_bytes=120 * 1024**3)
    with pytest.raises(InsufficientStorage):
        layout.require_admission(source_bytes=5 * 1024**3, free_bytes=24 * 1024**3)
    with pytest.raises(InsufficientStorage):
        layout.require_admission(
            source_bytes=5 * 1024**3,
            free_bytes=100 * 1024**3,
            current_usage=100 * 1024**3,
        )


def test_paths_use_generated_ids_not_original_names(tmp_path: Path) -> None:
    paths = StorageLayout(tmp_path).for_slide("01J123ABC")
    assert paths.original == tmp_path / "originals" / "01J123ABC" / "source.ome.tif"
    assert "patient" not in str(paths.original).lower()


def test_publish_and_unpublish_are_directory_atomic(tmp_path: Path) -> None:
    layout = StorageLayout(tmp_path)
    private = layout.for_slide("slide-1").private_derivative
    (private / "slide_files" / "0").mkdir(parents=True)
    (private / "slide.dzi").write_text("<Image />", encoding="utf-8")
    (private / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"jpeg")
    public = publish_derivative(layout, "slide-1", "public-1")
    assert (public / "slide.dzi").is_file()
    assert (public / "slide.dzi").stat().st_ino == (private / "slide.dzi").stat().st_ino
    assert (public / "slide_files" / "0" / "0_0.jpeg").stat().st_ino == (
        private / "slide_files" / "0" / "0_0.jpeg"
    ).stat().st_ino
    unpublish_derivative(layout, "public-1")
    assert not public.exists()
    assert (private / "slide.dzi").is_file()


def test_public_deletion_preserves_private_hardlinked_files(tmp_path: Path) -> None:
    layout = StorageLayout(tmp_path)
    private = layout.for_slide("slide-1").private_derivative
    (private / "slide_files" / "0").mkdir(parents=True)
    (private / "slide.dzi").write_text("<Image />", encoding="utf-8")
    tile = private / "slide_files" / "0" / "0_0.jpeg"
    tile.write_bytes(b"jpeg")

    publish_derivative(layout, "slide-1", "public-1")
    unpublish_derivative(layout, "public-1")

    assert tile.read_bytes() == b"jpeg"


def test_publication_failure_preserves_prior_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    layout = StorageLayout(tmp_path)
    private = layout.for_slide("slide-1").private_derivative
    (private / "slide_files" / "0").mkdir(parents=True)
    (private / "slide.dzi").write_text("<Image />", encoding="utf-8")
    (private / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"jpeg")
    public = publish_derivative(layout, "slide-1", "public-1")
    descriptor_inode = (public / "slide.dzi").stat().st_ino
    monkeypatch.setattr("wsi_viewer.storage.os.link", Mock(side_effect=OSError("cross-device")))

    with pytest.raises(PublicationError, match="PUBLICATION_LINK_FAILED"):
        publish_derivative(layout, "slide-1", "public-1")

    assert (public / "slide.dzi").stat().st_ino == descriptor_inode


def test_publication_rejects_symlinks(tmp_path: Path) -> None:
    layout = StorageLayout(tmp_path)
    private = layout.for_slide("slide-1").private_derivative
    private.mkdir(parents=True)
    (private / "slide.dzi").write_text("<Image />", encoding="utf-8")
    outside = tmp_path / "outside.jpeg"
    outside.write_bytes(b"private")
    link = private / "linked.jpeg"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")

    with pytest.raises(PublicationError, match="UNSAFE_DERIVATIVE"):
        publish_derivative(layout, "slide-1", "public-1")

    assert not layout.public_for("public-1").exists()


def test_two_concurrent_reservations_cannot_overcommit_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'reservations.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    required = admission_required(1)
    layout = StorageLayout(settings.data_root, cap_bytes=required)
    monkeypatch.setattr(
        "wsi_viewer.storage_accounting.shutil.disk_usage",
        Mock(return_value=SimpleNamespace(free=required * 10)),
    )

    def reserve(index: int) -> bool:
        try:
            reserve_new_slide(
                factory,
                layout,
                display_name=f"Slide {index}",
                original_filename=f"slide-{index}.ome.tif",
                source_bytes=1,
                actor_user_id=None,
            )
        except InsufficientStorage:
            return False
        return True

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve, range(2)))

    assert sorted(outcomes) == [False, True]
    with factory() as database:
        assert database.scalar(select(func.count()).select_from(Slide)) == 1


def test_reservation_checks_disk_without_walking_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'no-walk.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    layout = StorageLayout(settings.data_root, cap_bytes=100 * 1024**3)
    disk_usage = Mock(return_value=SimpleNamespace(free=100 * 1024**3))
    monkeypatch.setattr("wsi_viewer.storage_accounting.shutil.disk_usage", disk_usage)
    monkeypatch.setattr(StorageLayout, "usage", Mock(side_effect=AssertionError("walk called")))

    slide = reserve_new_slide(
        session_factory(settings),
        layout,
        display_name="Test",
        original_filename="test.ome.tif",
        source_bytes=1,
        actor_user_id=None,
    )

    assert slide.reserved_bytes == admission_required(1)
    disk_usage.assert_called_once_with(layout.root)


def test_failed_retry_rejection_leaves_state_and_jobs_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'retry-reject.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    with factory() as database:
        slide = Slide(
            display_name="Failed",
            original_filename="failed.ome.tif",
            source_bytes=1,
            derivative_bytes=17,
            derivative_file_count=2,
            state=SlideState.FAILED,
        )
        database.add(slide)
        database.commit()
        slide_id = slide.id
    layout = StorageLayout(settings.data_root, cap_bytes=1)
    monkeypatch.setattr(
        "wsi_viewer.storage_accounting.shutil.disk_usage",
        Mock(return_value=SimpleNamespace(free=100 * 1024**3)),
    )

    with pytest.raises(InsufficientStorage):
        reserve_retry(factory, layout, slide_id=slide_id, actor_user_id=None)

    with factory() as database:
        stored = database.get(Slide, slide_id)
        assert stored is not None
        assert stored.state is SlideState.FAILED
        assert stored.reserved_bytes == 0
        assert stored.derivative_bytes == 17
        assert database.scalar(select(func.count()).select_from(Job)) == 0


def test_reconciliation_backfills_derivative_and_active_reservation(
    tmp_path: Path,
) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'reconcile.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        ready = Slide(
            display_name="Ready",
            original_filename="ready.ome.tif",
            source_bytes=6,
            state=SlideState.READY_PRIVATE,
        )
        active = Slide(
            display_name="Active",
            original_filename="active.ome.tif",
            source_bytes=7,
            state=SlideState.QUEUED,
        )
        database.add_all([ready, active])
        database.commit()
        ready_id = ready.id
        active_id = active.id
    derivative = layout.for_slide(ready_id).private_derivative
    (derivative / "slide_files" / "0").mkdir(parents=True)
    (derivative / "slide.dzi").write_bytes(b"descriptor")
    (derivative / "slide_files" / "0" / "0_0.jpeg").write_bytes(b"jpeg")

    summary = reconcile_storage(factory, layout)

    assert summary.slide_count == 2
    assert summary.derivative_count == 1
    with factory() as database:
        ready = database.get(Slide, ready_id)
        active = database.get(Slide, active_id)
        assert ready is not None
        assert ready.derivative_bytes == 14
        assert ready.derivative_file_count == 2
        assert active is not None
        assert active.reserved_bytes == admission_required(7)


def test_reconciliation_repairs_legacy_invalid_slide_tags(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'legacy-tags.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        slide = Slide(
            display_name="Legacy tags",
            original_filename="legacy-tags.ome.tif",
            source_bytes=7,
            state=SlideState.QUEUED,
        )
        database.add(slide)
        database.commit()
        slide_id = slide.id
        database.execute(
            text("UPDATE slides SET tags = :legacy_tags WHERE id = :slide_id"),
            {"legacy_tags": "'[]'", "slide_id": slide_id},
        )
        database.commit()

    summary = reconcile_storage(factory, layout)

    assert summary.slide_count == 1
    with factory() as database:
        repaired = database.get(Slide, slide_id)
        assert repaired is not None
        assert repaired.tags == []


def test_reconciliation_rejects_unsafe_derivative_symlink(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'reconcile-symlink.sqlite3'}",
        data_root=tmp_path / "data",
    )
    create_schema(settings)
    factory = session_factory(settings)
    layout = StorageLayout(settings.data_root)
    with factory() as database:
        slide = Slide(
            display_name="Ready",
            original_filename="ready.ome.tif",
            source_bytes=1,
            state=SlideState.READY_PRIVATE,
        )
        database.add(slide)
        database.commit()
        slide_id = slide.id
    derivative = layout.for_slide(slide_id).private_derivative
    derivative.mkdir(parents=True)
    (derivative / "slide.dzi").write_bytes(b"descriptor")
    outside = tmp_path / "outside.jpeg"
    outside.write_bytes(b"private")
    try:
        (derivative / "linked.jpeg").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")

    with pytest.raises(PublicationError, match="UNSAFE_DERIVATIVE"):
        reconcile_storage(factory, layout)
