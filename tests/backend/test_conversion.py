import json
import logging
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from wsi_viewer import conversion
from wsi_viewer.conversion import (
    InvalidDerivative,
    generate_dzi,
    sanitize_and_validate_derivative,
)


class FakeImage:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.dzsave_options: dict[str, object] | None = None

    def get_typeof(self, _name: str) -> int:
        return 0

    def dzsave(self, output: str, **options: object) -> None:
        self.dzsave_options = options
        if self.error is not None:
            raise self.error
        output_path = Path(output)
        output_path.with_suffix(".dzi").write_bytes(b"<Image />")
        tiles = output_path.with_name(f"{output_path.name}_files") / "0"
        tiles.mkdir(parents=True)
        (tiles / "0_0.jpg").write_bytes(b"jpeg")


def install_fake_pyvips(
    monkeypatch: pytest.MonkeyPatch, image: FakeImage
) -> SimpleNamespace:
    fake = SimpleNamespace(
        Image=SimpleNamespace(new_from_file=Mock(return_value=image)),
        cache_set_max_mem=Mock(),
        cache_set_max_files=Mock(),
        cache_set_max=Mock(),
    )
    monkeypatch.setitem(sys.modules, "pyvips", fake)
    return fake


def conversion_events(caplog: pytest.LogCaptureFixture) -> list[dict[str, object]]:
    return [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "wsi_viewer.conversion"
    ]


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


def test_configure_libvips_applies_process_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = install_fake_pyvips(monkeypatch, FakeImage())
    monkeypatch.delenv("VIPS_CONCURRENCY", raising=False)

    conversion.configure_libvips(
        concurrency=2,
        cache_max_mem_bytes=123456,
        cache_max_files=17,
        cache_max_operations=19,
    )

    assert os.environ["VIPS_CONCURRENCY"] == "2"
    fake.cache_set_max_mem.assert_called_once_with(123456)
    fake.cache_set_max_files.assert_called_once_with(17)
    fake.cache_set_max.assert_called_once_with(19)


def test_failed_conversion_removes_temporary_derivative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    destination = tmp_path / "private"
    install_fake_pyvips(monkeypatch, FakeImage(error=RuntimeError("conversion failed")))

    with pytest.raises(RuntimeError, match="conversion failed"):
        generate_dzi(source, destination, series_index=0, bits=8)

    assert not (tmp_path / f"private.tmp-{os.getpid()}").exists()
    assert source.read_bytes() == b"source"


def test_failed_conversion_preserves_completed_derivative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    destination = tmp_path / "private"
    destination.mkdir()
    (destination / "completed.marker").write_bytes(b"old")
    install_fake_pyvips(monkeypatch, FakeImage(error=RuntimeError("conversion failed")))

    with pytest.raises(RuntimeError, match="conversion failed"):
        generate_dzi(source, destination, series_index=0, bits=8)

    assert (destination / "completed.marker").read_bytes() == b"old"


def test_successful_conversion_atomically_replaces_completed_derivative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    destination = tmp_path / "private"
    destination.mkdir()
    (destination / "completed.marker").write_bytes(b"old")
    install_fake_pyvips(monkeypatch, FakeImage())

    result = generate_dzi(source, destination, series_index=0, bits=8)

    assert result == destination / "slide.dzi"
    assert result.read_bytes() == b"<Image />"
    assert not (destination / "completed.marker").exists()
    assert not destination.with_name("private.previous").exists()
    assert not destination.with_name(f"private.tmp-{os.getpid()}").exists()
    assert source.read_bytes() == b"source"


def test_cleanup_failure_does_not_hide_conversion_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    destination = tmp_path / "private"
    original_error = RuntimeError("original conversion error")
    install_fake_pyvips(monkeypatch, FakeImage(error=original_error))
    real_rmtree = shutil.rmtree

    def fail_temporary_cleanup(path: str | Path, *args: object, **kwargs: object) -> None:
        if Path(path).name == f"private.tmp-{os.getpid()}":
            raise OSError("cleanup failed")
        real_rmtree(path, *args, **kwargs)

    monkeypatch.setattr(conversion.shutil, "rmtree", fail_temporary_cleanup)

    with pytest.raises(RuntimeError) as captured:
        generate_dzi(source, destination, series_index=0, bits=8)

    assert captured.value is original_error


def test_success_logging_records_measurements_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    install_fake_pyvips(monkeypatch, FakeImage())

    with caplog.at_level(logging.INFO, logger="wsi_viewer.conversion"):
        generate_dzi(source, tmp_path / "private", series_index=0, bits=8)

    events = conversion_events(caplog)
    assert [event["event"] for event in events] == [
        "conversion_start",
        "conversion_complete",
    ]
    assert events[0] == {"event": "conversion_start", "source_bytes": 6}
    assert events[1]["source_bytes"] == 6
    assert events[1]["derivative_bytes"] == 13
    assert events[1]["file_count"] == 2
    assert events[1]["tile_count"] == 1
    assert isinstance(events[1]["elapsed_seconds"], float)


def test_failure_logging_records_bounded_measurements(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    install_fake_pyvips(monkeypatch, FakeImage(error=RuntimeError("private detail")))

    with (
        caplog.at_level(logging.INFO, logger="wsi_viewer.conversion"),
        pytest.raises(RuntimeError),
    ):
        generate_dzi(source, tmp_path / "private", series_index=0, bits=8)

    events = conversion_events(caplog)
    assert [event["event"] for event in events] == [
        "conversion_start",
        "conversion_failure",
    ]
    assert events[1]["source_bytes"] == 6
    assert events[1]["error_type"] == "RuntimeError"
    assert isinstance(events[1]["elapsed_seconds"], float)
    assert "private detail" not in caplog.text


def test_dzi_image_output_settings_remain_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source.ome.tif"
    source.write_bytes(b"source")
    image = FakeImage()
    install_fake_pyvips(monkeypatch, image)

    generate_dzi(source, tmp_path / "private", series_index=0, bits=8)

    assert image.dzsave_options == {
        "tile_size": 512,
        "overlap": 1,
        "suffix": ".jpg[Q=85,strip]",
        "skip_blanks": -1,
        "depth": "onepixel",
    }
