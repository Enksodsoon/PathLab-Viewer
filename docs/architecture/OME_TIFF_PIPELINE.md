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
3. Finalization verifies the declared size and TIFF signature before queueing work; the worker records the SHA-256 digest before conversion.
4. The worker selects the highest-resolution primary series and validates the OME/TIFF contract.
5. Sixteen-bit samples are deterministically converted with `round(value / 257)`.
6. Embedded ICC profiles are transformed to sRGB; otherwise values are treated as sRGB.
7. libvips writes 512-pixel JPEG Deep Zoom tiles at quality 85 with one-pixel overlap.
8. The same conversion source produces `thumbnail.jpg` with a 640-pixel longest edge and quality 82.
9. Generator metadata is removed and the derivative tree is restricted to one `slide.dzi` descriptor and JPEG files.
10. A complete private derivative replaces the previous version atomically.
11. Publication validates the private derivative and atomically creates hardlinked delivery aliases. Removing the final grant removes the aliases without modifying the canonical private derivative.

## Runtime components

| Component | Responsibility |
|---|---|
| Caddy | HTTPS termination, SPA delivery, API proxying, static public delivery, and approved internal file redirects |
| FastAPI | Authentication, library lifecycle, upload admission, metadata, privacy review, grants, and delivery authorization |
| tusd | Resumable multi-gigabyte upload transport |
| Worker | Validation, conversion, cached thumbnail generation, cleanup, capacity monitoring, and job recovery |
| SQLite WAL | Single-node metadata, sessions, folders, collections, jobs, grants, annotations, audit records, and recovery state |
| Filesystem storage | Private originals, temporary uploads, private derivatives, delivery aliases, and share manifests |

## Privacy boundary

Original OME-TIFF files, temporary uploads, databases, logs, and secrets are not exposed through Caddy routes. Private derivatives are mounted read-only only for an API-authorized internal file redirect and have no direct public route. Public viewers receive only an unlisted identifier, approved display metadata, one DZI descriptor, sanitized JPEG tiles, and cached thumbnails through active publication/share delivery paths.

Individual and share revocation remove the corresponding hardlinked aliases or share manifests. Public metadata and pixel release remain gated by explicit de-identification confirmation.

## Performance contract

Conversion runs in the background with one resource-bounded worker, bounded libvips cache settings, heartbeat monitoring, stale-job recovery, upload cleanup, and storage-capacity warnings. Public derivative files use immutable caching only while the corresponding delivery alias exists; revocation removes the delivery path. The target load scenario is documented in `tests/load`; measured readiness evidence belongs in `docs/evidence/QA.md` rather than in static architecture claims.
