# PathLab Desktop Ingest Protocol

Protocol version: `pathlab-desktop-ingest/v1`

PathLab Forge pairs through `/api/v1/desktop/pairings`, then stores the exchanged
revocable credential in Windows Credential Manager. The credential is limited to
prepared ingest, private slide reads, and annotation synchronization.

Viewer advertises two compatible ingest modes. `prepared-v2` retains the
canonical prepared-package workflow. `ome-dynamic-v1` accepts a calibrated,
factor-2, 512-pixel tiled JPEG OME-TIFF directly and keeps it as the only
canonical image payload. Forge uses direct OME only after authenticated
capability negotiation; older Viewer versions continue to receive prepared v2.

Prepared packages use `pathlab-prepared-slide/v2`. A resumable ingest is created
with the immutable artifact revision ID, package length and SHA-256, and manifest
SHA-256 plus optional derivative bytes and file count. An authenticated
`GET /api/v1/desktop/capabilities` advertises accepted schemas and inventory
formats, upload limits, 64 MiB recommended/maximum chunks, and an exact
`omeProfiles` object. V1 requires RGB uint8/sRGB, three channels, factor 2,
512-pixel JPEG Q75 tiles, classic TIFF/BigTIFF support, native JPEG tiles, and
persisted SHA acknowledgement. Forge streams bounded chunks and
falls back to 16 MiB when capabilities are unavailable. Chunks are acknowledged
only after fsync and offset commit; `HEAD` only returns the authoritative offset.

The final chunk changes the ingest to `finalizing` and returns immediately. One
bounded worker claims it transactionally and recovers stale claims at startup.
Finalization uses one streaming TAR pass: it hashes through physical EOF,
validates canonical metadata/order, spools the bounded NDJSON inventory, hashes
and extracts each derivative once, validates JPEG signatures and deterministic
decodes, and derives DZI measurements without a second derivative scan. Output
remains private until every package and inventory check passes, then it is
atomically installed as `ready_private`.

New canonical v2 archives contain `manifest.json`, `manifest.sha256`,
`inventory.ndjson`, then lexicographically ordered derivatives. Existing v2
archives with `files[]` remain accepted. Failed packages stay quota-accounted in
private quarantine until configurable TTL cleanup; successful packages are
deleted only after the slide transaction commits.

Ingest metadata retains the source fingerprint, artifact revision, crop and
downsample coordinate transform, and output calibration. Viewer remains
authoritative for private delivery, library state, permissions, and canonical
annotation revisions.

Direct OME uploads use `POST /api/v1/desktop/ome-ingests`, then the same
resumable content and status contract as prepared ingest. The finalizer hashes
and validates the complete OME, verifies exact geometry and the dynamic profile,
builds a bounded immutable tile index, atomically installs the OME, and commits
the slide with `render_mode=ome_dynamic` and zero stored derivative bytes. A
ready response includes the SHA-256 calculated from the persisted final file.
The request includes `jpegQuality`; it is persisted in the immutable index and
used for on-demand virtual levels, so Viewer never silently increases or reduces
the Forge-selected encoding quality. Viewer independently requires Q75, verifies
standard libjpeg Q75 quantization plus 4:2:0 subsampling across every stored tile,
and rejects non-factor-2 pyramids. The negotiated V1 artifact uses a factor-2
pyramid; the tile reader may still recognize older supported layouts internally.
Missing DZI levels are rendered with a globally aligned resize before
the tile crop to avoid tile-boundary seams.
Failed OME uploads move to quota-accounted private quarantine for bounded TTL
cleanup. No endpoint exposes the OME file or arbitrary byte ranges.

`PATHLAB_DESKTOP_OME_DYNAMIC_ENABLED=false` removes the V1 advertisement and
rejects direct-ingest creation while leaving prepared-v2 unchanged.
