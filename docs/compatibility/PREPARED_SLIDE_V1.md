# PathLab Prepared Slide Package v1

## Status

This document defines the design contract that Task 1 must encode as `contracts/prepared-slide-v1.schema.json` and equivalent typed Python validation.

Package extension:

```text
.plslide
```

Container:

```text
uncompressed POSIX TAR
```

## Fixed layout

```text
manifest.json
thumbnail.jpg
dzi/slide.dzi
dzi/slide_files/<level>/<column>_<row>.jpg
archive/source.ome.tif                 optional
```

Schema version 1 permits no other top-level paths.

## Mandatory DZI contract

```text
Descriptor: dzi/slide.dzi
Tile directory: dzi/slide_files
Tile size: 512
Overlap: 1
Format: jpg
Pixel model: interleaved 8-bit RGB
```

The server must verify actual descriptor and files rather than trust manifest declarations.

## Manifest fields

Required root fields:

```text
schemaVersion
createdAt
producer
source
processing
image
dzi
archive
```

`displayName` is accepted as an optional suggestion. The server may use the authenticated upload-reservation value instead.

### Producer

Required:

```text
name
version
platform
architecture
reader
readerVersion
omeWriter
omeWriterVersion
dziGenerator
dziGeneratorVersion
```

### Source

Required:

```text
filename
format
seriesIndex
sourceWidth
sourceHeight
sourceFingerprint
companionFileCount
```

Rules:

- filename is a basename, not an absolute path;
- dimensions are positive integers;
- series index is a non-negative integer;
- fingerprint is local provenance, not a server security checksum.

### Processing

Required:

```text
crop.x
crop.y
crop.width
crop.height
downsample
renderProfile
rgb
bitsPerSample
iccOutput
```

Rules:

- crop values are level-zero source pixels;
- x and y are non-negative;
- width and height are positive;
- crop stays inside source dimensions;
- downsample is finite and at least 1.0;
- `rgb` is true;
- `bitsPerSample` is 8;
- allowed render profiles initially: `PATHOLOGY_STANDARD`, `DISPLAY_MATCHED_CUSTOM`;
- `iccOutput` is `sRGB` for package version 1.

### Image

Required:

```text
width
height
```

Optional as one complete group:

```text
physicalSizeX
physicalSizeY
physicalSizeUnit
```

Rules:

- output dimensions are positive integers;
- physical sizes are positive finite numbers when present;
- unit is a non-empty normalized string;
- do not invent physical scale when the source lacks it.

### DZI

Required exact values:

```text
descriptor = dzi/slide.dzi
tileDirectory = dzi/slide_files
tileSize = 512
overlap = 1
format = jpg
quality = integer 1..100
```

The server capability response may require quality 85 for its current contract. Schema v1 allows the quality field to record the actual encoder setting, while server policy may reject unsupported values.

### Archive

Required:

```text
included
path
```

Rules:

- when `included` is false, `path` is null;
- when `included` is true, `path` equals `archive/source.ome.tif`;
- the server may reject archive mode through capabilities or policy.

## Archive security rules

Reject:

- absolute paths;
- `..` traversal;
- Windows drive paths;
- backslash traversal;
- null bytes;
- duplicate normalized paths;
- symbolic or hard links;
- device, FIFO or other special entries;
- sparse entries unless explicitly implemented later;
- nested archives;
- encrypted entries;
- unexpected files or extensions;
- excessive path depth, filename length, file count or extracted bytes.

## Stable contract errors

Task 1 must establish:

```text
MANIFEST_INVALID
PREPARED_SCHEMA_UNSUPPORTED
```

Later importer tasks add archive, DZI, hash and lifecycle error codes.

## Versioning

- Never change the meaning of schema version 1 silently.
- Breaking changes create schema version 2.
- Viewer may accept multiple versions concurrently.
- Forge must query Viewer capabilities before upload.
- The JSON Schema in PathLab Viewer is the canonical server acceptance contract.
- PathLab Forge keeps a pinned compatible copy and tests it against server contract fixtures.