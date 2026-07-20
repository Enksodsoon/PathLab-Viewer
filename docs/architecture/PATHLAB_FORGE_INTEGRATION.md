# PathLab Forge Integration Architecture

## Product split

PathLab Forge and PathLab Viewer are separate repositories and separate deployable products.

```text
PathLab Forge desktop
Windows / macOS
    |
    | HTTPS capability API
    | short-lived upload authorization
    | resumable tus upload
    | versioned .plslide package
    v
PathLab Viewer server
Linux / OCI
```

## PathLab Forge owns

- WSI reader selection and companion-file discovery;
- local pan/zoom preview and image-series selection;
- full-slide or rectangle crop;
- configurable downsample;
- standardized 8-bit RGB rendering;
- pyramidal OME-TIFF export;
- DZI/JPEG generation;
- batch queue, persistence and retry;
- local validation and `.plslide` construction;
- Windows/macOS installers and legacy-client builds;
- automatic resumable upload.

None of those desktop responsibilities or native dependencies belong in PathLab Viewer.

## PathLab Viewer owns

- authentication and desktop-client authorization;
- capability negotiation;
- upload admission and storage limits;
- tus upload completion;
- package length and SHA-256 verification;
- hostile TAR inspection and bounded extraction;
- manifest, DZI and JPEG validation;
- slide lifecycle and metadata;
- private preview;
- publish, unpublish and delete;
- static DZI serving;
- backup and restore.

Prepared-package import must not initialize QuPath, Bio-Formats, OpenSlide or libvips image conversion.

## Data flow

```text
source WSI
  -> local RGB OME-TIFF
  -> local DZI
  -> local validation
  -> .plslide
  -> POST reservation
  -> tus upload
  -> queued_import
  -> importing
  -> ready_private
  -> explicit publish
```

The original proprietary WSI remains local in viewer-only mode.

## Version negotiation

PathLab Forge calls:

```text
GET /api/v1/desktop/capabilities
```

The response declares:

- supported API version;
- supported `.plslide` schema versions;
- maximum package bytes;
- whether OME archive upload is allowed;
- DZI tile size, overlap, format and quality contract.

PathLab Forge must check capabilities before building an upload intended for that server.

## Upload lifecycle

1. Forge creates and validates one package per slide.
2. Forge sends display name, filename, byte length, SHA-256 and schema version.
3. Viewer creates a slide in `uploading` state and returns a size-bound short-lived tus grant.
4. tus receives the package resumably.
5. Completion verifies byte length and places the package in private staging.
6. An asynchronous lightweight importer validates and installs assets.
7. The slide becomes `ready_private` or `failed` with a stable error code.
8. Forge polls status and can open the existing private browser preview.
9. Publication remains an explicit administrator action by default.

## Storage target

Prepared slides should use one canonical immutable DZI tree:

```text
/data/assets/{slide_id}/dzi/
/data/assets/{slide_id}/archive/source.ome.tif   optional
```

Public access must map to the canonical DZI without copying the full tile tree. The exact mapping must be atomic, constrained inside the asset root and reproducible during restore.

## Migration rule

The existing OME-TIFF upload and server conversion path remains operational until real VSI/SVS-to-Forge-to-Viewer evidence, upload recovery, backup/restore and existing-slide regression tests are complete.