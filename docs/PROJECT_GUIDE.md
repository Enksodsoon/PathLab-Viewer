# PathLab Viewer: project guide

## What this project is

PathLab Viewer is a small, private-first web application for viewing very large pathology slides (whole-slide images, or WSIs). An administrator uploads an OME-TIFF, the server validates and converts it into web-friendly Deep Zoom tiles, and the administrator can publish an unlisted link for read-only viewing. The original TIFF remains private.

This guide explains the product, the implementation, the tools used, how a slide moves through the system, how to run it, and what the current pull request and OCI deployment mean.

## The original objective

The project started from a compact WSI viewer requirement:

- accept OME-TIFF files up to 5 GiB;
- keep originals for future use, but never expose them through the public viewer;
- allow one authenticated administrator to upload, review, publish, unpublish, retry, and delete slides;
- let anonymous users view published slides through unlisted links;
- stay responsive on desktop, tablet, and phone;
- use small, cacheable JPEG tiles so many viewers can read the same slide efficiently;
- deploy on OCI Always Free with HTTPS.

The intentionally excluded scope is annotations, teams, a gallery, raw downloads, fluorescence controls, Z-stacks, and timepoints. A slide may contain only one Z plane and one timepoint (`SizeZ=1`, `SizeT=1`).

## What we built, from beginning to now

1. We created a test-first OME-TIFF contract and parameterized fixtures for classic TIFF and BigTIFF, both byte orders, flat and pyramidal layouts, tiled and striped storage, 8- and 16-bit RGB, and the supported compression formats.
2. We built the service around four runtime containers: Caddy, FastAPI, tusd, and a background worker.
3. We added SQLite in WAL mode, migrations, generated storage IDs, atomic file operations, a 120 GB application cap, upload headroom checks, SHA-256 recording, audit events, and a slide/job state machine.
4. We added resumable tus 1.0 uploads with signed short-lived upload tokens, size/signature checks, incomplete-upload expiry, and finalization checks.
5. We implemented OME validation, the 16-bit to 8-bit conversion rule, ICC-to-sRGB handling, libvips Deep Zoom generation, derivative cleanup, and private-to-public publication.
6. We added a bounded compatibility path for the supplied ImageJ-converter OME-TIFF example. It accepts that file when its first IFD is a valid decodable 2D RGB image with one Z plane and one timepoint, while still rejecting plain non-OME TIFFs and ImageJ Z-stacks.
7. We built the React/OpenSeadragon admin and public viewer experiences, including upload progress/resume, processing errors, preview, publish controls, copy-link, responsive controls, fullscreen, navigator, scale information, 404 handling, and `noindex` for unlisted slides.
8. We added administrator password change and recovery. Recovery codes are one-time, expire after 15 minutes, revoke sessions, and are never stored in the repository.
9. We ran backend, frontend, container, real-file, browser, and responsive checks. The latest local backend result is 218 passing tests; the required PR CI run is green.
10. We deployed the reviewed candidate to OCI and verified the live health endpoints, admin page, existing published slide metadata, DZI descriptor, representative JPEG tile, migration head, and backup creation.

## Technology choices

| Area | Technology | Why it is used |
|---|---|---|
| API | Python, FastAPI, Pydantic | Typed HTTP APIs and clear validation errors |
| Persistence | SQLite WAL, SQLAlchemy, Alembic | Durable single-node metadata with safe migrations and concurrent reads |
| Authentication | Argon2id, signed sessions, CSRF, throttling | Password protection and browser-session safety |
| Uploads | tusd and `tus-js-client` | Resume-friendly uploads for multi-gigabyte files |
| TIFF inspection | `tifffile`, OME-XML parsing | TIFF/BigTIFF structure and metadata validation |
| Conversion | libvips/pyvips | Low-memory, fast pyramid and JPEG tile generation |
| Frontend | React, TypeScript, Vite | Maintainable admin and public SPA |
| Viewer | OpenSeadragon | Smooth pan/zoom for Deep Zoom images |
| Serving | Caddy, Docker Compose | HTTPS, static tile caching, and simple deployment |
| Operations | systemd, Terraform, DuckDNS | Repeatable OCI setup, service recovery, and DNS |
| Performance proof | k6 | Reproducible 100-viewer load scenario |

## A slide's lifecycle

`uploading → queued → validating → converting → ready_private → published`

