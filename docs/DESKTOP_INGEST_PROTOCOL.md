# PathLab Desktop Ingest Protocol

Protocol version: `pathlab-desktop-ingest/v1`

PathLab Forge pairs through `/api/v1/desktop/pairings`, then stores the exchanged
revocable credential in Windows Credential Manager. The credential is limited to
prepared ingest, private slide reads, and annotation synchronization.

Prepared packages use `pathlab-prepared-slide/v2`. A resumable ingest is created
with the immutable artifact revision ID, package length and SHA-256, and manifest
SHA-256. Forge uploads bounded 16 MiB chunks with `Upload-Offset`; `HEAD` returns
the authoritative offset. Viewer verifies the archive hash, manifest hash,
revision identity, complete file inventory, every derivative hash, safe paths,
and the DZI layout before atomically installing a `ready_private` slide.

Ingest metadata retains the source fingerprint, artifact revision, crop and
downsample coordinate transform, and output calibration. Viewer remains
authoritative for private delivery, library state, permissions, and canonical
annotation revisions.
