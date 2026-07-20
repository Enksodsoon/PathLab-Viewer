# PathLab Prepared Slide Package v1

## Status

Design contract for the first server vertical slice. The canonical machine-readable schema will be created at `contracts/prepared-slide-v1.schema.json` by Task 1 in the active plan.

## File format

Extension:

```text
.plslide
```

Container:

```text
uncompressed POSIX TAR
```

ZIP compression is not the default because JPEG tiles and JPEG-compressed OME-TIFF data are already compressed.

## Fixed layout

```text
slide.plslide
├── manifest.json
├── thumbnail.jpg
├── dzi/
│   ├── slide.dzi
│   └── slide_files/
│       ├── 0/
│       ├── 1/
│       └── ...
└── archive/
    └── source.ome.tif
```

`archive/source.ome.tif` is optional. All other paths are fixed for schema version 1.

Allowed regular files:

```text
manifest.json
thumbnail.jpg
dzi/slide.dzi
dzi/slide_files/<level>/<column>_<row>.jpg
archive/source.ome.tif
```

No other files are allowed.

## DZI contract

```text
descriptor: dzi/slide.dzi
tile directory: dzi/slide_files
tile size: 512
overlap: 1
format: jpg
RGB bit depth: 8
```

The server verifies the descriptor and actual tile tree; it does not trust manifest declarations alone.

## Manifest example

```json
{
  "schemaVersion": 1,
  "displayName": "Oral cavity - SCC",
  "createdAt": "2026-07-20T08:00:00+07:00",
  "producer": {
    "name": "PathLab Prep",
    "version": "0.1.0",
    "buildChannel": "modern-windows",
    "platform": "Windows 11 x86-64",
    "reader": "Bio-Formats",
    "readerVersion": "record-real-version",
    "omeWriterVersion": "record-real-version",
    "dziGenerator": "libvips",
    "dziGeneratorVersion": "record-real-version",
    "jpegLibraryVersion": "record-real-version"
  },
  "source": {
    "filename": "Slide 07.vsi",
    "format": "VSI",
    "seriesIndex": 0,
    "sourceWidth": 37800,
    "sourceHeight": 34366,
    "sourceFingerprint": "local-non-secret-fingerprint",
    "companionFileCount": 6
  },
  "processing": {
    "crop": {
      "x": 0,
      "y": 0,
      "width": 37800,
      "height": 34366
    },
    "downsample": 2.0,
    "renderProfile": "PATHOLOGY_STANDARD",
    "rgb": true,
    "bitsPerSample": 8,
    "iccOutput": "sRGB"
  },
  "image": {
    "width": 18900,
    "height": 17183,
    "physicalSizeX": 1.0952,
    "physicalSizeY": 1.0952,
    "physicalSizeUnit": "um"
  },
  "dzi": {
    "descriptor": "dzi/slide.dzi",
    "tileDirectory": "dzi/slide_files",
    "tileSize": 512,
    "overlap": 1,
    "format": "jpg",
    "quality": 85
  },
  "archive": {
    "included": false,
    "path": null
  }
}
```

## Required semantic validation

- `schemaVersion` equals `1`.
- `displayName` is non-empty and length-bounded.
- Image and source dimensions are positive integers.
- Crop lies fully within level-zero source bounds.
- Downsample is finite and greater than or equal to 1.
- Output width and height are positive and match actual DZI dimensions.
- `rgb` is true and `bitsPerSample` is 8.
- DZI descriptor and tile-directory paths exactly match the fixed v1 paths.
- Tile size is 512, overlap is 1 and format is JPEG.
- Physical scale may be absent; it must never be invented.
- `archive.included=true` requires `archive.path="archive/source.ome.tif"` and the file must exist.
- `archive.included=false` requires no archive file.
- Local absolute source paths are prohibited.

## Archive safety rules

Reject:

- `../` or equivalent traversal
- Absolute Unix paths
- Windows drive or UNC paths
- Backslash-based traversal
- Null bytes
- Symlinks and hard links
- FIFO, device and socket entries
- Duplicate archive entries
- Unicode-normalized duplicate paths
- Unsupported extensions
- Excessive path depth or filename length
- Excessive file count
- Excessive package or extracted bytes
- Nested archives
- Multiple manifests or DZI descriptors

Extraction must use bounded streaming I/O into a unique staging directory. No package is moved to canonical assets until all checks pass.

## Stable initial error codes

```text
PREPARED_SCHEMA_UNSUPPORTED
PACKAGE_LENGTH_MISMATCH
PACKAGE_HASH_MISMATCH
PACKAGE_ARCHIVE_INVALID
PACKAGE_PATH_INVALID
PACKAGE_ENTRY_TYPE_INVALID
PACKAGE_DUPLICATE_ENTRY
PACKAGE_FILE_LIMIT_EXCEEDED
PACKAGE_EXTRACTED_SIZE_EXCEEDED
PACKAGE_LAYOUT_INVALID
MANIFEST_INVALID
MANIFEST_MISMATCH
DZI_DESCRIPTOR_INVALID
DZI_TILE_TREE_INVALID
DZI_TILE_INVALID
PREPARED_IMPORT_FAILED
```

## Test fixtures

Use tiny deterministic generated fixtures rather than committed real WSI files:

- Valid minimal package
- Unsupported schema
- Missing manifest
- Traversal path
- Absolute path
- Windows drive path
- Symlink
- Hard link
- Duplicate normalized path
- Extra executable
- Multiple DZI descriptors
- Malformed DZI XML
- XML external entity
- Invalid JPEG signature
- Manifest/DZI dimension mismatch
- Archive included/missing mismatch

Fixture generators should be code, not large binary blobs.