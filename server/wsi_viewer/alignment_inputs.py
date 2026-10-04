"""Bounded, fail-closed immutable overview inputs and regional pixel bindings."""

from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image

from .alignment import AlignmentRejected

DESCRIPTOR_NAME = "immutable-overview.json"
MAX_DESCRIPTOR_BYTES = 1024 * 1024
MAX_OVERVIEW_BYTES = 64 * 1024 * 1024


def pixel_digest(image: Image.Image) -> str:
    return hashlib.sha256(
        image.mode.encode() + str(image.size).encode() + image.tobytes()
    ).hexdigest()


def _safe_file(root: Path, name: Any) -> Path:
    if not isinstance(name, str) or not name or "\\" in name:
        raise AlignmentRejected("invalid immutable input filename")
    candidate = root / name
    if Path(name).is_absolute() or ".." in Path(name).parts:
        raise AlignmentRejected("invalid immutable input filename")
    if candidate.is_symlink() or not candidate.is_file():
        raise AlignmentRejected("immutable input file unavailable")
    if not candidate.resolve().is_relative_to(root.resolve()):
        raise AlignmentRejected("immutable input file escapes its snapshot")
    return candidate


@lru_cache(maxsize=256)
def _file_digest(path: str, size: int, mtime_ns: int, ctime_ns: int) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    after = Path(path).stat()
    if (after.st_size, after.st_mtime_ns, after.st_ctime_ns) != (size, mtime_ns, ctime_ns):
        raise AlignmentRejected("immutable input changed during digest verification")
    return digest.hexdigest()


