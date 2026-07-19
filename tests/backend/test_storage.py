from pathlib import Path

import pytest
from wsi_viewer.storage import (
    InsufficientStorage,
    StorageLayout,
    admission_required,
    publish_derivative,
    unpublish_derivative,
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
    unpublish_derivative(layout, "public-1")
    assert not public.exists()
