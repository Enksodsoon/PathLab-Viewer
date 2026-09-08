import importlib.util
import sys
from email.message import Message
from pathlib import Path

import pytest
from wsi_viewer.assessment_routes import _parse_rows


def test_capacity_import_creates_searchable_structured_student_ids(monkeypatch, tmp_path):
    module = fixture_module()
    sha = "a" * 40
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "fixture",
            "--base-url",
            "https://qualify.example.test",
            "--host-observer-url",
            "https://qualify.example.test/sample",
            "--release-sha",
            sha,
            "--slide-id",
            "slide",
            "--seats",
            "500",
            "--output",
            str(tmp_path / "fixture.json"),
        ],
    )
    for name in ("ASSESSMENT_ADMIN_COOKIE", "ASSESSMENT_ADMIN_CSRF", "ASSESSMENT_OBSERVER_TOKEN"):
        monkeypatch.setenv(name, "test-only")

    class ImportVerified(Exception):
        pass

    def call(method, url, headers, payload=None):
        if url.endswith("/sample"):
            return 200, {"releaseSha": sha}
        if url.endswith("/classes"):
            return 201, {"id": "cohort"}
        assert url.endswith("/import/preview")
        rows = _parse_rows(payload["rows"], require_structured=True)
        assert len(rows) == 500
        assert len({row.student_id for row in rows}) == 500
        assert all(row.student_id == row.identifier and row.first_name for row in rows)
        raise ImportVerified

    monkeypatch.setattr(module, "call", call)
    with pytest.raises(ImportVerified):
        module.main()


def fixture_module():
    path = Path(__file__).parents[2] / "scripts" / "assessment_capacity_fixture.py"
    spec = importlib.util.spec_from_file_location("assessment_capacity_fixture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DZI = b'<Image TileSize="256" Format="jpeg"><Size Width="2049" Height="1025"/></Image>'
BASE = "https://qualify.example.test"
PATH = "/assessment-assets/administration/grant/slide.dzi"


class Response:
    status = 200

    def __init__(self, url, payload, content_type):
        self.url, self.payload = url, payload
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, size):
        return self.payload[:size]


def test_probe_requests_full_resolution_center_jpeg_not_descriptor(monkeypatch):
    module = fixture_module()
    requested = []

    def open_asset(url, timeout):
        requested.append(url)
        assert timeout == 30
        return (
            Response(url, DZI, "application/xml")
            if url.endswith(".dzi")
            else Response(url, b"\xff\xd8\xff\xe0jpeg-image", "image/jpeg")
        )

    monkeypatch.setattr(module.urllib.request, "urlopen", open_asset)
    tile = module.measured_tile_url(BASE, PATH)
    assert tile == BASE + "/assessment-assets/administration/grant/slide_files/12/4_2.jpeg"
    assert requested == [BASE + PATH, tile]


@pytest.mark.parametrize(
    "path", ["https://elsewhere.test/slide.dzi", "/tiles/x/slide.dzi", PATH + "?token=x"]
)
def test_probe_rejects_wrong_asset_scope_before_network(monkeypatch, path):
    module = fixture_module()
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: pytest.fail("network not expected"),
    )
    with pytest.raises(ValueError, match="same-origin"):
        module.measured_tile_url(BASE, path)


@pytest.mark.parametrize(
    "payload,content_type", [(b"<html>fallback</html>", "text/html"), (DZI, "image/jpeg")]
)
def test_probe_rejects_non_image_success_response(monkeypatch, payload, content_type):
    module = fixture_module()
    monkeypatch.setattr(
        module.urllib.request,
        "urlopen",
        lambda url, **_: Response(
            url,
            DZI if url.endswith(".dzi") else payload,
            "application/xml" if url.endswith(".dzi") else content_type,
        ),
    )
    with pytest.raises(ValueError, match="JPEG image"):
        module.measured_tile_url(BASE, PATH)


@pytest.mark.parametrize(
    "payload",
    [
        b"bad xml",
        b"x" * 65537,
        b"<!DOCTYPE Image><Image/>",
        b'<Image TileSize="0" Format="jpeg"><Size Width="1" Height="1"/></Image>',
    ],
    ids=["malformed", "oversized", "doctype", "zero-tile-size"],
)
def test_probe_rejects_invalid_descriptor(monkeypatch, payload):
    module = fixture_module()
    monkeypatch.setattr(
        module.urllib.request, "urlopen", lambda url, **_: Response(url, payload, "application/xml")
    )
    with pytest.raises(ValueError):
        module.measured_tile_url(BASE, PATH)
