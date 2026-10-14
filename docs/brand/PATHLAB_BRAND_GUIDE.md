# PathLab brand guide

Use this reference for the PathLab Viewer, Forge, and future PathLab product marks.

## Brand structure

Place the three-layer mark to the left of a two-line wordmark. Put `PathLab` on the first line and the product name on the second. Keep both text lines aligned to the same left edge.

Use Cormorant Garamond Variable at weight 600 for `PathLab`. Use Source Sans 3 Variable at weight 400 for the product name. Set the wordmark tracking to `-0.02em`. Set the product name in uppercase with `0.3em` tracking. Both fonts are self-hosted Fontsource OFL assets.

Scale the mark and wordmark together for each layout. Keep the mark above and below the text block, and keep the gap between the mark and text consistent within that layout. The current CSS uses `--brand-mark-width`, `--brand-mark-height`, `--brand-gap`, `--brand-name-size`, and `--brand-product-size` for these values.

Give the lockup an accessible image role and a label in the form `PathLab <Product>`. Hide the decorative SVG from assistive technology.

## Current implementations

- Viewer markup lives in [`Brand.tsx`](../../apps/web/src/components/Brand.tsx). Shared Viewer styles live in [`styles.css`](../../apps/web/src/styles.css).
- Forge implements the same markup and spacing in `frontend/src/App.tsx` and `frontend/src/styles.css`.
- The original layered mark and its source rights are recorded in [`INDEPENDENT_PATHLAB_IDENTITY.md`](../supply-chain/INDEPENDENT_PATHLAB_IDENTITY.md).

Keep these implementations aligned. Do not add a dependency on the retired `@pathlab/viewer-ui` package to share brand code across repositories. New projects should follow this guide and verify their lockup at the sizes they ship.
