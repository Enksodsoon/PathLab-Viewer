from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy import select
from wsi_viewer.config import Settings
from wsi_viewer.database import session_factory
from wsi_viewer.domain import SlideState
from wsi_viewer.models import Cohort, Folder, Slide
from wsi_viewer.publication import INDIVIDUAL, delivery_version, ensure_grant
from wsi_viewer.storage import (
    StorageLayout,
    measure_derivative,
    publish_derivative,
    publish_individual_derivative,
)

DEMO_FOLDER_NAME = "Thoracic Pathology — Classroom Demo"
DEMO_SUBFOLDER_NAME = "Core teaching set"
DEMO_MARKER = "pathlab-local-classroom-demo-v1"
WIDTH = 1280
HEIGHT = 896
TILE_SIZE = 256

SLIDES = (
    {
        "case_id": "DEMO-THORAX-01",
        "name": "Synthetic H&E — Tissue overview",
        "organ": "Lung",
        "diagnosis": "Synthetic teaching overview",
        "seed": 17,
        "accent": (119, 67, 133),
    },
    {
        "case_id": "DEMO-THORAX-02",
        "name": "Synthetic H&E — Glandular pattern",
        "organ": "Thorax",
        "diagnosis": "Synthetic glandular teaching pattern",
        "seed": 29,
        "accent": (88, 68, 145),
    },
    {
        "case_id": "DEMO-THORAX-03",
        "name": "Synthetic H&E — Inflammatory field",
        "organ": "Lung",
        "diagnosis": "Synthetic inflammatory teaching pattern",
        "seed": 43,
        "accent": (139, 61, 105),
    },
)

STRESS_MODULES = (
    "Cardiovascular system", "Respiratory system", "Gastrointestinal system", "Hepatobiliary system",
    "Renal and urinary system", "Endocrine system", "Nervous system", "Musculoskeletal system",
    "Skin and soft tissue", "Breast pathology", "Female reproductive system", "Male reproductive system",
    "Hematolymphoid system", "Head and neck", "Ophthalmic pathology", "Pediatric pathology",
    "Placental pathology", "Molecular pathology", "Cytopathology", "Autopsy pathology",
    "Transplant pathology", "Infectious disease", "Environmental pathology",
    "Integrated clinicopathologic correlation with an intentionally long folder name",
)


def synthetic_histology(spec: dict[str, object]) -> Image.Image:
    rng = random.Random(int(spec["seed"]))
    image = Image.new("RGB", (WIDTH, HEIGHT), (251, 230, 235))
    draw = ImageDraw.Draw(image, "RGBA")

    for _ in range(85):
        x = rng.randint(-80, WIDTH)
        y = rng.randint(-80, HEIGHT)
        rx = rng.randint(45, 180)
        ry = rng.randint(28, 120)
        fill = rng.choice(((236, 139, 177, 55), (191, 105, 163, 48), (246, 170, 184, 45)))
        draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=fill)

    accent = tuple(spec["accent"])
    for _ in range(420):
        x = rng.randint(12, WIDTH - 12)
        y = rng.randint(12, HEIGHT - 12)
        r = rng.randint(3, 8)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=(*accent, rng.randint(110, 210)))

    for _ in range(18):
        x = rng.randint(70, WIDTH - 70)
        y = rng.randint(70, HEIGHT - 70)
        rx = rng.randint(34, 88)
        ry = rng.randint(22, 64)
        draw.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(250, 239, 241, 220), outline=(*accent, 165), width=6)

    image = image.filter(ImageFilter.GaussianBlur(radius=0.55))
    draw = ImageDraw.Draw(image, "RGBA")
    banner = "SYNTHETIC TEACHING DEMO  •  NOT FOR DIAGNOSIS"
    font = ImageFont.load_default(size=18)
    draw.rounded_rectangle((24, HEIGHT - 58, 548, HEIGHT - 18), radius=9, fill=(32, 27, 29, 210))
    draw.text((40, HEIGHT - 47), banner, fill=(255, 244, 240, 255), font=font)
    return image


