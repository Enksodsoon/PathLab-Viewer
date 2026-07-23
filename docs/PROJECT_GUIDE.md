# PathLab Viewer Project Guide

## Product overview

PathLab Viewer is a private-first web application for whole-slide image review and teaching. One authenticated administrator uploads an OME-TIFF file, the server validates and converts it into browser-friendly Deep Zoom tiles, and the administrator can publish an unlisted read-only link. Original slide files remain private.

## Current product scope

### Included

- OME-TIFF uploads up to 5 GiB
- One administrator account
- Resumable uploads
- Background validation and conversion
- Private preview
- Publish, unpublish, retry, and delete actions
- Unlisted anonymous public viewing
- Virtual folders, slide teaching metadata, and direct-child shared collections
- Responsive desktop, tablet, and phone interfaces
- Password change and server-assisted account recovery
- Docker Compose deployment with HTTPS

### Excluded

- public raw-file downloads;
- self-registration or multiple administrator accounts;
- teams, roles, and shared workspaces;
- slide galleries or public indexing;
- annotations and assessments;
- fluorescence controls;
- Z-stacks and time series.

Changes to these boundaries require an explicit product and security review.

## System architecture

| Area | Technology | Responsibility |
|---|---|---|
| Web application | React, TypeScript, Vite | Administration interface and public viewer |
| Viewer | OpenSeadragon | Deep Zoom pan, zoom, navigator, and scale display |
| API | Python, FastAPI, Pydantic | Authentication, slide lifecycle, upload admission, metadata, and publication |
| Persistence | SQLite WAL, SQLAlchemy, Alembic | Users, sessions, jobs, slides, virtual folders, publication grants, audit events, and recovery state |
| Upload transport | tusd and `tus-js-client` | Resumable multi-gigabyte uploads |
| TIFF inspection | `tifffile` and OME-XML parsing | Structural and metadata validation |
| Conversion | libvips and pyvips | Resource-bounded JPEG Deep Zoom generation |
| Edge and static delivery | Caddy | HTTPS, SPA delivery, immutable tiles, and API proxying |
| Deployment | Docker Compose, systemd, Terraform | Repeatable single-node OCI deployment |
| Load verification | k6 | Reproducible public-viewer concurrency scenario |

The runtime is separated into Caddy, FastAPI, tusd, and a conversion worker. SQLite and filesystem storage are shared through private application volumes.

## Slide lifecycle

```text
uploading → queued → validating → converting → ready_private → published
```

`failed` represents a recoverable processing failure. `deleting` represents explicit removal.

1. The browser requests upload admission and a signed, short-lived tus token.
2. tusd writes resumable chunks to a private temporary directory.
3. Finalization verifies declared length, TIFF signature, and SHA-256 before creating a queued job.
4. The worker claims the job, heartbeats while processing, and can recover stale work.
5. Validation selects the highest-resolution primary OME series and enforces the supported input contract.
6. libvips creates one DZI descriptor and 512-pixel JPEG tiles.
7. Generator metadata and unexpected derivative files are removed or rejected.
8. The complete derivative becomes available for private preview.
9. The first publication grant atomically hardlinks the sanitized private derivative into the public tree; later grants reuse it.
10. The public route `/s/{publicId}` loads the metadata and tiles without exposing the original.

Folders are SQLite metadata only: creating, renaming, sorting, or moving them does
not scan storage, move tile trees, copy images, or invoke conversion. A shared
folder publishes eligible direct children through grants and is opened at
`/f/{folderPublicId}`. See
[`architecture/LIBRARY_SHARING.md`](architecture/LIBRARY_SHARING.md).

## OME-TIFF contract

The primary image must be an interleaved two-dimensional RGB image with `SizeZ=1` and `SizeT=1`. The validator supports classic TIFF and BigTIFF, either byte order, flat or SubIFD pyramids, tiled or striped images, unsigned 8-bit or 16-bit samples, RGB or YCbCr, and JPEG, LZW, Deflate, or uncompressed payloads.

For 16-bit RGB, the conversion rule is `round(value / 257)`. Embedded ICC profiles are transformed to sRGB; values without a profile are treated as sRGB.

Missing physical scale is accepted. Auxiliary labels, thumbnails, macros, and non-primary series are ignored. Plain non-OME TIFF files, unsupported dimensions or pixel formats, malformed metadata, truncation, invalid offsets, and decompression failures are rejected with stable failure codes. Failed or incomplete derivatives are never published.

See [`architecture/OME_TIFF_PIPELINE.md`](architecture/OME_TIFF_PIPELINE.md) for the full durable contract.

## Privacy and security boundaries

Original files are stored under generated identifiers in a private storage root. Public links expose only an unlisted public identifier, display metadata required by the viewer, one DZI descriptor, and sanitized JPEG tiles.

The application uses:

- Argon2id password hashes;
- signed browser sessions;
- CSRF protection for authenticated mutations;
- login and recovery throttling;
- generated storage and publication identifiers;
- storage capacity and upload headroom checks;
- atomic file replacement and publication;
- audit events that exclude secrets;
- explicit public-path restrictions in Caddy.

Credentials, recovery codes, patient information, source slides, temporary uploads, private derivatives, databases, and logs must never be committed or routed through the public tile path.

## Administrator password management

A signed-in administrator can change the password through the Account Security dialog. A forgotten password is recovered with a server-generated one-time code that expires after 15 minutes. Successful password change, recovery, or emergency CLI reset revokes all active sessions and unused recovery codes.

The code-issuance command and operational procedure are documented in [`../deploy/README.md`](../deploy/README.md). The security design is documented in [`architecture/PASSWORD_RECOVERY.md`](architecture/PASSWORD_RECOVERY.md).

## Development and verification

The standard local toolchain is Python 3.12, Node.js 24, pnpm 11, and native libvips for complete conversion runs.

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

Behavior changes require regression coverage. Security, validation, state-transition, and file-handling changes should be tested at the responsible layer and reviewed for privacy impact.

## Deployment model

The supported production topology is a single Linux host running the Docker Compose stack behind Caddy HTTPS. Originals, temporary uploads, private derivatives, public derivatives, and SQLite data use explicit persistent storage paths. Deployment updates must preserve backups, database migrations, secret handling, and rollback options.

Use [`../deploy/README.md`](../deploy/README.md) for provisioning, updates, password recovery, backup, and restore procedures. Do not copy temporary hostnames, IP addresses, credentials, or environment-specific identifiers into general project documentation.

## Readiness and evidence

Automated CI verifies code quality, tests, builds, and Compose validity. It does not alone establish real-file compatibility, external concurrency, shaped-network performance, physical-device usability, backup recovery, infrastructure cost, or production security.

The current result of each operational gate belongs in [`evidence/QA.md`](evidence/QA.md). Product and architecture documentation should state the target and method, while the evidence ledger records whether the latest candidate has actually met it.
