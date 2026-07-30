# OME-Only Shared Tile Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let PathLab Forge upload its calibrated OME-TIFF directly to PathLab Viewer, keep that OME-TIFF as the only canonical image payload, and serve existing DZI-shaped viewer requests through a global disposable 2 GiB tile cache without reducing image-quality gates.

**Architecture:** Forge negotiates the authenticated `ome-dynamic-v1` capability and uploads the approved OME-TIFF through the resumable desktop-ingest API. Viewer validates and indexes that OME-TIFF once, stores no per-slide DZI tree, and marks the slide `ready_private` with `render_mode=ome_dynamic`. Existing API routes authorize each request and dispatch dynamic slides to an internal tile service. The service uses a raw fast path for indexed JPEG payloads when the TIFF layout permits it; otherwise it renders only the requested region with a bounded fallback through libvips, then atomically caches the result. Existing `static_dzi` slides and prepared-package v2 remain unchanged.

**Tech Stack:** Java 21/Gradle, QuPath/Bio-Formats, libvips CLI, Python 3.12, FastAPI, SQLAlchemy/Alembic, tifffile/imagecodecs, pyvips, SQLite, Caddy, Docker Compose, React/OpenSeadragon, pytest/Ruff/mypy, Vitest/Playwright, and k6.

## Global Constraints

- Work only in isolated worktrees and `codex/*` branches.
- Viewer implementation is a draft stacked on `origin/codex/viewer-streaming-prepared-ingest` until that branch lands. After it lands, rebase onto a freshly fetched `origin/main`.
- Preserve prepared-package v2, existing legacy-v2 `files[]` manifests, existing static-DZI uploads, and older Forge clients.
- Do not merge, deploy, resize OCI infrastructure, delete production data, or modify production configuration.
- Do not claim direct JPEG delivery until the real Forge OME fixture proves standalone JPEG compatibility. Fail closed to the bounded fallback renderer.
- OME-TIFF remains private and is never exposed through a download or arbitrary byte-range endpoint.
- The persistent tile cache hard limit is `2_147_483_648` bytes, excluding at most one in-progress temporary file capped at `8_388_608` bytes. Eviction starts before writes and targets `1_879_048_192` bytes (1.75 GiB).
- The decoded-memory cache hard limit is `268_435_456` bytes.
- Quality gates are exact geometry/calibration, complete factor-2 pyramid, no seams, every sampled ROI SSIM at least `0.985`, and mean Delta E00 at most `1.5`.
- Capacity certification is 300 virtual users: 2-minute ramp, 10-minute hold, 1-minute ramp-down; errors below 0.1%, tile p95 below 500 ms, sustained CPU below 80%, RAM below 85%, and no swap/OOM/restart.
- Use the real approved 1.5x OME fixture for compatibility, quality, and end-to-end evidence. Synthetic fixtures may cover malformed-input and unit-test cases only.

---

## Task 1: Establish the Integration Branches and Baseline Evidence

**Files:**

- Modify: `docs/evidence/OME_DYNAMIC_BASELINE_2026-07-30.json`
- Reference: `docs/superpowers/specs/2026-07-30-ome-shared-tile-cache-design.md`
- Reference: `docs/DESKTOP_INGEST_PROTOCOL.md`

- [ ] **Step 1: Refresh both repositories and record exact bases**

Run:

```powershell
$viewer = "C:\Users\enkso\.codex\worktrees\pathlab-forge-plan\viewer-ome-cache"
$forge = "C:\Users\enkso\.codex\worktrees\pathlab-forge-plan\forge-f1-1"
git -C $viewer fetch origin --prune
git -C $forge fetch origin --prune
git -C $viewer rev-parse origin/main
git -C $viewer rev-parse origin/codex/viewer-streaming-prepared-ingest
git -C $forge rev-parse HEAD
git -C $viewer merge-base --is-ancestor origin/main origin/codex/viewer-streaming-prepared-ingest
```

Expected: the ancestry command exits `0`; capture all three SHAs.

- [ ] **Step 2: Create the implementation worktrees**

Run:

```powershell
$viewerRepo = "C:\Users\enkso\OneDrive\Documents\New project"
$viewerImpl = "C:\Users\enkso\.codex\worktrees\pathlab-forge-plan\viewer-ome-shared-cache-impl"
$forgeRepo = "C:\Users\enkso\OneDrive\Documents\PathLab Forge"
$forgeImpl = "C:\Users\enkso\.codex\worktrees\pathlab-forge-plan\forge-ome-direct-upload"
git -C $viewerRepo worktree add -b codex/ome-shared-cache-impl $viewerImpl origin/codex/viewer-streaming-prepared-ingest
git -C $forgeRepo worktree add -b codex/forge-ome-direct-upload $forgeImpl origin/codex/forge-critical-path-optimization
```

Expected: both worktrees are clean and attached to the named branches.

- [ ] **Step 3: Write the machine-readable baseline**

Create `docs/evidence/OME_DYNAMIC_BASELINE_2026-07-30.json` with this complete shape and measured values:

```json
{
  "schema": "pathlab.ome-dynamic-evidence/v1",
  "viewerBaseSha": "373ca749b6442315730ac6de35b08b02328c4977",
  "preparedIngestBaseSha": "c7d943a048b69ae954c0d3b9e08eefc3ed33844a",
  "forgeBaseSha": "16a9cf6139f82fac9809b6682543692cccbd5654",
  "fixture": {
    "downsample": 1.5,
    "width": 110563,
    "height": 60490,
    "omeBytes": 433745579,
    "omeSeconds": 56.0,
    "preparedPackageBytes": 3982018048,
    "preparedTotalSeconds": 562.0
  },
  "quality": {
    "selectedJpegQuality": 95,
    "minimumWindowedSsim": 0.989477906,
    "meanDeltaE00": 0.182981001
  }
}
```

