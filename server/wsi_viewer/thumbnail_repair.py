"""Bounded recovery of legacy overview images from an existing DZI pyramid."""

import io
import os
import uuid
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image

from .storage import PublicationError


def recovered_thumbnail(root: Path) -> bytes | None:
    """Read one complete low-resolution tile; never reconstruct the full WSI."""
    if root.resolve() != root.absolute():
        raise PublicationError("UNSAFE_THUMBNAIL")
    thumbnail = root / "thumbnail.jpg"
    if os.path.lexists(thumbnail):
        if thumbnail.is_symlink() or not thumbnail.is_file():
            raise PublicationError("UNSAFE_THUMBNAIL")
        return None
    descriptor = root / "slide.dzi"
    try:
        if root.is_symlink() or descriptor.is_symlink() or descriptor.stat().st_size > 65536:
            raise ValueError("Unsafe descriptor")
        document = ElementTree.fromstring(descriptor.read_bytes())
        size = next(child for child in document if child.tag.rsplit("}", 1)[-1] == "Size")
        width, height = int(size.attrib["Width"]), int(size.attrib["Height"])
        tile_size = int(document.attrib["TileSize"])
        extension = document.attrib["Format"]
        if (
            not 0 < width <= 2**31
            or not 0 < height <= 2**31
            or not 128 <= tile_size <= 2048
            or extension not in {"jpg", "jpeg"}
        ):
            raise ValueError("Unsupported descriptor")
        maximum_level = (max(width, height) - 1).bit_length()
        level = min(maximum_level, min(tile_size, 640).bit_length() - 1)
        divisor = 1 << (maximum_level - level)
        expected_size = ((width + divisor - 1) // divisor, (height + divisor - 1) // divisor)
        tile = root / "slide_files" / str(level) / f"0_0.{extension}"
        if (
            any(parent.is_symlink() for parent in (tile, tile.parent, tile.parent.parent))
            or tile.stat().st_size > 4 * 1024 * 1024
        ):
            raise ValueError("Unsafe overview tile")
        with Image.open(tile) as image:
            if image.format != "JPEG" or image.size != expected_size:
                raise ValueError("Overview dimensions do not match the DZI")
            output = io.BytesIO()
            image.convert("RGB").save(output, "JPEG", quality=85)
            return output.getvalue()
    except (OSError, ValueError, KeyError, StopIteration, ElementTree.ParseError) as error:
        raise PublicationError("THUMBNAIL_RECOVERY_UNAVAILABLE") from error


def install_thumbnail(root: Path, payload: bytes) -> None:
    """Publish atomically without replacing an existing image."""
    temporary = root / f".thumbnail-repair-{uuid.uuid4().hex}"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, root / "thumbnail.jpg", follow_symlinks=False)
    finally:
        temporary.unlink(missing_ok=True)


def link_repaired_thumbnail(source: Path, target: Path) -> None:
    """Extend an existing matching grant without changing its URL or tiles."""
    if source.resolve() != source.absolute() or target.resolve() != target.absolute():
        raise PublicationError("UNSAFE_THUMBNAIL")
    thumbnail = target / "thumbnail.jpg"
    if os.path.lexists(thumbnail):
        if thumbnail.is_symlink() or not thumbnail.is_file():
            raise PublicationError("UNSAFE_THUMBNAIL")
        return
    descriptor = target / "slide.dzi"
    if (
        target.is_symlink()
        or descriptor.is_symlink()
        or descriptor.stat().st_size > 65536
        or descriptor.read_bytes() != (source / "slide.dzi").read_bytes()
    ):
        raise PublicationError("THUMBNAIL_DELIVERY_MISMATCH")
    os.link(source / "thumbnail.jpg", thumbnail, follow_symlinks=False)
