# Independent PathLab identity design record

> **Precedence status: `BASELINE_ONLY`.** This document controls the current UI
> implementation only. The [Architecture Precedence
> Register](../../docs/architecture/ARCHITECTURE_PRECEDENCE.md), [Governed
> Product Workflows](../../docs/architecture/GOVERNED_PRODUCT_WORKFLOWS.md), and
> applicable accessibility, rights, and release contracts control destination
> changes.

PathLab Viewer uses an independently specified clinical-imaging identity based
on instrument clarity, specimen mapping, and cool mineral colors. It does not
use another product, brand, screenshot, or supplied reference as a design source.

## Foundations

- Display type: Cormorant Garamond.
- UI type: Source Sans 3.
- Primary light canvas: `#f5f8fa`; primary dark canvas: `#081923`.
- Teal identifies primary actions; violet is reserved for keyboard focus.
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
| `--canvas` | `#f5f8fa` | `#081923` |
| `--surface` | `#eaf1f4` | `#102936` |
| `--surface-card` | `#e1ebef` | `#173644` |
| `--surface-elevated` | `#ffffff` | `#1d4252` |
| `--ink` | `#102a43` | `#f0f7fa` |
| `--body` | `#334e68` | `#c7dce5` |
| `--muted` | `#627d98` | `#91afbc` |
| `--border` | `#bcccdc` | `#355765` |
| `--border-soft` | `#d9e2ec` | `#274653` |
| `--primary` | `#006d77` | `#45c4c9` |
| `--primary-hover` | `#00545c` | `#74d8dc` |
| `--on-primary` | `#ffffff` | `#061a22` |
| `--focus` | `#7b2cbf` | `#c77dff` |
| `--success` | `#24735a` | `#70d6a8` |
| `--warning` | `#8a5d00` | `#f1c75b` |
| `--danger` | `#a33a46` | `#ff8892` |

`--font-display` resolves to Cormorant Garamond with a Georgia fallback;
`--font-ui` resolves to Source Sans 3 with a Segoe UI fallback.
`--radius-control` is `8px` and `--radius-card` is `12px` in both modes.

Viewer imagery uses the separate, mode-invariant `--viewer-stage: #090807` and
`--viewer-on-stage: #f2eadc` values. The viewer stage, OpenSeadragon surface,
poster, thumbnails, and tiles remain natural-color and receive no theme filter,
inversion, or blend mode.

## Responsive composition

### Authentication

- Above `820px`, the entry surface uses two balanced functional columns; the form
  column has a `460px` minimum and a CSS-only specimen field occupies the visual panel.
- At `820px` and below, the surface becomes one scrolling column with the
  specimen story above the form. Inputs remain at least `50px` high, the submit
  action at least `54px`, and the secondary authentication action at least
  `44px`.
- At `420px` and below, the story header stacks, the compact theme control moves
  below the brand, and both story and form use `18px` inline padding.

### Library workspace

- Above `600px`, a sticky `72px` product rail anchors a centered content canvas
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
Reduced-motion users bypass the GSAP authentication entrance, navigator and
shared-rail transitions are removed, the indeterminate processing animation is
disabled, and remaining CSS transitions are reduced to `0.01ms`.