Copy the exact values from Forge's `docs/evidence/CRITICAL_PATH_OPTIMIZATION_2026-07-30.json`; retain `omeSeconds=56.0` as the midpoint of the observed 55–57 second interval and identify it as an interval midpoint in the evidence metadata.

- [ ] **Step 4: Re-run clean baselines**

Run:

```powershell
$env:PATH = "C:\Users\enkso\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin;C:\Users\enkso\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\fallback_bin;$env:PATH"
$python = "C:\Users\enkso\.cache\pathlab-viewer-py312\Scripts\python.exe"
& $python -m pytest
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
pnpm test
pnpm build
```

Expected: backend tests, Ruff, mypy, frontend tests, and build pass. If the known library-explorer timing test alone flakes, rerun its file once and record both results.

- [ ] **Step 5: Commit baseline evidence**

```powershell
git add docs/evidence/OME_DYNAMIC_BASELINE_2026-07-30.json
git commit -m "test: record OME dynamic baseline"
```

## Task 2: Prove the Forge OME Tile Layout Before Selecting the Fast Path

**Files:**

- Create: `server/wsi_viewer/ome_tile_index.py`
- Create: `tests/backend/test_ome_tile_index.py`
- Modify: `tests/backend/test_ome.py`
- Create: `scripts/inspect_ome_tile_layout.py`

- [ ] **Step 1: Write failing index-contract tests**

Add tests for a tiled JPEG factor-2 pyramid, separate JPEG tables, strip/tile rejection, malformed offsets, overlap, and physical-EOF bounds:

```python
def test_indexes_factor_two_jpeg_pyramid(forge_ome: Path) -> None:
    index = build_ome_tile_index(forge_ome)
    assert [(level.width, level.height) for level in index.levels[:2]] == [
        (110_563, 60_490),
        (55_282, 30_245),
    ]
    assert index.tile_width == 512
    assert index.tile_height == 512
    assert index.codec == "jpeg"


def test_rejects_offset_past_physical_eof(tmp_path: Path) -> None:
    path = write_malformed_offset_tiff(tmp_path)
    with pytest.raises(OmeTileIndexError, match="physical EOF"):
        build_ome_tile_index(path)
```

Run:

```powershell
& $python -m pytest tests/backend/test_ome_tile_index.py -q
```

Expected: fail because `ome_tile_index` does not exist.

- [ ] **Step 2: Implement immutable index types and structural validation**

Implement these interfaces:

```python
@dataclass(frozen=True, slots=True)
class TileExtent:
    offset: int
    byte_count: int
    jpeg_tables: bytes | None


@dataclass(frozen=True, slots=True)
class OmeLevel:
    width: int
    height: int
    tiles_across: int
    tiles_down: int
    tiles: Sequence[TileExtent]


@dataclass(frozen=True, slots=True)
class OmeTileIndex:
    width: int
    height: int
    tile_width: int
    tile_height: int
    codec: Literal["jpeg"]
    levels: Sequence[OmeLevel]
    source_size: int
    source_mtime_ns: int
    source_sha256: str


def build_ome_tile_index(path: Path, *, expected_sha256: str | None = None) -> OmeTileIndex:
    source = _validated_regular_file(path, expected_sha256=expected_sha256)
    levels = _validated_jpeg_levels(source.path, physical_eof=source.size)
    return OmeTileIndex(
        width=levels[0].width,
        height=levels[0].height,
        tile_width=512,
        tile_height=512,
        codec="jpeg",
        levels=levels,
        source_size=source.size,
        source_mtime_ns=source.mtime_ns,
        source_sha256=source.sha256,
    )
```

Validation must require regular file, exact source identity, tiled JPEG RGB pages, factor-2 dimensions, positive/non-overlapping byte ranges, and every range inside physical EOF. Never trust TIFF offsets before bounds validation.

- [ ] **Step 3: Implement standalone JPEG assembly**

Expose:

```python
def read_indexed_jpeg(path: Path, tile: TileExtent) -> bytes:
    payload = _pread_exact(path, offset=tile.offset, length=tile.byte_count)
    return assemble_jpeg_tables(tile.jpeg_tables, payload) if tile.jpeg_tables else payload


def assemble_jpeg_tables(tables: bytes, payload: bytes) -> bytes:
    normalized_tables = _jpeg_segments_without_markers(tables, excluded_markers={0xD8, 0xD9})
    normalized_payload = _jpeg_segments_without_markers(payload, excluded_markers={0xD8})
    result = b"\xff\xd8" + normalized_tables + normalized_payload
    if not result.endswith(b"\xff\xd9"):
        result += b"\xff\xd9"
    return _validated_jpeg(result, maximum_bytes=8 * 1024**2)
```

Use `os.pread` on Windows where available and a locked `seek/read` fallback otherwise. Strip duplicate SOI/EOI markers, inject required DQT/DHT tables once, cap output at 8 MiB, and verify `0xFFD8`/`0xFFD9`.

- [ ] **Step 4: Run the real-fixture probe**

Run:

```powershell
& $python scripts/inspect_ome_tile_layout.py `
  --ome "C:\Users\enkso\.codex\worktrees\pathlab-forge-plan\forge-f1-1\build\real-dzi-benchmark\input.ome.tif" `
  --json docs/evidence/OME_DYNAMIC_TILE_LAYOUT_2026-07-30.json
```

The script must decode deterministic corner, center, edge, and seam tiles with Pillow/imagecodecs and report:

