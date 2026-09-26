# Integrity follow-up

Labels: wayfinder:ticket
Status: in progress

## Dependencies

First reviewed batch: PR #267, merged candidate `bd3ab41`, main `3a46ad525465fc49dc2edd2b50243a9dec430cc4`.
The separate checkout preserves the candidate while repairing additional reproduced mechanisms.

## Proven local repairs

- Folder topology serialization and restore depth; portable sort-order bounds; bounded desktop folder pagination and validated API CLI arguments.
- Atomic Study aggregate counters and serialized learner submissions; atomic IndexedDB appends across tabs.
- Presenter persistence shutdown, versioned teaching annotation acknowledgments, and hub connection accounting.
- Desktop transfer serialization, durable spool creation/cancellation, uncertain commit recovery, and deterministic content descriptor closure.
- Prepared and OME finalization preserve raw data and committed derivatives during rollback or acknowledgment failures; extraction and full-file hashing precede the SQLite writer transaction.
- Processing selection, editable keyboard boundaries, slide rotation reset, and reachable annotation controls.

## Verification and remaining work

954 report sections have evidence-backed dispositions; 29 security subclaims retain two external-evidence gaps. All98 confirmed canonical source groups are reconciled in REPAIR_COVERAGE.md. Additional independently reproduced campaign findings are recorded separately.
Focused native, concurrent and four-engine browser regressions pass. The initial broad frontend run passed all 460 tests; subsequent repairs receive focused regression checks and fresh CI. Local PostgreSQL cases skip until real PostgreSQL CI executes them.
All nine first-batch deployment-required checks passed on bd3ab41; PR #267 merged. No production deployment is claimed.
The protected deployment requires a real backup and restore drill before release replacement.
The Edge production tab is signed out; user sign-in remains pending for authenticated live qualification.

## Desktop folder contract

`GET /api/v2/desktop/library/items` retains the existing `cursor`/`nextCursor`, schema and 100-folder response bound. The opaque cursor now advances both slide and folder boundaries, so existing consumers following `nextCursor` receive the complete bounded folder snapshot without new request fields. Legacy slide-only cursors remain valid during rolling upgrades.

The actual Forge `ViewerSyncService.refreshLibrary` at `7de0d9159ee0c999c52de51670b21c86609cf790` follows opaque nextCursor and accumulates folders before replacing its snapshot. Native paired API regressions reproduce that loop with102folders and1/101slides, preserving all identities without duplicates. Forge itself was source-reviewed, not rebuilt or executed in this campaign.

The initial broad backend run failed only two inventory tests because concurrent browser screenshots were written under a governed source tree. The receipts were preserved under ignored evidence; all 12 software inventory regression tests passed after relocation. No asset admission rules were relaxed.

Post-squash main CI could not resolve the asset ledger subject. The existing immutable inventory fetch step now restores dependency, asset and software subjects before strict validation; no validator was relaxed. Fresh follow-up and main checks remain required.

Independent native review also repaired outer OME quarantine denial, failure-record commit errors that stopped queued work, and oversized Range conversion. The native worker suite passed18 cases. Final broad frontend checks found two stale source-string contract assertions. Updated selectors preserve roster pagination and direct presenter projection assertions; all10 focused contract checks pass. Full frozen frontend/backend runs are in progress.
