# PathLab Desktop Ingest Protocol

Protocol version: `pathlab-desktop-ingest/v1`

PathLab Forge pairs through `/api/v1/desktop/pairings`, then stores the exchanged
revocable credential in Windows Credential Manager. The credential is limited to
prepared ingest, private slide reads, and annotation synchronization.

Prepared packages use `pathlab-prepared-slide/v2`. A resumable ingest is created
with the immutable artifact revision ID, package length and SHA-256, and manifest
SHA-256 plus optional derivative bytes and file count. An authenticated
`GET /api/v1/desktop/capabilities` advertises accepted schemas and inventory
formats and 64 MiB recommended/maximum chunks. Forge streams bounded chunks and
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