def write_deep_zoom(image: Image.Image, root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    max_level = math.ceil(math.log2(max(image.size)))
    tile_root = root / "slide_files"
    for level in range(max_level + 1):
        divisor = 2 ** (max_level - level)
        level_size = (
            max(1, math.ceil(image.width / divisor)),
            max(1, math.ceil(image.height / divisor)),
        )
        level_image = image.resize(level_size, Image.Resampling.LANCZOS)
        level_dir = tile_root / str(level)
        level_dir.mkdir(parents=True, exist_ok=True)
        columns = math.ceil(level_size[0] / TILE_SIZE)
        rows = math.ceil(level_size[1] / TILE_SIZE)
        for column in range(columns):
            for row in range(rows):
                left = column * TILE_SIZE
                top = row * TILE_SIZE
                tile = level_image.crop(
                    (left, top, min(left + TILE_SIZE, level_size[0]), min(top + TILE_SIZE, level_size[1]))
                )
                tile.save(level_dir / f"{column}_{row}.jpg", "JPEG", quality=82, optimize=True)
    descriptor = (
        f'<Image TileSize="{TILE_SIZE}" Overlap="0" Format="jpg" '
        'xmlns="http://schemas.microsoft.com/deepzoom/2008">'
        f'<Size Width="{image.width}" Height="{image.height}" /></Image>'
    )
    (root / "slide.dzi").write_text(descriptor, encoding="utf-8")
    thumbnail = image.copy()
    thumbnail.thumbnail((420, 294), Image.Resampling.LANCZOS)
    thumbnail.save(root / "thumbnail.jpg", "JPEG", quality=84, optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed a local synthetic slide set for Classroom inspection")
    parser.add_argument("--class-id", required=True, help="Assessment class/cohort to receive the demo folder")
    parser.add_argument("--stress-folders", action="store_true", help="Add a large nested folder tree for browser testing")
    args = parser.parse_args()

    settings = Settings()
    storage = StorageLayout(settings.data_root, settings.storage_cap_bytes)
    factory = session_factory(settings)
    now = datetime.now(UTC).replace(tzinfo=None)

    with factory() as database:
        classroom = database.get(Cohort, args.class_id)
        if classroom is None:
            raise SystemExit(f"Class not found: {args.class_id}")

        folder = database.scalar(select(Folder).where(Folder.parent_id.is_(None), Folder.normalized_name == DEMO_FOLDER_NAME.casefold()))
        if folder is None:
            folder = Folder(
                name=DEMO_FOLDER_NAME,
                normalized_name=DEMO_FOLDER_NAME.casefold(),
                description=f"Local synthetic teaching slides for Classroom inspection. {DEMO_MARKER}",
            )
            database.add(folder)
            database.flush()
        elif DEMO_MARKER not in folder.description:
            raise SystemExit(f'A non-demo folder already uses the name "{DEMO_FOLDER_NAME}"')

        slide_folder = database.scalar(select(Folder).where(
            Folder.parent_id == folder.id,
            Folder.normalized_name == DEMO_SUBFOLDER_NAME.casefold(),
        ))
        if slide_folder is None:
            slide_folder = Folder(
                parent_id=folder.id,
                name=DEMO_SUBFOLDER_NAME,
                normalized_name=DEMO_SUBFOLDER_NAME.casefold(),
                description=f"Synthetic classroom slides. {DEMO_MARKER}",
            )
            database.add(slide_folder)
            database.flush()
        elif DEMO_MARKER not in slide_folder.description:
            raise SystemExit(f'A non-demo subfolder already uses the name "{DEMO_SUBFOLDER_NAME}"')

        stress_folder_count = 0
        if args.stress_folders:
            for module_index, module_name in enumerate(STRESS_MODULES, start=1):
                module = database.scalar(select(Folder).where(
                    Folder.parent_id == folder.id,
                    Folder.normalized_name == module_name.casefold(),
                ))
                if module is None:
                    module = Folder(
                        parent_id=folder.id,
                        name=module_name,
                        normalized_name=module_name.casefold(),
                        description=f"Folder-browser stress fixture. {DEMO_MARKER}",
                        sort_order=module_index,
                    )
                    database.add(module)
                    database.flush()
                elif DEMO_MARKER not in module.description:
                    raise SystemExit(f'A non-demo folder already uses the name "{module_name}"')
                stress_folder_count += 1
                for unit_index in range(1, 5):
                    unit_name = f"Teaching unit {unit_index:02d} — cases, references, and review material"
                    unit = database.scalar(select(Folder).where(
                        Folder.parent_id == module.id,
                        Folder.normalized_name == unit_name.casefold(),
                    ))
                    if unit is None:
                        unit = Folder(
                            parent_id=module.id,
                            name=unit_name,
                            normalized_name=unit_name.casefold(),
                            description=f"Nested folder-browser stress fixture. {DEMO_MARKER}",
                            sort_order=unit_index,
                        )
                        database.add(unit)
                    elif DEMO_MARKER not in unit.description:
                        raise SystemExit(f'A non-demo folder already uses the name "{unit_name}"')
                    stress_folder_count += 1

        seeded: list[Slide] = []
        for position, spec in enumerate(SLIDES):
            slide = database.scalar(select(Slide).where(Slide.case_id == spec["case_id"]))
            if slide is None:
                image = synthetic_histology(spec)
                encoded = image.tobytes()
                slide = Slide(
                    display_name=str(spec["name"]),
                    original_filename=f"{spec['case_id'].lower()}.synthetic.ome.tif",
                    source_bytes=len(encoded),
                    sha256=hashlib.sha256(encoded).hexdigest(),
                    state=SlideState.READY_PRIVATE,
                    slide_metadata={"width": WIDTH, "height": HEIGHT, "synthetic": True, "demoMarker": DEMO_MARKER},
                    folder_id=slide_folder.id,
                    description="Synthetic pathology-style image generated locally for UI and Classroom inspection.",
                    case_id=str(spec["case_id"]),
                    organ_site=str(spec["organ"]),
                    stain="Synthetic H&E palette",
                    diagnosis=str(spec["diagnosis"]),
                    course="PATH 301",
                    tags=["synthetic", "teaching-demo", "non-diagnostic"],
                    teaching_note="Use this synthetic field to inspect navigation, zoom, slide switching, and Classroom controls.",
                    admin_notes=f"Generated locally by {DEMO_MARKER}.",
                    thumbnail_filename="thumbnail.jpg",
                    privacy_status="passed",
                    privacy_scanned_at=now,
                    sort_order=position,
                    render_mode="static_dzi",
                )
                database.add(slide)
                database.flush()

                paths = storage.for_slide(slide.id)
                paths.original.parent.mkdir(parents=True, exist_ok=True)
                image.save(paths.original, "TIFF", compression="tiff_lzw")
                write_deep_zoom(image, paths.private_derivative)
                measurement = measure_derivative(paths.private_derivative)
                slide.derivative_bytes = measurement.derivative_bytes
                slide.derivative_file_count = measurement.file_count
                ensure_grant(database, storage, slide, INDIVIDUAL, slide.id)
            elif DEMO_MARKER not in (slide.admin_notes or ''):
                raise SystemExit(f"Demo case {spec['case_id']} already exists outside the demo folder")
            else:
                slide.folder_id = slide_folder.id

            # Demo databases are frequently copied between local worktrees without
            # their generated var/private assets. Rebuild the deterministic source,
            # DZI pyramid, and thumbnail whenever the database row outlives its files.
            paths = storage.for_slide(slide.id)
            descriptor = paths.private_derivative / "slide.dzi"
            thumbnail = paths.private_derivative / "thumbnail.jpg"
            published_thumbnail = storage.public_for(slide.public_id) / "thumbnail.jpg"
            individual_thumbnail = (
                storage.individual_delivery_for(slide.public_id, delivery_version(slide))
                / "thumbnail.jpg"
                if slide.published_at is not None
                else None
            )
            publication_missing = slide.published_at is not None and (
                not published_thumbnail.is_file()
                or individual_thumbnail is None
                or not individual_thumbnail.is_file()
            )
            if not descriptor.is_file() or not thumbnail.is_file() or publication_missing:
                image = synthetic_histology(spec)
                encoded = image.tobytes()
                paths.original.parent.mkdir(parents=True, exist_ok=True)
                image.save(paths.original, "TIFF", compression="tiff_lzw")
                write_deep_zoom(image, paths.private_derivative)
                measurement = measure_derivative(paths.private_derivative)
                slide.source_bytes = len(encoded)
                slide.sha256 = hashlib.sha256(encoded).hexdigest()
                slide.derivative_bytes = measurement.derivative_bytes
                slide.derivative_file_count = measurement.file_count
                slide.thumbnail_filename = "thumbnail.jpg"
                publish_derivative(storage, slide.id, slide.public_id)
                publish_individual_derivative(
                    storage,
                    slide.id,
                    slide.public_id,
                    delivery_version(slide),
                )
                ensure_grant(database, storage, slide, INDIVIDUAL, slide.id)
            seeded.append(slide)

        classroom.folder_id = folder.id
        database.commit()
        print(json.dumps({
            "classId": classroom.id,
            "folderId": folder.id,
            "folderName": folder.name,
            "subfolderId": slide_folder.id,
            "subfolderName": slide_folder.name,
            "stressFolderCount": stress_folder_count,
            "slides": [{"id": slide.id, "name": slide.display_name} for slide in seeded],
        }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
