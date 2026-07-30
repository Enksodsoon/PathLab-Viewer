import hashlib
import io
import json
import math
import os
import re
import shutil
import tarfile
import uuid
import xml.etree.ElementTree as et
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from PIL import Image

from .storage import DerivativeMeasurement

MAX_MANIFEST_BYTES = 16 * 1024 * 1024
MAX_INVENTORY_BYTES = 256 * 1024 * 1024
MAX_DERIVATIVE_FILES = 2_000_000
COPY_BUFFER_BYTES = 1024 * 1024


class PreparedIngestError(ValueError):
    pass


@dataclass(frozen=True)
class PreparedIngestResult:
    measurement: DerivativeMeasurement
    manifest: dict[str, Any]
    manifest_sha256: str


@dataclass(frozen=True)
class _DeclaredFile:
    path: str
    size: int
    sha256: str


@dataclass
class _DziTracker:
    width: int
    height: int
    tile_size: int
    maximum_level: int
    expected_per_level: dict[int, int]
    seen_per_level: dict[int, int]

    @classmethod
    def from_descriptor(cls, path: Path, slide: dict[str, Any]) -> "_DziTracker":
        width, height, tile_size = _validate_dzi(path, slide)
        maximum_level = math.ceil(math.log2(max(width, height)))
        expected: dict[int, int] = {}
        for level in range(maximum_level + 1):
            divisor = 1 << (maximum_level - level)
            level_width = math.ceil(width / divisor)
            level_height = math.ceil(height / divisor)
            expected[level] = math.ceil(level_width / tile_size) * math.ceil(
                level_height / tile_size
            )
        return cls(width, height, tile_size, maximum_level, expected, {})

    def observe(self, relative: Path) -> None:
        matched = re.fullmatch(r"slide_files/(\d+)/(\d+)_(\d+)\.jpg", relative.as_posix())
        if matched is None:
            raise PreparedIngestError("UNSAFE_DERIVATIVE")
        level, column, row = (int(value) for value in matched.groups())
        if level not in self.expected_per_level:
            raise PreparedIngestError("UNSAFE_DERIVATIVE")
        divisor = 1 << (self.maximum_level - level)
        columns = math.ceil(math.ceil(self.width / divisor) / self.tile_size)
        rows = math.ceil(math.ceil(self.height / divisor) / self.tile_size)
        if column >= columns or row >= rows:
            raise PreparedIngestError("UNSAFE_DERIVATIVE")
        self.seen_per_level[level] = self.seen_per_level.get(level, 0) + 1

    def require_complete(self) -> None:
        if self.seen_per_level != self.expected_per_level:
            raise PreparedIngestError("INCOMPLETE_DZI_PYRAMID")


class _HashingReader(io.RawIOBase):
    def __init__(self, source: BinaryIO) -> None:
        self.source = source
        self.digest = hashlib.sha256()

    def readable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        value = self.source.read(size)
        if value:
            self.digest.update(value)
        return value

    def drain(self) -> None:
        while self.read(COPY_BUFFER_BYTES):
            pass

    def hexdigest(self) -> str:
        return self.digest.hexdigest()


