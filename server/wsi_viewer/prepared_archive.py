from __future__ import annotations

import hashlib
import json
import re
import tarfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import BinaryIO, cast
from xml.etree import ElementTree

SCHEMA = "pathlab-prepared-slide/v1"
MAX_MANIFEST_BYTES = 1_048_576
MAX_FILE_COUNT = 1_000_000
MAX_PAYLOAD_BYTES = 1 << 40
_TILE_PATH = re.compile(r"derivative/slide_files/[0-9]+/[0-9]+_[0-9]+\.jpg")
_FIXED_PATHS = frozenset({"derivative/slide.dzi", "derivative/thumbnail.jpg"})


class PreparedArchiveError(ValueError):
    pass


@dataclass(frozen=True)
class ValidatedPreparedArchive:
    schema: str
    width: int
    height: int
    payload_bytes: int
    file_count: int


def _safe_path(name: str) -> None:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or ":" in path.parts[0]
    ):
        raise PreparedArchiveError(f"unsafe path: {name!r}")


def _read_json_manifest(archive: tarfile.TarFile, member: tarfile.TarInfo) -> dict[str, object]:
    if member.size > MAX_MANIFEST_BYTES:
        raise PreparedArchiveError("manifest exceeds byte limit")
    stream = archive.extractfile(member)
    if stream is None:
        raise PreparedArchiveError("manifest is not readable")
    try:
        value = json.loads(stream.read())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreparedArchiveError("manifest is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise PreparedArchiveError("manifest must be a JSON object")
    return cast(dict[str, object], value)


def _positive_int(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PreparedArchiveError(f"{field} must be a positive integer")
    return value


def _validate_dzi(content: bytes, expected: dict[str, object]) -> None:
    try:
        root = ElementTree.fromstring(content)
        size = next(child for child in root if child.tag.rsplit("}", 1)[-1] == "Size")
    except (ElementTree.ParseError, StopIteration) as exc:
        raise PreparedArchiveError("malformed DZI XML") from exc
    actual = {
        "tileSize": int(root.attrib["TileSize"]),
        "overlap": int(root.attrib["Overlap"]),
        "format": root.attrib["Format"],
        "width": int(size.attrib["Width"]),
        "height": int(size.attrib["Height"]),
    }
    if actual != expected:
        raise PreparedArchiveError("DZI metadata does not match manifest")


def validate_prepared_archive(fileobj: BinaryIO) -> ValidatedPreparedArchive:
    try:
        archive = tarfile.open(fileobj=fileobj, mode="r:")  # noqa: SIM115
    except tarfile.TarError as exc:
        raise PreparedArchiveError("invalid uncompressed TAR archive") from exc

    with archive:
        members = archive.getmembers()
        if not members or len(members) > MAX_FILE_COUNT + 1:
            raise PreparedArchiveError("archive file count is outside limits")

        names: set[str] = set()
        for member in members:
            _safe_path(member.name)
            if member.name in names:
                raise PreparedArchiveError(f"duplicate archive path: {member.name}")
            names.add(member.name)
            if not member.isfile():
                raise PreparedArchiveError("archive may contain regular files only")
            if (
                member.mtime != 0
                or member.uid != 0
                or member.gid != 0
                or member.uname
                or member.gname
                or member.mode != 0o644
            ):
                raise PreparedArchiveError("archive entries require canonical metadata")

        expected_order = [
            "manifest.json",
            *sorted(name for name in names if name != "manifest.json"),
        ]
        if [member.name for member in members] != expected_order:
            raise PreparedArchiveError("archive entries are not in canonical order")
        manifest = _read_json_manifest(archive, members[0])
        if manifest.get("schema") != SCHEMA:
            raise PreparedArchiveError(
                f"unsupported prepared slide schema: {manifest.get('schema')!r}"
            )

        slide = manifest.get("slide")
        files = manifest.get("files")
        if not isinstance(slide, dict) or not isinstance(files, list):
            raise PreparedArchiveError("manifest requires slide and files")
        width = _positive_int(slide.get("width"), "slide.width")
        height = _positive_int(slide.get("height"), "slide.height")
        tile_size = _positive_int(slide.get("tileSize"), "slide.tileSize")
        overlap = slide.get("overlap")
        image_format = slide.get("format")
        if overlap != 1 or image_format != "jpg":
            raise PreparedArchiveError("prepared slides require overlap 1 and jpg tiles")

        declared: dict[str, tuple[int, str]] = {}
        for entry in files:
            if not isinstance(entry, dict):
                raise PreparedArchiveError("manifest file entries must be objects")
            path = entry.get("path")
            size = entry.get("size")
            digest = entry.get("sha256")
            if not isinstance(path, str):
                raise PreparedArchiveError("manifest file path must be a string")
            _safe_path(path)
            if path in declared:
                raise PreparedArchiveError(f"duplicate manifest path: {path}")
            if path not in _FIXED_PATHS and _TILE_PATH.fullmatch(path) is None:
                raise PreparedArchiveError(f"unexpected path: {path}")
            if not isinstance(size, int) or isinstance(size, bool) or size < 0:
                raise PreparedArchiveError(f"invalid size for {path}")
            if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise PreparedArchiveError(f"invalid hash for {path}")
            declared[path] = (size, digest)

        required = {"derivative/slide.dzi", "derivative/thumbnail.jpg"}
        actual_payloads = names - {"manifest.json"}
        has_tile = any(_TILE_PATH.fullmatch(path) for path in declared)
        if not required.issubset(declared) or not has_tile:
            raise PreparedArchiveError("manifest is missing DZI, thumbnail, or tiles")
        if actual_payloads != set(declared):
            raise PreparedArchiveError("archive payloads do not exactly match manifest")

        total_bytes = 0
        dzi_content: bytes | None = None
        for member in members[1:]:
            expected_size, expected_hash = declared[member.name]
            if member.size != expected_size:
                raise PreparedArchiveError(f"size mismatch for {member.name}")
            total_bytes += member.size
            if total_bytes > MAX_PAYLOAD_BYTES:
                raise PreparedArchiveError("archive exceeds payload byte limit")
            stream = archive.extractfile(member)
            if stream is None:
                raise PreparedArchiveError(f"could not read {member.name}")
            digest = hashlib.sha256()
            first = b""
            last = b""
            content = bytearray() if member.name == "derivative/slide.dzi" else None
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                if not first:
                    first = chunk[:2]
                last = (last + chunk)[-2:]
                if content is not None:
                    content.extend(chunk)
            if digest.hexdigest() != expected_hash:
                raise PreparedArchiveError(f"hash mismatch for {member.name}")
            if member.name.endswith(".jpg") and (first != b"\xff\xd8" or last != b"\xff\xd9"):
                raise PreparedArchiveError(f"invalid JPEG signature for {member.name}")
            if content is not None:
                dzi_content = bytes(content)

        assert dzi_content is not None
        _validate_dzi(
            dzi_content,
            {
                "tileSize": tile_size,
                "overlap": overlap,
                "format": image_format,
                "width": width,
                "height": height,
            },
        )
        return ValidatedPreparedArchive(
            schema=SCHEMA,
            width=width,
            height=height,
            payload_bytes=total_bytes,
            file_count=len(declared),
        )
