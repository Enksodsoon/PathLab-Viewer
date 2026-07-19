import os
import shutil
from pathlib import Path


class InvalidDerivative(RuntimeError):
    pass


def sanitize_and_validate_derivative(root: Path) -> None:
    for properties in root.rglob("vips-properties.xml"):
        properties.unlink()
    dzi_files = list(root.glob("*.dzi"))
    if len(dzi_files) != 1:
        raise InvalidDerivative("Derivative must contain exactly one DZI descriptor")
    for item in root.rglob("*"):
        if item.is_dir():
            continue
        if item.suffix.lower() not in {".dzi", ".jpg", ".jpeg"}:
            raise InvalidDerivative(f"Unexpected derivative file: {item.name}")


def generate_dzi(source: Path, destination: Path, *, series_index: int, bits: int) -> Path:
    import pyvips  # type: ignore[import-untyped]  # Native library lives in worker image.

    staging = destination.with_name(f"{destination.name}.tmp-{os.getpid()}")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    image = pyvips.Image.new_from_file(str(source), access="sequential", page=series_index)
    if bits == 16:
        image = (image / 257.0).round().cast("uchar")
    if image.get_typeof("icc-profile-data"):
        image = image.icc_transform("srgb")
    output = staging / "slide"
    image.dzsave(
        str(output),
        tile_size=512,
        overlap=1,
        suffix=".jpg[Q=85,strip]",
        skip_blanks=-1,
        depth="onepixel",
    )
    sanitize_and_validate_derivative(staging)
    if destination.exists():
        shutil.rmtree(destination)
    staging.replace(destination)
    return destination / "slide.dzi"
