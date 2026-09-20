import json
import sys
from types import ModuleType

from PIL import Image
from wsi_viewer.storage import StorageLayout
from wsi_viewer.tile_routes import materialize_local_openslide_tile


def test_materializes_and_reuses_local_fixture_tile(tmp_path, monkeypatch) -> None:
    layout = StorageLayout(tmp_path)
    derivative = layout.for_slide("slide-1").private_derivative
    derivative.mkdir(parents=True)
    source = tmp_path / "source.svs"
    source.write_bytes(b"local fixture")
    (derivative / ".openslide-source.json").write_text(
        json.dumps({"source": str(source), "tileSize": 1024, "quality": 92}),
        encoding="utf-8",
    )

    calls = []

    class FakeSlide:
        def __init__(self, path: str) -> None:
            calls.append(path)

        def close(self) -> None:
            pass

    class FakeDeepZoom:
        level_count = 2
        level_tiles = ((1, 1), (2, 1))

        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def get_tile(self, level, address):
            assert (level, address) == (1, (1, 0))
            return Image.new("RGB", (16, 16), "purple")

    openslide = ModuleType("openslide")
    deepzoom = ModuleType("openslide.deepzoom")
    openslide.OpenSlide = FakeSlide
    deepzoom.DeepZoomGenerator = FakeDeepZoom
    monkeypatch.setitem(sys.modules, "openslide", openslide)
    monkeypatch.setitem(sys.modules, "openslide.deepzoom", deepzoom)

    first = materialize_local_openslide_tile(layout, "slide-1", "slide_files/1/1_0.jpg")
    assert first.is_file()
    assert Image.open(first).size == (16, 16)
    assert calls == [str(source)]

    assert materialize_local_openslide_tile(layout, "slide-1", "slide_files/1/1_0.jpg") == first
    assert calls == [str(source)]
