"""Seed synthetic metadata or alignment derivatives in the disposable QA database."""

import hashlib
import json
import math
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from sqlalchemy import select
from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Slide
from wsi_viewer.storage import StorageLayout


def qa_settings() -> Settings:
    if os.environ.get("PATHLAB_ENVIRONMENT") != "test":
        raise RuntimeError("Only the disposable fullstack launcher may seed QA records")
    settings = Settings()
    root = Path(settings.data_root).resolve().parent
    # Never accept an arbitrary configured database or a production target.
    expected = f"sqlite:///{(root / 'database.sqlite3').as_posix()}"
    if not root.name.startswith("pathlab-fullstack-") or settings.database_url != expected:
        raise RuntimeError("Only the disposable fullstack launcher may seed QA records")
    return settings


def seed_alignment(settings: Settings) -> None:
    layout = StorageLayout(settings.data_root)
    image = Image.new("RGB", (640, 480), "white")
    draw = ImageDraw.Draw(image)
    draw.polygon([(60, 80), (500, 50), (570, 350), (110, 420)], fill=(210, 135, 180))
    for x, y in np.random.default_rng(42).integers([100, 100], [490, 350], (400, 2)):
        draw.ellipse((int(x), int(y), int(x + 5), int(y + 5)), fill=(70, 35, 95))
    ids = [f"alignment-qa-{index:02d}" for index in range(12)]
    with session_factory(settings)() as database:
        for index, slide_id in enumerate(ids):
            if database.get(Slide, slide_id):
                continue
            moved = Image.new("RGB", image.size, "white")
            moved.paste(image, (index * 2, index))
            derivative = layout.for_slide(slide_id).private_derivative
            derivative.mkdir(parents=True, exist_ok=True)
            moved.save(derivative / "thumbnail.jpg")
            (derivative / "slide.dzi").write_text(
                '<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
                'TileSize="256" Overlap="1" Format="jpeg">'
                '<Size Width="640" Height="480"/></Image>'
            )
            maximum = math.ceil(math.log2(max(image.size)))
            for level in range(maximum + 1):
                divisor = 2 ** (maximum - level)
                small = moved.resize((math.ceil(640 / divisor), math.ceil(480 / divisor)))
                root = derivative / "slide_files" / str(level)
                root.mkdir(parents=True, exist_ok=True)
                for row in range(math.ceil(small.height / 256)):
                    for column in range(math.ceil(small.width / 256)):
                        small.crop(
                            (
                                max(0, column * 256 - 1),
                                max(0, row * 256 - 1),
                                min(small.width, (column + 1) * 256 + 1),
                                min(small.height, (row + 1) * 256 + 1),
                            )
                        ).save(root / f"{column}_{row}.jpeg", quality=95)
            database.add(
                Slide(
                    id=slide_id,
                    public_id=f"synthetic-{slide_id}",
                    display_name=f"Alignment QA {index:02d}",
                    original_filename=f"synthetic-{index}.ome.tif",
                    source_bytes=1,
                    sha256=hashlib.sha256(moved.tobytes()).hexdigest(),
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={
                        "width": 640,
                        "height": 480,
                        "physicalSizeX": 0.5,
                        "physicalSizeY": 0.5,
                    },
                    organ_site="Synthetic",
                    stain="QA",
                    tags=["alignment-qa"],
                )
            )
        database.commit()
    print(json.dumps({"slideIds": ids, "syntheticPixels": True}))


def main() -> None:
    settings = qa_settings()
    if sys.argv[1] == "alignment":
        seed_alignment(settings)
        return
    count = int(sys.argv[1])
    if count not in (0, 1, 100, 1000):
        raise ValueError("Unsupported QA fixture size")
    with session_factory(settings)() as database:
        existing = database.scalars(select(Slide).where(Slide.id.like("frontend-qa-%"))).all()
        if len(existing) > count:
            raise RuntimeError("Fixture sizes must increase; no fixture deletion during a campaign")
        for index in range(len(existing), count):
            database.add(
                Slide(
                    id=f"frontend-qa-{index:04d}",
                    display_name=f"Frontend QA {index:04d}",
                    original_filename=f"synthetic-{index:04d}.ome.tif",
                    source_bytes=0,
                    state=SlideState.FAILED,
                    error_code="QA_SYNTHETIC_METADATA",
                    error_message="Metadata-only QA fixture; no imaging data",
                    organ_site="Synthetic",
                    stain="QA",
                    tags=["frontend-qa"],
                )
            )
        database.commit()
    print(json.dumps({"seeded": count, "imagingData": False}))


if __name__ == "__main__":
    main()
