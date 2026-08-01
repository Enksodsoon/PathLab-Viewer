# OME-Only Viewing with a Shared Tile Cache

## Goal

PathLab Forge uploads its validated, downsampled pyramidal OME-TIFF directly to
PathLab Viewer. Viewer keeps that OME-TIFF as the only canonical image payload
for the slide and provides the existing OpenSeadragon experience through a
global, disposable tile cache capped at 2 GiB.

This design minimizes durable storage without lowering the quality already
present in the OME-TIFF. It does not claim 300-viewer capacity until the
candidate passes the existing production capacity profile.

## Decisions

- Add a new `ome_dynamic` render mode. Existing slides remain `static_dzi`.
- Retain exactly one canonical OME-TIFF per dynamic slide. Do not create a
  complete persistent DZI derivative.
- Cap the shared on-disk cache at 2,147,483,648 bytes across all slides.
- Cap the tile service's decoded-image memory cache at 256 MiB.
- Exclude the disposable cache from backups and logical slide storage
  accounting, but include it in physical free-space monitoring.
- Preserve exact Forge crop, downsample, dimensions, calibration and coordinate
  transform.
- Prefer direct pass-through of browser-decodable JPEG tile payloads from the
  OME-TIFF. Use bounded decode and quality-gated encoding only when direct
  pass-through is impossible.
- Preserve private, individual-public, folder-share, collection-share,
  annotation and de-identification behavior.
- Do not merge, deploy or change OCI infrastructure as part of implementation.

## Why this approach

Three approaches were considered:

1. Full static DZI per slide provides the simplest and fastest delivery, but
   multiplies durable storage.
2. Decoding and encoding every tile request keeps storage low, but adds too much
   cold-request CPU risk for the 300-viewer target.
3. A canonical OME-TIFF plus a bounded shared cache retains low storage while
   making repeat traffic static-file-like. This is the selected approach.

The shared cache is a server-wide performance allowance, not a per-slide copy.
Twenty 434 MB slides therefore consume about 8.7 GB of canonical storage plus
at most 2 GiB of disposable cache, rather than twenty full DZI trees.

## Forge output profile

Forge produces an 8-bit RGB/sRGB pyramidal OME-TIFF with:

- the user-selected exact crop and downsample, including 1.0 and 1.5;
- 512-pixel tiled storage;
- factor-two pyramid levels suitable for continuous OpenSeadragon zoom;
- deterministic geometry, calibration and transform metadata;
- stripped patient/vendor metadata outside the approved PathLab provenance;
- adaptive JPEG encoding that passes the existing native-ROI quality gates.

Before changing the current QuPath writer profile, benchmark factor-two output
against the existing factor-four profile on the same real slide. Record OME
bytes, write time, dimensions, calibration, pyramid completeness, peak process
tree memory, SSIM and Delta E00. The dynamic profile is accepted only if the
Viewer can address its tiles without a full-image decode and all fidelity gates
pass.

Forge does not generate DZI or `.plslide` for `ome_dynamic` uploads. It retains
the local OME-TIFF and uploads it resumably using the paired desktop credential.
Capability negotiation selects this mode only when Viewer explicitly advertises
`ome-dynamic-v1`; otherwise Forge keeps the existing prepared-package fallback.

## Viewer data model and lifecycle

Add a non-null `render_mode` field to `slides`:

```text
static_dzi
ome_dynamic
```

Migration defaults all existing rows to `static_dzi`. Downgrade removes only
the new field; upgrade, downgrade and upgrade must preserve existing rows and
their viewability.

For an `ome_dynamic` slide:

```text
/data/originals/<slide-id>/source.ome.tif
```

is the only canonical image payload. `derivative_bytes` and
`derivative_file_count` remain zero. The worker hashes and validates the file,
extracts bounded metadata and a compact tile index, then transitions directly
to `ready_private`. The index may be stored in SQLite or a small sidecar under
the original directory; it must not contain pixel payloads.

Logical storage accounting counts `source_bytes` only. Admission requires the
declared source bytes plus `max(512 MiB, 10% of source bytes)` physical
headroom. Before rejecting for physical capacity, Viewer may evict disposable
cache entries. The tus upload must be atomically renamed on the same data
volume so successful finalization does not create another source copy.

Trash removes all publication access but retains the OME-TIFF. Permanent
deletion removes the OME-TIFF, tile index, cache namespace and database row.

## Virtual DZI interface

Existing frontend components continue receiving a `tileSource` URL ending in
`slide.dzi`. For dynamic slides this URL is virtual:

```text
GET <authorized-slide-root>/slide.dzi
GET <authorized-slide-root>/slide_files/<level>/<column>_<row>.jpg
GET <authorized-slide-root>/thumbnail.jpg
```

The descriptor is derived from validated dimensions with tile size 512 and
overlap 0. Each tile request validates slide state, publication/share grant,
level and coordinates before accessing the OME-TIFF.

Tile resolution has two paths:

1. **Raw fast path:** read the indexed compressed tile payload with bounded
   positional I/O and return it without pixel decoding or recompression.
2. **Safe fallback:** read only the requested region and nearest pyramid level,
   render through a bounded libvips operation using a profile that passed the
   offline quality gate, and cache the result. Requests do not rerun the
   quality selector.

The implementation must first prove the raw fast path against real Forge OME
output. If TIFF JPEG tables prevent a standalone browser response, the writer
profile may emit independently decodable JPEG tiles or the tile service may
assemble the bounded JPEG tables and tile payload without pixel recompression.
It must never expose arbitrary file ranges or the downloadable OME-TIFF.

Thumbnail and descriptor responses are generated on demand and may use the same
disposable cache. Annotation coordinates remain based on full OME output
dimensions and require no frontend conversion.