`failed` is used for recoverable processing failures and `deleting` for explicit removal.

1. The browser asks the API for an upload admission and signed tus token.
2. tusd stores chunks in a temporary upload area; the browser can resume after interruption.
3. Finalization checks the declared size, TIFF signature, and SHA-256, then creates a queued job.
4. The worker claims the job, heartbeats while working, and can recover stale work.
5. Validation selects the highest-resolution primary OME series and rejects unsupported dimensions, channels, compression, truncation, or malformed metadata.
6. libvips writes a complete `.dzi` descriptor and 512-pixel JPEG tiles (quality 85, overlap 1). `vips-properties.xml` is explicitly removed and only `.dzi` plus JPEG tiles are allowed to remain.
7. The derivative is previewed privately. Publication atomically copies only sanitized derivatives to Caddy's immutable public tree.
8. The public route `/s/{publicId}` loads metadata and tiles without exposing the original file.

## OME-TIFF contract

Accepted inputs are classic TIFF or BigTIFF, big- or little-endian, flat or SubIFD pyramidal, tiled or striped, interleaved RGB/YCbCr, unsigned 8- or 16-bit, and JPEG, LZW, Deflate, or uncompressed payloads. Missing physical pixel scale is allowed. Auxiliary thumbnails, labels, macros, and non-primary series are ignored.

For uint16 RGB, conversion is deterministic: `round(value / 257)` to 8-bit. Embedded ICC profiles are converted to sRGB; without a profile, values are treated as sRGB.

Stable failure codes include `INVALID_OME_XML`, unsupported dimensions/data, truncation, invalid offsets, unsupported compression, and decompression failure. No failed derivative is published.

## Privacy and security model

Originals live under generated IDs and a private storage root. Public URLs expose only an unlisted public ID and sanitized tiles. The app uses one admin account, Argon2id password hashes, signed sessions, CSRF protection, rate limiting, audit events, upload size/headroom limits, and atomic publication. Secrets belong in deployment environment files or secret managers, never in Git. Do not put passwords or recovery codes in commits, screenshots, logs, or tickets.

## Password management

The Account Security dialog allows a logged-in administrator to change the password. Passwords are 12–128 Unicode code points; a changed password must differ from the current one. Forgot password uses a server-generated one-time recovery code, valid for 15 minutes. The CLI command is documented in [`deploy/README.md`](../deploy/README.md). A successful change or reset revokes all existing sessions and unused recovery codes.

## Running and verifying locally

See the root README for the short path. The normal development dependencies are Python 3.12, Node 24, pnpm 11, and native libvips. Useful checks are:

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

The detailed evidence ledger, screenshots, real-file checks, and known gaps are in [`docs/evidence/QA.md`](evidence/QA.md).

## OCI and current merge status

The live test deployment is at [pathlab-viewer.140-245-126-212.sslip.io](https://pathlab-viewer.140-245-126-212.sslip.io/admin). It is an OCI Always Free A1 deployment using Caddy HTTPS, Docker Compose, a 50 GB boot volume, and a 150 GB data volume. The active reviewed commit is `0d94cc3`.

Pull request [#1](https://github.com/Enksodsoon/PathLab-Viewer/pull/1) targets `main` and remains a draft until the owner decides to merge. It contains the OME-TIFF viewer, authentication, upload/worker pipeline, UI, tests, deployment files, password recovery, and this documentation. The latest required PR CI run passed backend, web, and container checks. Do not merge `main` automatically.

## What remains before calling the product fully ready

The implementation is usable, but the original acceptance contract is evidence-driven. The remaining gates are the measured external 100-viewer/10-minute k6 run, shaped 10 Mbps/50 ms interaction evidence, physical desktop/tablet/phone evidence, a clean backup-restore drill, and OCI billing/Always-Free proof. Until those artifacts are attached, label production readiness `BLOCKED`, not `READY`.

## Glossary

- **OME-TIFF**: TIFF plus OME-XML metadata describing image dimensions and channels.
- **WSI**: Whole-slide image, commonly many gigabytes and too large for a normal `<img>` element.
- **DZI**: Deep Zoom Image descriptor used by OpenSeadragon to request only visible tiles.
- **IFD**: TIFF image-file directory; a TIFF page/series entry.
- **tusd**: Reference tus resumable-upload server.
- **Primary series**: The highest-resolution image selected for viewing, excluding labels and thumbnails.