```json
{
  "rawFastPathSupported": true,
  "requiresJpegTableAssembly": false,
  "levels": 18,
  "tileWidth": 512,
  "tileHeight": 512,
  "decodedSamples": 32,
  "decodeFailures": 0
}
```

Do not force `rawFastPathSupported=true`; retain the measured boolean. A false result activates the fallback path in later tasks.

- [ ] **Step 5: Verify and commit**

```powershell
& $python -m pytest tests/backend/test_ome_tile_index.py tests/backend/test_ome.py -q
& $python -m ruff check server/wsi_viewer/ome_tile_index.py tests/backend/test_ome_tile_index.py scripts/inspect_ome_tile_layout.py
& $python -m mypy server/wsi_viewer
git add server/wsi_viewer/ome_tile_index.py tests/backend/test_ome_tile_index.py tests/backend/test_ome.py scripts/inspect_ome_tile_layout.py docs/evidence/OME_DYNAMIC_TILE_LAYOUT_2026-07-30.json
git commit -m "feat: validate and index dynamic OME tiles"
```

## Task 3: Add Render Mode and Correct OME-Only Storage Accounting

**Files:**

- Modify: `server/wsi_viewer/models.py`
- Modify: `server/wsi_viewer/storage.py`
- Modify: `server/wsi_viewer/storage_accounting.py`
- Create: `migrations/versions/20260730_0013_ome_dynamic_render_mode.py`
- Modify: `tests/backend/test_database.py`
- Modify: `tests/backend/test_storage.py`
- Modify: `tests/backend/test_worker.py`

- [ ] **Step 1: Write failing migration and admission tests**

```python
def test_ome_dynamic_admission_is_source_plus_headroom() -> None:
    assert admission_required(433_745_579, render_mode="ome_dynamic") == (
        433_745_579 + 512 * 1024**2
    )


def test_static_dzi_admission_remains_conservative() -> None:
    assert admission_required(100, render_mode="static_dzi") == 5 * 1024**3 + 400
```

Also assert migration upgrade, downgrade, and re-upgrade preserve existing rows as `static_dzi`.

Run:

```powershell
& $python -m pytest tests/backend/test_storage.py tests/backend/test_database.py -q
```

Expected: fail because `render_mode` is absent.

- [ ] **Step 2: Add the compatible model field**

Add:

```python
render_mode: Mapped[str] = mapped_column(
    String(20), nullable=False, default="static_dzi", server_default="static_dzi", index=True
)
```

The migration must add a check constraint permitting only `static_dzi` and `ome_dynamic`. Downgrade must remove the column without deleting OME files; those slides become inaccessible on the downgraded binary, not destroyed.

- [ ] **Step 3: Make accounting mode-aware**

Implement:

```python
def admission_required(source_bytes: int, *, render_mode: str = "static_dzi") -> int:
    if source_bytes <= 0:
        raise ValueError("source_bytes must be positive")
    if render_mode == "ome_dynamic":
        return source_bytes + max(512 * 1024**2, math.ceil(source_bytes * 0.10))
    if render_mode == "static_dzi":
        return 4 * source_bytes + 5 * GIB
    raise ValueError("unsupported render mode")
```

For ready `ome_dynamic` slides, `_accounted_bytes` must count `source_bytes` and zero derivatives. Reservations count `reserved_bytes` only while uploading/finalizing. The disposable cache is excluded from logical quota but included in physical free-space checks.

- [ ] **Step 4: Make reconciliation mode-aware**

`reconcile_storage` must:

- measure DZI derivatives only for `static_dzi`;
- set `derivative_bytes=0` and `derivative_file_count=0` for `ome_dynamic`;
- verify the OME and immutable index exist for ready dynamic slides;
- never convert a dynamic slide to static merely because its cache is empty.

- [ ] **Step 5: Verify and commit**

```powershell
& $python -m pytest tests/backend/test_storage.py tests/backend/test_database.py tests/backend/test_worker.py -q
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
git add server/wsi_viewer/models.py server/wsi_viewer/storage.py server/wsi_viewer/storage_accounting.py migrations/versions/20260730_0013_ome_dynamic_render_mode.py tests/backend/test_database.py tests/backend/test_storage.py tests/backend/test_worker.py
git commit -m "feat: account for OME-only render mode"
```

## Task 4: Extend Desktop Ingest for Direct OME Upload

**Files:**

- Modify: `server/wsi_viewer/desktop_routes.py`
- Modify: `server/wsi_viewer/desktop_finalizer.py`
- Create: `server/wsi_viewer/ome_ingest.py`
- Modify: `server/wsi_viewer/models.py`
- Create: `migrations/versions/20260730_0014_desktop_ome_ingest.py`
- Modify: `tests/backend/test_prepared_ingest.py`
- Create: `tests/backend/test_ome_ingest.py`
- Modify: `docs/DESKTOP_INGEST_PROTOCOL.md`

- [ ] **Step 1: Write failing capability and creation tests**

Assert authenticated capabilities include:

```json
{
  "desktopApiVersion": "pathlab-desktop-ingest/v1",
  "ingestModes": ["prepared-v2", "ome-dynamic-v1"],
  "inventoryFormats": ["ndjson-v1", "files-v1"],
  "maxChunkBytes": 67108864,
  "recommendedChunkBytes": 67108864
}
```

Add `POST /api/v1/desktop/ome-ingests` tests with:

```json
{
  "displayName": "case-1.5x",
  "artifactRevisionId": "revision-id",
  "omeLength": 433745579,
  "omeSha256": "64-lowercase-hex",
  "profile": "ome-dynamic-v1",
  "width": 110563,
  "height": 60490,
  "downsample": 1.5
}
```