## Shared cache

Cache root:

```text
/data/cache/ome-tiles
```

Cache keys include:

```text
source SHA-256
render profile version
level
column
row
response format
```

Required behavior:

- hard maximum: 2,147,483,648 bytes plus at most one temporary tile capped at
  8 MiB;
- eviction target after crossing the maximum: 1.75 GiB;
- atomic temporary-write, fsync and rename;
- regular files only; reject links and unsafe paths;
- request coalescing so one cache miss performs one tile operation;
- most-recently-used eviction using bounded metadata, never a request-time full
  filesystem scan;
- startup reconciliation that removes partial, invalid and unreferenced files;
- immediate purge support when physical free space crosses the critical
  threshold;
- cache failures degrade to regeneration or a bounded `503`, never slide-data
  corruption;
- cache content excluded from backup archives and canonical quota usage.

Published slide activation prewarms the descriptor, thumbnail and the lowest
viewing levels under a bounded queue. Prewarming may not delay publication or
starve active tile requests.

## Delivery and authorization

The API retains authority for private sessions and public/share grants. Cache
hits use internal redirects so Caddy transfers bytes without Python copying
the response body.

Individual publication URLs include a publication version. Unpublish removes
the corresponding cache namespace before the grant transaction completes.
Folder and collection shares continue rechecking active share state. Cache keys
never contain display names, patient data or credentials.

The original OME-TIFF is not mounted into Caddy and has no download route.
Only the virtual descriptor, thumbnail and validated tile coordinates are
servable.

## Runtime isolation

Tile work runs in a bounded internal service built from the existing backend
image. It owns:

- positional OME reads;
- raw-tile response assembly;
- fallback libvips rendering;
- request coalescing;
- 256 MiB decoded-image cache;
- the 2 GiB disk-cache policy.

API processes keep authentication, authorization, metadata and lifecycle
transactions. Caddy keeps TLS and byte delivery. Legacy conversion remains in
the existing serial worker. Tile-service failure must not affect login,
library, upload, annotation or deletion APIs.

Resource limits are selected from measured cold/warm load evidence, not by
increasing OCI shape size. The implementation must not claim 300-user support
from unit tests or local synthetic results.

## Backups and recovery

Backups include the SQLite snapshot, originals and any legacy static
derivatives. They exclude `/data/cache`. Restore recreates dynamic tile indexes
if missing and starts with an empty cache.

Backup copies are expected recovery storage and are separate from canonical
application storage. At least one encrypted, verified backup must remain
outside the application VM.

## Compatibility

- Existing `static_dzi` slides, publication hardlinks and URLs remain valid.
- Existing admin OME uploads retain their current behavior unless the request
  explicitly selects `ome_dynamic`.
- Existing prepared-package v2 ingest remains accepted.
- Older Forge versions fall back to prepared packages.
- New Forge versions do not send a dynamic OME unless capabilities advertise
  support.
- Migration upgrade, downgrade and upgrade must preserve existing slide rows.

## Failure handling

- Source hash or size mismatch: fail before `ready_private`.
- Unsupported pyramid/tile layout: reject dynamic mode or use the explicitly
  validated fallback; never silently create a full DZI.
- Cache corruption: delete the entry and regenerate.
- Concurrent miss: one producer; bounded waiters receive the same result.
- Cache pressure: evict to 1.75 GiB before accepting new cached output.
- Low disk: purge cache first, then reject new uploads if canonical headroom
  still fails.
- Tile-service overload: return `503` with bounded retry guidance; do not queue
  unbounded work.
- Server restart: retain OME and index, discard partial cache writes, recover
  without conversion.
- Publication revocation: invalidate its namespace before access is considered
  revoked.

## Quality and acceptance gates

Use the same authorized Forge OME for local and Viewer comparisons.

Quality:

- exact width, height, crop transform and calibration;
- complete factor-two pyramid;
- no missing, duplicate or out-of-bounds tiles;
- no visible seams at tile boundaries;
- raw fast-path tiles decode to the same pixels as their OME tile payload;
- fallback tiles pass windowed SSIM at least 0.985 for every deterministic ROI
  and mean Delta E00 at most 1.5;
- deterministic descriptor, index and cache keys.

Storage:

- canonical dynamic-slide bytes equal source OME bytes plus bounded
  index/database metadata;
- no persistent DZI exists for a dynamic slide;
- shared cache never exceeds 2 GiB plus one bounded temporary tile;
- cache is absent from backup archives and logical slide quota.

Performance:

- cold descriptor and thumbnail become available after validation without a
  full DZI pass;
- warm cache hits use internal redirect delivery;
- test 300 viewers with the existing two-minute ramp, ten-minute hold and
  one-minute ramp-down;
- test both one popular slide and a deterministic mixed-slide manifest;
- tile/API errors below 0.1%;
- tile/API p95 below 500 ms;
- host CPU below 80% sustained and memory below 85%;
- no swap growth, OOM kill or container restart;
- administrator operations remain responsive while upload validation and cache
  misses occur.

Run backend pytest, Ruff and strict mypy; frontend Vitest, ESLint, TypeScript,
production build and cross-browser viewer workflows; Compose and repository
policy checks; malicious path/index/cache cases; source mutation; low
disk/RAM; restart; revocation; cache stampede; legacy DZI; and migration
upgrade-downgrade-upgrade.

## Delivery

Implement Viewer from fresh `origin/main` in an isolated worktree and Forge
from its isolated optimization branch. Produce coordinated draft PRs and
machine-readable evidence. Do not merge, deploy, resize OCI, delete existing
slides or modify production data without separate authorization.
