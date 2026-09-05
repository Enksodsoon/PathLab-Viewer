# PathLab Viewer

PathLab Viewer is a private-first web application for reviewing and publishing OME-TIFF whole-slide images. An authenticated administrator uploads an original slide, the server validates and converts it into sanitized Deep Zoom JPEG tiles, and anonymous viewers can open an unlisted read-only link. Original slide files remain private.

## Core capabilities

- Resumable OME-TIFF uploads up to 5 GiB
- Background validation and Deep Zoom conversion
- Private preview before publication
- Unlisted, read-only public slide links
- Responsive OpenSeadragon viewing on desktop, tablet, and phone
- Single-administrator authentication with password recovery
- Storage admission controls, audit records, and atomic publication
- Nested folders, many-to-many collections, saved views, and restorable Trash
- Bounded server-side library search, filters, facets, and cursor pagination
- Conversion-time cached thumbnails for library browsing
- Default-disabled live Classroom sessions with teacher follow, bounded
  questions and control, transient teaching marks, and browser-owned notes
- Default-disabled private administrator annotations, calibrated measurements,
  and bounded GeoJSON/QuPath interchange
- Dormant, privacy-gated folder and collection share contracts with a reusable
  multi-slide viewer; production activation remains disabled by default
- Docker Compose deployment with Caddy HTTPS termination

## Repository structure

| Path | Purpose |
|---|---|
| `apps/web` | React and TypeScript administration interface and public viewer |
| `server/wsi_viewer` | FastAPI application, authentication, storage, validation, conversion, and worker |
| `migrations` | Alembic database migrations |
| `deploy` | Docker Compose, Caddy, Terraform, systemd, backup, restore, and deployment scripts |
| `tests/backend` | Backend, security, storage, and conversion tests |
| `tests/load` | Reproducible viewer load scenario |
| `docs/architecture` | Durable technical design and security references |
| `docs/evidence` | Verification ledger and evidence status |

See [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md) for file ownership and common change locations.

## Supported slide contract

The primary image must be an interleaved two-dimensional RGB OME-TIFF with one Z plane and one timepoint (`SizeZ=1`, `SizeT=1`). Supported storage variants include classic TIFF and BigTIFF, either byte order, flat or SubIFD pyramids, tiled or striped images, unsigned 8-bit or 16-bit samples, and JPEG, LZW, Deflate, or uncompressed payloads.

A bounded compatibility path supports specific legacy ImageJ converter output when the first IFD is independently valid and the metadata still declares one Z plane and one timepoint. Plain non-OME TIFF files, Z-stacks, time series, unsupported pixel formats, malformed metadata, and truncated files are rejected.

The complete processing contract is documented in [`docs/architecture/OME_TIFF_PIPELINE.md`](docs/architecture/OME_TIFF_PIPELINE.md).

Library organization is metadata-only: folders and collections never move,
scan, decode, or duplicate a slide or its tile tree. See
[`docs/architecture/LIBRARY_DOMAIN.md`](docs/architecture/LIBRARY_DOMAIN.md).

## Local development

### Requirements

- Python 3.12
- Node.js 24
- pnpm 11
- tusd 2.9.2 for resumable local uploads
- native libvips for complete conversion runs

### Setup

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
pnpm install
alembic upgrade head
go install github.com/tus/tusd/v2/cmd/tusd@v2.9.2
```

Start the services in separate terminals:

```bash
pathlab-admin create-admin
pathlab-api
pathlab-worker
pnpm --dir apps/web dev
```

On Windows, start the resumable upload service in another PowerShell terminal:

```powershell
.\scripts\start-local-tusd.ps1
```

The web development proxy expects tusd on `127.0.0.1:8080`. Uploads cannot
start if only the API and Vite processes are running.

Open `http://127.0.0.1:5173/admin`. Published local slides use `/s/{publicId}`.

## Verification

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

Current verification results belong in CI and [`docs/evidence/QA.md`](docs/evidence/QA.md). Static documentation intentionally avoids hard-coded test counts, deployment addresses, commit hashes, or pull-request status because those values become stale.

## Deployment

Production deployment uses the assets in `deploy/`. Caddy terminates HTTPS, serves the web application, and proxies authorized tile, API, and tus upload requests. Review [`deploy/README.md`](deploy/README.md) before provisioning, updating, backing up, or restoring an installation.

## Public-repository safeguards

- Production configuration fails closed unless a unique secret and secure cookies are set.
- Deployment endpoints and infrastructure addresses are supplied through protected settings,
  not committed source files.
