# P0-T05 Asset Rights Ledger

## Result

The machine-readable [`ASSET_RIGHTS_LEDGER.json`](./ASSET_RIGHTS_LEDGER.json) reconciles every
currently governed repository visual/media file, archive member, inline image, bundled runtime
font, and imported icon at subject commit
`929e561db7820e48b24f26fda165ffcaabfb0049`. That subject is the exact P0-T05A clean-room
replacement implementation tree inspected before the final receipt refresh. P0-T01 authority is
PR [#190](https://github.com/Enksodsoon/PathLab-Viewer/pull/190), merged as
`c62b11172e95f2246def92aabf77ff7925413eb7`.

The ledger contains four top-level records:

- 3 exact self-hosted WOFF2 runtime fonts; and
- 1 exact Phosphor package record containing 99 individually named and SHA-256-bound imported
  icon definitions.

There are no governed audio/video files or binary test fixtures in the current tree. JSON protocol
fixtures and code that captures screenshots at test runtime are not media assets and are not
misclassified as shipped artifacts.

## Release disposition

The repository-wide asset gate is `ADMITTED`, an executed `SUCCESS` release-admission result. All four
dependency-backed records are admitted: the three exact OFL-1.1 Fontsource files and the exact MIT
Phosphor icon subset, all tied to checksum-verified P0-T03 inventory artifacts and notice hashes.

P0-T07 removed all 30 blockers in its scope: the unverified authentication images, design/evidence
screenshots, DOCX and embedded media/fonts, application-authored icon SVGs, functional SVG drawing
surfaces, and URL-encoded cursor art. CSS geometry and Canvas now provide the non-package visual
surfaces, while exact admitted Phosphor imports provide interface symbols. Retired paths and hashes
are enforced by policy. P0-T05A removed the final blocked SVG by deleting the AGPL-declared package
and independently replacing its sole consumer; no release blocker remains in this asset ledger.

This asset result does not establish the broader source-code ownership or Apache relicensing
authority owned by P0-T02. Repository presence, Git authorship, visual inspection, and an inferred
absence of identifiers remain insufficient rights or privacy receipts.

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

That command fails whenever any `BLOCKED_RELEASE` record exists. It must not be
removed from a release procedure or made advisory to preserve a green result.

## Rollback

Revert the P0-T05 merge commit to remove this ledger and check. Reverting does not establish rights
for any asset and must not be interpreted as release admission.
