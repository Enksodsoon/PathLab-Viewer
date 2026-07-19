from pathlib import Path

import pytest
from wsi_viewer.conversion import InvalidDerivative, sanitize_and_validate_derivative


def test_vips_metadata_is_deleted_and_only_dzi_jpegs_remain(tmp_path: Path) -> None:
    (tmp_path / "slide.dzi").write_text("<Image />", encoding="utf-8")
    tiles = tmp_path / "slide_files" / "0"
    tiles.mkdir(parents=True)
    (tiles / "0_0.jpeg").write_bytes(b"jpeg")
    (tmp_path / "slide_files" / "vips-properties.xml").write_text("private", encoding="utf-8")
    sanitize_and_validate_derivative(tmp_path)
    assert not (tmp_path / "slide_files" / "vips-properties.xml").exists()


def test_unexpected_derivative_file_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "slide.dzi").write_text("<Image />", encoding="utf-8")
    (tmp_path / "secret.xml").write_text("no", encoding="utf-8")
    with pytest.raises(InvalidDerivative):
        sanitize_and_validate_derivative(tmp_path)
