from __future__ import annotations

import argparse
import io
import json
from pathlib import Path
from typing import Any

from PIL import Image
from wsi_viewer.ome_tile_index import OmeTileIndex, build_ome_tile_index, read_indexed_jpeg


def _sample_positions(total: int, count: int) -> tuple[int, ...]:
    if total <= count:
        return tuple(range(total))
    return tuple((index * (total - 1)) // (count - 1) for index in range(count))


def _decode_samples(path: Path, index: OmeTileIndex, count: int = 32) -> tuple[int, int]:
    flattened = tuple(tile for level in index.levels for tile in level.tiles)
    failures = 0
    positions = _sample_positions(len(flattened), min(count, len(flattened)))
    for position in positions:
        try:
            with Image.open(io.BytesIO(read_indexed_jpeg(path, flattened[position]))) as image:
                image.load()
                if image.mode not in {"RGB", "YCbCr"}:
                    failures += 1
        except Exception:
            failures += 1
    return len(positions), failures


def inspect(path: Path) -> dict[str, Any]:
    index = build_ome_tile_index(path)
    decoded_samples, decode_failures = _decode_samples(path, index)
    complete_factor_two = index.pyramid_factors == tuple(
        2**level for level in range(len(index.pyramid_factors))
    )
    return {
        "schema": "pathlab.ome-tile-layout/v1",
        "source": str(path.resolve()),
        "sourceBytes": index.source_size,
        "sourceSha256": index.source_sha256,
        "width": index.width,
        "height": index.height,
        "codec": index.codec,
        "levels": len(index.levels),
        "levelDimensions": [
            {"width": level.width, "height": level.height} for level in index.levels
        ],
        "pyramidFactors": list(index.pyramid_factors),
        "completeFactorTwoPyramid": complete_factor_two,
        "tileWidth": index.tile_width,
        "tileHeight": index.tile_height,
        "rawFastPathSupported": index.standalone_jpeg,
        "requiresJpegTableAssembly": not index.standalone_jpeg,
        "decodedSamples": decoded_samples,
        "decodeFailures": decode_failures,
        "dynamicProfileConformant": (
            complete_factor_two
            and index.tile_width == 512
            and index.tile_height == 512
            and decode_failures == 0
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a Forge OME tile layout")
    parser.add_argument("--ome", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    arguments = parser.parse_args()
    result = inspect(arguments.ome)
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    main()