Cover authentication, scope, duplicate active ingest, invalid hash, oversize, low disk, wrong offset, resume, fsync-before-offset-commit, network interruption, and server restart.

- [ ] **Step 2: Add a discriminated ingest mode**

Extend `DesktopIngest` with `ingest_mode`, default/server-default `prepared_v2`, constrained to `prepared_v2` or `ome_dynamic_v1`. Do not change existing prepared endpoints or response fields.

- [ ] **Step 3: Stream OME chunks durably**

Share the current upload writer, but enforce:

```python
MAX_REQUEST_BUFFER_BYTES = 1024 * 1024
MAX_CHUNK_BYTES = 64 * 1024 * 1024
```

Read request bodies in at most 1 MiB pieces. Call `flush()` and `os.fsync()` before committing `received_bytes`. The final PATCH sets `finalizing`, returns immediately, and enqueues one bounded finalizer. `HEAD` and status routes never finalize.

- [ ] **Step 4: Implement OME finalization**

`finalize_ome_ingest` must:

1. transactionally claim the ingest;
2. stream SHA-256 through physical EOF;
3. validate exact length/hash and `validate_ome_tiff`;
4. build and persist the immutable tile index privately;
5. compare declared geometry/profile to measured values;
6. atomically rename the upload to `originals/<slide-id>/source.ome.tif`;
7. create/update the slide as `ome_dynamic`, `derivative_bytes=0`;
8. commit `ready_private`;
9. delete successful ingest state only after the slide transaction commits.

Failure moves the OME to quota-accounted quarantine with the configured TTL. Startup recovers stale claims.

- [ ] **Step 5: Keep prepared-v2 tests green**

Run:

```powershell
& $python -m pytest tests/backend/test_prepared_ingest.py tests/backend/test_ome_ingest.py -q
```

Expected: both ingest modes pass, including legacy v2 `files[]`.

- [ ] **Step 6: Verify and commit**

```powershell
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
git add server/wsi_viewer/desktop_routes.py server/wsi_viewer/desktop_finalizer.py server/wsi_viewer/ome_ingest.py server/wsi_viewer/models.py migrations/versions/20260730_0014_desktop_ome_ingest.py tests/backend/test_prepared_ingest.py tests/backend/test_ome_ingest.py docs/DESKTOP_INGEST_PROTOCOL.md
git commit -m "feat: ingest Forge OME artifacts directly"
```

## Task 5: Build the Bounded Shared Tile Cache

**Files:**

- Create: `server/wsi_viewer/tile_cache.py`
- Create: `tests/backend/test_tile_cache.py`
- Modify: `server/wsi_viewer/config.py`
- Modify: `tests/backend/test_config.py`

- [ ] **Step 1: Write failing cache invariant tests**

Cover atomic visibility, LRU eviction to 1.75 GiB, 2 GiB hard maximum, one bounded temp file, traversal rejection, symlink/non-regular rejection, request coalescing, canceled waiter, failed producer, startup reconciliation, orphan cleanup, and emergency purge.

```python
def test_coalesces_same_key(cache: TileCache) -> None:
    calls = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: cache.get_or_create(KEY, produce), range(8)))
    assert calls == 1
    assert len({result.read_bytes() for result in results}) == 1
```

- [ ] **Step 2: Implement safe cache keys and paths**

Use:

```python
@dataclass(frozen=True, slots=True)
class TileKey:
    slide_sha256: str
    level: int
    column: int
    row: int
    quality_profile: str

    def digest(self) -> str:
        material = f"{self.slide_sha256}:{self.level}:{self.column}:{self.row}:{self.quality_profile}"
        return hashlib.sha256(material.encode("ascii")).hexdigest()
```

Store entries as `<first-two-hex>/<digest>.jpg`. Never use user-controlled path text.

- [ ] **Step 3: Implement bounded eviction and coalescing**

Maintain a SQLite cache index with `digest`, `bytes`, `last_access_ns`, and `state`. A single writer lock reserves space, evicts oldest entries to the low-water mark, and creates `<digest>.<nonce>.tmp` with mode `0600`. After JPEG validation: flush, fsync, `os.replace`, fsync parent, and atomically mark ready.

Requests for the same digest share one in-flight future. Requests for different keys may run concurrently up to the tile-render semaphore.

- [ ] **Step 4: Add settings**

```python
tile_cache_root: Path = Path("./var/data/cache/ome-tiles")
tile_cache_max_bytes: PositiveInt = 2 * 1024**3
tile_cache_low_water_bytes: PositiveInt = 1792 * 1024**2
tile_cache_max_temp_bytes: PositiveInt = 8 * 1024**2
tile_cache_memory_bytes: PositiveInt = 256 * 1024**2
tile_render_concurrency: PositiveInt = 2
```

Validate low-water < max, temp <= 8 MiB, and memory <= 512 MiB.

- [ ] **Step 5: Verify and commit**

```powershell
& $python -m pytest tests/backend/test_tile_cache.py tests/backend/test_config.py -q
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
git add server/wsi_viewer/tile_cache.py server/wsi_viewer/config.py tests/backend/test_tile_cache.py tests/backend/test_config.py
git commit -m "feat: add bounded shared OME tile cache"
```

## Task 6: Implement Dynamic DZI Rendering with Raw and Bounded Fallback Paths

**Files:**

- Create: `server/wsi_viewer/ome_tiles.py`
- Create: `tests/backend/test_ome_tiles.py`
- Modify: `server/wsi_viewer/conversion.py`
- Modify: `server/wsi_viewer/ome.py`

- [ ] **Step 1: Write failing descriptor/coordinate tests**

