# P0-T05 Asset Rights Ledger

## Result

The machine-readable [`ASSET_RIGHTS_LEDGER.json`](./ASSET_RIGHTS_LEDGER.json) reconciles every
currently governed repository visual/media file, archive member, inline image, bundled runtime
font, and imported icon at subject commit
`355ef0675cd88d8c457e0fc4380ef367fdc8600d`. That subject is the exact P0-T07 independent-identity
implementation tree inspected before the final receipt refresh. P0-T01 authority is
PR [#190](https://github.com/Enksodsoon/PathLab-Viewer/pull/190), merged as
`c62b11172e95f2246def92aabf77ff7925413eb7`.

The ledger contains five top-level records:

- 3 exact self-hosted WOFF2 runtime fonts; and
- 1 exact Phosphor package record containing 99 individually named and SHA-256-bound imported
  icon definitions; and
- 1 inline SVG retained solely inside the separate AGPL `packages/viewer-ui` boundary.

There are no governed audio/video files or binary test fixtures in the current tree. JSON protocol
fixtures and code that captures screenshots at test runtime are not media assets and are not
misclassified as shipped artifacts.

## Release disposition

The repository-wide asset gate remains `BLOCKED`, an executed `NEGATIVE` release-admission result. Four
dependency-backed records are admitted: the three exact OFL-1.1 Fontsource files and the exact MIT
Phosphor icon subset, all tied to checksum-verified P0-T03 inventory artifacts and notice hashes.

P0-T07 removed all 30 blockers in its scope: the unverified authentication images, design/evidence
screenshots, DOCX and embedded media/fonts, application-authored icon SVGs, functional SVG drawing
surfaces, and URL-encoded cursor art. CSS geometry and Canvas now provide the non-package visual
surfaces, while exact admitted Phosphor imports provide interface symbols. Retired paths and hashes
are enforced by policy. The single remaining `BLOCKED_RELEASE` record is the SVG inside the
AGPL-declared viewer package; the unresolved Apache/AGPL release boundary is owned exclusively by
P0-T05A.

This negative repository-wide result does not weaken P0-T07's task result: every P0-T07-owned
replacement is complete and the remaining blocker is explicitly outside its package boundary.
Repository presence, Git authorship, visual inspection, and an inferred absence of identifiers
remain insufficient rights or privacy receipts.

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
