# P0-T05 Asset Rights Ledger

## Result

The machine-readable [`ASSET_RIGHTS_LEDGER.json`](./ASSET_RIGHTS_LEDGER.json) reconciles every
currently governed repository visual/media file, archive member, inline image, bundled runtime
font, and imported icon at subject commit
`cf9e07d6914532a75db3aac9a1c19a26732e33be`. That subject is the P0-T04 merge and the exact
asset-bearing tree inspected before this ledger and its validators were added. P0-T01 authority is
PR [#190](https://github.com/Enksodsoon/PathLab-Viewer/pull/190), merged as
`c62b11172e95f2246def92aabf77ff7925413eb7`.

The ledger contains 35 top-level records:

- 10 tracked binary files;
- 9 assets embedded inside the tracked DOCX, including one diagram and eight font files;
- 9 inline SVG source objects;
- 3 URL-encoded SVG cursor objects;
- 3 exact self-hosted WOFF2 runtime fonts; and
- 1 exact Phosphor package record containing 87 individually named and SHA-256-bound imported
  icon definitions.

There are no governed audio/video files or binary test fixtures in the current tree. JSON protocol
fixtures and code that captures screenshots at test runtime are not media assets and are not
misclassified as shipped artifacts.

## Release disposition

The asset gate is currently `BLOCKED`, an executed `NEGATIVE` release-admission result. Four
dependency-backed records are admitted: the three exact OFL-1.1 Fontsource files and the exact MIT
Phosphor icon subset, all tied to checksum-verified P0-T03 inventory artifacts and notice hashes.

The other 31 records are `BLOCKED_RELEASE`, not presumed permitted:

- both shipped histology-style authentication images lack creator, generation-source,
  provider-terms, permission, and attribution receipts;
- the design concepts and evidence screenshots contain biomedical/slide imagery whose source,
  permission, and deidentification review are unavailable, so they remain PHI-risk;
- the DOCX and its embedded diagram lack independent creator/source rights, and its eight embedded
  Helvetica Neue files have no redistribution license receipt;
- custom inline SVGs and cursor artwork lack asset-specific creator/assignment evidence; and
- the SVG inside the AGPL-declared viewer package also remains inside the unresolved Apache/AGPL
  release boundary owned by P0-T05A.

This negative admission result does not delete an existing artifact or weaken the production
plan. It creates the fail-closed input for replacement, isolation, or accountable rights evidence
in later tasks. Repository presence, Git authorship, visual inspection, and an inferred absence of
identifiers are not rights or privacy receipts.

## Reconciliation and release gate

The policy is [`asset-rights-policy.json`](./asset-rights-policy.json). It governs common image,
font, audio/video, design-source, document, and vector extensions under application, package,
documentation, and test roots. The generator also inventories media/font members inside governed
archives, inline SVG/data images, exact bundled fonts, and every statically imported Phosphor icon.

Generate after installing the exact frozen JavaScript graph and committing the asset-bearing
implementation tree:

```text
pnpm install --frozen-lockfile
python scripts/generate_asset_rights_ledger.py --subject <exact-implementation-commit>
```

Validate ledger integrity and reconciliation on every candidate:

```text
python scripts/validate_asset_rights_ledger.py
python -m pytest -q tests/backend/test_asset_rights_ledger.py
```

The validator fails on an unknown governed asset, stale entry, changed content hash, missing or
duplicate rule/entry, changed imported-icon set, package checksum/notice mismatch, malformed
required field, or any risky record that is not explicitly release-blocking. Use the stricter gate
for a release candidate:

```text
python scripts/validate_asset_rights_ledger.py --release
```

That command intentionally fails while any `BLOCKED_RELEASE` record remains. It must not be
removed from a release procedure or made advisory to obtain a green result.

## Rollback

Revert the P0-T05 merge commit to remove this ledger and check. Reverting does not establish rights
for any asset and must not be interpreted as release admission.