def install_prepared_package(
    package: Path,
    destination: Path,
    *,
    expected_package_sha256: str,
    expected_artifact_revision_id: str,
    expected_manifest_sha256: str,
) -> PreparedIngestResult:
    if not _is_sha256(expected_package_sha256) or not _is_sha256(
        expected_manifest_sha256
    ):
        raise PreparedIngestError("INVALID_HASH")
    if not expected_artifact_revision_id.strip():
        raise PreparedIngestError("INVALID_ARTIFACT_REVISION")
    if not package.is_file():
        raise PreparedIngestError("PACKAGE_MISSING")

    staging = destination.with_name(f".{destination.name}.ingest-{uuid.uuid4().hex}")
    staging.parent.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] | None = None
    manifest_sha256 = ""
    total_bytes = 0
    file_count = 0
    descriptor_count = 0
    dzi: _DziTracker | None = None
    try:
        staging.mkdir()
        with package.open("rb") as source:
            hashing = _HashingReader(source)
            with tarfile.open(fileobj=hashing, mode="r|") as archive:
                members = iter(archive)
                manifest_member = _next_member(members, "manifest.json")
                manifest_bytes = _read_control(
                    archive, manifest_member, MAX_MANIFEST_BYTES
                )
                manifest_hash_member = _next_member(members, "manifest.sha256")
                manifest_hash_bytes = _read_control(archive, manifest_hash_member, 64)
                manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
                if (
                    manifest_hash_bytes.decode("ascii", errors="strict").lower()
                    != manifest_sha256
                    or manifest_sha256 != expected_manifest_sha256.lower()
                ):
                    raise PreparedIngestError("MANIFEST_HASH_MISMATCH")
                try:
                    parsed = json.loads(manifest_bytes)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise PreparedIngestError("INVALID_MANIFEST") from error
                manifest = _validate_manifest(parsed, expected_artifact_revision_id)

                declared, pending_member, declared_count = _declared_files(
                    archive, members, manifest, staging
                )
                for expected_count, expected in enumerate(declared, start=1):
                    if expected_count > MAX_DERIVATIVE_FILES:
                        raise PreparedIngestError("PACKAGE_FILE_LIMIT")
                    member = pending_member or next(members, None)
                    pending_member = None
                    if member is None or member.name != expected.path:
                        raise PreparedIngestError("PACKAGE_INVENTORY_MISMATCH")
                    _validate_payload_member(member, expected)
                    relative = _derivative_relative(member.name)
                    target = staging / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    digest, first_bytes, last_bytes = _extract_payload(
                        archive, member, target
                    )
                    if digest != expected.sha256:
                        raise PreparedIngestError("PACKAGE_PAYLOAD_HASH_MISMATCH")
                    if target.suffix.lower() in {".jpg", ".jpeg"} and not (
                        first_bytes.startswith(b"\xff\xd8")
                        and last_bytes.endswith(b"\xff\xd9")
                    ):
                        raise PreparedIngestError("UNSAFE_DERIVATIVE")
                    if target.suffix.lower() in {".jpg", ".jpeg"} and (
                        relative == Path("thumbnail.jpg")
                        or expected_count == 2
                        or expected_count % max(1, declared_count // 16) == 0
                    ):
                        _decode_jpeg(target)
                    total_bytes += expected.size
                    file_count += 1
                    if relative == Path("slide.dzi"):
                        descriptor_count += 1
                        dzi = _DziTracker.from_descriptor(target, manifest["slide"])
                    elif relative.parts and relative.parts[0] == "slide_files":
                        if dzi is None:
                            raise PreparedIngestError("NON_CANONICAL_PACKAGE_ORDER")
                        dzi.observe(relative)
                if next(members, None) is not None:
                    raise PreparedIngestError("PACKAGE_INVENTORY_MISMATCH")
            hashing.drain()
            if hashing.hexdigest() != expected_package_sha256.lower():
                raise PreparedIngestError("PACKAGE_HASH_MISMATCH")

        if descriptor_count != 1 or manifest is None:
            raise PreparedIngestError("UNSAFE_DERIVATIVE")
        if dzi is None:
            raise PreparedIngestError("UNSAFE_DERIVATIVE")
        dzi.require_complete()
        if os.path.lexists(destination):
            raise PreparedIngestError("DERIVATIVE_ALREADY_EXISTS")
        staging.replace(destination)
        return PreparedIngestResult(
            DerivativeMeasurement(total_bytes, file_count),
            manifest,
            manifest_sha256,
        )
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _next_member(members: Iterator[tarfile.TarInfo], expected: str) -> tarfile.TarInfo:
    member = next(members, None)
    if member is None or member.name != expected:
        raise PreparedIngestError("NON_CANONICAL_PACKAGE_ORDER")
    _validate_regular_member(member)
    return member


def _read_control(
    archive: tarfile.TarFile, member: tarfile.TarInfo, maximum: int
) -> bytes:
    if member.size > maximum:
        raise PreparedIngestError("PACKAGE_CONTROL_FILE_MISSING")
    source = archive.extractfile(member)
    if source is None:
        raise PreparedIngestError("PACKAGE_CONTROL_FILE_MISSING")
    with source:
        value = source.read(maximum + 1)
    if len(value) != member.size:
        raise PreparedIngestError("TRUNCATED_PACKAGE")
    return value


def _declared_files(
    archive: tarfile.TarFile,
    members: Iterator[tarfile.TarInfo],
    manifest: dict[str, Any],
    staging: Path,
) -> tuple[Iterator[_DeclaredFile], tarfile.TarInfo | None, int]:
    inventory = manifest.get("inventory")
    if inventory is None:
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise PreparedIngestError("INVALID_MANIFEST")
        declared = [_declared_file(item) for item in files]
        if declared != sorted(declared, key=lambda item: item.path):
            raise PreparedIngestError("NON_CANONICAL_PACKAGE_ORDER")
        if len({item.path for item in declared}) != len(declared):
            raise PreparedIngestError("DUPLICATE_PACKAGE_PATH")
        return iter(declared), next(members, None), len(declared)

    if not isinstance(inventory, dict) or inventory.get("format") != "ndjson-v1":
        raise PreparedIngestError("INVALID_MANIFEST")
    inventory_path = inventory.get("path")
    if inventory_path != "inventory.ndjson":
        raise PreparedIngestError("INVALID_MANIFEST")
    inventory_member = _next_member(members, inventory_path)
    if inventory_member.size > MAX_INVENTORY_BYTES:
        raise PreparedIngestError("PACKAGE_FILE_LIMIT")
    expected_hash = str(inventory.get("sha256", "")).lower()
    expected_count = int(inventory.get("fileCount", -1))
    expected_bytes = int(inventory.get("derivativeBytes", -1))
    if (
        not _is_sha256(expected_hash)
        or expected_count < 1
        or expected_count > MAX_DERIVATIVE_FILES
        or expected_bytes < 1
    ):
        raise PreparedIngestError("INVALID_MANIFEST")
    inventory_file = staging / ".inventory.ndjson"
    digest, _, _ = _extract_payload(archive, inventory_member, inventory_file)
    if digest != expected_hash:
        raise PreparedIngestError("PACKAGE_INVENTORY_HASH_MISMATCH")
    return (
        _iter_ndjson_inventory(
            inventory_file, expected_count=expected_count, expected_bytes=expected_bytes
        ),
        None,
        expected_count,
    )


def _iter_ndjson_inventory(
    path: Path, *, expected_count: int, expected_bytes: int
) -> Iterator[_DeclaredFile]:
    count = 0
    total = 0
    previous = ""
    try:
        with path.open("r", encoding="utf-8", newline="\n") as source:
            for line in source:
                if not line.endswith("\n"):
                    raise PreparedIngestError("INVALID_PACKAGE_INVENTORY")
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as error:
                    raise PreparedIngestError("INVALID_PACKAGE_INVENTORY") from error
                declared = _declared_file(item)
                if declared.path <= previous:
                    raise PreparedIngestError("NON_CANONICAL_PACKAGE_ORDER")
                previous = declared.path
                count += 1
                total += declared.size
                yield declared
    finally:
        path.unlink(missing_ok=True)
    if count != expected_count or total != expected_bytes:
        raise PreparedIngestError("PACKAGE_INVENTORY_MISMATCH")


def _declared_file(value: Any) -> _DeclaredFile:
    try:
        path = str(value["path"])
        size = int(value["size"])
        sha256 = str(value["sha256"]).lower()
    except (KeyError, TypeError, ValueError) as error:
        raise PreparedIngestError("INVALID_PACKAGE_INVENTORY") from error
    if size < 1 or not _is_sha256(sha256):
        raise PreparedIngestError("INVALID_PACKAGE_INVENTORY")
    _derivative_relative(path)
    return _DeclaredFile(path, size, sha256)


def _validate_regular_member(member: tarfile.TarInfo) -> None:
    if (
        not member.isfile()
        or member.issym()
        or member.islnk()
        or member.uid != 0
        or member.gid != 0
        or member.mtime != 0
    ):
        raise PreparedIngestError("UNSAFE_PACKAGE_ENTRY")


def _validate_payload_member(member: tarfile.TarInfo, expected: _DeclaredFile) -> None:
    _validate_regular_member(member)
    if member.size != expected.size:
        raise PreparedIngestError("PACKAGE_METADATA_MISMATCH")


def _extract_payload(
    archive: tarfile.TarFile, member: tarfile.TarInfo, target: Path
) -> tuple[str, bytes, bytes]:
    source = archive.extractfile(member)
    if source is None:
        raise PreparedIngestError("PACKAGE_ENTRY_MISSING")
    digest = hashlib.sha256()
    first = bytearray()
    tail = bytearray()
    written = 0
    with source, target.open("xb") as output:
        while block := source.read(COPY_BUFFER_BYTES):
            digest.update(block)
            output.write(block)
            written += len(block)
            if len(first) < 4:
                first.extend(block[: 4 - len(first)])
            tail.extend(block)
            if len(tail) > 4:
                del tail[:-4]
    if written != member.size:
        raise PreparedIngestError("TRUNCATED_PACKAGE")
    return digest.hexdigest(), bytes(first), bytes(tail)


def _validate_manifest(manifest: Any, expected_revision: str) -> dict[str, Any]:
    try:
        schema = manifest["schema"]
        provenance = manifest["provenance"]
        slide = manifest["slide"]
        revision = provenance["artifactRevisionId"]
        source_fingerprint = provenance["sourceFingerprint"]
        configuration_revision = provenance["configurationRevision"]
        transform = provenance["coordinateTransform"]
        calibration = provenance["calibration"]
    except (KeyError, TypeError) as error:
        raise PreparedIngestError("INVALID_MANIFEST") from error
    encoding = slide.get("encoding")
    if encoding is not None and (
        not isinstance(encoding, dict)
        or encoding.get("codec") != "jpeg"
        or encoding.get("quality") not in {85, 90, 95}
        or encoding.get("selector") != "quality-gated-v1"
        or encoding.get("qualityProfile") != "pathlab-visual-v1"
    ):
        raise PreparedIngestError("INVALID_MANIFEST")
    if (
        schema != "pathlab-prepared-slide/v2"
        or revision != expected_revision
        or not _is_sha256(str(source_fingerprint))
        or not _is_sha256(str(configuration_revision))
        or int(slide.get("width", 0)) <= 0
        or int(slide.get("height", 0)) <= 0
        or slide.get("tileSize") != 512
        or slide.get("overlap") != 1
        or slide.get("format") != "jpg"
        or not isinstance(transform, dict)
        or not isinstance(calibration, dict)
    ):
        raise PreparedIngestError("INVALID_MANIFEST")
    if not isinstance(manifest, dict):
        raise PreparedIngestError("INVALID_MANIFEST")
    return manifest


def _validate_dzi(path: Path, slide: dict[str, Any]) -> tuple[int, int, int]:
    try:
        root = et.parse(path).getroot()
        size = next(child for child in root if child.tag.rsplit("}", 1)[-1] == "Size")
        tile_size = int(root.attrib["TileSize"])
        overlap = int(root.attrib["Overlap"])
        format_name = root.attrib["Format"]
        width = int(size.attrib["Width"])
        height = int(size.attrib["Height"])
    except (OSError, et.ParseError, KeyError, StopIteration, TypeError, ValueError) as error:
        raise PreparedIngestError("UNSAFE_DERIVATIVE") from error
    if (
        tile_size != 512
        or overlap != 1
        or format_name.lower() not in {"jpg", "jpeg"}
        or width != int(slide["width"])
        or height != int(slide["height"])
    ):
        raise PreparedIngestError("UNSAFE_DERIVATIVE")
    return width, height, tile_size


def _decode_jpeg(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
            if image.width < 1 or image.height < 1:
                raise PreparedIngestError("UNSAFE_DERIVATIVE")
    except (OSError, SyntaxError) as error:
        raise PreparedIngestError("UNSAFE_DERIVATIVE") from error


def _derivative_relative(name: str) -> Path:
    pure = PurePosixPath(name)
    if (
        pure.is_absolute()
        or len(pure.parts) < 2
        or pure.parts[0] != "derivative"
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise PreparedIngestError("UNSAFE_PACKAGE_PATH")
    relative = PurePosixPath(*pure.parts[1:])
    suffix = relative.suffix.lower()
    if suffix not in {".dzi", ".jpg", ".jpeg"}:
        raise PreparedIngestError("UNSAFE_PACKAGE_PATH")
    return Path(*relative.parts)


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdefABCDEF" for character in value
    )