Assert exact OpenSeadragon DZI level mapping, edge-tile dimensions, invalid coordinates, thumbnail generation, and no full-slide decode:

```python
def test_descriptor_preserves_exact_geometry(renderer: OmeTileRenderer) -> None:
    response = renderer.descriptor(slide)
    assert response.body == (
        b'<Image xmlns="http://schemas.microsoft.com/deepzoom/2008" '
        b'Format="jpg" Overlap="0" TileSize="512">'
        b'<Size Width="110563" Height="60490"/></Image>'
    )
```

- [ ] **Step 2: Implement DZI-to-OME mapping**

Create immutable `DziRequest` and map DZI level `ceil(log2(max(width,height)))` down to the matching OME factor-2 page. Validate level/column/row before any file access.

- [ ] **Step 3: Implement the measured fast path**

If the persisted index says the requested OME tile is standalone or safely assemblable, call `read_indexed_jpeg`. Decode deterministic samples during ingest and 1 in every 10,000 served cache misses in diagnostic mode. Never re-encode a fast-path tile.

- [ ] **Step 4: Implement the bounded fallback**

Use pyvips sequential access for only the requested region:

```python
region = pyvips.Image.tiffload(
    str(source),
    page=page_index,
    access="sequential",
).crop(left, top, width, height)
payload = region.jpegsave_buffer(
    Q=selected_quality,
    strip=True,
    optimize_coding=True,
    keep="none",
)
```

Reject a request if the predicted decoded region exceeds 16 MiB. Configure libvips concurrency and cache from settings. The selected quality/profile comes from the validated OME index; no request-time quality search is allowed.

- [ ] **Step 5: Cache only completed JPEGs**

`render_tile` first checks the 256 MiB decoded-memory cache, then the persistent 2 GiB cache, then produces once. Descriptor responses are generated in memory and are not charged as tiles.

- [ ] **Step 6: Verify and commit**

```powershell
& $python -m pytest tests/backend/test_ome_tiles.py tests/backend/test_ome.py -q
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
git add server/wsi_viewer/ome_tiles.py server/wsi_viewer/conversion.py server/wsi_viewer/ome.py tests/backend/test_ome_tiles.py
git commit -m "feat: render virtual DZI tiles from OME"
```

## Task 7: Route Private, Public, and Shared Requests Without Exposing OME

**Files:**

- Create: `server/wsi_viewer/tile_routes.py`
- Modify: `server/wsi_viewer/main.py`
- Modify: `server/wsi_viewer/library_routes.py`
- Modify: `server/wsi_viewer/publication.py`
- Modify: `server/wsi_viewer/storage.py`
- Modify: `tests/backend/test_api.py`
- Modify: `tests/backend/test_library_v2.py`
- Modify: `tests/backend/test_public_hardening.py`

- [ ] **Step 1: Write failing authorization and compatibility tests**

Test these unchanged URL shapes:

- `/api/v1/admin/slides/{id}/preview/slide.dzi`
- `/api/v1/admin/slides/{id}/preview/slide_files/{level}/{col}_{row}.jpg`
- `/api/v1/admin/slides/{id}/preview/thumbnail.jpg`
- `/api/v1/public/slides/{public_id}/tiles/{tile_path:path}`
- `/api/v2/public/folders/{public_id}/slides/{position}/tiles/{tile_path:path}`
- `/api/v2/public/collections/{public_id}/slides/{position}/tiles/{tile_path:path}`

For each route, cover `static_dzi`, `ome_dynamic`, unauthorized, unpublished, trashed, invalid path, and missing tile. Add a negative test proving no route returns `source.ome.tif` or honors `Range` against it.

- [ ] **Step 2: Centralize authorized tile resolution**

Expose:

```python
@dataclass(frozen=True, slots=True)
class AuthorizedTile:
    slide_id: str
    slide_sha256: str
    render_mode: Literal["static_dzi", "ome_dynamic"]
    relative_path: str
    cache_control: str
```

API routes resolve grants/state, then either call the legacy static-file delivery or attach an internal redirect target for dynamic rendering.

- [ ] **Step 3: Remove publication hardlink dependence for dynamic slides**

For `ome_dynamic`, `ensure_grant` writes only the database grant/manifest namespace. `remove_grant` invalidates authorization and optional cache namespace metadata; it does not remove the canonical OME. Keep existing hardlink behavior for `static_dzi`.

- [ ] **Step 4: Preserve lifecycle semantics**

Trash keeps the OME and index. Restore makes it viewable again. Permanent delete removes OME, index, quarantine entry, and cache keys for the slide hash. Unpublish revokes all direct/share delivery immediately.

- [ ] **Step 5: Verify and commit**

```powershell
& $python -m pytest tests/backend/test_api.py tests/backend/test_library_v2.py tests/backend/test_public_hardening.py -q
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
git add server/wsi_viewer/tile_routes.py server/wsi_viewer/main.py server/wsi_viewer/library_routes.py server/wsi_viewer/publication.py server/wsi_viewer/storage.py tests/backend/test_api.py tests/backend/test_library_v2.py tests/backend/test_public_hardening.py
git commit -m "feat: route authorized dynamic OME tiles"
```

## Task 8: Isolate Tile Serving Behind Caddy and Make Cache Operationally Safe

**Files:**

- Modify: `deploy/compose.yaml`
- Modify: `deploy/Caddyfile`
- Modify: `deploy/Dockerfile.backend`
- Modify: `deploy/.env.example`
- Modify: `deploy/scripts/backup.sh`
- Modify: `deploy/scripts/restore.sh`
- Create: `server/wsi_viewer/tile_service.py`
- Modify: `server/wsi_viewer/readiness.py`
- Modify: `server/wsi_viewer/worker.py`
- Modify: `tests/backend/test_deploy_config.py`
- Modify: `tests/backend/test_backup_restore.py`
- Modify: `tests/backend/test_readiness.py`

