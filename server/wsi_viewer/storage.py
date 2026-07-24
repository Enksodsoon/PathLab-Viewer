import os
import shutil
import stat
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3


class InsufficientStorage(RuntimeError):
    pass


class PublicationError(RuntimeError):
    pass


def admission_required(source_bytes: int) -> int:
    if source_bytes <= 0:
        raise ValueError("Source length must be positive")
    return source_bytes + 3 * source_bytes + 5 * GIB


@dataclass(frozen=True)
class SlidePaths:
    original: Path
    derivative_staging: Path
    private_derivative: Path
    public_derivative: Path


@dataclass(frozen=True)
class DerivativeMeasurement:
    derivative_bytes: int
    file_count: int


class StorageLayout:
    def __init__(self, root: Path, cap_bytes: int = 120 * GIB) -> None:
        self.root = root
        self.cap_bytes = cap_bytes

    def for_slide(self, slide_id: str) -> SlidePaths:
        allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        if not slide_id or any(character not in allowed for character in slide_id):
            raise ValueError("Invalid generated slide id")
        return SlidePaths(
            original=self.root / "originals" / slide_id / "source.ome.tif",
            derivative_staging=self.root / "staging" / slide_id,
            private_derivative=self.root / "private" / slide_id,
            public_derivative=self.root / "public" / slide_id,
        )

    def usage(self) -> int:
        total = 0
        for directory, _, files in os.walk(self.root):
            for filename in files:
                total += (Path(directory) / filename).stat().st_size
        return total

    def require_admission(
        self,
        source_bytes: int,
        *,
        free_bytes: int | None = None,
        current_usage: int | None = None,
    ) -> int:
        required = admission_required(source_bytes)
        disk_free = free_bytes if free_bytes is not None else shutil.disk_usage(self.root).free
        used = current_usage if current_usage is not None else self.usage()
        if disk_free < required:
            raise InsufficientStorage(f"Upload needs {required} bytes; disk has {disk_free} free")
        if used + required > self.cap_bytes:
            raise InsufficientStorage("Upload would exceed the 120 GB application storage cap")
        return required

    def public_for(self, public_id: str) -> Path:
        allowed = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_"
        if not public_id or any(character not in allowed for character in public_id):
            raise ValueError("Invalid generated public id")
        return self.root / "public" / public_id

    def public_tile(self, public_id: str, tile_path: str) -> Path:
        root = self.public_for(public_id).resolve()
        target = (root / tile_path).resolve()
        if not target.is_relative_to(root) or target.suffix.lower() not in {
            ".dzi",
            ".jpg",
            ".jpeg",
        }:
            raise FileNotFoundError("Public tile was not found")
        if not target.is_file():
            raise FileNotFoundError("Public tile was not found")
        return target


def publish_derivative(layout: StorageLayout, slide_id: str, public_id: str) -> Path:
    source = layout.for_slide(slide_id).private_derivative
    if not source.exists():
        raise FileNotFoundError("Private derivative is not ready")
    measure_derivative(source)
    target = layout.public_for(public_id)
    staging = target.with_name(f".{target.name}.publish-{uuid.uuid4().hex}")
    previous = target.with_name(f".{target.name}.previous-{uuid.uuid4().hex}")
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        staging.mkdir()
        for source_file, relative in _iter_derivative_files(source):
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.link(source_file, destination, follow_symlinks=False)
        measure_derivative(staging)
    except PublicationError:
        _remove_entry(staging)
        raise
    except OSError as error:
        _remove_entry(staging)
        raise PublicationError("PUBLICATION_LINK_FAILED") from error
    had_target = os.path.lexists(target)
    if had_target:
        target.replace(previous)
    try:
        staging.replace(target)
    except OSError as error:
        if had_target and os.path.lexists(previous) and not os.path.lexists(target):
            previous.replace(target)
        _remove_entry(staging)
        raise PublicationError("PUBLICATION_SWAP_FAILED") from error
    _remove_entry(previous)
    return target


def unpublish_derivative(layout: StorageLayout, public_id: str) -> None:
    target = layout.public_for(public_id)
    if not os.path.lexists(target):
        return
    tombstone = target.with_name(f".{target.name}.delete-{uuid.uuid4().hex}")
    target.replace(tombstone)
    _remove_entry(tombstone)


def _remove_entry(path: Path) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        path.unlink()
    else:
        shutil.rmtree(path)


def _iter_derivative_files(root: Path) -> Iterator[tuple[Path, Path]]:
    try:
        root_mode = root.lstat().st_mode
    except FileNotFoundError as error:
        raise PublicationError("UNSAFE_DERIVATIVE") from error
    if stat.S_ISLNK(root_mode) or not stat.S_ISDIR(root_mode):
        raise PublicationError("UNSAFE_DERIVATIVE")
    pending = [(root, Path())]
    while pending:
        directory, relative_root = pending.pop()
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as error:
            raise PublicationError("UNSAFE_DERIVATIVE") from error
        for entry in entries:
            relative = relative_root / entry.name
            if entry.is_symlink():
                raise PublicationError("UNSAFE_DERIVATIVE")
            if entry.is_dir(follow_symlinks=False):
                pending.append((Path(entry.path), relative))
                continue
            if not entry.is_file(follow_symlinks=False):
                raise PublicationError("UNSAFE_DERIVATIVE")
            if Path(entry.name).suffix.lower() not in {".dzi", ".jpg", ".jpeg"}:
                raise PublicationError("UNSAFE_DERIVATIVE")
            yield Path(entry.path), relative


def measure_derivative(root: Path) -> DerivativeMeasurement:
    total = 0
    count = 0
    descriptors: list[Path] = []
    for path, relative in _iter_derivative_files(root):
        try:
            size = path.stat(follow_symlinks=False).st_size
        except OSError as error:
            raise PublicationError("UNSAFE_DERIVATIVE") from error
        total += size
        count += 1
        if path.suffix.lower() == ".dzi":
            descriptors.append(relative)
    if descriptors != [Path("slide.dzi")]:
        raise PublicationError("UNSAFE_DERIVATIVE")
    return DerivativeMeasurement(total, count)
