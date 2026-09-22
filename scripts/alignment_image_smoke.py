"""ARM64 alignment image smoke test with real engine execution."""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from wsi_viewer.alignment import AlignmentRejected, map_registration_point
from wsi_viewer.alignment_engines import ENGINE_NATIVE, engine_availability
from wsi_viewer.alignment_fast import PreparationCache, register_prepared
from wsi_viewer.worker import _run_alignment_bounded


def synthetic_pair() -> tuple[Image.Image, Image.Image]:
    reference = Image.new("RGB", (600, 420), "white")
    drawing = ImageDraw.Draw(reference)
    drawing.ellipse((70, 50, 530, 370), fill=(220, 155, 185), outline=(60, 40, 90), width=7)
    for x in range(110, 500, 35):
        for y in range(90, 340, 35):
            drawing.ellipse((x, y, x + 7, y + 7), fill=(65, 45, 110))
    moving = Image.new("RGB", reference.size, "white")
    moving.paste(reference, (15, 0))
    return reference, moving


def main() -> None:
    availability = engine_availability()
    assert availability[ENGINE_NATIVE]["available"], availability
    reference, moving = synthetic_pair()
    with tempfile.TemporaryDirectory(prefix="pathlab-alignment-smoke-") as temporary:
        root = Path(temporary)
        cache = PreparationCache()
        fixed, _ = cache.prepare("fixed", reference, (1200, 840))
        floating, _ = cache.prepare("floating", moving, (1200, 840))
        result = register_prepared(fixed, floating).as_json()
        assert result["status"] == "approximate" and not result["triangles"]
        # Exercise coordinate round trip using the published approximate cells.
        overview = {**result, "triangles": result["overviewTriangles"]}
        moving_triangle = overview["triangles"][0]["moving"]
        point = tuple(np.mean(np.asarray(moving_triangle), axis=0))
        mapped = map_registration_point(overview, *point)
        restored = map_registration_point(overview, *mapped, inverse=True)
        assert np.linalg.norm(np.asarray(restored) - point) < 0.5

        reference_dir = root / "reference"
        moving_dir = root / "moving"
        reference_dir.mkdir()
        moving_dir.mkdir()
        reference.save(reference_dir / "thumbnail.jpg")
        moving.save(moving_dir / "thumbnail.jpg")
        try:
            _run_alignment_bounded(
                reference_dir,
                moving_dir,
                reference.size,
                moving.size,
                engine_name=ENGINE_NATIVE,
                timeout_seconds=60,
                memory_bytes=1,
            )
        except AlignmentRejected as error:
            assert "memory ceiling" in str(error)
        else:
            raise AssertionError("memory ceiling was not enforced")


if __name__ == "__main__":
    main()