- [ ] **Step 1: Write failing deployment-contract tests**

Assert:

- the tile service has no public host port;
- Caddy can reach it only over the internal network;
- API authorization precedes an internal redirect;
- cache root is a named volume capped by application policy;
- backup excludes `cache/ome-tiles`;
- restore starts with an empty cache and rebuildable index;
- readiness fails if the tile service cannot read a known index or enforce its cap.

- [ ] **Step 2: Add the internal tile-service command**

Add `pathlab-tiles = "wsi_viewer.tile_service:main"` to `pyproject.toml` and run it from the existing backend image with:

```yaml
tile-service:
  image: ${PATHLAB_BACKEND_IMAGE}
  command: ["pathlab-tiles"]
  expose: ["8090"]
  volumes:
    - pathlab-data:/data
  networks:
    - pathlab-internal
```

Reuse the backend image and readonly OME access; grant write access only to `/data/cache/ome-tiles`.

- [ ] **Step 3: Configure internal redirects**

Caddy serves a cache-hit file directly after authorization. Cache misses proxy to the internal tile service. Never expose the internal service or OME root. Keep response headers for JPEG content type, immutable cache control, nosniff, and private/public policy.

- [ ] **Step 4: Add cache monitoring and purge**

Worker monitoring logs cache bytes, entries, evictions, hit/miss/coalescing rates, temp bytes, and render latency. Add an authenticated admin-only emergency purge that removes cache files and rebuilds the cache index without changing slides.

- [ ] **Step 5: Verify and commit**

```powershell
& $python -m pytest tests/backend/test_deploy_config.py tests/backend/test_backup_restore.py tests/backend/test_readiness.py -q
docker compose -f deploy/compose.yaml --env-file deploy/.env.example config
git add deploy/compose.yaml deploy/Caddyfile deploy/Dockerfile.backend deploy/.env.example deploy/scripts/backup.sh deploy/scripts/restore.sh server/wsi_viewer/tile_service.py server/wsi_viewer/readiness.py server/wsi_viewer/worker.py pyproject.toml tests/backend/test_deploy_config.py tests/backend/test_backup_restore.py tests/backend/test_readiness.py
git commit -m "feat: isolate and monitor dynamic tile delivery"
```

## Task 9: Make Forge Produce and Validate the Dynamic OME Profile

**Files:**

- Modify: `src/main/java/org/pathlab/forge/derivative/DerivativeEngine.java`
- Modify: `src/main/java/org/pathlab/forge/derivative/VipsRuntime.java`
- Create: `src/main/java/org/pathlab/forge/derivative/OmeDynamicProfile.java`
- Modify: `src/main/java/org/pathlab/forge/conversion/ConversionService.java`
- Modify: `src/main/java/org/pathlab/forge/conversion/ArtifactRevision.java`
- Modify: `src/main/java/org/pathlab/forge/conversion/ArtifactRevisionRepository.java`
- Modify: `src/main/java/org/pathlab/forge/conversion/ArtifactIntegrityStamp.java`
- Modify: `src/test/java/org/pathlab/forge/derivative/VipsRuntimeTest.java`
- Create: `src/test/java/org/pathlab/forge/derivative/OmeDynamicProfileTest.java`
- Modify: `src/test/java/org/pathlab/forge/conversion/DirectFinalOmeAssemblyTest.java`
- Modify: `src/test/java/org/pathlab/forge/conversion/ArtifactRevisionRepositoryTest.java`

- [ ] **Step 1: Write failing profile tests**

```java
@Test
void dynamicProfileRequiresFactorTwo512JpegRgb() {
    var profile = OmeDynamicProfile.V1;
    assertEquals(512, profile.tileSize());
    assertEquals(2, profile.pyramidFactor());
    assertEquals("jpeg", profile.codec());
    assertEquals("sRGB", profile.colorSpace());
}
```

Add command tests that require `tile-width=512`, `tile-height=512`, JPEG compression at the selected adaptive quality, factor-2 pyramid, 8-bit RGB/sRGB, stripped sensitive metadata, exact dimensions, and preserved physical calibration.

- [ ] **Step 2: Add a profile-aware final OME writer**

Extend the interface:

```java
void assembleRegionsFinal(
        List<Path> regions,
        Path pyramidalOme,
        int width,
        int height,
        double downsample,
        OmeDynamicProfile profile,
        int jpegQuality) throws IOException;
```

Keep the existing overload delegating to the current behavior for prepared-v2 compatibility.

- [ ] **Step 3: Persist the OME profile identity**

Extend `ArtifactRevision` and its properties repository with:

```java
String omeProfile;
int omeJpegQuality;
```

Old revisions load with `omeProfile=""` and remain uploadable through prepared v2. Integrity stamps include OME path, size, mtime, SHA-256, profile, and quality.

- [ ] **Step 4: Validate actual output**

After writing, inspect every IFD/subIFD for factor-2 geometry and JPEG tiled layout. Fail conversion if the profile cannot be proven. Do not generate DZI solely for a dynamic-capable upload; preserve on-demand prepared-v2 generation for fallback.

- [ ] **Step 5: Benchmark factor 2 versus factor 4**

Run three cold writes per configuration on the approved 1.5x fixture. Adopt factor 2 unless factor 4 is at least 5% faster and Viewer can expose a seam-free virtual factor-2 DZI without additional stored levels. Record medians and quality in `docs/evidence/FORGE_OME_DYNAMIC_WRITER_2026-07-30.json`.

