# Prepared Slide Ingest Architecture

## Status

Proposed durable architecture for accepting a locally prepared PathLab Forge package without server-side WSI decoding or pyramid generation.

This design extends the current library, worker, storage-accounting, thumbnail, publication-grant, sharing, Trash, annotation, delivery, backup, and reconciliation contracts. It does not create parallel versions of those systems.

## Objective

Allow an approved desktop client to upload one validated `.plslide` package containing browser-ready derivative assets. The server verifies and installs the package through the current serial worker, then exposes the slide through the existing administrator library and private preview.

The original proprietary WSI and standardized OME-TIFF remain local to the desktop in package version 1.

## Package version 1

Uncompressed POSIX TAR layout:

```text
manifest.json
derivative/slide.dzi
derivative/slide_files/<level>/<column>_<row>.jpg
derivative/thumbnail.jpg
```

No other entries are accepted in version 1.

Required derivative settings:

```text
DZI tile size: 512
DZI overlap: 1
DZI format: jpg
DZI JPEG quality: 85
Thumbnail filename: thumbnail.jpg
Thumbnail longest edge: 640
Thumbnail JPEG quality: 82
Pixel model: interleaved 8-bit RGB/sRGB
```

The canonical JSON Schema belongs at:

```text
contracts/prepared-slide-v1.schema.json
```

The manifest records producer versions, source provenance without absolute paths, crop, downsample, render profile, image dimensions, physical scale when known, descriptor paths, measured derivative bytes, file count, and tile count.

All manifest values are untrusted until checked against actual archive contents.

## Existing state model

The MVP reuses the current slide states:

```text
uploading -> queued -> validating -> converting -> ready_private
```

For `prepared_package` ingest:

- `queued` means waiting for the existing serial worker;
- `validating` means package hash, archive, manifest, DZI, JPEG, and declared-bound validation;
- `converting` means staging, atomic installation, and derivative measurement; it performs no WSI conversion.

A new `ingest_mode` field distinguishes:

```text
legacy_ome
prepared_package
```

The default is `legacy_ome`, preserving all existing rows and behavior. Reusing current states keeps library processing counts, status polling, frontend state unions, stale-job recovery, and Trash busy-state handling compatible.

## Reservation and storage accounting

Prepared reservation is separate from legacy OME admission.

Request inputs include:

- display name;
- `.plslide` basename;
- package byte length;
- package SHA-256;
- schema version;
- declared derivative bytes;
- declared derivative file count;
- optional active folder ID.

Required reservation:

```text
package bytes
+ declared derivative bytes
+ configured extraction safety headroom
```

The server enforces independent limits for package bytes, extracted bytes, entry count, path depth, filename length, and individual file size.

During active ingest, `reserved_bytes` accounts for upload and extraction. After successful import, the uploaded package is deleted and accounting counts the measured private derivative only. A failed retained package remains accounted until retry or deletion.

The existing `source_bytes` field may continue to expose the uploaded artifact size for library display. Storage-accounting expressions must branch on `ingest_mode` so a deleted prepared package is not counted as retained storage.

An optional `folderId` places the slide directly in an active folder. No folder places it in Unfiled. Reservation rejects missing or trashed folders.

## Upload transport

New desktop JSON routes use `/api/v2/desktop`. The existing tus transport remains `/api/v1/uploads/`.

Proposed routes:

```text
GET  /api/v2/desktop/capabilities
POST /api/v2/desktop/prepared-slides
GET  /api/v2/desktop/prepared-slides/{slideId}
```

The reservation returns the existing tus endpoint and a short-lived grant bound to slide ID and expected length. Tus pre-create and post-finish hooks remain private behind Caddy.

Upload finalization branches on the persisted slide `ingest_mode`:

- legacy OME keeps current TIFF-signature and original-storage behavior;
- prepared package moves the completed upload to a private package path and queues `Job.kind=prepared_import`.

## Desktop authorization

Desktop authorization is separate from the browser cookie/CSRF session.

Initial credentials are:

- administrator-created;
- random and high entropy;
- stored hashed at rest;
- revocable;
- scoped;
- recorded in audit events without secret material.

Initial scopes:

```text
prepared:create
prepared:upload
prepared:status
folders:read        optional
```

Desktop credentials do not grant password, recovery, annotation, publication, sharing, Trash, database, or filesystem access.

Browser-assisted device pairing may replace manual credential creation after the end-to-end ingest path is validated.

## Safe archive validation

Treat every package as hostile.

Reject:

