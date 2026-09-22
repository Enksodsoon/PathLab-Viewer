"""Local overview benchmark; excludes queue/browser time and is not accuracy qualification.

Optional private manifest: [{"slides": [{"source": "hash", "path": "derivative",
"size": [width, height]}]}]. First slide is the reference. Receipts omit paths/identities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from wsi_viewer.alignment import AlignmentRejected
from wsi_viewer.alignment_fast import PREPARATION_VERSION, PreparationCache, register_prepared
from wsi_viewer.alignment_pyramid import read_region
from wsi_viewer.worker import _process_rss_bytes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()
    cv2.setNumThreads(1)
    cv2.setRNGSeed(0)
    rng = np.random.default_rng(42)
    base = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(base)
    draw.polygon([(60, 80), (500, 50), (570, 350), (110, 420)], fill=(210, 135, 180))
    for x, y in rng.integers([100, 100], [490, 350], (400, 2)):
        draw.ellipse((int(x), int(y), int(x + 5), int(y + 5)), fill=(70, 35, 95))
    stacks = (
        json.loads(args.manifest.read_text())
        if args.manifest
        else [
            {"slides": [{"source": str(i), "size": list(base.size)} for i in range(n)]}
            for n in (2, 4, 8, 12)
        ]
    )
    records = []
    for stack_index, stack in enumerate(stacks):
        for repeat in range(args.repeats):
            cache = PreparationCache()
            for mode in ("cold", "warm"):
                start = time.perf_counter()
                prepared = []
                hits = 0
                reasons = []
                for index, slide in enumerate(stack["slides"]):
                    size = tuple(slide["size"])
                    scale = None
                    if "path" in slide:
                        scale = 1
                        while max(size) / scale > 1024:
                            scale *= 2

                        def load(slide=slide, size=size):
                            return read_region(Path(slide["path"]), (0, 0, *size), maximum=1024)[0]
                    else:

                        def load(index=index):
                            image = Image.new("RGB", base.size, "white")
                            image.paste(base, (index * 2, index))
                            return image

                    try:
                        value, hit = cache.prepare(
                            slide["source"], load, size, sampling_scale=scale
                        )
                        prepared.append(value)
                        hits += int(hit)
                    except (AlignmentRejected, OSError, ValueError) as error:
                        prepared.append(None)
                        reasons.append(str(error))
                preparation_seconds = time.perf_counter() - start
                accepted = 0
                for moving in prepared[1:]:
                    try:
                        if prepared[0] is None or moving is None:
                            raise AlignmentRejected("preparation failed")
                        result = register_prepared(prepared[0], moving)
                        accepted += bool(result.overview_triangles or result.triangles)
                    except AlignmentRejected as error:
                        reasons.append(str(error))
                records.append(
                    {
                        "stack": stack_index,
                        "slides": len(prepared),
                        "repeat": repeat,
                        "cache": mode,
                        "preparationCacheHits": hits,
                        "preparationSeconds": preparation_seconds,
                        "totalComputeSeconds": time.perf_counter() - start,
                        "acceptedOverviewPairs": accepted,
                        "eligiblePairs": len(prepared) - 1,
                        "sampledRssBytes": _process_rss_bytes(os.getpid()),
                        "processLifetimePeakRssBytes": _process_rss_bytes(os.getpid(), peak=True),
                        "rejections": reasons,
                    }
                )
    payload = {
        "preparationVersion": PREPARATION_VERSION,
        "pythonVersion": platform.python_version(),
        "platform": platform.platform(),
        "opencvVersion": cv2.__version__,
        "inputDigest": hashlib.sha256(
            json.dumps(
                [[(s["source"], s["size"]) for s in stack["slides"]] for stack in stacks],
                sort_keys=True,
            ).encode()
        ).hexdigest(),
        "scope": "single-thread local compute; no queue, startup, browser, or landmark accuracy",
        "synthetic": args.manifest is None,
        "records": records,
    }
    args.output.write_text(json.dumps(payload, indent=2))
    for index in range(len(stacks)):
        rows = [r for r in records if r["stack"] == index]
        print(
            json.dumps(
                {
                    "stack": index,
                    "slides": rows[0]["slides"],
                    "computeP95Seconds": float(
                        np.percentile([r["totalComputeSeconds"] for r in rows], 95)
                    ),
                    "acceptedOverviewPairs": sum(r["acceptedOverviewPairs"] for r in rows),
                    "eligiblePairRuns": sum(r["eligiblePairs"] for r in rows),
                    "maxSampledRssBytes": max(r["sampledRssBytes"] for r in rows),
                }
            )
        )


if __name__ == "__main__":
    main()
