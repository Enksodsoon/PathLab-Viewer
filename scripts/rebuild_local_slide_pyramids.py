"""Rebuild local demo DZI pyramids from original whole-slide pixels.

This is intentionally a local maintenance command. It never copies or commits the
source WSI. Derivatives are built beside the current private derivative and are
atomically exchanged after validation.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import openslide
from openslide.deepzoom import DeepZoomGenerator


def _scale_point(point: list[float], sx: float, sy: float) -> list[float]:
    return [float(point[0]) * sx, float(point[1]) * sy]


def _scale_box(box: list[float] | None, sx: float, sy: float) -> list[float] | None:
    if not box:
        return box
    return [float(box[0]) * sx, float(box[1]) * sy, float(box[2]) * sx, float(box[3]) * sy]


def _scale_registration(
    registration: dict[str, Any],
    moving_scale: tuple[float, float],
    reference_scale: tuple[float, float],
) -> None:
    mx, my = moving_scale
    rx, ry = reference_scale
    matrix = registration.get("movingToReference")
    if matrix:
        registration["movingToReference"] = [
            [matrix[0][0] * rx / mx, matrix[0][1] * rx / my, matrix[0][2] * rx],
            [matrix[1][0] * ry / mx, matrix[1][1] * ry / my, matrix[1][2] * ry],
        ]
    registration["movingSupport"] = _scale_box(registration.get("movingSupport"), mx, my)
    registration["referenceSupport"] = _scale_box(registration.get("referenceSupport"), rx, ry)
    for control in registration.get("controlPoints") or []:
        control["moving"] = _scale_point(control["moving"], mx, my)
        control["reference"] = _scale_point(control["reference"], rx, ry)
        if control.get("errorPixels") is not None:
            control["errorPixels"] = float(control["errorPixels"]) * math.sqrt(rx * ry)
    for key in ("triangles", "overviewTriangles"):
        for triangle in registration.get(key) or []:
            triangle["moving"] = [_scale_point(point, mx, my) for point in triangle["moving"]]
            triangle["reference"] = [_scale_point(point, rx, ry) for point in triangle["reference"]]
            if triangle.get("maxResidualPixels") is not None:
                triangle["maxResidualPixels"] = float(triangle["maxResidualPixels"]) * math.sqrt(
                    rx * ry
                )
    polygons = registration.get("supportPolygons") or {}
    polygons["moving"] = [
        [_scale_point(point, mx, my) for point in polygon]
        for polygon in polygons.get("moving") or []
    ]
    polygons["reference"] = [
        [_scale_point(point, rx, ry) for point in polygon]
        for polygon in polygons.get("reference") or []
    ]
    if polygons:
        registration["supportPolygons"] = polygons
    if registration.get("medianErrorPixels") is not None and registration["medianErrorPixels"] >= 0:
        registration["medianErrorPixels"] = float(registration["medianErrorPixels"]) * math.sqrt(
            rx * ry
        )


def _build(
    source: Path,
    staging: Path,
    *,
    tile_size: int,
    quality: int,
    workers: int,
    lazy: bool,
) -> tuple[int, int]:
    slide = openslide.OpenSlide(str(source))
    try:
        generator = DeepZoomGenerator(slide, tile_size=tile_size, overlap=1, limit_bounds=False)
        staging.mkdir(parents=True)
        (staging / "slide.dzi").write_text(generator.get_dzi("jpg"), encoding="utf-8")
        if lazy:
            (staging / ".openslide-source.json").write_text(
                json.dumps(
                    {"source": str(source.resolve()), "tileSize": tile_size, "quality": quality}
                ),
                encoding="utf-8",
            )
            thumbnail = slide.get_thumbnail((640, 640)).convert("RGB")
            thumbnail.save(staging / "thumbnail.jpg", "JPEG", quality=88, subsampling=0)
            return slide.dimensions
        tiles_root = staging / "slide_files"
        total = sum(columns * rows for columns, rows in generator.level_tiles)
        tasks: list[tuple[int, int, int]] = []
        for level, (columns, rows) in enumerate(generator.level_tiles):
            level_root = tiles_root / str(level)
            level_root.mkdir(parents=True)
            for row in range(rows):
                for column in range(columns):
                    tasks.append((level, column, row))

        local = threading.local()

        def render(task: tuple[int, int, int]) -> None:
            if not hasattr(local, "generator"):
                local.slide = openslide.OpenSlide(str(source))
                local.generator = DeepZoomGenerator(
                    local.slide, tile_size=tile_size, overlap=1, limit_bounds=False
                )
            level, column, row = task
            tile = local.generator.get_tile(level, (column, row)).convert("RGB")
            tile.save(
                tiles_root / str(level) / f"{column}_{row}.jpg",
                "JPEG",
                quality=quality,
                subsampling=0,
            )

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="dzi") as executor:
            futures = [executor.submit(render, task) for task in tasks]
            for completed, future in enumerate(as_completed(futures), 1):
                future.result()
                if completed % 250 == 0 or completed == total:
                    print(f"  tiles {completed}/{total}", flush=True)
        thumbnail = slide.get_thumbnail((640, 640)).convert("RGB")
        thumbnail.save(staging / "thumbnail.jpg", "JPEG", quality=88, subsampling=0)
        return slide.dimensions
    finally:
        slide.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--source-root", action="append", type=Path, required=True)
    parser.add_argument("--set", dest="sets", action="append", default=[])
    parser.add_argument("--tile-size", type=int, default=1024)
    parser.add_argument("--quality", type=int, default=92)
    parser.add_argument("--workers", type=int, default=min(8, os.cpu_count() or 1))
    parser.add_argument(
        "--lazy",
        action="store_true",
        help="Create a local on-demand OpenSlide pyramid instead of pre-rendering every tile",
    )
    args = parser.parse_args()

    connection = sqlite3.connect(args.database)
    connection.row_factory = sqlite3.Row
    selected_ids: list[str] = []
    if args.sets:
        for set_id in args.sets:
            row = connection.execute(
                "select member_slide_ids from comparison_sets where id = ?", (set_id,)
            ).fetchone()
            if row is None:
                raise SystemExit(f"Unknown comparison set: {set_id}")
            selected_ids.extend(json.loads(row[0]))
    else:
        selected_ids = [row[0] for row in connection.execute("select id from slides")]
    selected_ids = list(dict.fromkeys(selected_ids))
    placeholders = ",".join("?" for _ in selected_ids)
    slides = {
        row["id"]: dict(row)
        for row in connection.execute(
            "select id, original_filename, slide_metadata from slides "
            f"where id in ({placeholders})",
            selected_ids,
        )
    }
    sources = {
        path.name: path for root in args.source_root for path in root.rglob("*") if path.is_file()
    }
    scale_by_slide: dict[str, tuple[float, float]] = {}
    dimensions_by_slide: dict[str, tuple[int, int]] = {}
    derivative_stats: dict[str, tuple[int, int]] = {}

    for index, slide_id in enumerate(selected_ids, 1):
        row = slides[slide_id]
        source = sources.get(row["original_filename"])
        if source is None:
            raise SystemExit(f"Source is unavailable for {row['original_filename']}")
        destination = args.private_root / slide_id
        staging = destination.with_name(f"{destination.name}.fullres-{os.getpid()}")
        previous = destination.with_name(f"{destination.name}.overview-backup")
        if staging.exists():
            shutil.rmtree(staging)
        print(f"[{index}/{len(selected_ids)}] {slide_id}: {source.name}", flush=True)
        width, height = _build(
            source,
            staging,
            tile_size=args.tile_size,
            quality=args.quality,
            workers=max(1, args.workers),
            lazy=args.lazy,
        )
        metadata = json.loads(row["slide_metadata"] or "{}")
        old_width = float(metadata.get("width") or width)
        old_height = float(metadata.get("height") or height)
        scale_by_slide[slide_id] = (width / old_width, height / old_height)
        dimensions_by_slide[slide_id] = (width, height)
        files = [path for path in staging.rglob("*") if path.is_file()]
        derivative_stats[slide_id] = (sum(path.stat().st_size for path in files), len(files))
        if previous.exists():
            shutil.rmtree(previous)
        destination.replace(previous)
        staging.replace(destination)
        shutil.rmtree(previous)

    for slide_id, (width, height) in dimensions_by_slide.items():
        row = slides[slide_id]
        metadata = json.loads(row["slide_metadata"] or "{}")
        metadata["width"] = width
        metadata["height"] = height
        metadata["originalWidth"] = width
        metadata["originalHeight"] = height
        metadata["overviewLevel"] = 0
        source = sources[row["original_filename"]]
        handle = openslide.OpenSlide(str(source))
        try:
            if handle.properties.get(openslide.PROPERTY_NAME_MPP_X):
                metadata["physicalSizeX"] = float(handle.properties[openslide.PROPERTY_NAME_MPP_X])
            if handle.properties.get(openslide.PROPERTY_NAME_MPP_Y):
                metadata["physicalSizeY"] = float(handle.properties[openslide.PROPERTY_NAME_MPP_Y])
        finally:
            handle.close()
        derivative_bytes, file_count = derivative_stats[slide_id]
        connection.execute(
            "update slides set slide_metadata = ?, derivative_bytes = ?, "
            "derivative_file_count = ? where id = ?",
            (json.dumps(metadata), derivative_bytes, file_count, slide_id),
        )

    for row in connection.execute(
        "select id, reference_slide_id, registrations from comparison_sets"
    ):
        registrations = json.loads(row["registrations"] or "{}")
        changed = False
        for moving_id, registration in registrations.items():
            moving_scale = scale_by_slide.get(moving_id, (1.0, 1.0))
            reference_id = (
                registration.get("coordinateReferenceId")
                or registration.get("anchorSlideId")
                or row["reference_slide_id"]
            )
            reference_scale = scale_by_slide.get(reference_id, (1.0, 1.0))
            if moving_scale != (1.0, 1.0) or reference_scale != (1.0, 1.0):
                _scale_registration(registration, moving_scale, reference_scale)
                changed = True
        if changed:
            connection.execute(
                "update comparison_sets set registrations = ? where id = ?",
                (json.dumps(registrations), row["id"]),
            )
    connection.commit()
    connection.close()
    print("Full-resolution pyramids and coordinate maps committed.", flush=True)


if __name__ == "__main__":
    main()
