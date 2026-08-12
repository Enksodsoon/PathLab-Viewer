# `pathlab-private-results/v1`

The private result sidecar is a TAR.GZ containing:

- `manifest.json`
- `objects.ndjson`
- `measurements.ndjson`
- `runs.ndjson`
- optional `attachments/<sha256>.<extension>` files

The manifest binds the sidecar to its artifact revision and persisted slide SHA-256. Every attachment name is its content SHA-256. Archive paths, links, expanded bytes, records, objects, masks, and request chunks are bounded before activation.

Viewer stores searchable run, object, and measurement metadata in the database. Attachments remain managed private files. Imported objects stay hidden until the complete delivery is validated and committed. The create and upload operations are idempotent; an existing completed delivery or private annotation edit causes a conflict instead of an overwrite.

The API is private and credential-scoped:

- `POST /api/v2/desktop/slides/{slideId}/result-deliveries`
- `HEAD/PATCH .../{deliveryId}/content`
- `GET/DELETE .../{deliveryId}`

The contract does not expose public routes or frontend functionality.
