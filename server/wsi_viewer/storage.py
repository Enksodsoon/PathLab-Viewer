import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

GIB = 1024**3


class InsufficientStorage(RuntimeError):
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


def publish_derivative(layout: StorageLayout, slide_id: str, public_id: str) -> Path:
    source = layout.for_slide(slide_id).private_derivative
    if not source.is_dir() or not (source / "slide.dzi").is_file():
        raise FileNotFoundError("Private derivative is not ready")
    target = layout.public_for(public_id)
    staging = target.with_name(f".{target.name}.publish-{uuid.uuid4().hex}")
    staging.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, staging)
    if target.exists():
        unpublish_derivative(layout, public_id)
    staging.replace(target)
    return target


def unpublish_derivative(layout: StorageLayout, public_id: str) -> None:
    target = layout.public_for(public_id)
    if not target.exists():
        return
    tombstone = target.with_name(f".{target.name}.delete-{uuid.uuid4().hex}")
    target.replace(tombstone)
    shutil.rmtree(tombstone)
