# PathLab Viewer Canvas Focus design record

> **Precedence status: `BASELINE_ONLY`.** This document controls the current UI
> implementation only. The [Architecture Precedence
> Register](../../docs/architecture/ARCHITECTURE_PRECEDENCE.md), [Governed
> Product Workflows](../../docs/architecture/GOVERNED_PRODUCT_WORKFLOWS.md), and
> applicable accessibility, rights, and release contracts control destination
> changes.

PathLab Viewer restores its warm cream/coral and charcoal/coral design from
`7eb949a724b3450e67b227e34ad45bb65ec75c99`. The exact original login artwork,
layered-slide mark, and square loader are governed by the
[restoration receipt](../../docs/supply-chain/WARM_UI_ASSET_RECEIPT.json).
No new visual concept or third-party design source is introduced.

## Foundations

- Display type: Cormorant Garamond.
- UI type: Source Sans 3.
- Primary light canvas: `#faf9f5`; primary dark canvas: `#181715`.
- Coral is reserved for primary actions and high-value emphasis.
- Light and dark modes preserve the same component geometry, spacing, radii,
  focus visibility, and semantic status meaning.

## Semantic tokens

`src/theme/theme.css` is the authority for mode-varying semantic chrome
tokens. Components consume variables such as `--canvas`, `--surface`, `--ink`,
`--border`, `--primary`, and `--focus`; they do not branch on the active mode.
Fixed pathology-imaging tokens live in `src/styles.css` and never vary by
theme.

| Token | Light | Dark |
| --- | --- | --- |
| `--canvas` | `#faf9f5` | `#181715` |
| `--surface` | `#f5f0e8` | `#1f1e1b` |
| `--surface-card` | `#efe9de` | `#252320` |
| `--surface-elevated` | `#ffffff` | `#2d2b27` |
| `--ink` | `#141413` | `#faf9f5` |
| `--body` | `#3d3d3a` | `#dedad2` |
| `--muted` | `#6c6a64` | `#a09d96` |
| `--border` | `#e6dfd8` | `#403d37` |
| `--border-soft` | `#ebe6df` | `#34322e` |
| `--primary` | `#cc785c` | `#e18a6d` |
| `--primary-hover` | `#a9583e` | `#ef9b7e` |
| `--on-primary` | `#141413` | `#181715` |
| `--on-primary-hover` | `#ffffff` | `#181715` |
| `--focus` | `#8f432e` | `#f0aa90` |
| `--success` | `#3f7d4d` | `#72c486` |
| `--warning` | `#936b00` | `#e8bb59` |
| `--danger` | `#a33f35` | `#ef8175` |

`--font-display` resolves to Cormorant Garamond with a Georgia fallback;
`--font-ui` resolves to Source Sans 3 with a Segoe UI fallback.
`--radius-control` is `8px` and `--radius-card` is `12px` in both modes.

The original palette is preserved. Primary buttons use the dedicated hover
foreground to retain 4.5:1 normal-text contrast on the darker coral hover fill.

Viewer imagery uses the separate, mode-invariant `--viewer-stage: #090807` and
`--viewer-on-stage: #f2eadc` values. The viewer stage, OpenSeadragon surface,
poster, thumbnails, and tiles remain natural-color and receive no theme filter,
inversion, or blend mode.

## Responsive composition

### Authentication

- Above `940px`, the entry surface uses `.94fr / 1.06fr` columns with the
  form on the left and original theme-specific artwork on the right.
- At `940px` and below, the surface becomes one scrolling column with the
  form above the artwork. Inputs remain at least `50px` high, the submit
  action at least `54px`, and the secondary authentication action at least
  `44px`.
- At `520px` and below, the authentication header and content use compact
  padding; theme controls retain 44px targets.

### Canvas Focus library

- Above `600px`, a sticky collapsible `46px` product rail (`156px` expanded) anchors a centered content canvas
  capped at `1560px`. The library navigator is a fixed overlay up to `360px`
  wide, and slide details use a fixed right overlay up to `390px`; neither
  consumes a permanent content-grid column.
- At `1250px` and below, command groups stack and filters use three columns. At
  `900px` and below, filters use two columns and content padding contracts.
- At `600px` and below, the product rail becomes a fixed `72px` bottom dock,
  the navigator opens from the left, slide details stop above the dock, and
  interactive library controls use a `44px` minimum target. Slide cards use two
  columns, except processing cards which remain single-column.
- At `390px` and below, slide cards and the content heading become
  single-column. At `340px` and below, command actions reflow to three equal
  columns.

### Single-slide and shared viewers

- Private and individual public viewers switch at `760px`: the header becomes
  `60px`, viewer tools become a centered bottom row with `44px` controls, and
  Loading mode keeps a `44px` select. Offline status begins at `top: 76px`,
  leaving an `8px` gap below the `58px` loading container, while the scale bar
  sits above the tools.
- Folder and collection viewers use a `320px` slide rail and `74px` header above
  `760px`. At `760px` and below, the header becomes `68px`, the rail becomes a
  left drawer up to `340px` or `90vw`, and menu, close, and viewer controls are
  `44px`.
- Both viewer layouts keep the stage warm-black at every breakpoint and in
  light, dark, and system preferences.

## Accessibility and motion

Text and controls require WCAG AA contrast in each theme. Keyboard focus uses
the semantic `--focus` token with a `3px` outline. Theme selection is an
accessible three-choice radio group; its compact controls are `44px`.
Reduced-motion users bypass the CSS authentication entrance, navigator and
shared-rail transitions are removed, the indeterminate processing animation is
disabled, and remaining CSS transitions are reduced to `0.01ms`.
