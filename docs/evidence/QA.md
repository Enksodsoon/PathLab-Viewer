# Verification Evidence Ledger

This ledger separates reproducible evidence from product or architecture claims. Results are historical unless they are reproduced for the current candidate. CI is the source of truth for the current branch's automated checks.

The machine-readable source for capability claims is
[`capability-registry.json`](capability-registry.json). Each entry has exactly
one evidence state, supporting evidence, required tests, and explicit claim
restrictions. The state ladder is ordered but non-transitive: `BUILT` does not
imply `SYNTHETICALLY_VERIFIED`, and no state implies a later state.

## 2026-08-21 Program 0A baseline

The registry baseline is exact `origin/main` SHA
`b9d56022dea04940ffa8d262460a15b51074a37b`. On that unchanged baseline, 632
backend tests passed with 6 intentional skips, 276 frontend tests passed, and
72 browser tests passed across desktop Chromium, Firefox, WebKit, and mobile
Chromium. Ruff, strict mypy, ESLint, the production web build, the public
repository scan, registry validation, and Docker Compose configuration also
passed locally. These are baseline results, not protected CI evidence for this
candidate and not deployment, activation, capacity, pilot, production, or
clinical evidence.

## Acceptance gates

| Gate | Evidence recorded | Status |
|---|---|---|
| Backend tests, lint, and type checks | Reproducible in GitHub Actions | Verify in current CI |
| Frontend tests, lint, and production build | Reproducible in GitHub Actions | Verify in current CI |
| Docker Compose configuration and ARM64 image builds | Reproducible in GitHub Actions | Verify in current CI |
| Local administrator workflow | Sign-in, upload, processing, preview, publish controls, and public viewing exercised against local services | Verified historically; repeat after material UI or API changes |
| Real OME-TIFF viewing | A 24,970 × 31,087 converter example opened through OpenSeadragon and representative DZI/tile requests returned successfully | Verified historically; file-specific |
| Responsive browser layout | Desktop, tablet, and phone Chromium viewports checked without horizontal page overflow | Verified historically; emulated viewports only |
| Password recovery | Migration, one-time code consumption, code reuse rejection, session revocation, and replacement-password sign-in exercised in an isolated two-worker deployment | Verified historically; secret-free isolated environment |
| External 100-viewer load | Run `tests/load` against the deployed candidate | Not recorded |
| Shaped-network interaction | Measure at the target bandwidth and latency | Not recorded |
| Physical desktop, tablet, and phone use | Test real devices and browsers | Not recorded |
| Clean backup and restore | Restore into a disposable host and compare records, hashes, manifests, and representative tiles | Not recorded |
| Real 300–500 MB conversion | Measure a representative synthetic or authorized slide through validation and conversion | Not recorded |
| Production 300-viewer certification | Run the protected `Capacity certification` workflow and retain its sanitized aggregate report | Not recorded |
| Infrastructure cost and eligibility | Review the active tenancy billing page and deployed resources | Not recorded |

## 2026-07-27 private-annotation candidate

These are machine-local results for the `codex/admin-annotations` candidate.
They are reproducible evidence for that candidate only and do not replace
protected CI or production acceptance.

- Backend: 364 passed, 2 intentional skips; Ruff and strict mypy passed.
- Frontend: 183 Vitest tests passed; ESLint, TypeScript, and the production
  build passed.
- Browser: 121 passed and 3 expected skips across Chromium, Firefox, WebKit,
  and mobile Chromium. The browser contract observed no annotation UI, API
  request, payload field, or lazy-module request on individual-slide,
  folder-share, or collection-share public routes.
- Build budget against detached `origin/main` `63966f3`: HTML-linked initial
  JavaScript and CSS, including `/theme-init.js`, grew 125 gzip bytes
  (5,120-byte limit). The complete incremental lazy annotation payload was
  183,107 raw bytes and 52,555 gzip bytes across all transitive JavaScript,
  CSS, and the boolean worker (307,200-byte raw limit).
- SQLite/WAL: four readers ran during one 50-operation update. Every
  single-statement snapshot was either complete pre-commit state or complete
  post-commit state; no lock error occurred.
- Synthetic 25,000-annotation API run: 19,705,856-byte database; 800.747 ms
  seed; 29.711 ms manifest; 681.271 ms 5,000-item page; 169.598 ms 1,000-item
  viewport; 33,889,146 peak traced endpoint-allocation bytes. EXPLAIN used the
  API's full-column ORM count/page shapes. The active page used
  `ix_annotations_slide_active` without the prior temporary order B-tree; the
  viewport count/page used `ix_annotations_slide_bbox`.
- Synthetic 25,000-record Vitest/jsdom run: 26.425 ms RBush load, 93.476 ms
  density render plan, 448.648 ms store load plus one compact edit, 79,148,624
  observed heap-delta bytes, zero mounted individual shapes, 5,000 cached
  records, 1,024 density cells, and a 268-byte recovery draft.

The API and frontend timings are single machine-local synthetic observations,
not enforced latency or memory service-level objectives. No live multi-user
traffic, OCI host, physical device, patient slide, production backup restore,
clinical use, or production deployment was tested or claimed.

