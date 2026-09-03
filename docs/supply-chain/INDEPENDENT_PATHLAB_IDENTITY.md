# Independent PathLab Identity

P0-T07 replaces the unresolved visual assets identified by the P0-T05 Asset
Rights Ledger. The replacement identity is specified directly from PathLab's
product needs: clear clinical-imaging controls, a cool mineral palette, an
admitted microscope symbol, strong focus indication, and natural-color slide
rendering. No third-party product screen, brand, trade dress, or disputed
repository image is a design input.

## Rights and provenance

- The product mark and interface icons are exact imports from
  `@phosphor-icons/react@2.1.10`, admitted under MIT by the dependency and asset
  ledgers with its notice preserved.
- Source Sans 3, Cormorant Garamond, and Sofia Sans remain exact self-hosted
  Fontsource artifacts admitted under OFL-1.1.
- The authentication specimen field is CSS geometry and gradients authored in
  the P0-T07 change; it embeds no image, tissue sample, patient information, or
  external network reference.
- Local and teaching annotations render user-provided coordinates on Canvas.
  They are functional data rendering, not bundled artwork.
- Ten unverified binary assets and documents are retired by both path and
  content hash in `asset-rights-policy.json`. The validator rejects their
  reintroduction under a different name.

P0-T05A subsequently removed the separately AGPL-declared `packages/viewer-ui`
work and replaced its one live consumer with local code using the same admitted
Phosphor icon source. No custom application SVG remains. This record does not
establish the broader copyright/relicensing authority governed by P0-T02.

## Product and evidence boundaries

Authentication, storage, publication, sharing, authorization, and route
semantics are unchanged. Light, dark, system-theme, responsive, reduced-motion,
keyboard-focus, and natural-color viewer contracts remain required. Historical
screenshots without source and deidentification receipts are removed; future
visual evidence must use a rights-clear synthetic fixture and pass sensitive
data review before publication.

The machine ledger is generated from and bound to the exact implementation
commit. The current check requires all retired content absent, no custom
application SVG or data-image art, exact package-asset hashes, web tests and
build success, and an empty asset release blocker list.