- absolute paths;
- `..` or backslash traversal;
- Windows drive paths;
- null bytes;
- duplicate normalized paths;
- symbolic links and hard links;
- sparse, device, FIFO, socket, or other special entries;
- nested archives;
- unexpected files or extensions;
- excessive entry count, extracted bytes, path depth, filename length, or per-file size;
- missing or duplicate manifest, descriptor, thumbnail, or tile tree;
- malformed JSON or unsupported schema;
- XML external entities or malformed DZI;
- manifest/descriptor dimension mismatch;
- invalid JPEG signatures or tile-coordinate names;
- actual derivative size/file count above the reservation bounds.

Inspection and extraction are streaming and bounded. The complete package is never buffered in memory.

## Worker integration

Do not add another runtime service for the MVP.

The current worker scheduler already provides:

- serial job processing;
- heartbeat health;
- graceful shutdown;
- stale-job recovery;
- incomplete-upload cleanup;
- storage-capacity monitoring.

`process_next` dispatches `Job.kind=prepared_import` to a focused prepared-import helper. Archive and manifest logic live in dedicated modules rather than expanding `worker.py` inline.

Processing flow:

1. verify private package path and expected byte length;
2. compute SHA-256 and compare with the reservation;
3. transition to `validating`;
4. inspect TAR headers and fixed layout;
5. validate manifest, DZI, thumbnail, tile names, signatures, counts, and sizes;
6. extract `derivative/` into a unique private staging directory;
7. validate the extracted tree with the existing derivative rules;
8. transition to `converting` for atomic installation;
9. install into the existing private derivative root;
10. measure derivative bytes and file count;
11. set `thumbnail_filename=thumbnail.jpg`;
12. store actual image metadata from the verified manifest;
13. clear reservation, set privacy pending, mark the job complete, and transition to `ready_private`;
14. delete the uploaded package only after the database and filesystem result are durable.

Failures use stable codes, clear `reserved_bytes` only when retained artifacts are correctly accounted, and preserve enough state for explicit retry or re-upload.

## Final private derivative

Prepared import installs the same final layout produced by legacy conversion:

```text
private/{slideId}/slide.dzi
private/{slideId}/slide_files/
private/{slideId}/thumbnail.jpg
```

This keeps current private preview, thumbnail delivery, annotations, publication grants, shared viewers, Trash, deletion, backup, and reconciliation compatible.

## Library behavior

After import, a prepared slide:

- appears in All and Unfiled or its selected folder;
- contributes to existing navigation and storage counts;
- exposes measured `derivativeBytes`;
- serves the existing thumbnail endpoint;
- loads through `/admin/preview/{slideId}`;
- participates in existing metadata search after metadata edits;
- starts with privacy status pending;
- is eligible for existing publication/share review only when ready;
- uses current Trash, restore, permanent deletion, annotation, collection, and saved-view behavior.

The prepared-ingest API does not create collections, annotations, publication grants, or shares.

## Publication and delivery

Do not replace the current hardlink/grant design.

A valid prepared derivative is published through existing `ensure_grant` behavior. The first grant creates validated hardlinked delivery aliases, later grants reuse the canonical private derivative, and removing the final grant removes the public alias.

Explicit de-identification confirmation remains mandatory. Prepared import never marks privacy review as passed.

## Reconciliation, backup, and deletion

Storage reconciliation must understand `ingest_mode` and prepared reservations while continuing to:

- measure canonical private derivatives;
- reject ready slides with missing derivatives;
- restore individual/share deliveries from grants;
- rebuild share manifests.

Deletion removes:

- retained prepared package, if any;
- package/extraction staging;
- private derivative;
- current public/delivery aliases through existing grant cleanup.

Backup and restore require no new public asset format beyond the database and existing private/public/delivery roots.

## Compatibility and migration

The first migration after current head adds only backward-compatible prepared-ingest fields and credential tables. Existing slides remain `legacy_ome` and retain public identifiers, folders, collections, grants, thumbnails, annotations, and Trash state.

The legacy OME upload and conversion path remains enabled until real Forge packages, interrupted upload, worker restart, storage reconciliation, publication/share, annotation preview, Trash, backup/restore, and current browser upload regressions are evidenced.

## Verification

Required automated coverage includes:

- package schema and typed validation;
- hostile TAR corpus;
- prepared reservation/storage races;
- folder validation;
- tus pre-create/post-finish separation by ingest mode;
- hash and declared-bound mismatch;
- worker stale recovery and retry;
- atomic derivative installation and rollback;
- thumbnail/private preview;
- library navigation/status/storage responses;
- existing publication grants and sharing;
- Trash/restore/permanent deletion;
- reconciliation and backup/restore;
- unchanged legacy OME upload and conversion.

Operational readiness additionally requires real Forge-generated VSI/SVS/OME packages, external viewing, network shaping, physical desktop clients, and storage-capacity evidence.
