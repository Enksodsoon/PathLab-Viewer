from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import tifffile
from ome_types import from_xml


class OmeError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class OmeMetadata:
    width: int
    height: int
    bits_per_sample: int
    physical_size_x: float | None
    physical_size_y: float | None
    physical_size_unit: str | None
    has_icc_profile: bool
    series_index: int


def convert_uint16_to_uint8(source: np.ndarray) -> np.ndarray:
    if source.dtype != np.uint16:
        raise TypeError("Expected an unsigned 16-bit array")
    return np.rint(source.astype(np.float64) / 257.0).astype(np.uint8)


def _stable_error(error: Exception) -> OmeError:
    if isinstance(error, OmeError):
        return error
    message = str(error).lower()
    if "compression" in message or "decode" in message:
        return OmeError("DECOMPRESSION_FAILED", "The TIFF payload could not be decoded")
    if "offset" in message or "truncat" in message or "eof" in message:
        return OmeError("INVALID_TIFF_STRUCTURE", "The TIFF structure is truncated or invalid")
    return OmeError("INVALID_TIFF_STRUCTURE", "The TIFF structure could not be read")


def _enum_name(value: Any) -> str:
    return str(getattr(value, "name", value)).upper()


def _validate_supported_page(page: Any) -> None:
    compression = _enum_name(page.compression)
    supported = {"NONE", "JPEG", "LZW", "DEFLATE", "ADOBE_DEFLATE"}
    if compression not in supported:
        raise OmeError("UNSUPPORTED_COMPRESSION", f"Unsupported TIFF compression: {compression}")


def _imagej_dimension(metadata: dict[str, Any], name: str, default: int) -> int:
    try:
        return int(metadata.get(name, default))
    except (TypeError, ValueError) as error:
        raise OmeError("INVALID_IMAGEJ_METADATA", "The ImageJ dimensions are invalid") from error


def _validate_legacy_imagej(tif: tifffile.TiffFile, path: Path) -> OmeMetadata:
    """Validate the bounded legacy ImageJ RGB format emitted by older converters.

    Some converter outputs contain one valid RGB IFD followed by a broken page
    chain.  Reading ``tif.series`` follows that chain and fails, so this path
    deliberately validates and converts only the first IFD.
    """

    metadata = tif.imagej_metadata or {}
    slices = _imagej_dimension(metadata, "slices", 1)
    frames = _imagej_dimension(metadata, "frames", 1)
    channels = _imagej_dimension(metadata, "channels", 1)
    images = _imagej_dimension(metadata, "images", channels * slices * frames)
    if slices != 1 or frames != 1:
        raise OmeError("UNSUPPORTED_DIMENSIONS", "Only SizeZ=1 and SizeT=1 are supported")
    if channels not in {1, 3} or images != channels * slices * frames:
        raise OmeError("INVALID_IMAGEJ_METADATA", "The ImageJ dimensions are inconsistent")

    page = tif.pages[0]
    if not isinstance(page, tifffile.TiffPage):
        raise OmeError("INVALID_TIFF_STRUCTURE", "The primary TIFF page is invalid")
    samples = int(page.samplesperpixel or 1)
    dtype = np.dtype(page.dtype)
    photometric = _enum_name(page.photometric)
    planar_config = _enum_name(page.planarconfig)
    if (
        samples != 3
        or dtype not in (np.dtype("uint8"), np.dtype("uint16"))
        or photometric not in {"RGB", "YCBCR"}
        or planar_config not in {"CONTIG", "1"}
    ):
        raise OmeError("UNSUPPORTED_PIXEL_TYPE", "Only unsigned 8- or 16-bit RGB is supported")
    _validate_supported_page(page)

    offsets = tuple(int(offset) for offset in page.dataoffsets)
    byte_counts = tuple(int(count) for count in page.databytecounts)
    file_size = path.stat().st_size
    if (
        not offsets
        or len(offsets) != len(byte_counts)
        or any(
            offset < 0 or count <= 0 or offset + count > file_size
            for offset, count in zip(offsets, byte_counts, strict=True)
        )
    ):
        raise OmeError("INVALID_TIFF_STRUCTURE", "The primary TIFF image data is truncated")

    return OmeMetadata(
        width=int(page.imagewidth),
        height=int(page.imagelength),
        bits_per_sample=dtype.itemsize * 8,
        physical_size_x=None,
        physical_size_y=None,
        physical_size_unit=None,
        has_icc_profile=page.tags.get(34675) is not None,
        series_index=0,
    )


def validate_ome_tiff(path: Path) -> OmeMetadata:
    try:
        with tifffile.TiffFile(path) as tif:
            xml = tif.ome_metadata
            if not xml:
                if tif.is_imagej:
                    return _validate_legacy_imagej(tif, path)
                raise OmeError("INVALID_OME_XML", "A valid OME-XML document is required")
            try:
                ome = from_xml(xml, validate=True)
            except Exception as error:
                raise OmeError("INVALID_OME_XML", "The OME-XML document is invalid") from error
            candidates: list[tuple[int, int, int]] = []
            for index, series in enumerate(tif.series):
                axes = series.axes
                shape = series.shape
                if "Y" not in axes or "X" not in axes:
                    continue
                height = int(shape[axes.index("Y")])
                width = int(shape[axes.index("X")])
                candidates.append((width * height, index, width))
            if not candidates:
                raise OmeError("UNSUPPORTED_PIXEL_TYPE", "No two-dimensional RGB OME image exists")
            _, series_index, width = max(candidates, key=lambda item: item[0])
            series = tif.series[series_index]
            axes = series.axes
            shape = series.shape
            height = int(shape[axes.index("Y")])
            image = ome.images[min(series_index, len(ome.images) - 1)]
            pixels = image.pixels
            if pixels.size_z != 1 or pixels.size_t != 1:
                raise OmeError("UNSUPPORTED_DIMENSIONS", "Only SizeZ=1 and SizeT=1 are supported")
            samples = int(shape[axes.index("S")]) if "S" in axes else 1
            if samples != 3 or series.dtype not in (np.dtype("uint8"), np.dtype("uint16")):
                raise OmeError(
                    "UNSUPPORTED_PIXEL_TYPE", "Only unsigned 8- or 16-bit RGB is supported"
                )
            page = series.pages[0]
            if page is None or not hasattr(page, "tags"):
                raise OmeError("INVALID_TIFF_STRUCTURE", "The primary TIFF page is invalid")
            _validate_supported_page(page)
            icc_tag = page.tags.get(34675)
            unit = str(pixels.physical_size_x_unit) if pixels.physical_size_x_unit else None
            return OmeMetadata(
                width=width,
                height=height,
                bits_per_sample=series.dtype.itemsize * 8,
                physical_size_x=float(pixels.physical_size_x) if pixels.physical_size_x else None,
                physical_size_y=float(pixels.physical_size_y) if pixels.physical_size_y else None,
                physical_size_unit=unit,
                has_icc_profile=icc_tag is not None,
                series_index=series_index,
            )
    except Exception as error:
        raise _stable_error(error) from error
