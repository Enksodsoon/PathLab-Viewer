# PathLab Viewer

**A private-first whole-slide image library and browser viewer for pathology education.**

PathLab Viewer accepts validated OME-TIFF slides, prepares browser-friendly Deep Zoom JPEG tiles, and provides responsive viewing on desktop, tablet, and phone. Source slides remain private. Teaching slides can be published through explicit, unlisted, read-only links after de-identification review.

> **Project status:** active development. Automated checks support development quality, but they do not by themselves establish production readiness, clinical suitability, external load capacity, backup recovery, network performance, or device compatibility.

## How it works

```text
OME-TIFF upload
      │
      ▼
Bounded validation ──► background conversion ──► private preview
                                                        │
                                                        ▼
                                           explicit publication
                                                        │
                                                        ▼
                                     unlisted read-only viewer
```

Original files, temporary uploads, private derivatives, databases, and credentials are kept outside the public tile path.

## Core capabilities

### Slide handling

- Resumable OME-TIFF uploads up to 5 GiB
- Bounded image and metadata validation
- Background conversion to sanitized Deep Zoom JPEG tiles
- Conversion-time thumbnail generation
- Private preview before publication

### Library management

- Nested folders and many-to-many collections
- Saved views, search, filters, facets, sorting, and cursor pagination
- Processing, failed, and restorable Trash views
- Storage admission controls and audit records

### Viewing and sharing

- Responsive OpenSeadragon viewer
- Desktop, tablet, and phone layouts
- Explicit publication with de-identification confirmation
- Unlisted, read-only individual slide links
- Folder and collection sharing contracts are present but remain disabled by default until their privacy gate is fully evidenced

### Operations

- Single-administrator authentication and password recovery
- Docker Compose deployment with Caddy HTTPS termination
- Alembic database migrations
- Backup, restore, deployment, security, and capacity workflows

## Repository map

| Path | Responsibility |
|---|---|
| `apps/web` | React and TypeScript administration interface and public viewer |
| `server/wsi_viewer` | FastAPI application, authentication, storage, validation, conversion, and worker |
| `packages` | Shared frontend packages |
| `migrations` | Alembic database migrations |
| `deploy` | Compose, Caddy, Terraform, systemd, backup, restore, and deployment assets |
| `tests/backend` | Backend, security, storage, and conversion tests |
| `tests/load` | Reproducible viewer load scenarios |
| `docs/architecture` | Durable technical and security decisions |
| `docs/evidence` | Verification ledger and current evidence status |

See [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md) for file ownership and common change locations.

## Supported slide contract

The primary image must be an interleaved two-dimensional RGB OME-TIFF with one Z plane and one timepoint (`SizeZ=1`, `SizeT=1`). Supported variants include:

- classic TIFF and BigTIFF;
- either byte order;
- flat or SubIFD pyramids;
- tiled or striped images;
- unsigned 8-bit or 16-bit samples; and
- JPEG, LZW, Deflate, or uncompressed payloads.

A bounded compatibility path supports specific legacy ImageJ converter output when the first IFD is independently valid and the metadata still declares one Z plane and one timepoint. Plain non-OME TIFF files, Z-stacks, time series, unsupported pixel formats, malformed metadata, and truncated files are rejected.

The full processing contract is documented in [`docs/architecture/OME_TIFF_PIPELINE.md`](docs/architecture/OME_TIFF_PIPELINE.md). Library organization is metadata-only: folders and collections do not move, scan, decode, or duplicate slide files or tile trees. See [`docs/architecture/LIBRARY_DOMAIN.md`](docs/architecture/LIBRARY_DOMAIN.md).

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

The development proxy expects tusd on `127.0.0.1:8080`. Uploads cannot start when only the API and Vite processes are running.

Open `http://127.0.0.1:5173/admin`. Published local slides use `/s/{publicId}`.

## Verification

Run the checks relevant to the change:

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

Current results belong in CI and [`docs/evidence/QA.md`](docs/evidence/QA.md). Documentation intentionally avoids hard-coded test counts, deployment addresses, commit hashes, and pull-request status because those values become stale.

## Deployment

Production deployment uses the assets in `deploy/`. Caddy terminates HTTPS, serves the web client, and proxies authorized tile, API, and resumable-upload requests. Review [`deploy/README.md`](deploy/README.md) before provisioning, updating, backing up, or restoring an installation.

## Security and privacy

- Production configuration fails closed unless a unique secret and secure cookies are configured.
- Infrastructure addresses and deployment endpoints are supplied through protected settings rather than committed source files.
- Internal upload-hook routes are blocked at the public reverse proxy.
- Publication requires explicit confirmation that the image and public teaching fields are de-identified.
- Public links expose only an unlisted identifier, display metadata, a DZI descriptor, and sanitized JPEG tiles.
- Credentials, recovery codes, source slides, generated tiles, databases, `.env` files, and patient information must never be committed.
- Suspected vulnerabilities or patient-data exposure must be reported privately rather than through a public issue.

Administrator recovery is documented in [`docs/architecture/PASSWORD_RECOVERY.md`](docs/architecture/PASSWORD_RECOVERY.md). General reporting guidance is in [`SECURITY.md`](SECURITY.md).

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md) before changing code. Keep changes focused, preserve privacy and storage boundaries, add regression coverage for behavior changes, and submit work through a reviewable pull request.
