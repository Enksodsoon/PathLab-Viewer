"""Capture read-only requests and immutable workspace pixels for operational regression."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import itertools
import json
import math
import os
import re
import shutil
import sqlite3
import time
import xml.etree.ElementTree as ET
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from wsi_viewer.alignment_calibration import metadata_frame_digest, normalized_microns_per_pixel
from wsi_viewer.alignment_geometry import derivative_sampling_geometry
from wsi_viewer.alignment_inputs import immutable_descriptor, pixel_digest


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bounded_probe(path: Path) -> tuple[Any, str]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 16 * 1024**2:
        raise ValueError("candidate admission requires bounded regular probe receipts")
    with path.open("rb") as stream:
        raw = stream.read(16 * 1024**2 + 1)
    if len(raw) > 16 * 1024**2:
        raise ValueError("candidate admission receipt exceeds bound")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _candidate_admissions(
    heavy_path: Path | None, header_path: Path | None
) -> dict[str, dict[str, Any]]:
    if heavy_path is None and header_path is None:
        return {}
    if heavy_path is None or header_path is None:
        raise ValueError("candidate admission requires both probe stages")
    heavy, heavy_sha = _bounded_probe(heavy_path)
    headers, header_sha = _bounded_probe(header_path)
    if (
        not isinstance(heavy, dict)
        or heavy.get("status") != "probe-complete"
        or heavy.get("processContainment") != "windows-job-object"
        or not isinstance(headers, list)
        or not 0 < len(headers) <= 100
        or not heavy.get("sourceHashesAtStart")
        or heavy.get("sourceHashesAtStart") != heavy.get("sourceHashesAtTerminal")
    ):
        raise ValueError("candidate admission lacks complete contained terminal proof")
    for key in ("peakMemoryBytes", "peakCommittedMemoryBytes", "committedMemoryLimitBytes"):
        value = heavy.get(key)
        if type(value) is not int or not 0 < value <= 7 * 1024**3:
            raise ValueError("candidate admission exceeds verified heavy resource boundary")
    if heavy["peakCommittedMemoryBytes"] > heavy["committedMemoryLimitBytes"]:
        raise ValueError("candidate admission exceeded committed-memory bound")
    seconds = heavy.get("wallSeconds")
    if (
        not isinstance(seconds, (int, float))
        or isinstance(seconds, bool)
        or not math.isfinite(seconds)
        or not 0 <= seconds <= 600
    ):
        raise ValueError("candidate admission exceeds verified heavy time boundary")
    by_sha = {row.get("sourceSha256"): row for row in headers if isinstance(row, dict)}
    rows = heavy.get("regionalProof")
    if not isinstance(rows, list) or not 0 < len(rows) <= 100:
        raise ValueError("candidate admission lacks regional proof")
    admitted = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid candidate admission row")
        sha = row.get("sourceSha256EarlierVerified")
        header = by_sha.get(sha, {})
        size, frame = row.get("trueSourceSize"), row.get("returnedFrame")
        if (
            not isinstance(sha, str)
            or re.fullmatch(r"[0-9a-f]{64}", sha) is None
            or not isinstance(size, list)
            or len(size) != 2
            or any(type(axis) is not int or axis <= 0 for axis in size)
            or not isinstance(frame, list)
            or len(frame) != 3
            or frame[:2] != [0, 0]
            or type(frame[2]) is not int
            or frame[2] <= 0
            or frame[2] & (frame[2] - 1)
            or row.get("requestedSourceBounds") != [0, 0, *size]
            or row.get("returnedSize") != [math.ceil(axis / frame[2]) for axis in size]
            or max(row["returnedSize"]) > 2048
            or [row.get(key) for key in ("tileSize", "overlap", "quality")] != [512, 1, 92]
            or row.get("executionBoundary") != "diagnostic-heavy-contained-7GiB-not-foreground"
            or header.get("databaseChecksumMatch") is not True
            or header.get("sourceStatUnchanged") is not True
            or header.get("openslideDimensions") != size
            or header.get("openslideFormat") != "generic-tiff"
            or header.get("openslideBoundedRead", {}).get("size") != [512, 512]
            or not isinstance(header.get("openslideBoundedRead", {}).get("pixelSha256"), str)
            or re.fullmatch(r"[0-9a-f]{64}", header["openslideBoundedRead"]["pixelSha256"]) is None
            or header.get("header", {}).get("isOme") is not True
            or sha in admitted
        ):
            raise ValueError("candidate admission differs from verified bytes/frame/reader profile")
        admitted[sha] = {
            "sourceSize": size,
            "heavyProbeSha256": heavy_sha,
            "headerProbeSha256": header_sha,
            "originalStageVerified": False,
            "maximumAnalysisDimension": 2048,
            "executionBoundary": "alignment-heavy-contained-7GiB-not-foreground",
            "rendering": {"tileSize": 512, "overlap": 1, "quality": 92, "limitBounds": False},
            "testedPyramidDivisor": frame[2],
            "nativeRoiPixelSha256": header["openslideBoundedRead"]["pixelSha256"],
        }
    return admitted


def _verify_candidate_reader(original: Path, expected_size: tuple[int, int]) -> dict[str, Any]:
    """Reverify copied bytes with a native 512-pixel ROI; never decode an overview."""
    openslide = importlib.import_module("openslide")
    before = original.stat()
    slide = openslide.OpenSlide(str(original))
    try:
        if (
            tuple(slide.dimensions) != expected_size
            or openslide.OpenSlide.detect_format(str(original)) != "generic-tiff"
        ):
            raise ValueError("copied candidate reader differs from admitted header")
        pixels = slide.read_region(
            (expected_size[0] // 2, expected_size[1] // 2), 0, (512, 512)
        ).convert("RGB")
        result = {
            "sourceSize": list(slide.dimensions),
            "nativeRoiSize": [512, 512],
            "nativeRoiPixelSha256": hashlib.sha256(pixels.tobytes()).hexdigest(),
        }
    finally:
        slide.close()
    after = original.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ):
        raise ValueError("copied candidate changed during bounded reader verification")
    return result


def _copy_verified(source: Path, target: Path) -> str:
    if source.is_symlink() or not source.is_file():
        raise ValueError("source copy requires a regular local file")
    before = source.stat()
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        for block in iter(lambda: incoming.read(1024 * 1024), b""):
            outgoing.write(block)
            digest.update(block)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    ) or _hash_file(target) != digest.hexdigest():
        raise ValueError("source changed during verified workspace copy")
    return digest.hexdigest()


def capture(database: Path, output: Path) -> dict[str, Any]:
    """SQLite backup supplies one consistent image including committed WAL rows."""
    output.mkdir(parents=True, exist_ok=False)
    captured = output / "capture.sqlite3"
    with (
        closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(captured)) as destination,
    ):
        source.backup(destination)
    with closing(sqlite3.connect(captured)) as connection:
        connection.row_factory = sqlite3.Row
        columns = {row[1] for row in connection.execute("PRAGMA table_info(slides)")}
        render_column = "render_mode" if "render_mode" in columns else "NULL AS render_mode"
        slides = [
            dict(row)
            for row in connection.execute(
                f"SELECT id, sha256, slide_metadata, original_filename, {render_column} "
                "FROM slides ORDER BY id"
            )
        ]
        stacks = [
            dict(row)
            for row in connection.execute(
                "SELECT id, member_slide_ids FROM comparison_sets ORDER BY id"
            )
        ]
    raw = [
        {
            "ordinal": index,
            "stackId": stack["id"],
            "referenceSlideId": reference,
            "movingSlideId": moving,
        }
        for index, (stack, reference, moving) in enumerate(
            (stack, reference, moving)
            for stack in stacks
            for reference, moving in itertools.permutations(
                json.loads(stack["member_slide_ids"]), 2
            )
        )
    ]
    value = {
        "schema": "pathlab-development-source-capture/1",
        "capturedAt": datetime.now(UTC).isoformat(),
        "databaseSha256": _hash_file(captured),
        "slides": slides,
        "stacks": stacks,
        "rawOrderedRequests": raw,
        "sourceMetadataDigest": _digest({"slides": slides, "stacks": stacks}),
    }
    (output / "source-capture.json").write_text(json.dumps(value, indent=2), encoding="utf-8")
    return value


def _source_files(
    directory: Path, data_root: Path, slide: dict[str, Any]
) -> tuple[Path | None, list[Path], dict[str, Any], str]:
    pointer = directory / ".openslide-source.json"
    rendering: dict[str, Any] = {}
    original: Path | None = None
    source_kind = "unavailable"
    if pointer.is_file():
        rendering = json.loads(pointer.read_text(encoding="utf-8"))
        candidate = Path(rendering["source"])
        if candidate.is_absolute() and candidate.is_file():
            original = candidate
            source_kind = "explicit-openslide-pointer"
    if original is None:
        candidate = data_root / "originals" / slide["id"] / "source.ome.tif"
        if candidate.is_file():
            original = candidate
            source_kind = "storage-ome-candidate"
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.name != ".openslide-source.json"
    ]
    if len(files) > 100_000 or any(path.is_symlink() for path in files):
        raise ValueError("derivative inventory exceeds bounded regular files")
    if source_kind == "explicit-openslide-pointer":
        files = [path for path in files if path.name in {"slide.dzi", "thumbnail.jpg"}]
    return original, sorted(files), rendering, source_kind


def _copied_overview_available(root: Path, size: tuple[int, int]) -> bool:
    geometry = derivative_sampling_geometry(root, size, maximum=4096)
    if geometry is None:
        return False
    tree = ET.parse(root / "slide.dzi").getroot()
    tile_size = int(tree.attrib["TileSize"])
    width, height = geometry["analysisSize"]
    return all(
        (
            root
            / "slide_files"
            / str(geometry["selectedLevel"])
            / f"{column}_{row}.{tree.attrib['Format']}"
        ).is_file()
        for row in range(math.ceil(height / tile_size))
        for column in range(math.ceil(width / tile_size))
    )


def _complete_pyramid(root: Path) -> bool:
    descriptor = root / "slide.dzi"
    if not descriptor.is_file():
        return False
    tree = ET.parse(descriptor).getroot()
    size = next(node for node in tree if node.tag.rsplit("}", 1)[-1] == "Size")
    width, height = int(size.attrib["Width"]), int(size.attrib["Height"])
    maximum = math.ceil(math.log2(max(width, height)))
    tile_size = int(tree.attrib["TileSize"])
    for level in range(maximum + 1):
        divisor = 2 ** (maximum - level)
        for row in range(math.ceil(math.ceil(height / divisor) / tile_size)):
            for column in range(math.ceil(math.ceil(width / divisor) / tile_size)):
                if not (
                    root / "slide_files" / str(level) / f"{column}_{row}.{tree.attrib['Format']}"
                ).is_file():
                    return False
    return True


def _original_calibration(
    original: Path, expected_size: tuple[int, int]
) -> tuple[float, float] | None:
    openslide = importlib.import_module("openslide")
    slide = openslide.OpenSlide(str(original))
    try:
        if tuple(slide.dimensions) != expected_size:
            raise ValueError("verified original dimensions differ from captured frame")
        return normalized_microns_per_pixel(
            {
                "physicalSizeX": slide.properties.get(openslide.PROPERTY_NAME_MPP_X),
                "physicalSizeY": slide.properties.get(openslide.PROPERTY_NAME_MPP_Y),
                "physicalSizeUnit": "um",
            }
        )
    finally:
        slide.close()


def deduplicate(captured: dict[str, Any], sources: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pairs: list[dict[str, Any]] = []
    indices: dict[tuple[str, str], int] = {}
    mapping = []
    for request in captured["rawOrderedRequests"]:
        reference, moving = (sources[request[key]] for key in ("referenceSlideId", "movingSlideId"))
        key = (reference["contentFrameDigest"], moving["contentFrameDigest"])
        if key[0] == key[1]:
            mapping.append({**request, "pairIndex": None, "reason": "identical-content-self-pair"})
            continue
        if key not in indices:
            indices[key] = len(pairs)
            pairs.append(
                {
                    "kind": "positive",
                    "reference": reference["manifestSide"],
                    "moving": moving["manifestSide"],
                    "landmarks": [],
                    "landmarksFitFree": False,
                    "independentlyReviewed": False,
                    "developmentStacks": [],
                }
            )
        index = indices[key]
        pairs[index]["developmentStacks"].append(request["stackId"])
        mapping.append({**request, "pairIndex": index})
    return {
        "schema": "pathlab-development-stacks/2",
        "purpose": "ordered-pair-operational-regression-without-independent-ground-truth",
        "qualificationEligible": False,
        "sourceMetadataDigest": captured["sourceMetadataDigest"],
        "requestedOrderedPairs": len(mapping),
        "deduplicatedOrderedPairs": len(pairs),
        "contentIdenticalSelfRequestsExcluded": sum(row["pairIndex"] is None for row in mapping),
        "rawRequestMapping": mapping,
        "pairs": pairs,
        "settings": {},
    }


def _load_fallback_overview(root: Path, size: tuple[int, int]) -> tuple[Any, dict[str, Any]]:
    from PIL import Image

    with Image.open(root / "thumbnail.jpg") as opened:
        image = opened.convert("RGB")
    image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
    return image, {
        "schema": "pathlab-sampling-frame/1",
        "kind": "thumbnail-fallback",
        "sourceSize": list(size),
        "analysisSize": list(image.size),
        "coordinateFrameSize": list(size),
        "samplingScale": [size[0] / image.width, size[1] / image.height],
        "cropOrigin": [0, 0],
    }


def prepare(
    database: Path,
    data_root: Path,
    output: Path,
    *,
    storage_budget_bytes: int = 24 * 1024**3,
    tile_cache_budget_bytes: int = 8 * 1024**3,
    storage_candidate_admission: Path | None = None,
    storage_candidate_headers: Path | None = None,
) -> dict[str, Any]:
    from wsi_viewer.worker import _load_dzi_overview, _process_rss_bytes

    started = time.monotonic()
    admissions = _candidate_admissions(storage_candidate_admission, storage_candidate_headers)
    captured = capture(database, output)
    needed = {
        request[key]
        for request in captured["rawOrderedRequests"]
        for key in ("referenceSlideId", "movingSlideId")
    }
    plans = []
    for slide in captured["slides"]:
        if slide["id"] not in needed:
            continue
        if not re.fullmatch(r"[A-Za-z0-9_-]+", slide["id"]):
            raise ValueError("invalid captured source identifier")
        directory = data_root / "private" / slide["id"]
        original, files, rendering, source_kind = _source_files(directory, data_root, slide)
        plans.append((slide, directory, original, files, rendering, source_kind))
    required = (
        sum(
            (original.stat().st_size if original else 0)
            + sum(path.stat().st_size for path in files)
            + 64 * 1024**2
            for _, _, original, files, _, _ in plans
        )
        + tile_cache_budget_bytes
    )
    if required > storage_budget_bytes or required + 4 * 1024**3 > shutil.disk_usage(output).free:
        raise ValueError("immutable snapshot storage preflight failed")
    sources: dict[str, dict[str, Any]] = {}
    preparation: list[dict[str, Any]] = []
    for slide, directory, original, files, rendering, source_kind in plans:
        tick = time.monotonic()
        root = output / "sources" / slide["id"]
        root.mkdir(parents=True)
        metadata = json.loads(slide["slide_metadata"])
        size = (int(metadata["width"]), int(metadata["height"]))
        copied = []
        for path in files:
            name = path.relative_to(directory).as_posix()
            copied.append({"name": name, "sha256": _copy_verified(path, root / name)})
        original_info: dict[str, Any] = {
            "verified": False,
            "reason": "original-unavailable",
            "databaseDeclaredSha256": slide["sha256"],
        }
        region: dict[str, Any] = {
            "available": False,
            "kind": "copied-dzi-incomplete",
            "files": copied,
            "reason": "complete-regional-pyramid-unavailable",
        }
        if original is not None:
            name = (
                "original" + original.suffix.lower()
                if source_kind == "explicit-openslide-pointer"
                else "stored-candidate.ome.tif"
            )
            sha = _copy_verified(original, root / name)
            if (
                source_kind == "explicit-openslide-pointer"
                and slide["sha256"]
                and sha != slide["sha256"]
            ):
                raise ValueError("original pixels differ from captured source digest")
            original_info = {
                "verified": source_kind == "explicit-openslide-pointer",
                "kind": source_kind,
                "file": name,
                "sha256": sha,
                "databaseDeclaredSha256": slide["sha256"],
                "databaseChecksumMatch": sha == slide["sha256"] if slide["sha256"] else None,
                "copiedBytesVerified": True,
            }
            if source_kind == "storage-ome-candidate":
                original_info["reason"] = "stored-candidate-original-stage-unverified"
        if source_kind == "explicit-openslide-pointer":
            tile_size, quality = (
                int(rendering.get("tileSize", 1024)),
                int(rendering.get("quality", 92)),
            )
            if not 128 <= tile_size <= 1024 or not 1 <= quality <= 100:
                raise ValueError("immutable regional rendering exceeds bounded tile profile")
            (root / ".openslide-source.json").write_text(
                json.dumps(
                    {
                        "source": str((root / name).resolve()),
                        "tileSize": tile_size,
                        "quality": quality,
                    }
                ),
                encoding="utf-8",
            )
            region = {
                "available": True,
                "kind": "openslide-original",
                "file": name,
                "sha256": sha,
                "descriptorSha256": _hash_file(root / "slide.dzi"),
                "rendering": {
                    "tileSize": tile_size,
                    "quality": quality,
                    "overlap": 1,
                    "limitBounds": False,
                },
                "tileCacheLimitBytes": tile_cache_budget_bytes // max(1, len(plans)),
            }
        elif source_kind == "storage-ome-candidate" and sha in admissions:
            admission = admissions[sha]
            tree = ET.parse(root / "slide.dzi").getroot()
            dzi_size = next(node for node in tree if node.tag.rsplit("}", 1)[-1] == "Size")
            if (
                admission["sourceSize"] != list(size)
                or original_info["databaseChecksumMatch"] is not True
                or tree.attrib.get("TileSize") != "512"
                or tree.attrib.get("Overlap") != "1"
                or tree.attrib.get("Format") != "jpg"
                or [int(dzi_size.attrib[axis]) for axis in ("Width", "Height")] != list(size)
            ):
                raise ValueError("candidate admission differs from copied source/DZI frame")
            reader = _verify_candidate_reader(root / name, size)
            if (
                reader["nativeRoiPixelSha256"] != admission["nativeRoiPixelSha256"]
                or tile_cache_budget_bytes <= 0
            ):
                raise ValueError(
                    "candidate admission differs from bounded reader pixels/cache budget"
                )
            admission_value = {
                **admission,
                "copiedSourceSha256": sha,
                "copiedReaderVerification": reader,
            }
            (root / "candidate-admission.json").write_text(
                json.dumps(admission_value, indent=2), encoding="utf-8"
            )
            (root / ".openslide-source.json").write_text(
                json.dumps(
                    {"source": str((root / name).resolve()), "tileSize": 512, "quality": 92}
                ),
                encoding="utf-8",
            )
            region = {
                "available": True,
                "kind": "verified-openslide-candidate",
                "file": name,
                "sha256": sha,
                "descriptorSha256": _hash_file(root / "slide.dzi"),
                "rendering": admission["rendering"],
                "admissionFile": "candidate-admission.json",
                "admissionSha256": _hash_file(root / "candidate-admission.json"),
                "maximumAnalysisDimension": 2048,
                "executionBoundary": admission["executionBoundary"],
                "tileCacheLimitBytes": tile_cache_budget_bytes // max(1, len(plans)),
            }
        elif _complete_pyramid(root):
            region = {"available": True, "kind": "copied-dzi", "files": copied}
        copy_seconds = time.monotonic() - tick
        overview_started = time.monotonic()
        try:
            if region["kind"] == "verified-openslide-candidate" or (
                source_kind != "explicit-openslide-pointer"
                and not _copied_overview_available(root, size)
            ):
                raise FileNotFoundError("copied bounded overview level is incomplete")
            image = _load_dzi_overview(root, maximum=4096)
            geometry = image.info["alignmentGeometry"]
        except (FileNotFoundError, OSError, ET.ParseError):
            image, geometry = _load_fallback_overview(root, size)
        overview_kind = geometry["kind"]
        pixels = pixel_digest(image)
        geometry = {**geometry, "kind": "immutable-overview", "snapshotPixelSha256": pixels}
        image.save(root / "overview.png", "PNG")
        mpp = normalized_microns_per_pixel(metadata)
        original_mpp = (
            _original_calibration(root / region["file"], size)
            if original_info["verified"]
            else None
        )
        calibration_source = (
            "captured-normalized-metadata" if mpp else "uncalibrated-missing-or-unknown-unit"
        )
        if mpp is None and original_mpp is not None:
            mpp = original_mpp
            calibration_source = "verified-original-openslide-mpp-properties"
        descriptor = {
            "schema": "pathlab-immutable-overview/1",
            "image": "overview.png",
            "imageSha256": _hash_file(root / "overview.png"),
            "pixelSha256": pixels,
            "overviewSourceKind": overview_kind,
            "geometry": geometry,
            "regionSource": region,
            "originalSource": original_info,
            "capturedRenderMode": slide["render_mode"],
            "calibration": {
                "micronsPerPixel": list(mpp) if mpp else None,
                "source": calibration_source,
                "verifiedOriginalMicronsPerPixel": list(original_mpp) if original_mpp else None,
                "metadataFrameDigest": metadata_frame_digest(metadata),
                "rawMetadata": metadata,
            },
            "tissueCrop": False,
            "inputScope": "immutable-wsi-regional-source"
            if region["available"]
            else "immutable-overview-regional-source-unavailable",
        }
        (root / "immutable-overview.json").write_text(
            json.dumps(descriptor, indent=2), encoding="utf-8"
        )
        immutable_descriptor(root, source_size=size)
        side = {"path": str(root.resolve()), "size": list(size), "tissueCrop": False}
        if mpp:
            side["micronsPerPixel"] = list(mpp)
        semantic = {
            "pixels": pixels,
            "geometry": geometry,
            "calibration": list(mpp) if mpp else None,
            "tissueCrop": False,
            "regional": region,
            "copiedSourceContent": {
                "kind": original_info["kind"],
                "sha256": original_info["sha256"],
            }
            if original_info.get("copiedBytesVerified") is True
            else None,
        }
        sources[slide["id"]] = {
            "manifestSide": side,
            "contentFrameDigest": _digest(semantic),
            "descriptorDigest": _digest(descriptor),
        }
        preparation.append(
            {
                "sourceOrdinal": len(preparation),
                "copyAndHashSeconds": copy_seconds,
                "overviewAndVerificationSeconds": time.monotonic() - overview_started,
                "originalVerified": original_info["verified"],
                "originalCandidatePresent": original is not None,
                "originalCandidateKind": source_kind,
                "regionalSourceAvailable": region["available"],
                "workerLifetimePeakRssBytes": _process_rss_bytes(os.getpid(), peak=True),
                "memoryMeasurementScope": "snapshot-preparation-process-lifetime-high-water",
            }
        )
        print(
            json.dumps({"preparedSources": len(sources), "plannedSources": len(plans)}), flush=True
        )
    manifest = deduplicate(captured, sources)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "source-bindings.json").write_text(json.dumps(sources, indent=2), encoding="utf-8")
    receipt = {
        "sourceMetadataDigest": captured["sourceMetadataDigest"],
        "sourceCount": len(sources),
        "originalVerifiedCount": sum(row["originalVerified"] for row in preparation),
        "missingOriginalCount": sum(not row["originalCandidatePresent"] for row in preparation),
        "unverifiedOriginalStageCount": sum(not row["originalVerified"] for row in preparation),
        "storageCandidateCount": sum(
            row["originalCandidateKind"] == "storage-ome-candidate" for row in preparation
        ),
        "manifestSha256": _hash_file(output / "manifest.json"),
        "wallSeconds": time.monotonic() - started,
        "storagePreflightBytes": required,
        "preparation": preparation,
    }
    (output / "preparation-receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--storage-budget-bytes", type=int, default=24 * 1024**3)
    parser.add_argument("--tile-cache-budget-bytes", type=int, default=8 * 1024**3)
    parser.add_argument("--storage-candidate-admission", type=Path)
    parser.add_argument("--storage-candidate-headers", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            prepare(
                args.database,
                args.data_root,
                args.output,
                storage_budget_bytes=args.storage_budget_bytes,
                tile_cache_budget_bytes=args.tile_cache_budget_bytes,
                storage_candidate_admission=args.storage_candidate_admission,
                storage_candidate_headers=args.storage_candidate_headers,
            )
        )
    )


if __name__ == "__main__":
    main()
