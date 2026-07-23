import json
import logging
import os
import shutil
import stat
import time
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


class InvalidDerivative(RuntimeError):
    pass


class ConversionWorkspaceCleanupError(RuntimeError):
    pass


@dataclass(frozen=True)
class ConversionResult:
    descriptor: Path
    derivative_bytes: int
    derivative_file_count: int
    tile_count: int


def _log_event(event: str, **measurements: object) -> None:
    logger.info(
        json.dumps(
            {"event": event, **measurements},
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def configure_libvips(
    *,
    concurrency: int,
    cache_max_mem_bytes: int,
    cache_max_files: int,
    cache_max_operations: int,
) -> None:
    os.environ["VIPS_CONCURRENCY"] = str(concurrency)
    import pyvips  # type: ignore[import-untyped]  # Native library lives in worker image.

    pyvips.cache_set_max_mem(cache_max_mem_bytes)
    pyvips.cache_set_max_files(cache_max_files)
    pyvips.cache_set_max(cache_max_operations)


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


def _measure_derivative(root: Path) -> tuple[int, int, int]:
    derivative_bytes = 0
    file_count = 0
    tile_count = 0
    for item in root.rglob("*"):
        if not item.is_file():
            continue
        derivative_bytes += item.stat().st_size
        file_count += 1
        if item.suffix.lower() in {".jpg", ".jpeg"}:
            tile_count += 1
    return derivative_bytes, file_count, tile_count


def _remove_path_without_following_symlink(path: Path) -> None:
    mode = path.lstat().st_mode
    if stat.S_ISLNK(mode):
        path.unlink()
    elif stat.S_ISDIR(mode):
        shutil.rmtree(path)
    else:
        path.unlink()


def _remove_tree_without_masking_error(path: Path) -> None:
    try:
        _remove_path_without_following_symlink(path)
    except FileNotFoundError:
        return
    except Exception as error:
        _log_event("conversion_cleanup_failure", error_type=type(error).__name__)


def _remove_stale_conversion_workspaces(destination: Path) -> None:
    parent = destination.parent
    if not parent.exists():
        return
    prefix = f"{destination.name}.tmp-"
    try:
        # Runtime contract: one serial conversion worker. Every matching sibling at
        # conversion start therefore belongs to a terminated or completed attempt.
        candidates = [item for item in parent.iterdir() if item.name.startswith(prefix)]
        for candidate in candidates:
            try:
                _remove_path_without_following_symlink(candidate)
            except FileNotFoundError:
                continue
    except Exception as error:
        _log_event(
            "conversion_stale_cleanup_failure", error_type=type(error).__name__
        )
        raise ConversionWorkspaceCleanupError(
            "Unable to remove stale conversion workspace; conversion aborted"
        ) from error


def _recover_previous_derivative(destination: Path, previous: Path) -> None:
    if not previous.exists():
        return
    if destination.exists():
        shutil.rmtree(previous)
    else:
        previous.replace(destination)


def generate_dzi(
    source: Path,
    destination: Path,
    *,
    series_index: int,
    bits: int,
) -> ConversionResult:
    staging = destination.with_name(f"{destination.name}.tmp-{os.getpid()}")
    previous = destination.with_name(f"{destination.name}.previous")
    source_bytes = source.stat().st_size
    started = time.monotonic()
    _log_event("conversion_start", source_bytes=source_bytes)
    try:
        _remove_stale_conversion_workspaces(destination)
        _recover_previous_derivative(destination, previous)
        staging.mkdir(parents=True)

        import pyvips  # Native library lives in worker image.

        image = pyvips.Image.new_from_file(
            str(source), access="sequential", page=series_index
        )
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
        derivative_bytes, file_count, tile_count = _measure_derivative(staging)

        had_destination = destination.exists()
        if had_destination:
            destination.replace(previous)
        try:
            staging.replace(destination)
        except Exception:
            if had_destination and previous.exists() and not destination.exists():
                try:
                    previous.replace(destination)
                except Exception as rollback_error:
                    _log_event(
                        "conversion_rollback_failure",
                        error_type=type(rollback_error).__name__,
                    )
            raise

        if previous.exists():
            _remove_tree_without_masking_error(previous)
        _log_event(
            "conversion_complete",
            derivative_bytes=derivative_bytes,
            elapsed_seconds=round(time.monotonic() - started, 3),
            file_count=file_count,
            source_bytes=source_bytes,
            tile_count=tile_count,
        )
        return ConversionResult(
            descriptor=destination / "slide.dzi",
            derivative_bytes=derivative_bytes,
            derivative_file_count=file_count,
            tile_count=tile_count,
        )
    except Exception as error:
        _log_event(
            "conversion_failure",
            elapsed_seconds=round(time.monotonic() - started, 3),
            error_type=type(error).__name__,
            source_bytes=source_bytes,
        )
        raise
    finally:
        _remove_tree_without_masking_error(staging)