- [ ] **Step 6: Verify and commit**

```powershell
.\gradlew.bat test --tests "*VipsRuntimeTest" --tests "*OmeDynamicProfileTest" --tests "*DirectFinalOmeAssemblyTest" --tests "*ArtifactRevisionRepositoryTest"
.\gradlew.bat check
git add src/main/java/org/pathlab/forge/derivative/DerivativeEngine.java src/main/java/org/pathlab/forge/derivative/VipsRuntime.java src/main/java/org/pathlab/forge/derivative/OmeDynamicProfile.java src/main/java/org/pathlab/forge/conversion/ConversionService.java src/main/java/org/pathlab/forge/conversion/ArtifactRevision.java src/main/java/org/pathlab/forge/conversion/ArtifactRevisionRepository.java src/main/java/org/pathlab/forge/conversion/ArtifactIntegrityStamp.java src/test/java/org/pathlab/forge/derivative/VipsRuntimeTest.java src/test/java/org/pathlab/forge/derivative/OmeDynamicProfileTest.java src/test/java/org/pathlab/forge/conversion/DirectFinalOmeAssemblyTest.java src/test/java/org/pathlab/forge/conversion/ArtifactRevisionRepositoryTest.java docs/evidence/FORGE_OME_DYNAMIC_WRITER_2026-07-30.json
git commit -m "feat: produce Viewer dynamic OME profile"
```

## Task 10: Negotiate Direct OME Upload in Forge

**Files:**

- Create: `src/main/java/org/pathlab/forge/viewer/ViewerCapabilities.java`
- Modify: `src/main/java/org/pathlab/forge/viewer/ViewerConnection.java`
- Modify: `src/main/java/org/pathlab/forge/viewer/ViewerPairingService.java`
- Modify: `src/main/java/org/pathlab/forge/viewer/ViewerUploadStatus.java`
- Modify: `src/main/java/org/pathlab/forge/server/ForgeServer.java`
- Modify: `src/test/java/org/pathlab/forge/viewer/ViewerPairingServiceTest.java`
- Modify: `src/test/java/org/pathlab/forge/server/ForgeLibraryApiTest.java`

- [ ] **Step 1: Write failing negotiation tests**

Cover:

- dynamic-capable Viewer uploads `revision.omePath()`;
- missing/404 capability endpoint falls back to prepared-v2 and 16 MiB chunks;
- dynamic profile mismatch falls back to prepared-v2;
- 64 MiB recommendation is capped at 64 MiB;
- upload streams with at most 1 MiB buffers;
- resume starts at Viewer offset;
- source size/mtime/stamp mutation aborts;
- ready status triggers annotation sync exactly once.

- [ ] **Step 2: Parse capabilities strictly**

```java
public record ViewerCapabilities(
        Set<String> ingestModes,
        long maxChunkBytes,
        long recommendedChunkBytes) {
    public boolean supportsDynamicOme() {
        return ingestModes.contains("ome-dynamic-v1");
    }
}
```

Unknown fields are ignored. Invalid sizes or malformed JSON produce legacy capabilities, not an unsafe guess.

- [ ] **Step 3: Select the upload artifact**

If Viewer supports `ome-dynamic-v1` and the approved revision has that exact profile, upload OME length/hash/geometry to `/api/v1/desktop/ome-ingests`. Otherwise, lazily ensure the prepared v2 package exists and use `/api/v1/desktop/ingests`.

The direct path must never read `manifest.json` or require a `.plslide`.

- [ ] **Step 4: Stream and resume**

Continue using `BoundedFileInputStream`, but cap its internal buffer at 1 MiB and each PATCH at the negotiated chunk size. Poll finalization asynchronously. Keep the permanent localhost app URL and current pairing credential behavior unchanged.

- [ ] **Step 5: Expose the selected mode**

Add `uploadMode` (`OME_DYNAMIC` or `PREPARED_V2`) and human-readable progress to the local API so the UI clearly states whether it is uploading only the OME or building/uploading a package.

- [ ] **Step 6: Verify and commit**

```powershell
.\gradlew.bat test --tests "*ViewerPairingServiceTest" --tests "*ForgeLibraryApiTest"
.\gradlew.bat check
git add src/main/java/org/pathlab/forge/viewer/ViewerCapabilities.java src/main/java/org/pathlab/forge/viewer/ViewerConnection.java src/main/java/org/pathlab/forge/viewer/ViewerPairingService.java src/main/java/org/pathlab/forge/viewer/ViewerUploadStatus.java src/main/java/org/pathlab/forge/server/ForgeServer.java src/test/java/org/pathlab/forge/viewer/ViewerPairingServiceTest.java src/test/java/org/pathlab/forge/server/ForgeLibraryApiTest.java
git commit -m "feat: upload approved OME directly to Viewer"
```

## Task 11: Prove Fidelity and End-to-End Compatibility

**Files:**

- Create: `tests/backend/test_ome_dynamic_quality.py`
- Create: `tests/backend/test_ome_dynamic_e2e.py`
- Modify: `apps/web/e2e/capacity-upload-dialog.spec.ts`
- Create: `apps/web/e2e/ome-dynamic-viewer.spec.ts`
- Create: `docs/evidence/OME_DYNAMIC_E2E_2026-07-30.json`

- [ ] **Step 1: Add deterministic quality checks**

Use at least 32 deterministic tissue, background, edge, and seam ROIs. Compare native source to OME and OME to served tiles. Record minimum windowed SSIM and mean Delta E00. Fail on any ROI below 0.985 SSIM or mean Delta E00 above 1.5.

- [ ] **Step 2: Cover the full matrix**

Run:

