# OME native JPEG pass-through — Phase 0 evidence

## Result

Native JPEG pass-through is **feasible for the existing `ome-dynamic-v1` baseline
profile**. The existing authorized DZI tile route already selected native TIFF tile
bytes before libvips. This spike hardened that path rather than adding a protocol,
route, cache, dependency, or Forge implementation.

The production change validates a bounded baseline JPEG marker stream, reconstructs
abbreviated image streams from TIFF `JPEGTables`, ignores table-stream metadata and
no-op state markers, rejects global/local table redefinition, validates the JPEG SOF
against the TIFF tile geometry, and translates extraction failures through the
existing stable tile error boundary.

## Repository alignment

- Viewer base: `ec97febbb9706f4b1109ba8fa45c3f807b3ff510`
- Viewer branch: `codex/ome-native-jpeg-spike`
- Forge direct OME lineage inspected: `5be079cf24b2987e6f44f145b08d523b71c1face`
- Forge critical-path ancestor inspected: `16a9cf6139f82fac9809b6682543692cccbd5654`
- Forge factor-2/teaching lineage inspected: `c7a8f80a9e3a4824e08f37269f02b2350ba00760`
- Forge production changes: none

The Forge tips diverge after `16a9cf6`. The direct-upload tip advertises
`ome-dynamic-v1` with factor 4. The factor-2 tip advertises `ome-dynamic-v2`, while
this Viewer accepts `ome-dynamic-v1`. No Forge lineage was selected or merged for
this Viewer-only feasibility spike.

## Existing implementation inventory

| Requirement | Phase 0 classification |
| --- | --- |
| Direct canonical OME ingest | Already implemented |
| Factor-2 and factor-4 recognition | Already implemented |
| Immutable TIFF offset/count index | Already implemented |
| Globally aligned virtual levels | Already implemented |
| Bounded memory and persistent tile caches | Already implemented |
| Resumable direct upload recovery | Already implemented |
| Geometry and dynamic-profile validation | Already implemented |
| `ready_private` integrity validation | Already implemented |
| Native standalone JPEG byte serving | Already implemented |
| Safe shared-`JPEGTables` reconstruction | Partially implemented; hardened here |
| Baseline marker/table/SOF validation | Missing; implemented here |
| New public V3 profile or endpoint | Not required for Phase 0 |

## Deterministic fixture and byte evidence

The generated fixture was a 700 × 650 RGB gradient, JPEG-compressed tiled BigTIFF
with 512 × 512 tiles and a factor-2 SubIFD. It was 90,844 bytes and had a 2 × 2
full-resolution tile grid. The bottom-right tile had a logical visible region of
188 × 138, while its JPEG SOF correctly remained 512 × 512 as required for a tiled
TIFF edge tile.

- Indexed tile offset: 58,606
- Original TIFF compressed range: 8,401 bytes
- Returned JPEG: 8,401 bytes
- Byte identity: exact
- Compressed SHA-256: `a4d3ce7f775c5f8b13ace62ff7d40b12bff05777eadb25948939bc02aeea22ed`
- Decoded mode and size: RGB, 512 × 512
- Decoded RGB SHA-256: `f393fbe0fa78094d08d6531c4b93fb6a6bdab54e932690948b9812cb408a8078`
- Edge logical-region comparison against TIFF decode: exact array equality
- Chromium `HTMLImageElement.decode()`: complete, 512 × 512

The shared-table test starts from a real Pillow-generated baseline JPEG, separates
DQT/DHT into a TIFF-style tables stream, reconstructs an SOI/EOI-wrapped abbreviated
payload, and requires the decoded RGB bytes to equal the standalone source JPEG. It
also verifies that APP/COM-compatible metadata and shared DRI state are not copied
into the returned stream.

## Timing observation

On this host, 100 repeated reads of the sampled 8,401-byte native tile averaged
0.0663 ms per validated pass-through. A diagnostic Pillow decode/re-encode loop at
quality 75 averaged 0.9358 ms per tile. This approximately 14× request-path
difference is directional evidence only: it is not a libvips production benchmark,
not a conversion-time result, and not a release-performance certification.

Pass-through produces no additional lossy generation and no stored DZI derivative.
It does not make the canonical OME source smaller; its storage benefit is avoiding a
second prepared tile artifact and avoiding per-request re-encoded tile variants.

## Verification

- Focused native-index, renderer, and tile-service tests: passed (`22 passed`,
  `1 skipped`; the skip is the opt-in real Forge fixture)
- Existing dynamic OME API regression: passed
- Full backend suite: passed with four existing optional skips
- Ruff policy check over `server` and `tests`: passed
- Mypy over all 33 server source files: passed
- Chromium decode smoke check: passed

The focused tests cover exact route bytes, forced-failure fallback protection for a
native edge tile, standalone and shared-table decode, SOI-wrapped abbreviated tiles,
malformed table lengths, global/local table conflicts, physical-EOF truncation,
invalid offsets, unsupported TIFF compression, DZI bounds, exact edge geometry, and
decoded channel/orientation parity.

## Security and compatibility boundaries

- No arbitrary offset or byte-range route was added.
- Existing authorization, slide hash, relative-path, cache, and `nosniff` behavior
  remains unchanged.
- The raw path is deliberately limited to one-scan, 8-bit, three-component SOF0
  JPEG with resolved DQT/DHT tables and exact 512 × 512 SOF geometry.
- Progressive, arithmetic, lossless, multi-scan, DNL, unknown markers, malformed
  entropy markers, missing tables, and mismatched geometry fail closed.
- TIFF edge tiles remain padded 512 × 512 JPEGs. The existing Deep Zoom client clips
  the logical 188 × 138 edge region; changing the encoded edge dimensions would
  require re-encoding and would violate TIFF tiled-JPEG geometry.
- No proprietary or real WSI was committed. The optional real-file regression was
  not run because `PATHLAB_REAL_FORGE_OME` was not configured.

## Exact proposed Phase 1 scope

1. Reconcile the Forge profile mismatch before choosing a Forge base; do not merge
   the divergent tips broadly.
2. Keep one fixed factor-2 libjpeg profile and the existing direct OME endpoint.
3. Negotiate before Forge creates DZI/package derivatives and skip them only when
   the exact Viewer profile is accepted.
4. Run one representative, non-proprietary or locally supplied WSI through upload,
   `ready_private`, native stored levels, virtual missing levels, and clean-browser
   viewing.
5. Add an OpenSeadragon edge-clipping screenshot assertion and sampled real-file
   shared-`JPEGTables` evidence if that layout exists in supported Forge output.
6. Keep prepared-v2 unchanged and the optimized behavior disabled by default.
7. Stop before Jpegli, factor-4 comparison, schema changes, full certification, PR,
   deployment, or migration.

References: [TIFF/JPEG Technical Note 2](https://libtiff.gitlab.io/libtiff/specification/technote2.html)
and the [OME-TIFF specification](https://ome-model.readthedocs.io/en/latest/ome-tiff/specification.html).
