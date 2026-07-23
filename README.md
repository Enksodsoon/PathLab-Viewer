# PathLab Viewer

PathLab Viewer is a private-first web application for reviewing and publishing OME-TIFF whole-slide images. An authenticated administrator uploads an original slide, the server validates and converts it into sanitized Deep Zoom JPEG tiles, and anonymous viewers can open an unlisted read-only link. Original slide files remain private.

## Core capabilities

- Resumable OME-TIFF uploads up to 5 GiB
- Background validation and Deep Zoom conversion
- Private preview before publication
- Unlisted, read-only public slide links
- Three-level virtual folders, private teaching metadata, and bearer-link folder sharing
- Responsive OpenSeadragon viewing on desktop, tablet, and phone
- Single-administrator authentication with password recovery
- Storage admission controls, audit records, and atomic publication
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

## Local development

### Requirements

- Python 3.12
- Node.js 24
- pnpm 11
- native libvips for complete conversion runs

### Setup

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
pnpm install
alembic upgrade head
```

Start the services in separate terminals:

```bash
pathlab-admin create-admin
pathlab-api
pathlab-worker
pnpm --dir apps/web dev
```

Open `http://127.0.0.1:5173/admin`. Published local slides use `/s/{publicId}`;
shared collections use `/f/{folderPublicId}`.

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

Production deployment uses the assets in `deploy/`. Caddy terminates HTTPS, serves the web application and immutable public tiles, and proxies the API and tus upload service. Review [`deploy/README.md`](deploy/README.md) before provisioning, updating, backing up, or restoring an installation.

## Security and privacy

- Original slides, temporary uploads, private derivatives, databases, and secrets are never served from the public tile path.
- Public links expose only an unlisted identifier, display metadata, a DZI descriptor, and sanitized JPEG tiles.
- Credentials, recovery codes, source slides, generated tiles, databases, and `.env` files must not be committed.
- Suspected vulnerabilities or patient-data exposure should be reported privately rather than through a public issue.

Administrator recovery architecture is documented in [`docs/architecture/PASSWORD_RECOVERY.md`](docs/architecture/PASSWORD_RECOVERY.md).
Virtual organization, publication grants, and collection-sharing boundaries are
documented in [`docs/architecture/LIBRARY_SHARING.md`](docs/architecture/LIBRARY_SHARING.md).

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing code. Keep changes focused, add regression coverage for behavior changes, run the relevant checks, and submit changes through a reviewable pull request.

## Project status

PathLab Viewer is under active development. A green CI run verifies automated checks but does not by itself establish production readiness, external load capacity, backup recovery, network performance, or device compatibility. Use the evidence ledger for the current acceptance status of those operational gates.
