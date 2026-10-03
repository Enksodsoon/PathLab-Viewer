"""Freeze deduplicated ordered development pairs without changing the slide database."""
from __future__ import annotations

import argparse
import itertools
import json
import sqlite3
from pathlib import Path


def prepare(database: Path, private_slides: Path, output: Path) -> dict:
    if output.exists():
        raise FileExistsError("use a fresh output; development manifests are immutable")
    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        slides = {row["id"]: dict(row) for row in connection.execute(
            "SELECT id, sha256, slide_metadata FROM slides")}
        stacks = list(connection.execute(
            "SELECT id, member_slide_ids FROM comparison_sets ORDER BY id"))
    finally:
        connection.close()
    pairs: dict[tuple[str, str], dict] = {}
    requested = 0

    def slide(slide_id: str) -> dict:
        metadata = json.loads(slides[slide_id]["slide_metadata"])
        directory = private_slides.resolve() / slide_id
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        return {"path": str(directory), "size": [metadata["width"], metadata["height"]],
                "micronsPerPixel": [metadata.get("physicalSizeX"), metadata.get("physicalSizeY")]}

    for stack in stacks:
        for reference, moving in itertools.permutations(json.loads(stack["member_slide_ids"]), 2):
            requested += 1
            key = (slides[reference]["sha256"] or reference, slides[moving]["sha256"] or moving)
            if key in pairs:
                pairs[key]["developmentStacks"].append(stack["id"])
                continue
            pairs[key] = {"kind": "positive", "reference": slide(reference),
                          "moving": slide(moving), "landmarks": [],
                          "landmarksFitFree": False, "independentlyReviewed": False,
                          "developmentStacks": [stack["id"]]}
    manifest = {"schema": "pathlab-development-stacks/1",
                "purpose": "ordered-pair-regression-without-independent-ground-truth",
                "requestedOrderedPairs": requested, "deduplicatedOrderedPairs": len(pairs),
                "qualificationEligible": False, "pairs": list(pairs.values()), "settings": {}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {key: manifest[key] for key in ("requestedOrderedPairs", "deduplicatedOrderedPairs")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--private-slides", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.database, args.private_slides, args.output)))


if __name__ == "__main__":
    main()
