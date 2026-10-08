"""Live-loader regressions use image bytes, not registration engine substitutes."""

from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image
from test_alignment_api import _client, _headers
from test_alignment_engine_routes import _stack
from test_alignment_frame_routes import _candidate
from test_alignment_immutable_inputs import snapshot
from wsi_viewer import worker
from wsi_viewer.alignment_geometry import derivative_sampling_geometry
from wsi_viewer.database import session_factory
from wsi_viewer.models import ComparisonSet, Job, LibraryShare, ShareSlide, Slide
from wsi_viewer.storage import StorageLayout


def _empty_pyramid(root, size=(1003, 809), thumbnail=(123, 87)):
    root.mkdir(parents=True, exist_ok=True)
    (root / "slide.dzi").write_text(
        '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        'TileSize="256" Overlap="0" Format="png">'
        f'<Size Width="{size[0]}" Height="{size[1]}"/></Image>'
    )
    Image.new("RGB", thumbnail, (170, 80, 120)).save(root / "thumbnail.jpg")


def test_all_missing_dzi_tiles_raise_and_live_loader_uses_real_thumbnail_with_exact_frame(tmp_path):
    _empty_pyramid(tmp_path)
    with pytest.raises(FileNotFoundError, match="tiles"):
        worker._load_dzi_overview(tmp_path)
    image = worker._load_alignment_overview(tmp_path)
    assert image.size == (123, 87)
    assert image.getpixel((10, 10)) != (255, 255, 255)
    geometry = image.info["alignmentGeometry"]
    assert geometry["kind"] == "thumbnail-fallback"
    assert geometry["analysisSize"] == [123, 87]
    assert geometry["sourceSize"] == geometry["coordinateFrameSize"] == [1003, 809]
    assert geometry["samplingScale"] == [1003 / 123, 809 / 87]


@pytest.mark.parametrize("namespace", [True, False])
def test_genuine_sparse_pyramid_with_one_tile_keeps_missing_background(tmp_path, namespace):
    _empty_pyramid(tmp_path)
    if not namespace:
        descriptor = tmp_path / "slide.dzi"
        descriptor.write_text(
            descriptor.read_text().replace(
                ' xmlns="http://schemas.microsoft.com/deepzoom/2008"', ""
            )
        )
    tile = tmp_path / "slide_files" / "10" / "0_0.png"
    tile.parent.mkdir(parents=True)
    Image.new("RGB", (256, 256), (80, 120, 170)).save(tile)
    image = worker._load_alignment_overview(tmp_path)
    assert image.size == (1003, 809)
    assert image.getpixel((10, 10)) == (80, 120, 170)
    assert image.getpixel((900, 700)) == (255, 255, 255)
    assert image.info["alignmentGeometry"]["kind"] == "dzi-pyramid"


def test_foreground_preparation_and_cache_bind_actual_thumbnail_fallback_geometry(
    tmp_path, monkeypatch
):
    layout = StorageLayout(tmp_path)
    for name in ("r", "m"):
        _empty_pyramid(layout.for_slide(name).private_derivative)
    database = MagicMock()
    database.scalar.return_value = None
    comparison = ComparisonSet(
        id="set",
        name="Set",
        version=1,
        reference_slide_id="r",
        member_slide_ids=["r", "m"],
        source_versions={"r": "r", "m": "m"},
        registrations={},
    )
    slides = [
        Slide(id=name, sha256=name, slide_metadata={"width": 1003, "height": 809})
        for name in ("r", "m")
    ]
    job = Job(
        id="job",
        checkpoint={
            "setVersion": 1,
            "foregroundDeadlineAt": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        },
    )
    captured = []

    def prepare(key, image, size, **kwargs):
        actual = image() if callable(image) else image
        captured.append((key, actual, size, kwargs))
        return object(), False

    monkeypatch.setattr(worker, "_preparation_cache", SimpleNamespace(prepare=prepare))
    monkeypatch.setattr(
        worker,
        "register_prepared",
        lambda *_: SimpleNamespace(as_json=lambda: {"status": "needs_refinement", "triangles": []}),
    )
    monkeypatch.setattr(worker, "_preview_maps", OrderedDict())
    monkeypatch.setattr(worker, "_preview_map_bytes", 0)
    monkeypatch.setattr(worker, "_best_compatible_registration", lambda *_a, **_k: None)
    worker._preview_alignment(database, layout, job, comparison, *slides)
    assert captured, comparison.registrations
    assert captured[0][1].size == (123, 87)
    assert captured[0][2] == (1003, 809)
    assert not captured[0][3].get("sampling_scale")
    settings = comparison.registrations["m"]["engineSettings"]
    assert settings["referenceGeometry"]["kind"] == "thumbnail-fallback"
    assert settings["movingGeometry"]["samplingScale"] == [1003 / 123, 809 / 87]
    original_key = captured[0][0]
    Image.new("RGB", (124, 87), (80, 120, 170)).save(
        layout.for_slide("r").private_derivative / "thumbnail.jpg"
    )
    job.checkpoint["foregroundDeadlineAt"] = (datetime.now(UTC) + timedelta(seconds=10)).isoformat()
    worker._preview_alignment(database, layout, job, comparison, *slides)
    assert captured[2][0] != original_key


