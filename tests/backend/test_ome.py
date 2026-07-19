from itertools import product
from pathlib import Path

import numpy as np
import pytest
import tifffile
from wsi_viewer.ome import OmeError, convert_uint16_to_uint8, validate_ome_tiff


def _write_ome(path: Path, dtype: str = "uint8", *, size_z: int = 1) -> None:
    shape = (size_z, 32, 48, 3) if size_z > 1 else (32, 48, 3)
    data = np.zeros(shape, dtype=dtype)
    axes = "ZYXS" if size_z > 1 else "YXS"
    tifffile.imwrite(path, data, ome=True, metadata={"axes": axes}, photometric="rgb")


def test_valid_flat_rgb_ome_tiff_is_accepted(tmp_path: Path) -> None:
    source = tmp_path / "valid.ome.tif"
    _write_ome(source)
    result = validate_ome_tiff(source)
    assert (result.width, result.height, result.bits_per_sample) == (48, 32, 8)


def test_legacy_imagej_rgb_tiff_is_accepted_without_physical_scale(tmp_path: Path) -> None:
    source = tmp_path / "imagej.tif"
    description = "\n".join(
        [
            "ImageJ=",
            "hyperstack=true",
            "images=3",
            "channels=3",
            "slices=1",
            "frames=1",
        ]
    )
    with tifffile.TiffWriter(source, bigtiff=True, byteorder=">") as writer:
        writer.write(
            np.zeros((32, 48, 3), dtype="uint8"),
            description=description,
            photometric="ycbcr",
            compression="jpeg",
            tile=(16, 16),
        )
    # Match the converter defect in Slide no.7: the first IFD is valid, but its
    # next-page pointer targets EOF instead of another IFD.
    with source.open("r+b") as binary:
        binary.seek(8)
        first_ifd = int.from_bytes(binary.read(8), "big")
        binary.seek(first_ifd)
        tag_count = int.from_bytes(binary.read(8), "big")
        binary.seek(first_ifd + 8 + tag_count * 20)
        binary.write(source.stat().st_size.to_bytes(8, "big"))
    result = validate_ome_tiff(source)
    assert (result.width, result.height, result.bits_per_sample) == (48, 32, 8)
    assert result.series_index == 0
    assert result.physical_size_x is None
    assert result.physical_size_y is None


def test_plain_non_ome_tiff_is_still_rejected_with_stable_code(tmp_path: Path) -> None:
    source = tmp_path / "plain.tif"
    tifffile.imwrite(source, np.zeros((32, 48, 3), dtype="uint8"), photometric="rgb")
    with pytest.raises(OmeError) as error:
        validate_ome_tiff(source)
    assert error.value.code == "INVALID_OME_XML"


def test_legacy_imagej_z_stack_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "imagej-z-stack.tif"
    tifffile.imwrite(
        source,
        np.zeros((2, 32, 48, 3), dtype="uint8"),
        imagej=True,
        metadata={"axes": "ZYXS"},
        photometric="rgb",
    )
    with pytest.raises(OmeError) as error:
        validate_ome_tiff(source)
    assert error.value.code == "UNSUPPORTED_DIMENSIONS"


def test_z_stack_is_rejected(tmp_path: Path) -> None:
    source = tmp_path / "z-stack.ome.tif"
    _write_ome(source, size_z=2)
    with pytest.raises(OmeError) as error:
        validate_ome_tiff(source)
    assert error.value.code == "UNSUPPORTED_DIMENSIONS"


def test_uint16_mapping_is_exact_and_rounded() -> None:
    source = np.array([0, 1, 128, 256, 257, 32768, 65535], dtype=np.uint16)
    assert convert_uint16_to_uint8(source).tolist() == [0, 0, 0, 1, 1, 128, 255]


ACCEPTED_MATRIX = list(
    product(
        [False, True],
        ["<", ">"],
        [False, True],
        [False, True],
        ["uint8", "uint16"],
        [None, "jpeg", "lzw", "deflate"],
    )
)


@pytest.mark.parametrize(
    ("bigtiff", "byteorder", "pyramidal", "tiled", "dtype", "compression"),
    ACCEPTED_MATRIX,
)
def test_full_accepted_storage_matrix(
    tmp_path: Path,
    bigtiff: bool,
    byteorder: str,
    pyramidal: bool,
    tiled: bool,
    dtype: str,
    compression: str | None,
) -> None:
    path = tmp_path / "matrix.ome.tif"
    data = np.zeros((32, 48, 3), dtype=dtype)
    storage = {"tile": (16, 16)} if tiled else {"rowsperstrip": 8}
    with tifffile.TiffWriter(path, ome=True, bigtiff=bigtiff, byteorder=byteorder) as writer:
        writer.write(
            data,
            metadata={"axes": "YXS"},
            photometric="rgb",
            planarconfig="contig",
            compression=compression,
            subifds=1 if pyramidal else None,
            **storage,
        )
        if pyramidal:
            writer.write(
                data[::2, ::2],
                photometric="rgb",
                planarconfig="contig",
                compression=compression,
                subfiletype=1,
                **storage,
            )
    metadata = validate_ome_tiff(path)
    with tifffile.TiffFile(path) as generated:
        encoded_bits = generated.series[0].dtype.itemsize * 8
    assert metadata.bits_per_sample == encoded_bits


def test_ycbcr_jpeg_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "ycbcr.ome.tif"
    tifffile.imwrite(
        path,
        np.zeros((32, 48, 3), dtype=np.uint8),
        ome=True,
        metadata={"axes": "YXS"},
        photometric="ycbcr",
        compression="jpeg",
        tile=(16, 16),
    )
    assert validate_ome_tiff(path).bits_per_sample == 8
