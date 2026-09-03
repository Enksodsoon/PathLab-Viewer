# P0-T05A Clean-room Viewer UI Boundary Receipt

## Disposition

P0-T05A selects deletion and local replacement. It does not claim authority to
relicense `packages/viewer-ui`, and it does not change the package's historical
AGPL-3.0-or-later declaration. The complete nine-file package is absent from the
release tree at implementation commit
`929e561db7820e48b24f26fda165ffcaabfb0049` (tree
`6a3bcff58e1e0f298fc7a0960a75038b771aefe6`). Its one live consumer is now an
application-local rail built from current observable behavior requirements and
existing admitted dependencies.

## Frozen source boundary

The P0-T02A audit subject is
`7816671b0d9e531158868d820d132ed8808c0b76`; its complete package tree-list
SHA-256 is `b27cc56e01475061ab2168131cb174a57d2347981b1a11d96debb00556e96e65`.
The exact retired paths and content SHA-256 values are machine-bound in
[`viewer-ui-clean-room-policy.json`](./viewer-ui-clean-room-policy.json). CI
rejects any original path, byte-identical copy under another path, or release
reference to `@pathlab/viewer-ui` or `packages/viewer-ui`.

## Preserved consumer contract

The local `AppRail` preserves tested observable behavior: expanded/collapsed
navigation, navigator state and focus ref, Upload, optional Classroom and Study
destinations, account/sign-out actions, inert state, and storage capacity text,
meter values, active state, and labels. It reuses the independently established
P0-T07 `Brand` and exact MIT Phosphor imports. No new dependency, image, inline
SVG, schema, migration, network call, deployment action, or activation is added.

The obsolete workspace dependency, lock importer, and Docker build copy are
removed. Dependency inventory remains complete; the asset ledger now contains
four admitted records and zero release blockers.

## Authority boundary

This receipt resolves only the separately declared AGPL package's inclusion in
the production artifact. It is not a legal clean-room opinion, copyright
assignment, authorship attestation, root-license grant, or Apache-2.0 admission
for the rest of the repository. P0-T02 remains blocked until its exact signed
authority receipt exists.

## Rollback

Revert the eventual P0-T05A merge commit. Rollback restores the separate AGPL
package boundary and therefore restores its release blocker; it never converts
that package into Apache-licensed work.