@pytest.mark.parametrize("delivery", ["admin", "shared"])
@pytest.mark.parametrize("kind", ["dzi-pyramid", "thumbnail-fallback"])
def test_actual_map_endpoint_accepts_recorded_sampling_level_and_rejects_changed_input(
    tmp_path, delivery, kind
):
    size = (5003, 4009)
    with _client(tmp_path, enabled=True) as client:
        headers = _headers(client)
        layout = StorageLayout(client.app.state.settings.data_root)
        for name in ("slide-1", "slide-2"):
            _empty_pyramid(layout.for_slide(name).private_derivative, size, (123, 87))
        with session_factory(client.app.state.settings)() as database:
            for name in ("slide-1", "slide-2"):
                slide = database.get(Slide, name)
                slide.slide_metadata = {**slide.slide_metadata, "width": size[0], "height": size[1]}
            database.commit()
        stack = _stack(client, headers)
        geometries = {
            side + "Geometry": derivative_sampling_geometry(
                layout.for_slide(name).private_derivative, size, maximum=1024, kind=kind
            )
            for side, name in (("reference", "slide-1"), ("moving", "slide-2"))
        }
        _candidate(client, stack, geometries)
        with session_factory(client.app.state.settings)() as database:
            comparison = database.get(ComparisonSet, stack["id"])
            comparison.registrations = {
                "slide-2": {**comparison.registrations["slide-2"], "status": "approximate"}
            }
            share = LibraryShare(
                public_id="fallback-share",
                target_type="collection",
                target_id="collection",
                privacy_status="passed",
            )
            database.add(share)
            database.flush()
            database.add_all(
                [
                    ShareSlide(share_id=share.id, slide_id=name, sort_order=index)
                    for index, name in enumerate(("slide-1", "slide-2"))
                ]
            )
            database.commit()
        url = (
            f"/api/v1/admin/comparison-sets/{stack['id']}"
            if delivery == "admin"
            else f"/api/v2/public/collections/fallback-share/comparisons/{stack['id']}"
        )
        response = client.get(url)
        assert response.status_code == 200, response.text
        assert response.json()["members"][1]["registration"]["status"] == "approximate"
        root = layout.for_slide("slide-2").private_derivative
        if kind == "thumbnail-fallback":
            Image.new("RGB", (123, 87), (80, 120, 170)).save(root / "thumbnail.jpg")
            assert client.get(url).json()["members"][1]["registration"]["status"] == "stale"
            Image.new("RGB", (123, 87), (170, 80, 120)).save(root / "thumbnail.jpg")
        descriptor = root / "slide.dzi"
        descriptor.write_text(descriptor.read_text().replace('Width="5003"', 'Width="5004"'))
        assert client.get(url).json()["members"][1]["registration"]["status"] == "stale"


def test_foreground_immutable_overview_uses_png_frame_without_dzi_loading(tmp_path, monkeypatch):
    layout = StorageLayout(tmp_path)
    for name in ("r", "m"):
        root = layout.for_slide(name).private_derivative
        root.parent.mkdir(parents=True, exist_ok=True)
        snapshot(root)
        (root / "slide.dzi").write_text("This descriptor must never drive overview loading")
    database = MagicMock()
    database.scalar.return_value = None
    comparison = ComparisonSet(
        id="set",
        name="Set",
        version=1,
        reference_slide_id="r",
        member_slide_ids=["r", "m"],
        source_versions={"r": "r", "m": "m"},
        registrations={},
    )
    slides = [
        Slide(id=name, sha256=name, slide_metadata={"width": 100, "height": 99})
        for name in ("r", "m")
    ]
    job = Job(
        id="job",
        checkpoint={
            "setVersion": 1,
            "foregroundDeadlineAt": (datetime.now(UTC) + timedelta(seconds=10)).isoformat(),
        },
    )
    captured = []

    def no_dzi(*args, **kwargs):
        raise AssertionError("immutable overview attempted raw DZI loading")

    def prepare(key, image, size, **kwargs):
        actual = image() if callable(image) else image
        captured.append((actual, size))
        return object(), False

    monkeypatch.setattr(worker, "_load_dzi_overview", no_dzi)
    monkeypatch.setattr(worker, "_preparation_cache", SimpleNamespace(prepare=prepare))
    monkeypatch.setattr(
        worker,
        "register_prepared",
        lambda *_: SimpleNamespace(as_json=lambda: {"status": "needs_refinement", "triangles": []}),
    )
    monkeypatch.setattr(worker, "_preview_maps", OrderedDict())
    monkeypatch.setattr(worker, "_preview_map_bytes", 0)
    monkeypatch.setattr(worker, "_best_compatible_registration", lambda *_a, **_k: None)
    worker._preview_alignment(database, layout, job, comparison, *slides)
    assert captured[0][0].size == (13, 13)
    assert captured[0][1] == (104, 104)
    settings = comparison.registrations["m"]["engineSettings"]
    assert settings["referenceGeometry"]["kind"] == "immutable-overview"
    assert settings["movingGeometry"]["samplingScale"] == [8, 8]
