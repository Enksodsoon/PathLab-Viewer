from __future__ import annotations

import hashlib
import io
import json
import tarfile

import pytest
from wsi_viewer.prepared_archive import PreparedArchiveError, validate_prepared_archive

JPEG = b"\xff\xd8fixture\xff\xd9"
DZI = (
    b'<?xml version="1.0" encoding="UTF-8"?>'
    b'<Image TileSize="512" Overlap="1" Format="jpg" '
    b'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
    b'<Size Width="1024" Height="768"/></Image>'
)


def _archive(
    *,
    tile: bytes = JPEG,
    tile_name: str = "derivative/slide_files/10/0_0.jpg",
    link: bool = False,
    duplicate: bool = False,
    bad_hash: bool = False,
) -> bytes:
    payloads = {
        "derivative/slide.dzi": DZI,
        tile_name: tile,
        "derivative/thumbnail.jpg": JPEG,
    }
    manifest = {
        "schema": "pathlab-prepared-slide/v1",
        "slide": {
            "width": 1024,
            "height": 768,
            "tileSize": 512,
            "overlap": 1,
            "format": "jpg",
        },
        "files": [
            {
                "path": path,
                "size": len(content),
                "sha256": "0" * 64 if bad_hash else hashlib.sha256(content).hexdigest(),
            }
            for path, content in sorted(payloads.items())
        ],
    }
    entries = [("manifest.json", json.dumps(manifest, separators=(",", ":")).encode())]
    entries.extend(sorted(payloads.items()))
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            if link and name == tile_name:
                info.type = tarfile.SYMTYPE
                info.linkname = "manifest.json"
                info.size = 0
            archive.addfile(info, io.BytesIO(content))
            if duplicate and name == tile_name:
                archive.addfile(info, io.BytesIO(content))
    return output.getvalue()


def test_accepts_canonical_prepared_slide() -> None:
    validated = validate_prepared_archive(io.BytesIO(_archive()))

    assert validated.schema == "pathlab-prepared-slide/v1"
    assert validated.width == 1024
    assert validated.height == 768
    assert validated.payload_bytes == len(DZI) + 2 * len(JPEG)


@pytest.mark.parametrize(
    ("archive", "message"),
    [
        (_archive(tile_name="../escape.jpg"), "unsafe path"),
        (_archive(tile_name="/absolute.jpg"), "unsafe path"),
        (_archive(link=True), "regular files"),
        (_archive(duplicate=True), "duplicate"),
        (_archive(tile_name="derivative/original.ome.tiff"), "unexpected path"),
        (_archive(tile=b"not-jpeg"), "JPEG"),
        (_archive(bad_hash=True), "hash"),
    ],
    ids=[
        "traversal",
        "absolute",
        "link",
        "duplicate",
        "unexpected",
        "bad-jpeg",
        "bad-hash",
    ],
)
def test_rejects_unsafe_or_invalid_prepared_slides(archive: bytes, message: str) -> None:
    with pytest.raises(PreparedArchiveError, match=message):
        validate_prepared_archive(io.BytesIO(archive))


def test_rejects_noncanonical_tar_metadata() -> None:
    content = _archive()
    source = io.BytesIO(content)
    output = io.BytesIO()
    with (
        tarfile.open(fileobj=source, mode="r:") as original,
        tarfile.open(fileobj=output, mode="w", format=tarfile.USTAR_FORMAT) as changed,
    ):
        for member in original:
            extracted = original.extractfile(member)
            assert extracted is not None
            payload = extracted.read()
            member.mtime = 1
            changed.addfile(member, io.BytesIO(payload))

    with pytest.raises(PreparedArchiveError, match="canonical metadata"):
        validate_prepared_archive(io.BytesIO(output.getvalue()))