- small crop at 1x and 1.5x;
- full 16x and full 1.5x;
- OME-TIFF source;
- Q85, Q90, and Q95 selection;
- cancellation and checkpoint resume;
- source mutation;
- low disk/RAM;
- network interruption and resume;
- Viewer restart during finalization;
- duplicate finalizer claims;
- prepared v2 and legacy-v2;
- malformed OME/TIFF offsets and hostile paths;
- migration upgrade, downgrade, re-upgrade;
- publish, share, unpublish, trash, restore, permanent delete.

- [ ] **Step 3: Run the real local browser workflow**

Start local Viewer Compose and Forge. In a clean browser profile:

1. pair Forge with Viewer;
2. select the approved exact 1.5x revision;
3. verify UI says direct OME upload;
4. interrupt and resume upload;
5. wait for `ready_private`;
6. open at overview and maximum zoom;
7. inspect seam ROIs and annotation alignment;
8. publish/share and verify authorized access;
9. unpublish and verify the clean profile loses access immediately.

- [ ] **Step 4: Assert storage**

Evidence must show:

```json
{
  "canonicalOmeBytes": 433745579,
  "storedDerivativeBytes": 0,
  "tileCacheHardLimitBytes": 2147483648,
  "tileCacheIncludedInBackup": false,
  "preparedPackageCreated": false
}
```

Use actual measured values for the fixture.

- [ ] **Step 5: Run all repository gates**

Viewer:

```powershell
& $python -m pytest
& $python -m ruff check .
& $python -m mypy server/wsi_viewer
pnpm test
pnpm build
pnpm test:e2e
docker compose -f deploy/compose.yaml --env-file deploy/.env.example config
```

Forge:

```powershell
.\gradlew.bat test
.\gradlew.bat check
```

- [ ] **Step 6: Commit evidence**

```powershell
git add tests/backend/test_ome_dynamic_quality.py tests/backend/test_ome_dynamic_e2e.py apps/web/e2e/capacity-upload-dialog.spec.ts apps/web/e2e/ome-dynamic-viewer.spec.ts docs/evidence/OME_DYNAMIC_E2E_2026-07-30.json
git commit -m "test: prove OME-only Viewer workflow"
```

## Task 12: Certify 300-User Capacity and Deliver Coordinated Draft PRs

**Files:**

- Modify: `tests/load/viewer.js`
- Modify: `tests/load/test_load_contract.py`
- Modify: `deploy/scripts/run-viewer-load-test.sh`
- Create: `docs/evidence/OME_DYNAMIC_CAPACITY_2026-07-30.json`
- Modify: `README.md`
- Modify: `docs/PROJECT_GUIDE.md`
- Modify: `docs/DESKTOP_INGEST_PROTOCOL.md`

- [ ] **Step 1: Add dynamic-slide load scenarios**

Use two scenarios:

- 70% popular-slide traffic with realistic repeated navigation and cache hits;
- 30% mixed-slide traffic that creates controlled cache misses and eviction.

Use:

```javascript
export const options = {
  scenarios: {
    viewers: {
      executor: "ramping-vus",
      stages: [
        { duration: "2m", target: 300 },
        { duration: "10m", target: 300 },
        { duration: "1m", target: 0 }
      ]
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.001"],
    http_req_duration: ["p(95)<500"]
  }
};
```

- [ ] **Step 2: Measure server resources and admin responsiveness**

Collect per-second CPU, RSS, swap, restarts, cache bytes/hits/misses/evictions, render queue depth, tile latency, and disk I/O. Every minute, run an authenticated library/status request and require p95 below 750 ms.

- [ ] **Step 3: Run three cold certifications**

Purge only the disposable local test cache between runs. Do not delete OME files or production data. Report medians plus each run. A pass requires every hard threshold in Global Constraints.

- [ ] **Step 4: Complete final machine-readable evidence**

Merge the before/after data into:

```json
{
  "schema": "pathlab.ome-dynamic-evidence/v1",
  "timings": {},
  "bytesRead": {},
  "bytesWritten": {},
  "storage": {},
  "memory": {},
  "quality": {},
  "capacity": {},
  "compatibility": {},
  "repositoryChecks": {}
}
```

Every value must be measured or explicitly `null` with a `reason`; no inferred pass values.

- [ ] **Step 5: Update documentation**

Document:

- OME is canonical for `ome_dynamic`;
- the 2 GiB cache is disposable and excluded from backup/quota;
- prepared v2/static DZI remain supported;
- direct OME is selected only through capability negotiation;
- operations for metrics, purge, restore, and rollback;
- no claim that one application node alone guarantees 300 users unless the certification passed.

- [ ] **Step 6: Rebase the Viewer branch if the dependency merged**

If prepared-ingest v2 is on `origin/main`:

```powershell
git fetch origin --prune
git rebase origin/main
```

Otherwise keep the draft PR explicitly stacked on `codex/viewer-streaming-prepared-ingest`.

- [ ] **Step 7: Push coordinated branches and open draft PRs**

```powershell
git push -u origin codex/ome-shared-cache-impl
git push -u origin codex/forge-ome-direct-upload
```

Open two draft PRs that cross-link each other, list exact base/head SHAs, attach evidence, and state:

- no production deployment was performed;
- prepared v2/static DZI compatibility remains;
- merge order/dependency;
- capacity result and any unmet gate;
- rollback is selecting `static_dzi`/prepared-v2, not deleting OME data.

- [ ] **Step 8: Final verification before handoff**

Run:

```powershell
git status --short
git log -1 --oneline
```

Expected: both worktrees clean. Report exact SHAs, draft PR URLs, all test counts, measured storage, quality, timing, capacity, and any external/no-details check separately.
