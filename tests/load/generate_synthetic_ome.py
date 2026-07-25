#!/usr/bin/env python3
import argparse
import struct
from pathlib import Path

DEFAULT_WIDTH = 11_000
DEFAULT_HEIGHT = 10_000


def generate_ome_tiff(path: Path, *, width: int, height: int) -> None:
    if width <= 0 or height <= 0:
        raise ValueError("dimensions must be positive")
    pixel_bytes = width * height * 3
    if pixel_bytes >= 2**32:
        raise ValueError("classic TIFF payload must be smaller than 4 GiB")
    description = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">'
        '<Image ID="Image:0" Name="Synthetic capacity certification">'
        f'<Pixels ID="Pixels:0" DimensionOrder="XYCZT" Type="uint8" '
        f'SizeX="{width}" SizeY="{height}" SizeC="3" SizeZ="1" SizeT="1" '
        'Interleaved="true">'
        '<Channel ID="Channel:0:0" SamplesPerPixel="3"/>'
        '<TiffData IFD="0" PlaneCount="1"/>'
        '</Pixels></Image></OME>\x00'
    ).encode()
    entries = 14
    ifd_offset = 8
    extra_offset = ifd_offset + 2 + entries * 12 + 4
    bits_offset = extra_offset
    x_resolution_offset = bits_offset + 6
    y_resolution_offset = x_resolution_offset + 8
    description_offset = y_resolution_offset + 8
    pixel_offset = (description_offset + len(description) + 7) & ~7

    def entry(tag: int, kind: int, count: int, value: int) -> bytes:
        if kind == 3 and count == 1:
            encoded = struct.pack("<H", value) + b"\x00\x00"
        else:
            encoded = struct.pack("<I", value)
        return struct.pack("<HHI", tag, kind, count) + encoded

    ifd = b"".join(
        [
            entry(256, 4, 1, width),
            entry(257, 4, 1, height),
            entry(258, 3, 3, bits_offset),
            entry(259, 3, 1, 1),
            entry(262, 3, 1, 2),
            entry(270, 2, len(description), description_offset),
            entry(273, 4, 1, pixel_offset),
            entry(277, 3, 1, 3),
            entry(278, 4, 1, height),
            entry(279, 4, 1, pixel_bytes),
            entry(282, 5, 1, x_resolution_offset),
            entry(283, 5, 1, y_resolution_offset),
            entry(284, 3, 1, 1),
            entry(296, 3, 1, 2),
        ]
    )
    # The count must match the entry list; keep this check beside the serializer.
    entries = len(ifd) // 12
    header = b"II*\x00" + struct.pack("<I", ifd_offset)
    payload = (
        header
        + struct.pack("<H", entries)
        + ifd
        + struct.pack("<I", 0)
        + struct.pack("<HHH", 8, 8, 8)
        + struct.pack("<II", 72, 1)
        + struct.pack("<II", 72, 1)
        + description
    )
    if len(payload) > pixel_offset:
        raise ValueError("TIFF metadata exceeded its reserved offset")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(payload)
        stream.write(b"\x00" * (pixel_offset - len(payload)))
        stream.seek(pixel_offset + pixel_bytes - 1)
        stream.write(b"\x00")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a synthetic non-PHI OME-TIFF")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    args = parser.parse_args()
    generate_ome_tiff(args.output, width=args.width, height=args.height)


if __name__ == "__main__":
    main()
