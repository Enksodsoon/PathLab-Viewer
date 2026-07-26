# Task 4 report: private, public, and shared viewer chrome

## Scope

- Added the existing light, dark, and system theme control to private/public
  single-slide and folder/collection shared-viewer headers.
- Rethemed headers, rails, captions, controls, loading chrome, and privacy-safe
  states with the established semantic Canvas Focus tokens.
- Kept the WSI field on the same warm-black stage in both themes and removed the
  poster saturation filter. No stage, poster, tile, or canvas inversion, theme
  filter, or blend treatment was introduced.
- Preserved API selection, public routes, viewer handles, loading mode,
  OpenSeadragon persistence, scale bars, retry/backoff, keyboard navigation,
  session position, and generic missing-state wording.

## RED evidence

Focused Vitest initially recorded exactly three expected failures:

- private/public ViewerPage had no accessible `Theme preference` group;
- shared folder/collection ViewerPage had no accessible `Theme preference`
  group;
- the imagery invariant detected `filter:saturate(.92)` on `.viewer-poster`.

The remaining 19 focused viewer/shared tests passed. A targeted Chromium E2E
also failed at the missing shared-viewer theme control before production code
changed.

## GREEN evidence

| Check | Result |
| --- | --- |
| Focused viewer/shared unit suite | PASS: 24/24 |
| Full unit suite, one worker | PASS: 16 files / 90 tests |
| Chromium route/theme matrix | PASS: 5/5 |
| Full responsive Playwright matrix | PASS: 20/20 across Chromium, Firefox, WebKit, and mobile Chromium |
| Lint | PASS |
| Production build | PASS: 4,637 modules transformed |
| `git diff --check` | PASS |
| Viewer GSAP scan | PASS: no GSAP in viewer surfaces |
| Viewer filter/inversion scan | PASS: no filter, mix-blend, or invert declarations |

The all-project matrix uses a four-worker cap. Its 12-navigation breakpoint
stress case has a scoped 120-second test budget; before that budget was raised,
all 16 other checks passed and only that test exhausted Playwright's default
30-second timeout in each browser. A later WebKit run exposed a redundant
global readiness wait before the matrix began; readiness now lives in the tests
that consume it, and the final all-project run passed 20/20.

## Route and behavior coverage

- Individual public `/s/public-1` and private
  `/admin/preview/private-1` routes were exercised at 390 and 1584px in light
  and dark modes.
- Folder `/f/share-public` was exercised with a fresh navigation at 320, 390,
  600, 760, 761, 768, 901, 1024, 1251, 1440, 1584, and 1920px.
- Collection `/c/share-public` was exercised at mobile and desktop widths.
- Computed checks require light/dark chrome colors to differ while
  `.viewer-stage` and `.osd-surface` remain `rgb(9, 8, 7)` and poster/stage
  filters remain `none`.
- Unit checks prove a theme change does not recreate or destroy the
  OpenSeadragon instance, and preserve the collection API endpoint plus
  `pathlab-share-position:collection:share-public` key.

## Rendered Browser QA

An authenticated real private slide was reviewed at 1912×901 in light and dark
modes. The header changed from `rgb(250, 249, 245)` to `rgb(24, 23, 21)` while
the stage and OSD surface stayed `rgb(9, 8, 7)`. The primary OSD canvas remained
`filter:none`, `opacity:1`, and `mix-blend-mode:normal`; the slide imagery,
loading selector, scale bar, theme control, and all four viewer controls
rendered successfully.

Console output had no application exception. It retained the repository's
existing React Router v7 future-flag warnings and an OpenSeadragon
`[TiledImage] options.drawer is required` log while the real slide still loaded
and rendered.

## Impeccable review

The single permitted detector pass reported two legacy `Inter` declarations at
the top of `styles.css`. Both were replaced with the established Source Sans
and `--font-ui` typography. Per the detector's one-pass rule, it was not rerun.

The independent finish reviewer then found one actionable P2: at 390px the
single-slide viewer buttons measured 40×40px and Loading mode measured 30px
high. A new rendered Chromium assertion failed RED at 40px. Mobile-only CSS now
raises Zoom in, Zoom out, Home view, Fullscreen, and Loading mode to the 44px
floor. The focused regression passed, followed by the final 20/20 all-project
matrix. The reviewer reported no other visual, responsive, accessibility,
clinical-imagery, contract, or scope finding.

## Limitations

- The local authenticated library listed published slides, but the two public
  links opened from its own UI returned the existing privacy-safe
  `SLIDE_NOT_FOUND` response. A live successful public-slide render therefore
  could not be claimed; its successful route/theme/render evidence comes from
  the cross-browser intercepted fixture.
- The local dataset had no usable folder or collection public share. Successful
  folder and collection evidence likewise comes from the cross-browser
  intercepted manifests.
- No backend, storage, conversion, publication, deployment, or OCI state was
  changed.
