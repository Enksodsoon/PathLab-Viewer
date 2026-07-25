import json
from unittest.mock import patch

import pytest
from generate_remote_manifest import RemoteManifestError, generate_remote_manifest

BASE_URL = "https://viewer.example.test"
PUBLIC_ID = "approved-public-id"
DZI = (
    b'<Image TileSize="512" Overlap="1" Format="jpg" '
    b'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
    b'<Size Width="4096" Height="3072"/></Image>'
)


def response_for(url: str) -> bytes:
    if url.endswith(f"/api/v1/public/slides/{PUBLIC_ID}"):
        return json.dumps(
            {
                "tileSource": f"/tiles/{PUBLIC_ID}/v1/slide.dzi",
                "thumbnailUrl": f"/tiles/{PUBLIC_ID}/v1/poster.jpeg",
            }
        ).encode()
    if url.endswith(f"/tiles/{PUBLIC_ID}/v1/slide.dzi"):
        return DZI
    raise AssertionError(f"Unexpected URL: {url}")


def test_remote_manifest_is_deterministic_bounded_and_multilevel() -> None:
    with patch("generate_remote_manifest._fetch", side_effect=response_for):
        first = generate_remote_manifest(BASE_URL, [PUBLIC_ID], seed=42)
        second = generate_remote_manifest(BASE_URL, [PUBLIC_ID], seed=42)

    assert first == second
    slide = first["slides"][0]
    assert set(slide) == {"publicId", "dziPath", "commonTiles", "randomTiles"}
    assert len(slide["commonTiles"]) <= 12
    assert len(slide["randomTiles"]) <= 256
    levels = {
        path.split("/")[1]
        for path in slide["commonTiles"] + slide["randomTiles"]
    }
    assert levels == {"10", "11", "12"}


def test_remote_manifest_never_embeds_metadata_or_absolute_urls() -> None:
    with patch("generate_remote_manifest._fetch", side_effect=response_for):
        manifest = generate_remote_manifest(BASE_URL, [PUBLIC_ID])

    serialized = json.dumps(manifest)
    assert BASE_URL not in serialized
    assert "thumbnailUrl" not in serialized
    assert "tileSource" not in serialized
    assert "displayName" not in serialized


@pytest.mark.parametrize(
    "base_url",
    [
        "http://viewer.example.test",
        "https://user:pass" + "@" + "viewer.example.test",
        "https://viewer.example.test/path",
        "https://viewer.example.test?token=secret",
    ],
)
def test_remote_manifest_rejects_unsafe_base_urls(base_url: str) -> None:
    with pytest.raises(RemoteManifestError):
        generate_remote_manifest(base_url, [PUBLIC_ID])


def test_remote_manifest_rejects_cross_origin_resources() -> None:
    def cross_origin(url: str) -> bytes:
        if "/api/v1/public/slides/" in url:
            return json.dumps(
                {
                    "tileSource": "https://attacker.example/slide.dzi",
                    "thumbnailUrl": f"/tiles/{PUBLIC_ID}/poster.jpeg",
                }
            ).encode()
        return DZI

    with (
        patch("generate_remote_manifest._fetch", side_effect=cross_origin),
        pytest.raises(RemoteManifestError, match="invalid resource path"),
    ):
        generate_remote_manifest(BASE_URL, [PUBLIC_ID])


def test_remote_manifest_rejects_a_different_slides_dzi_path() -> None:
    def wrong_slide(url: str) -> bytes:
        if "/api/v1/public/slides/" in url:
            return json.dumps(
                {
                    "tileSource": "/tiles/different-slide/v1/slide.dzi",
                    "thumbnailUrl": f"/tiles/{PUBLIC_ID}/v1/poster.jpeg",
                }
            ).encode()
        return DZI

    with (
        patch("generate_remote_manifest._fetch", side_effect=wrong_slide),
        pytest.raises(RemoteManifestError, match="approved slide"),
    ):
        generate_remote_manifest(BASE_URL, [PUBLIC_ID])
