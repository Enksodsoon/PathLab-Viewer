# Verification Evidence Ledger

This ledger separates reproducible evidence from product or architecture claims. Results are historical unless they are reproduced for the current candidate. CI is the source of truth for the current branch's automated checks.

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
| Infrastructure cost and eligibility | Review the active tenancy billing page and deployed resources | Not recorded |

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

The external acceptance profile must run 100 virtual users for 10 minutes while recording tile latency and failure thresholds plus host CPU, RAM, disk I/O, and network behavior. Observe viewing while one conversion is active.

Remaining manual evidence:

- real external 100-viewer acceptance run;
- CPU, RAM, disk I/O, and network observation;
- viewing while one conversion is active;
- shaped 10 Mbps / 50 ms network verification;
- physical desktop, tablet, and phone testing;
- clean backup-and-restore drill;
- real 300–500 MB conversion benchmark.

## Local browser workflow evidence

The recorded local workflow used the real FastAPI and tusd services rather than mocked API responses:

1. Sign in through the administrator interface.
2. Select a synthetic OME-TIFF and reserve a resumable upload.
3. Complete the tus upload and observe the queued processing state.
4. Open the generated slide through OpenSeadragon.
5. Request representative DZI and JPEG tile resources.
6. Exercise viewer controls at desktop and mobile viewport sizes.

Historical screenshot names:

- `admin-desktop.png`
- `admin-mobile.png`
- `viewer-desktop.png`
- `viewer-mobile.png`
- `viewer-tablet.png`

Screenshots are supporting evidence only when they are stored with the candidate they represent and reviewed for sensitive data before publication.

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
