"""Freeze fit-free public CIMA/BIRL screening inputs from checked-out datasets.

No registration or landmark fitting is performed. These uncalibrated public
samples provide development evidence, not final evaluation or clinical claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import shutil
import subprocess
from pathlib import Path

from PIL import Image


def prepare(sources: Path, output: Path) -> Path:
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    birl = sources / "BIRL" / "data-images"
    histology = sources / "histology-landmarks"

    def image(path: Path) -> dict:
        directory = output / path.stem
        directory.mkdir(exist_ok=True)
        shutil.copy2(path, directory / "thumbnail.jpg")
        with Image.open(path) as opened:
            return {"path": str(directory), "size": list(opened.size)}

    def points(path: Path, scale: float) -> dict:
        with path.open(encoding="utf-8") as source:
            return {row[0]: [float(row[1]) * scale, float(row[2]) * scale]
                    for row in list(csv.reader(source))[1:]}

    def pair(reference: Path, moving: Path, reference_csv: Path,
             moving_csv: Path, scale: float) -> dict:
        ref, mov = image(reference), image(moving)
        rp, mp = points(reference_csv, scale), points(moving_csv, scale)
        common = set(rp) & set(mp)
        if len(common) < 3:
            raise ValueError("insufficient corresponding published landmark identities")
        landmarks = []
        for key in sorted(common, key=int):
            for point, slide in ((rp[key], ref), (mp[key], mov)):
                if not all(0 <= value < bound for value, bound in
                           zip(point, slide["size"], strict=True)):
                    raise ValueError("landmark is outside its published image frame")
            landmarks.append({"eligible": True, "referencePoint": rp[key],
                              "movingPoint": mp[key], "referenceSize": ref["size"],
                              "wrongStructure": False})
        return {"kind": "positive", "reference": ref, "moving": mov,
                "landmarksFitFree": True, "independentlyReviewed": True,
                "landmarks": landmarks,
                "unmatchedPublishedLandmarks": len(set(rp) ^ set(mp))}

    images = sorted((histology / "dataset/lung-lesion_3/scale-5pc").glob("*.jpg"))
    if len(images) != 5:
        raise ValueError("expected five published lung-lesion_3 stain images")
    annotations = histology / "annotations/lung-lesion_3/user-PS_scale-50pc"
    pairs = [pair(a, b, annotations / f"{a.stem}.csv", annotations / f"{b.stem}.csv", .1)
             for a, b in itertools.combinations(images, 2)]
    for tissue in ("rat-kidney_", "lesions_"):
        samples = sorted((birl / tissue / "scale-5pc").glob("*.jpg"))
        if len(samples) != 2:
            raise ValueError("expected two BIRL histology sample images")
        pairs.append(pair(samples[0], samples[1], samples[0].with_suffix(".csv"),
                          samples[1].with_suffix(".csv"), 1))
    kidney = pairs[-2]
    for ref, mov in ((kidney["reference"], image(images[0])),
                     (kidney["moving"], image(images[1])),
                     (image(images[2]), kidney["reference"]),
                     (image(images[3]), kidney["moving"])):
        pairs.append({"kind": "negative", "reference": ref, "moving": mov,
                      "landmarks": [], "landmarksFitFree": True,
                      "independentlyReviewed": True})
    manifest = {"schema": "pathlab-public-screening/1",
                "purpose": "development-screening-not-final-evaluation",
                "calibration": "unavailable-relative-error-only",
                "landmarkSources": "Published CIMA ImageJ annotation;50pc to5pc factor0.1; "
                                   "BIRL landmarks same5pc image frame",
                "sources": {name: subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=sources / name, text=True).strip()
                    for name in ("BIRL", "histology-landmarks")},
                "pairs": pairs, "settings": {}}
    destination = output / "public-screening.json"
    if destination.exists():
        raise FileExistsError("use a fresh output directory; frozen manifests are immutable")
    destination.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(hashlib.sha256(destination.read_bytes()).hexdigest())
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sources", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare(args.sources, args.output)
