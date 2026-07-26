#!/usr/bin/env python3
import argparse
import hashlib
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

PUBLIC_ID = re.compile(r"^[A-Za-z0-9_-]+$")
MAX_COMMON_PER_LEVEL = 4
MAX_RANDOM_TOTAL = 256
MAX_RESPONSE_BYTES = 1_048_576


class RemoteManifestError(ValueError):
    pass


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json, application/xml, text/xml"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise RemoteManifestError("Approved public resource was unavailable")
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, urllib.error.URLError) as error:
        raise RemoteManifestError("Unable to fetch approved public resource") from error
    if len(body) > MAX_RESPONSE_BYTES:
        raise RemoteManifestError("Approved public resource exceeded the size limit")
    return body


def _same_origin_path(value: Any, *, suffix: str | None = None) -> str:
    if not isinstance(value, str) or not value.startswith("/"):
        raise RemoteManifestError("Public metadata contained an invalid resource path")
    parsed_value = urllib.parse.urlsplit(value)
    if parsed_value.scheme or parsed_value.netloc or parsed_value.query or parsed_value.fragment:
        raise RemoteManifestError("Public metadata resource must stay on the approved origin")
    if suffix is not None and not parsed_value.path.endswith(suffix):
        raise RemoteManifestError("Public metadata resource had an unexpected path")
    return parsed_value.path


def _score(seed: int, public_id: str, relative: str) -> int:
    payload = f"{seed}:{public_id}:{relative}".encode()
    return int.from_bytes(hashlib.sha256(payload).digest(), "big")


def _level_tiles(
    level: int,
    *,
    width: int,
    height: int,
    max_level: int,
    tile_size: int,
    image_format: str,
) -> list[str]:
    divisor = 2 ** (max_level - level)
    level_width = math.ceil(width / divisor)
    level_height = math.ceil(height / divisor)
    columns = math.ceil(level_width / tile_size)
    rows = math.ceil(level_height / tile_size)
    return [
        f"slide_files/{level}/{column}_{row}.{image_format}"
        for column in range(columns)
        for row in range(rows)
    ]


def _build_slide(base_url: str, public_id: str, seed: int) -> dict[str, Any]:
    if PUBLIC_ID.fullmatch(public_id) is None:
        raise RemoteManifestError("Invalid public ID")
    metadata_url = urllib.parse.urljoin(
        f"{base_url.rstrip('/')}/",
        f"api/v1/public/slides/{urllib.parse.quote(public_id)}",
    )
    try:
        metadata = json.loads(_fetch(metadata_url))
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RemoteManifestError("Public metadata was malformed") from error
    if not isinstance(metadata, dict):
        raise RemoteManifestError("Public metadata was malformed")
    dzi_path = _same_origin_path(metadata.get("tileSource"), suffix="/slide.dzi")
    thumbnail_url = metadata.get("thumbnailUrl")
    if thumbnail_url is not None:
        _same_origin_path(thumbnail_url)
    expected_prefix = f"/tiles/{public_id}/"
    if not dzi_path.startswith(expected_prefix) or "/../" in dzi_path:
        raise RemoteManifestError("Public DZI path did not match the approved slide")
    descriptor_url = urllib.parse.urljoin(f"{base_url.rstrip('/')}/", dzi_path.lstrip("/"))
    try:
        root = ET.fromstring(_fetch(descriptor_url))
    except ET.ParseError as error:
        raise RemoteManifestError("DZI descriptor was malformed") from error
    try:
        tile_size = int(root.attrib["TileSize"])
        image_size = next(child for child in root if child.tag.endswith("Size"))
        width = int(image_size.attrib["Width"])
        height = int(image_size.attrib["Height"])
    except (KeyError, StopIteration, TypeError, ValueError) as error:
        raise RemoteManifestError("DZI descriptor was incomplete") from error
    if not (1 <= tile_size <= 4096 and width > 0 and height > 0):
        raise RemoteManifestError("DZI descriptor dimensions were invalid")
    image_format = root.attrib.get("Format", "").lower()
    if image_format not in {"jpg", "jpeg"}:
        raise RemoteManifestError("DZI descriptor format was unsupported")

    max_level = math.ceil(math.log2(max(width, height)))
    selected_levels = list(range(max_level, max(-1, max_level - 3), -1))
    all_levels = [
        _level_tiles(
            level,
            width=width,
            height=height,
            max_level=max_level,
            tile_size=tile_size,
            image_format=image_format,
        )
        for level in selected_levels
    ]
    random_limit = max(1, MAX_RANDOM_TOTAL // len(all_levels))
    common_tiles: list[str] = []
    random_tiles: list[str] = []
    for tiles in all_levels:
        coordinates = [
            (
                int(path.rsplit("/", 1)[1].split("_", 1)[0]),
                int(path.rsplit("_", 1)[1].split(".", 1)[0]),
                path,
            )
            for path in tiles
        ]
        max_column = max(item[0] for item in coordinates)
        max_row = max(item[1] for item in coordinates)
        common_tiles.extend(
            item[2]
            for item in sorted(
                coordinates,
                key=lambda item: (
                    (item[0] - max_column / 2) ** 2 + (item[1] - max_row / 2) ** 2,
                    item[2],
                ),
            )[:MAX_COMMON_PER_LEVEL]
        )
        random_tiles.extend(
            sorted(
                tiles,
                key=lambda path: (_score(seed, public_id, path), path),
            )[:random_limit]
        )
    return {
        "publicId": public_id,
        "dziPath": "slide.dzi",
        "commonTiles": common_tiles,
        "randomTiles": random_tiles[:MAX_RANDOM_TOTAL],
    }


def generate_remote_manifest(
    base_url: str,
    public_ids: list[str],
    *,
    seed: int = 0,
) -> dict[str, Any]:
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path not in {"", "/"}:
        raise RemoteManifestError("Base URL must be an HTTPS origin")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise RemoteManifestError("Base URL must not contain credentials or parameters")
    if not public_ids:
        raise RemoteManifestError("At least one public ID is required")
    return {
        "slides": [
            _build_slide(base_url.rstrip("/"), public_id, seed)
            for public_id in public_ids
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a public-only viewer load manifest from production metadata"
    )
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--public-id", action="append", required=True, dest="public_ids")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    manifest = generate_remote_manifest(
        args.base_url,
        args.public_ids,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
