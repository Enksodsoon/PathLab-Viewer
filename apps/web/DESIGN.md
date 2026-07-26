# PathLab Viewer Canvas Focus design record

PathLab Viewer uses a warm, light-dominant clinical canvas inspired by the
supplied editorial reference. It is a PathLab design system, not a copy of the
reference product or brand.

## Foundations

- Display type: Cormorant Garamond.
- UI type: Source Sans 3.
- Primary light canvas: `#faf9f5`; primary dark canvas: `#181715`.
- Coral is reserved for primary actions and high-value emphasis.
- Light and dark modes preserve the same component geometry, spacing, radii,
  focus visibility, and semantic status meaning.

## Semantic tokens

`src/theme/theme.css` is the token authority. Components consume semantic
variables such as `--canvas`, `--surface`, `--ink`, `--border`, `--primary`,
and `--focus`; they do not branch on the active mode.

The main radius rule is 8px for controls and 12px for cards. The page floor is
warm cream in light mode and warm charcoal in dark mode. Viewer stages are a
separate warm-black surface in both modes, preserving pathology image color.

## Accessibility and motion

Text and controls require WCAG AA contrast in each theme. Keyboard focus uses
the semantic `--focus` token. Theme selection is an accessible three-choice
radio group. Reduced-motion users receive no nonessential transitions.
