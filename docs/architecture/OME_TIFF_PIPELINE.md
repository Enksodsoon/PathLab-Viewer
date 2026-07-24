# OME-TIFF Processing Architecture

## Purpose

PathLab Viewer accepts a constrained OME-TIFF input, keeps the original file private, and produces a sanitized Deep Zoom derivative for browser viewing. This document records the durable system contract rather than an implementation checklist.

## Supported input

The primary image must be a two-dimensional interleaved RGB image with one Z plane and one timepoint (`SizeZ=1`, `SizeT=1`). The validator supports:

- classic TIFF and BigTIFF;
- little-endian and big-endian byte order;
- flat images and SubIFD pyramids;
- tiled and striped storage;
- unsigned 8-bit and 16-bit samples;
- RGB or YCbCr photometric interpretation;
- JPEG, LZW, Deflate, or uncompressed payloads.

Missing physical scale is accepted. Auxiliary labels, thumbnails, macros, and non-primary series are ignored. Plain non-OME TIFF files, Z-stacks, time series, unsupported pixel formats, malformed metadata, truncated data, and invalid offsets are rejected.

A bounded compatibility path accepts legacy ImageJ converter output only when the first IFD independently contains a valid, decodable 2D RGB image and the metadata declares one Z plane and one timepoint. It does not relax validation for arbitrary TIFF files or stacks.

## Processing flow

1. The authenticated administrator reserves an upload and receives a short-lived tus upload token.
2. `tusd` stores resumable chunks in the private upload area.
3. Finalization verifies the declared size, TIFF signature, and SHA-256 digest before queueing work.
4. The worker selects the highest-resolution primary series and validates the OME/TIFF contract.
5. Sixteen-bit samples are deterministically converted with `round(value / 257)`.
6. Embedded ICC profiles are transformed to sRGB; otherwise values are treated as sRGB.
7. libvips writes 512-pixel JPEG Deep Zoom tiles with one-pixel overlap.
8. Generator metadata is removed and the derivative tree is restricted to one `.dzi` descriptor and JPEG tiles.
9. A complete private derivative replaces the previous version atomically.
10. Publishing copies only the sanitized derivative into the public tree.

## Runtime components

| Component | Responsibility |
|---|---|
| Caddy | HTTPS termination, SPA delivery, and API proxying |
| FastAPI | Authentication, slide lifecycle, upload admission, metadata, and publication controls |
| tusd | Resumable multi-gigabyte upload transport |
| Worker | Validation, conversion, cleanup, and job recovery |
| SQLite WAL | Single-node metadata, sessions, jobs, audit records, and recovery state |
| Filesystem storage | Private originals, temporary uploads, private derivatives, and published derivatives |

## Privacy boundary

Original OME-TIFF files, temporary uploads, private previews, databases, logs, and secrets are never mounted into Caddy. Public viewers receive only an unlisted identifier, slide metadata required for display, one DZI descriptor, and sanitized JPEG tiles through API routes that recheck the active publication grant or share capability on every request.

## Performance contract

Conversion runs in the background and is resource-bounded. Public tile responses use `private, no-store` so share rotation, expiry, and revocation take effect on the next request. The target load scenario is documented in `tests/load`; measured readiness evidence belongs in `docs/evidence/QA.md` rather than in static architecture claims.
