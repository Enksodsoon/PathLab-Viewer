# Independent PathLab Identity

The September 5 restoration returns PathLab's warm cream/coral and
charcoal/coral identity from `7eb949a`. The earlier P0-T07 mineral palette,
microscope mark, CSS specimen field, and circular loader are superseded.
The current visual contract is [DESIGN.md](../../apps/web/DESIGN.md).
Original-asset evidence and the pending image-specific approval are recorded
in [WARM_UI_ASSET_RECEIPT.json](./WARM_UI_ASSET_RECEIPT.json).

## Rights and provenance

- The original layered-slide product mark and square loader exactly match
  source blobs covered by the GitHub-verified signed ownership receipt at
  `e5677dc6d5ea6eccc3a88ebd82ce0fc43684dc6f`. Both have exact path/hash rules.
- Other interface icons remain imports from `@phosphor-icons/react@2.1.10`,
  admitted under MIT with its notice preserved.
- Source Sans 3, Cormorant Garamond, and Sofia Sans remain exact self-hosted
  Fontsource artifacts admitted under OFL-1.1.
- The two original authentication images were traced to July 26 image-generation
  calls and reproduced byte-for-byte from their source PNGs. The dark image
  used no input image; the light image used only that generated dark image.
  Source evidence does not replace the image-specific owner approval: both
  image entries remain `BLOCKED_RELEASE` until that approval is recorded.
- Local and teaching annotations render user-provided coordinates on Canvas.
  They are functional data rendering, not bundled artwork.
- Eight unrelated unverified binary assets and documents remain retired by path and
  content hash in `asset-rights-policy.json`. The validator rejects their
  reintroduction under a different name.

P0-T05A subsequently removed the separately AGPL-declared `packages/viewer-ui`
work and replaced its one live consumer with local code using the same admitted
Phosphor icon source. Only the two hash-bound original SVGs are restored;
other custom artwork remains subject to the existing blocked rules. This record does not
establish the broader copyright/relicensing authority governed by P0-T02.

## Product and evidence boundaries

Authentication, storage, publication, sharing, authorization, and route
semantics are unchanged. Light, dark, system-theme, responsive, reduced-motion,
keyboard-focus, and natural-color viewer contracts remain required. Historical
screenshots without source and deidentification receipts are removed; future
visual evidence must use a rights-clear synthetic fixture and pass sensitive
data review before publication.

The machine ledger is generated from and bound to the exact implementation
commit. Exact original-asset rules take precedence over the generic blocked
classification only when their hashes match. The release check still requires
all retired content absent, exact asset hashes, web tests and build success,
and an empty asset release blocker list. Approval is not inferred from a
request to implement the UI restoration.
