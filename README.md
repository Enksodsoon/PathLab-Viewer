# PathLab Viewer

Compact, public OME-TIFF whole-slide image viewer for small laboratories and pathology teaching.

## Product contract

- One authenticated administrator uploads and manages OME-TIFF files up to 5 GiB.
- Published slides are anonymous, read-only, and available through unlisted links.
- Private originals are converted into sanitized JPEG Deep Zoom derivatives.
- Desktop, tablet, and phone viewing use OpenSeadragon.
- OCI Always Free is the deployment target; readiness requires measured 100-viewer proof.

## What is accepted

The worker normally requires valid OME-XML and one interleaved RGB primary image with `SizeZ=1` and `SizeT=1`. Classic TIFF/BigTIFF, both byte orders, flat/SubIFD pyramids, tiles/strips, uint8/uint16, RGB/YCbCr, and JPEG/LZW/Deflate/uncompressed payloads are covered by the parameterized test matrix. Missing physical scale is allowed. A bounded legacy compatibility path also accepts ImageJ converter output when its first IFD is a valid, decodable 2D RGB image and its metadata declares one Z plane and one timepoint; malformed trailing page-chain entries are ignored. Plain non-OME TIFFs and ImageJ Z-stacks remain rejected.

The original is stored under a generated ID and is never routed publicly. Publication copies only one `.dzi` descriptor and JPEG tiles into the Caddy-served public tree. `vips-properties.xml` is deleted and every other derivative file type is rejected.

## Local development

Python 3.12, Node 24, pnpm 11, and native libvips are required for a complete worker run.

```bash
python -m venv .venv
.venv/bin/pip install -e '.[dev]'
pnpm install
alembic upgrade head
pathlab-admin create-admin
pathlab-api
pathlab-worker
pnpm --dir apps/web dev
```

Open `http://127.0.0.1:5173/admin`. Public links use `/s/{publicId}`. For production, use the four-container deployment in `deploy/`; Caddy terminates HTTPS, serves the SPA and immutable tiles, and proxies the API and tus 1.0 uploads.

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

See `docs/evidence/QA.md` for the local browser and real-file evidence. Local evidence does not satisfy OCI billing, external 100-viewer, shaped-network, backup-restore, or physical-device gates; those remain `BLOCKED` until executed against the deployed candidate.
