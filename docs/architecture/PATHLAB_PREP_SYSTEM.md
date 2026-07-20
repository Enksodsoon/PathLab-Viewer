# PathLab Prep System Architecture

## Objective

PathLab Prep is a cross-platform desktop companion for PathLab Viewer. It performs expensive WSI reading, RGB rendering, cropping, downsampling, OME-TIFF writing and DZI generation on Windows or macOS. PathLab Viewer then receives a completely prepared package and performs only authenticated upload, checksum verification, safe import, metadata registration and static tile serving.

## Final responsibility split

```text
LOCAL COMPUTER
Open WSI dataset
→ detect reader and companion files
→ select primary series
→ view and crop
→ choose downsample and RGB preset
→ write pyramidal RGB OME-TIFF
→ generate DZI from that OME-TIFF
→ validate locally
→ create .plslide package
→ upload resumably

SERVER
Authenticate device
→ reserve storage
→ receive package with tus
→ verify size and SHA-256
→ inspect and safely extract archive
→ validate manifest and DZI
→ register canonical assets
→ private preview
→ explicit publication
→ static tile delivery
```

The server must not open, decode, render, downsample or convert the original WSI for prepared packages.

## Existing server baseline

The current server already provides:

- FastAPI API and administrator authentication
- SQLite metadata database
- tus resumable OME-TIFF upload
- OME-TIFF validation
- libvips DZI generation
- private OpenSeadragon preview
- unlisted public OpenSeadragon viewer
- Caddy static tile delivery
- worker lifecycle and deletion jobs

The prepared path must coexist with the existing legacy OME-TIFF path until end-to-end validation is complete.

## Server prepared-package lifecycle

```text
uploading
→ queued_import
→ importing
→ ready_private
→ published
```

Shared failure/control states:

```text
failed
deleting
```

Every slide records an explicit ingest mode:

```text
legacy_ome
prepared_package
```

Do not infer ingest mode from the filename.

## Prepared importer

The tus completion hook must return promptly after registering the package and queuing an import job. Extraction must not happen synchronously in the hook request.

The importer performs:

1. Verify package existence and byte length.
2. Calculate and compare SHA-256.
3. Inspect all TAR headers before extraction.
4. Reject unsafe paths, links, special files, duplicates and unsupported entries.
5. Enforce package, extracted-size, path-depth and file-count limits.
6. Validate `manifest.json` against the supported contract.
7. Extract into a unique staging directory using bounded streaming I/O.
8. Parse `dzi/slide.dzi` with external entities disabled.
9. Verify dimensions, tile size, overlap, format and tile tree.
10. Verify JPEG signatures and representative decodability.
11. Compare actual files and descriptor values with the manifest.
12. Atomically move the DZI and optional OME archive into canonical storage.
13. Delete the temporary package only after successful import.
14. Set the slide to `ready_private`.

## Canonical storage

Target layout:

```text
/data/assets/{slide_id}/dzi/
/data/assets/{slide_id}/archive/source.ome.tif
/data/public/{public_id}
```

Private preview reads directly from canonical assets. Publication creates a controlled atomic public mapping to the same immutable DZI tree. It must not copy the entire tile directory. Unpublication removes only the public mapping. Deletion removes the mapping before canonical assets.

## Desktop application

The desktop application will live in a separate repository named `Enksodsoon/PathLab-Prep` once the server vertical slice is stable.

Recommended logical modules:

```text
reader        source discovery, reader routing, series and companion files
viewer        pan, zoom, thumbnail, scale and crop
render        8-bit RGB and sRGB rendering profiles
ome           pyramidal OME-TIFF writer and validation
dzi           libvips Deep Zoom generation and validation
package       manifest and .plslide creation
queue         persistent batch orchestration
upload        capabilities, reservation, tus and status polling
auth          scoped device credentials and OS keychain
persistence   SQLite jobs, checkpoints and settings
diagnostics   sanitized errors, timings and compatibility evidence
platform      Windows/macOS runtime and packaging adapters
```

QuPath/OpenSlide/Bio-Formats-specific objects must remain behind reader interfaces. Batch, packaging and upload code must not depend directly on one QuPath version.

## Batch conversion

Batch conversion is an MVP requirement.

Inputs:

- Multiple files
- A folder
- Multiple folders
- Optional recursive scanning
- Multi-file WSI datasets such as VSI plus ETS companions
- Mixed supported formats in one queue

