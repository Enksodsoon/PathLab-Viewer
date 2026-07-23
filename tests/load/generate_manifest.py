#!/usr/bin/env python3
import argparse
import hashlib
import heapq
import json
import os
import re
import stat
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path
from typing import Any

PUBLIC_ID = re.compile(r"^[A-Za-z0-9_-]+$")
TILE_NAME = re.compile(r"^(?P<column>\d+)_(?P<row>\d+)\.(?:jpg|jpeg)$", re.IGNORECASE)
MAX_COMMON_PER_LEVEL = 4
MAX_RANDOM_TOTAL = 256


class ManifestError(ValueError):
    pass


def _require_directory(path: Path, *, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise ManifestError(f"{label} is missing") from error
    if stat.S_ISLNK(mode):
        raise ManifestError(f"{label} must not be a symlink")
    if not stat.S_ISDIR(mode):
        raise ManifestError(f"{label} must be a directory")


def _require_regular_file(path: Path, *, label: str) -> None:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as error:
        raise ManifestError(f"{label} is missing") from error
    if stat.S_ISLNK(mode):
        raise ManifestError(f"{label} must not be a symlink")
    if not stat.S_ISREG(mode):
        raise ManifestError(f"{label} must be a regular file")


def _tile_entries(level_directory: Path) -> Iterator[os.DirEntry[str]]:
    try:
        entries = os.scandir(level_directory)
    except OSError as error:
        raise ManifestError("Unable to inspect public tiles") from error
    with entries:
        for entry in entries:
            if entry.is_symlink():
                raise ManifestError("Public tile tree contains a symlink")
            if not entry.is_file(follow_symlinks=False):
                raise ManifestError("Public tile tree contains an unexpected entry")
            if TILE_NAME.fullmatch(entry.name) is None:
                raise ManifestError("Public tile tree contains an unexpected filename")
            yield entry


def _score(seed: int, public_id: str, relative: str) -> int:
    payload = f"{seed}:{public_id}:{relative}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def _sample_level(
    level_directory: Path,
    *,
    public_id: str,
    seed: int,
    random_limit: int,
) -> tuple[list[str], list[str]]:
    level = level_directory.name
    max_column = -1
    max_row = -1
    random_heap: list[tuple[int, str]] = []
    for entry in _tile_entries(level_directory):
        match = TILE_NAME.fullmatch(entry.name)
        if match is None:
            raise ManifestError("Public tile tree contains an unexpected filename")
        max_column = max(max_column, int(match.group("column")))
        max_row = max(max_row, int(match.group("row")))
        relative = f"slide_files/{level}/{entry.name}"
        scored = _score(seed, public_id, relative)
        candidate = (-scored, relative)
        if len(random_heap) < random_limit:
            heapq.heappush(random_heap, candidate)
        elif scored < -random_heap[0][0]:
            heapq.heapreplace(random_heap, candidate)
    if max_column < 0 or max_row < 0:
        raise ManifestError("Selected pyramid level has no tiles")

    center_column = max_column / 2
    center_row = max_row / 2
    common: list[tuple[float, str]] = []
    for entry in _tile_entries(level_directory):
        match = TILE_NAME.fullmatch(entry.name)
        if match is None:
            raise ManifestError("Public tile tree contains an unexpected filename")
        column = int(match.group("column"))
        row = int(match.group("row"))
        distance = (column - center_column) ** 2 + (row - center_row) ** 2
        common.append((distance, f"slide_files/{level}/{entry.name}"))
        common.sort()
        del common[MAX_COMMON_PER_LEVEL:]
    return (
        [relative for _, relative in common],
        sorted(relative for _, relative in random_heap),
    )


def _slide_manifest(public_root: Path, public_id: str, seed: int) -> dict[str, Any]:
    if PUBLIC_ID.fullmatch(public_id) is None:
        raise ManifestError("Invalid public ID")
    slide_root = public_root / public_id
    _require_directory(slide_root, label="Public slide directory")
    descriptor = slide_root / "slide.dzi"
    _require_regular_file(descriptor, label="DZI descriptor")
    try:
        ET.parse(descriptor)
    except (ET.ParseError, OSError) as error:
        raise ManifestError("DZI descriptor is malformed") from error
    tile_root = slide_root / "slide_files"
    _require_directory(tile_root, label="DZI tile directory")

    levels: list[int] = []
    for entry in os.scandir(tile_root):
        if entry.is_symlink():
            raise ManifestError("Public tile tree contains a symlink")
        if not entry.is_dir(follow_symlinks=False) or not entry.name.isdigit():
            raise ManifestError("Public tile tree contains an unexpected level")
        levels.append(int(entry.name))
    selected = sorted(levels, reverse=True)[:3]
    if len(selected) < 2:
        raise ManifestError("DZI pyramid must contain multiple levels")
    random_per_level = max(1, MAX_RANDOM_TOTAL // len(selected))
    common_tiles: list[str] = []
    random_tiles: list[str] = []
    for level in selected:
        common, random_sample = _sample_level(
            tile_root / str(level),
            public_id=public_id,
            seed=seed,
            random_limit=random_per_level,
        )
        common_tiles.extend(common)
        random_tiles.extend(random_sample)
    return {
        "publicId": public_id,
        "dziPath": "slide.dzi",
        "commonTiles": common_tiles,
        "randomTiles": random_tiles[:MAX_RANDOM_TOTAL],
    }


def generate_manifest(
    public_root: Path,
    public_ids: list[str],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    _require_directory(public_root, label="Public root")
    if not public_ids:
        raise ManifestError("At least one public ID is required")
    return {"slides": [_slide_manifest(public_root, public_id, seed) for public_id in public_ids]}


def write_manifest(output: Path, manifest: dict[str, Any]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a public-only viewer load manifest")
    parser.add_argument("--public-root", type=Path, required=True)
    parser.add_argument("--public-id", action="append", required=True, dest="public_ids")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    write_manifest(
        args.output,
        generate_manifest(args.public_root, args.public_ids, seed=args.seed),
    )


if __name__ == "__main__":
    main()