## Reproducible viewer load checks

Generate a public-only manifest:

```bash
python tests/load/generate_manifest.py \
  --public-root /srv/pathlab/data/public \
  --public-id '<public-id>' \
  --output /absolute/path/to/viewer-load-manifest.json \
  --seed 1
```

Run a small routing and manifest smoke check:

```bash
BASE_URL="$BASE_URL" \
MANIFEST_PATH=/absolute/path/to/viewer-load-manifest.json \
deploy/scripts/run-viewer-load-test.sh smoke
```

The smoke profile proves only that the selected public metadata and sampled tile routes remain valid under a small local k6 workload. It does not establish production capacity.

The external `capacity300` profile must ramp to 300 virtual users, hold all 300
for 10 minutes, and ramp down while recording poster/tile latency and failure
thresholds plus host CPU, RAM, swap, disk I/O, and network behavior. Observe
viewing while one conversion and the administrator workflow are active. Also
complete the shaped-browser and 30-second dropout checks in
[`ADAPTIVE_VIEWER_CAPACITY.md`](../architecture/ADAPTIVE_VIEWER_CAPACITY.md).

Record a baseline and candidate measurement with the same manifest and authorized
300–500 MB source. The candidate passes only when:

- tile and API failures stay below 0.1%;
- tile and API latency stay below 500 ms at p95;
- host CPU stays below 80% sustained and memory stays below 85%;
- swap does not grow and no container is OOM-terminated;
- administrator search, metadata changes, upload status, and publication remain responsive;
- the active conversion completes without increasing the student-viewer failure rate.

Use `docker stats --no-stream` for container CPU, memory, and network snapshots and
the host's standard disk and swap tools. The worker checks filesystem capacity once
per minute and emits path-free `storage_capacity_warning` events only when crossing
70%, 80%, or 90%, plus one `storage_capacity_recovered` event after recovery. These
events contain only utilization, threshold, and free-byte values.

Remaining manual evidence:

- real external 300-viewer capacity run;
- 256 Kbit/s, 1 s RTT, 5% loss, and 30-second dropout browser evidence;
- CPU, RAM, disk I/O, and network observation;
- viewing while one conversion is active;
- shaped 10 Mbps / 50 ms network verification;
- physical desktop, tablet, and phone testing;
- clean backup-and-restore drill;
- real 300–500 MB conversion benchmark.

## Protected production certification

The repository includes a manually dispatched, production-environment-approved
certification workflow. Its existence is not evidence that the test passed.
Only a completed run for the exact deployed commit with a retained aggregate
report may change the production 300-viewer gate above.

The report passes only when the 300-viewer latency/failure thresholds, host
resource gates, exact release marker, exact service set, real administrator
interaction, temporary synthetic conversion, cleanup, and degraded-browser
recovery all pass. The report deliberately excludes slide IDs, raw URLs,
credentials, screenshots, tissue imagery, host paths, and raw monitoring or k6
streams.

## Local browser workflow evidence

The recorded local workflow used the real FastAPI and tusd services rather than mocked API responses:

1. Sign in through the administrator interface.
2. Select a synthetic OME-TIFF and reserve a resumable upload.
3. Complete the tus upload and observe the queued processing state.
4. Open the generated slide through OpenSeadragon.
5. Request representative DZI and JPEG tile resources.
6. Exercise viewer controls at desktop and mobile viewport sizes.

The earlier unverified screenshots were removed by P0-T07. New visual evidence
must be generated from a rights-clear synthetic fixture, bound to the candidate,
and reviewed for sensitive data before publication. Browser assertions and
traceable test output remain the authority for the checks described here.

## Visual acceptance criteria

- The administration page maintains a clear upload area and slide inventory.
- Destructive actions use restrained destructive styling and an in-application confirmation dialog.
- Long slide names and processing errors remain usable on narrow screens.
- The viewer keeps the tissue canvas as the primary visual focus.
- Zoom, home, fullscreen, navigator, and scale controls remain accessible.
- Public-facing copy accurately states that originals remain private and only sanitized derivatives are published.
- No fake magnification value is shown without calibrated objective metadata.

## Password-recovery evidence criteria

A complete recovery verification should prove:

- database migration reaches the expected head without losing existing user or session records;
- the server issues a one-time code without logging or persisting its plaintext value;
- a valid code works once and reuse fails;
- password change, recovery, and emergency reset revoke existing sessions and outstanding codes;
- old credentials fail and replacement credentials succeed;
- invalid-code cases do not disclose whether a username or code was valid;
- request limits and persistent throttling remain effective across API workers;
- audit records exclude usernames, passwords, recovery codes, and code digests where required;
- the administrator UI clears password and recovery-code fields and does not store them in browser storage.

## Evidence handling rules

- Do not record credentials, recovery codes, patient information, private slide content, application secrets, or private infrastructure identifiers.
- Do not treat a historical commit hash, test count, or screenshot as evidence for a later candidate.
- Do not mark an operational gate complete without a reproducible procedure and retained result.
- Update this ledger when a current candidate adds or invalidates evidence.
