import base64
import io
import json
from pathlib import Path

import numpy as np
import tifffile
from fastapi.testclient import TestClient
from PIL import Image
from wsi_viewer.config import Settings
from wsi_viewer.ome_ingest import serialize_ome_tile_index
from wsi_viewer.ome_tile_index import build_ome_tile_index, read_indexed_jpeg
from wsi_viewer.storage import StorageLayout
from wsi_viewer.tile_service import create_tile_app


def _service(
    tmp_path: Path, *, malformed_tables: bool = False
) -> tuple[TestClient, str, str, bytes]:
    settings = Settings(
        _env_file=None,
        data_root=tmp_path / "data",
        tile_cache_root=tmp_path / "cache",
        tile_cache_max_bytes=4 * 1024**2,
        tile_cache_low_water_bytes=3 * 1024**2,
        tile_cache_memory_bytes=1024**2,
    )
    slide_id = "dynamic-service"
    paths = StorageLayout(settings.data_root).for_slide(slide_id)
    paths.original.parent.mkdir(parents=True)
    full = np.zeros((1024, 1024, 3), dtype=np.uint8)
    with tifffile.TiffWriter(paths.original, ome=True, bigtiff=True) as writer:
        writer.write(
            full,
            metadata={"axes": "YXS"},
            photometric="ycbcr",
            compression="jpeg",
            tile=(512, 512),
            subifds=1,
        )
        writer.write(
            full[::2, ::2],
            photometric="ycbcr",
            compression="jpeg",
            tile=(512, 512),
            subfiletype=1,
        )
    index = build_ome_tile_index(paths.original)
    serialized = serialize_ome_tile_index(index)
    if malformed_tables:
        document = json.loads(serialized)
        document["levels"][0]["jpegTables"] = base64.b64encode(
            b"\xff\xd8\xff\xdb\x00\x20\xff\xd9"
        ).decode("ascii")
        document["levels"][0]["tiles"][0]["standaloneJpeg"] = False
        serialized = json.dumps(document).encode("utf-8")
    paths.ome_index.write_bytes(serialized)
    native = read_indexed_jpeg(
        paths.original,
        index.levels[0].tiles[0],
        expected_width=512,
        expected_height=512,
    )
    return TestClient(create_tile_app(settings)), slide_id, index.source_sha256, native


def test_internal_tile_service_serves_only_virtual_dzi_shapes(tmp_path: Path) -> None:
    client, slide_id, slide_sha256, native = _service(tmp_path)
    root = f"/_pathlab_ome/{slide_id}/{slide_sha256}"
    with client:
        assert client.get("/livez").status_code == 200
        ready = client.get("/readyz")
        assert ready.status_code == 200
        assert ready.json()["cacheMaxBytes"] == 4 * 1024**2

        descriptor = client.get(f"{root}/slide.dzi")
        assert descriptor.status_code == 200
        assert b'Width="1024" Height="1024"' in descriptor.content
        tile = client.get(f"{root}/slide_files/10/0_0.jpg")
        assert tile.status_code == 200
        assert tile.content == native
        with Image.open(io.BytesIO(tile.content)) as decoded:
            assert decoded.size == (512, 512)

        assert client.get(f"{root}/source.ome.tif").status_code == 404
        assert client.get(f"{root}/../source.ome.tif").status_code == 404
        assert (
            client.get(
                f"/_pathlab_ome/{slide_id}/{'b' * 64}/slide.dzi"
            ).status_code
            == 503
        )


def test_internal_tile_service_maps_malformed_native_jpeg_to_stable_503(
    tmp_path: Path,
) -> None:
    client, slide_id, slide_sha256, _ = _service(tmp_path, malformed_tables=True)
    root = f"/_pathlab_ome/{slide_id}/{slide_sha256}"

    with client:
        response = client.get(f"{root}/slide_files/10/0_0.jpg")

    assert response.status_code == 503
    assert response.json() == {"detail": {"code": "TILE_UNAVAILABLE"}}