- Internal upload hook routes are blocked at the public reverse proxy.
- Publishing requires explicit confirmation that image and public teaching fields are deidentified.
- CI checks the current tree for common secret and infrastructure disclosures, audits dependencies,
  and runs CodeQL.

## Security and privacy

- Original slides, temporary uploads, private derivatives, databases, and secrets are never served from the public tile path.
- Public links expose only an unlisted identifier, display metadata, a DZI descriptor, and sanitized JPEG tiles.
- Multi-slide folder and collection sharing remains disabled until an automated privacy scanner is evidenced; existing individual `/s/{publicId}` links are unchanged.
- Credentials, recovery codes, source slides, generated tiles, databases, and `.env` files must not be committed.
- Suspected vulnerabilities or patient-data exposure should be reported privately rather than through a public issue.

[`docs/architecture/PASSWORD_RECOVERY.md`](docs/architecture/PASSWORD_RECOVERY.md) records legacy source behavior and migration input only. The ratified recovery authority, quorum, and implementation sequence are controlled by [`docs/architecture/FINAL_PRODUCTION_ENDPOINT.md`](docs/architecture/FINAL_PRODUCTION_ENDPOINT.md), [`docs/architecture/ROLE_APPROVAL_MATRIX.md`](docs/architecture/ROLE_APPROVAL_MATRIX.md), and [`docs/execution/PHASE_2_TRUST_AND_OPERATIONS.md`](docs/execution/PHASE_2_TRUST_AND_OPERATIONS.md) wherever they conflict.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing code. Keep changes focused, add regression coverage for behavior changes, run the relevant checks, and submit changes through a reviewable pull request.

## License

PathLab-authored material admitted to the release boundary is available under
the [Apache License 2.0](LICENSE). See [NOTICE](NOTICE) and the
[license and notice policy](docs/supply-chain/LICENSE_AND_NOTICE_POLICY.md) for
the exact boundary, third-party treatment, and distribution requirements.

## Project status

PathLab Viewer is under active development. A green CI run verifies automated checks but does not by itself establish production readiness, external load capacity, backup recovery, network performance, or device compatibility. Use the evidence ledger for the current acceptance status of those operational gates.

## Ratified production endpoint plan

The future Full-Surface destination is specified separately from the current implementation:

- [`docs/architecture/FINAL_PRODUCTION_ENDPOINT.md`](docs/architecture/FINAL_PRODUCTION_ENDPOINT.md) defines the complete zero-cash and future-scalable architecture and delivery phases.
- [`docs/architecture/FEATURE_COMPLETION_MATRIX.md`](docs/architecture/FEATURE_COMPLETION_MATRIX.md) distinguishes capabilities present in source from every remaining completion obligation.
- [`docs/architecture/PRODUCTION_QUALIFICATION.md`](docs/architecture/PRODUCTION_QUALIFICATION.md) defines the exact-release workload, recovery, interoperability and evidence gates.
- [`docs/architecture/DELIVERY_STATE_LEDGER.md`](docs/architecture/DELIVERY_STATE_LEDGER.md) prevents planning, checks, merge, deployment, pilot, qualification and activation from being conflated.
- [`docs/architecture/RECEIPT_SCHEMA_REGISTRY.md`](docs/architecture/RECEIPT_SCHEMA_REGISTRY.md) assigns every end-to-end evidence and lifecycle receipt a versioned schema, owner, source and ledger effect.
- [`docs/architecture/ROLE_APPROVAL_MATRIX.md`](docs/architecture/ROLE_APPROVAL_MATRIX.md), [`docs/architecture/EDGE_NODE_PROFILE.md`](docs/architecture/EDGE_NODE_PROFILE.md), and [`docs/architecture/GOLDEN_INSTITUTION_JOURNEY.md`](docs/architecture/GOLDEN_INSTITUTION_JOURNEY.md) make the human authority, disconnected-node and end-to-end acceptance contracts executable.
- [`CONTEXT-MAP.md`](CONTEXT-MAP.md) defines the fourteen bounded contexts and authority relationships.
- [`docs/adr/README.md`](docs/adr/README.md) indexes all 132 accepted decisions.
- [Wayfinder: Ratify the zero-cash Full-Surface production endpoint](https://github.com/Enksodsoon/PathLab-Viewer/issues/187) is the canonical navigable decision map; execution and evidence remain in its separately linked backlog.
- [Tracking issue #188: Implement and qualify the ratified PathLab Full-Surface endpoint](https://github.com/Enksodsoon/PathLab-Viewer/issues/188) tracks delivery work without reopening the closed decision record in issue #187.

These documents are planning and acceptance contracts. They do not claim that the current source, CI, deployment, production host, or feature flags have already implemented, qualified, or activated the destination.
