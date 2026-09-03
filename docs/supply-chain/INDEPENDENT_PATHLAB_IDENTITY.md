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

The remaining custom SVG belongs to the separately AGPL-declared
`packages/viewer-ui` boundary. P0-T07 does not alter or admit it; P0-T05A owns
its replacement or isolation. This record also does not establish the broader
copyright/relicensing authority that remains governed by P0-T02.

## Product and evidence boundaries

Authentication, storage, publication, sharing, authorization, and route
semantics are unchanged. Light, dark, system-theme, responsive, reduced-motion,
keyboard-focus, and natural-color viewer contracts remain required. Historical
screenshots without source and deidentification receipts are removed; future
visual evidence must use a rights-clear synthetic fixture and pass sensitive
data review before publication.

The machine ledger is generated from and bound to the exact implementation
commit. A successful P0-T07 check requires all retired content absent, no custom
application SVG or data-image art, exact package-asset hashes, web tests and
build success, and only the explicitly separate P0-T05A record remaining in the
asset release blocker list.