Default execution:

```text
maximum conversions: 1
maximum uploads: 1
```

On adequate machines:

```text
convert slide B while uploading slide A
```

In legacy/low-resource mode:

```text
convert A → upload A → clean A → convert B
```

A failed slide does not stop later valid slides by default.

Persistent per-slide states:

```text
PENDING
INSPECTING
NEEDS_REVIEW
READY
EXPORTING_OME
VALIDATING_OME
GENERATING_DZI
VALIDATING_DZI
PACKAGING
READY_TO_UPLOAD
UPLOADING
SERVER_IMPORTING
READY_PRIVATE
PUBLISHED
PAUSED
FAILED_RETRYABLE
FAILED_PERMANENT
CANCELLED
SKIPPED
```

The queue must survive application and operating-system restart. Upload interruption must never require reconversion when a valid package remains.

## Rendering contract

Default profile: `PATHOLOGY_STANDARD`.

- Interleaved 8-bit RGB
- Convert embedded ICC profile to sRGB when available
- Treat unprofiled RGB as sRGB
- Deterministic 16-bit to 8-bit conversion equivalent to `round(value / 257)`
- Flatten alpha onto white
- Preserve or correctly update physical scale
- No subjective brightness or contrast changes

Optional `DISPLAY_MATCHED_CUSTOM` may store display adjustments, but must be labelled as unsuitable for quantitative pixel analysis.

Generate DZI from the exported OME-TIFF, not independently from the proprietary source. This guarantees the OME-TIFF and DZI share the same crop, downsample, rendering and dimensions.

## Batch presets

Initial presets:

```text
Teaching Compact: 2×, RGB, DZI JPEG quality 85
Maximum Detail: 1×, RGB, DZI JPEG quality 90
Small Preview: 4×, RGB, DZI JPEG quality 80
```

Prepared package schema version 1 fixes:

```text
DZI tile size: 512
DZI overlap: 1
DZI format: JPEG
```

## Source compatibility

Do not claim universal file-format support. Use:

> PathLab Prep supports WSI and microscopy formats available through its installed reader engines, verified through a tested compatibility matrix.

Priority formats:

- OME-TIFF/TIFF/BigTIFF
- Aperio SVS
- Olympus VSI with complete ETS companions
- NDPI, MRXS, SCN and other formats when supported by the installed readers

VSI datasets must be grouped as one logical source. Missing companions must produce `MISSING_COMPANION_FILES`; incomplete datasets must never be silently exported.

## Operating-system compatibility

Modern targets:

- Windows 10/11 x64
- Current macOS Apple Silicon
- Current macOS Intel where available

Legacy investigation order:

- Windows 8.1 x64
- Windows 7 SP1 x64
- macOS 10.15 Intel
- macOS 10.14 Intel
- macOS 10.13 Intel

All releases must be self-contained. Normal users must not install Java, Python, libvips, OpenSlide, Bio-Formats, Homebrew or Chocolatey.

Use a shared Java-17-compatible contract/core where practical and isolate modern/legacy reader and native-library adapters. Do not require AVX, AVX2, CUDA or a modern GPU. Do not weaken server authentication, HTTPS or package validation for legacy clients.

A platform is supported only after actual launch, viewing, batch conversion, DZI, upload and restart-recovery evidence exists.

## Security and privacy

- Source WSI remains local in viewer-only mode.
- Upload only prepared DZI, manifest, thumbnail and optional explicit OME archive.
- Treat package values as untrusted and verify them against actual files.
- Reject traversal, absolute paths, Windows drive paths, symlinks, hard links, special files, duplicate normalized paths and unexpected extensions.
- Store desktop credentials in Windows Credential Manager or macOS Keychain.
- Automatic public publication is disabled by default.
- Never include local absolute paths or access tokens in the server manifest.

## Explicit non-goals

Do not add AI diagnosis, annotations, collaborative viewing, student accounts, fluorescence analysis, Z-stack/time navigation, DICOM WSI, PACS integration, cloud conversion or a new universal proprietary WSI decoder.

## Evidence labels

Use only:

```text
DESIGN_COMPLETE
IMPLEMENTED_UNVERIFIED
VALIDATED_LIMITED
PRODUCTION_READY
BLOCKED
```

Do not label production-ready until physical-device, real-format, interrupted-upload, malicious-package, backup/restore, storage and load evidence are complete.