def verify_file(root: Path, name: Any, expected: Any, *, maximum: int | None = None) -> Path:
    if not isinstance(expected, str) or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        raise AlignmentRejected("invalid immutable input digest")
    path = _safe_file(root, name)
    stat = path.stat()
    if maximum is not None and stat.st_size > maximum:
        raise AlignmentRejected("immutable input exceeds its bounded size")
    if (
        _file_digest(str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        != expected
    ):
        raise AlignmentRejected("immutable input digest mismatch")
    return path


def immutable_descriptor(
    root: Path, *, source_size: tuple[int, int] | None = None
) -> dict[str, Any]:
    from .alignment_geometry import validate_sampling_geometry

    path = _safe_file(root, DESCRIPTOR_NAME)
    if path.stat().st_size > MAX_DESCRIPTOR_BYTES:
        raise AlignmentRejected("immutable descriptor exceeds its bounded size")
    with path.open("rb") as stream:
        raw = stream.read(MAX_DESCRIPTOR_BYTES + 1)
    if len(raw) > MAX_DESCRIPTOR_BYTES:
        raise AlignmentRejected("immutable descriptor exceeds its bounded size")
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as error:
        raise AlignmentRejected("invalid immutable input descriptor") from error
    if not isinstance(value, dict) or value.get("schema") != "pathlab-immutable-overview/1":
        raise AlignmentRejected("invalid immutable input schema")
    geometry = validate_sampling_geometry(value.get("geometry"), source_size=source_size)
    if geometry["kind"] != "immutable-overview":
        raise AlignmentRejected("invalid immutable overview geometry")
    if value.get("pixelSha256") != geometry.get("snapshotPixelSha256"):
        raise AlignmentRejected("immutable pixel digest differs from sampling provenance")
    original = value.get("originalSource", {})
    if isinstance(original, dict) and original.get("copiedBytesVerified") is True:
        verify_file(root, original.get("file"), original.get("sha256"))
    image_path = verify_file(
        root, value.get("image"), value.get("imageSha256"), maximum=MAX_OVERVIEW_BYTES
    )
    with Image.open(image_path) as image:
        if (
            max(image.size) > 4096
            or min(image.size) <= 0
            or list(image.size) != geometry["analysisSize"]
        ):
            raise AlignmentRejected("immutable overview differs from its bounded geometry")
        if image.mode != "RGB":
            raise AlignmentRejected("immutable overview requires explicit RGB pixels")
    region = value.get("regionSource")
    if not isinstance(region, dict) or type(region.get("available")) is not bool:
        raise AlignmentRejected("invalid immutable regional source provenance")
    if region.get("kind") in {"copied-dzi", "copied-dzi-incomplete"}:
        files = region.get("files")
        if not isinstance(files, list) or not files or len(files) > 100_000:
            raise AlignmentRejected("invalid immutable regional tile inventory")
        for item in files:
            if not isinstance(item, dict):
                raise AlignmentRejected("invalid immutable regional tile inventory")
            verify_file(root, item.get("name"), item.get("sha256"))
    if region["available"]:
        if region.get("kind") in {"openslide-original", "verified-openslide-candidate"}:
            original = verify_file(root, region.get("file"), region.get("sha256"))
            verify_file(root, "slide.dzi", region.get("descriptorSha256"))
            pointer = _safe_file(root, ".openslide-source.json")
            if pointer.stat().st_size > 64 * 1024:
                raise AlignmentRejected("invalid immutable regional loader binding")
            try:
                loader = json.loads(pointer.read_text(encoding="utf-8"))
            except (ValueError, UnicodeDecodeError) as error:
                raise AlignmentRejected("invalid immutable regional loader binding") from error
            rendering = region.get("rendering", {})
            if Path(str(loader.get("source", ""))).resolve() != original.resolve() or any(
                loader.get(key) != rendering.get(key) for key in ("tileSize", "quality")
            ):
                raise AlignmentRejected(
                    "immutable regional loader binding differs from its admitted source"
                )
            tile_size, quality = rendering.get("tileSize"), rendering.get("quality")
            if (
                type(tile_size) is not int
                or not 128 <= tile_size <= 1024
                or type(quality) is not int
                or not 1 <= quality <= 100
            ):
                raise AlignmentRejected("immutable regional rendering exceeds bounded tile profile")
            if region["kind"] == "verified-openslide-candidate":
                admission_path = verify_file(
                    root,
                    region.get("admissionFile"),
                    region.get("admissionSha256"),
                    maximum=MAX_DESCRIPTOR_BYTES,
                )
                with admission_path.open("rb") as stream:
                    admission = json.loads(stream.read(MAX_DESCRIPTOR_BYTES + 1))
                if (
                    not isinstance(admission, dict)
                    or region.get("executionBoundary")
                    != "alignment-heavy-contained-7GiB-not-foreground"
                    or region.get("maximumAnalysisDimension") != 2048
                    or admission.get("maximumAnalysisDimension") != 2048
                    or admission.get("executionBoundary") != region["executionBoundary"]
                    or admission.get("copiedSourceSha256") != region["sha256"]
                    or admission.get("sourceSize") != geometry["sourceSize"]
                    or admission.get("rendering") != rendering
                    or admission.get("originalStageVerified") is not False
                    or any(
                        not isinstance(admission.get(key), str)
                        or re.fullmatch(r"[0-9a-f]{64}", admission[key]) is None
                        for key in ("heavyProbeSha256", "headerProbeSha256", "nativeRoiPixelSha256")
                    )
                    or not isinstance(admission.get("copiedReaderVerification"), dict)
                    or admission["copiedReaderVerification"].get("sourceSize")
                    != geometry["sourceSize"]
                    or admission["copiedReaderVerification"].get("nativeRoiSize") != [512, 512]
                    or admission["copiedReaderVerification"].get("nativeRoiPixelSha256")
                    != admission["nativeRoiPixelSha256"]
                    or value.get("overviewSourceKind") != "thumbnail-fallback"
                    or [tile_size, rendering.get("overlap"), quality] != [512, 1, 92]
                    or not isinstance(value.get("originalSource"), dict)
                    or value["originalSource"].get("verified") is not False
                    or value["originalSource"].get("sha256") != region["sha256"]
                ):
                    raise AlignmentRejected(
                        "immutable candidate differs from its heavy-only admission"
                    )
        elif region.get("kind") == "copied-dzi":
            pass  # Its complete inventory was verified above.
        else:
            raise AlignmentRejected("invalid immutable regional source kind")
    return value


def load_immutable_overview(root: Path) -> Image.Image:
    descriptor = immutable_descriptor(root)
    with Image.open(root / descriptor["image"]) as opened:
        image = opened.copy()
    if pixel_digest(image) != descriptor["pixelSha256"]:
        raise AlignmentRejected("immutable pixel digest mismatch")
    image.info["alignmentGeometry"] = descriptor["geometry"]
    return image


def require_snapshot_region_limit(root: Path, maximum: int) -> None:
    if not (root / DESCRIPTOR_NAME).exists():
        return
    region = immutable_descriptor(root)["regionSource"]
    if not region["available"]:
        raise AlignmentRejected("immutable regional source unavailable")
    if region.get("kind") == "verified-openslide-candidate" and maximum > 2048:
        raise AlignmentRejected("immutable candidate exceeds admitted regional analysis bound")


def require_snapshot_tile_capacity(root: Path, *, tile_bytes: int = 4 * 1024**2) -> None:
    if not (root / DESCRIPTOR_NAME).exists():
        return
    descriptor = immutable_descriptor(root)
    region = descriptor["regionSource"]
    if not region["available"]:
        raise AlignmentRejected("immutable regional source unavailable")
    limit = region.get("tileCacheLimitBytes")
    if region.get("kind") in {"openslide-original", "verified-openslide-candidate"}:
        if type(limit) is not int or limit <= 0:
            raise AlignmentRejected("immutable regional cache budget unavailable")
        used = sum(
            path.stat().st_size for path in (root / "slide_files").rglob("*") if path.is_file()
        )
        if used + tile_bytes > limit:
            raise AlignmentRejected("immutable regional tile cache storage budget exceeded")
