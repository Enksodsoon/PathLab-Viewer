# Claude Canvas Frontend Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. All production behavior changes use test-driven development.

**Goal:** Rebuild every PathLab Viewer web surface in the approved warm, light-dominant Claude-inspired Canvas Focus design while preserving all application behavior and privacy boundaries.

**Architecture:** A global semantic theme layer resolves `light`, `dark`, and `system` before React starts, then exposes the same preference through a React context. Authentication, the Canvas Focus admin shell, and viewer chrome consume shared tokens and controls; the OpenSeadragon stage remains visually and behaviorally isolated. GSAP is code-split with authentication only.

**Tech Stack:** React 19, TypeScript, Vite, CSS, Phosphor Icons, Fontsource, GSAP, Vitest, Testing Library, Playwright.

## Global Constraints

- Start from fresh `origin/main` in `codex/claude-canvas-redesign`; do not modify the dirty root checkout.
- Use `claude/DESIGN.md` and `claude/THEME_MODES.md` from the root checkout as source references; root Mastercard `DESIGN.md` remains untouched.
- Canvas Focus composition: narrow persistent icon rail, overlay library navigator, maximum-width content canvas, right overlay inspector.
- Light mode is the primary expression; dark mode is complete; viewer stages stay warm-black in both modes.
- Store `light | dark | system` under `pathlab-theme:v1`; apply resolved `data-theme="light|dark"` before React with a same-origin external script compatible with `script-src 'self'`.
- Use Cormorant Garamond for display text, Source Sans 3 for UI text, and Phosphor for controls. Use an original PathLab tissue-layer SVG for branding.
- GSAP runs only on the authentication entry sequence and must be excluded from viewer/admin authorized chunks.
- Preserve routes, API calls, URL state, upload flow, storage/conversion/publication/sharing behavior, OpenSeadragon lifecycle, WSI colors, accessible names, keyboard shortcuts, focus restoration, and native dialog semantics.
- Respect `prefers-reduced-motion`; maintain WCAG AA token contrast and 44px mobile targets.
- No backend, database, migration, infrastructure, deployment, or factual-copy changes.

---

### Task 1: Canonical Records and Theme Foundation

**Files:**
- Create: `apps/web/PRODUCT.md`
- Create: `apps/web/DESIGN.md`
- Create: `apps/web/public/theme-init.js`
- Create: `apps/web/src/theme/theme.ts`
- Create: `apps/web/src/theme/ThemeProvider.tsx`
- Create: `apps/web/src/theme/ThemeControl.tsx`
- Create: `apps/web/src/theme/theme.css`
- Create: `apps/web/src/test/theme.test.tsx`
- Modify: `apps/web/index.html`
- Modify: `apps/web/src/main.tsx`
- Modify: `apps/web/package.json`
- Modify: `pnpm-lock.yaml`

**Interfaces:**
- Produces `ThemePreference = 'light' | 'dark' | 'system'`.
- Produces `ResolvedTheme = 'light' | 'dark'`.
- Produces `ThemeContextValue { preference, resolvedTheme, setPreference }`.
- Produces `ThemeProvider`, `useTheme()`, and `ThemeControl({ compact?, className? })`.
- Produces local storage key `pathlab-theme:v1` and root `data-theme`.

- [ ] Write failing tests for default system resolution, stored light/dark resolution, invalid-storage fallback, OS preference changes, persistence, and accessible three-choice controls.
- [ ] Run `pnpm --dir apps/web test -- src/test/theme.test.tsx` and confirm failures are caused by missing theme interfaces.
- [ ] Add Fontsource, Phosphor, GSAP, and `@gsap/react`; implement theme modules, semantic tokens, and the CSP-safe pre-React initializer.
- [ ] Wrap the application in `ThemeProvider`, import fonts/tokens, and verify the focused test passes.
- [ ] Run the complete unit suite, lint, and build; commit as `feat(web): add Claude theme foundation`.

### Task 2: Brand, Icons, and Authentication

**Files:**
- Modify: `apps/web/src/components/Brand.tsx`
- Split/modify: `apps/web/src/components/AuthPanels.tsx`
- Create focused authentication/security modules only when required to keep GSAP out of authorized admin chunks.
- Modify: `apps/web/src/styles.css`
- Modify: `apps/web/src/test/admin.test.tsx`
- Add a performance-contract test proving GSAP is imported only by the lazy authentication surface.
- Modify all remaining Lucide imports after tests cover the representative accessible behavior.

**Interfaces:**
- `Brand` retains accessible name `PathLab Viewer` and accepts existing variants.
- Authentication remains lazy from the authorized admin bundle.
- Existing login, recovery, password-change, and session callbacks remain unchanged.

- [ ] Add failing tests for original tissue-layer brand markup, theme control presence, two-line editorial authentication structure, reduced-motion behavior, and GSAP isolation.
- [ ] Verify focused tests fail for the missing redesign.
- [ ] Implement the warm editorial split using the existing histology asset, original SVG mark, Phosphor icons, and one `useGSAP` entrance sequence with cleanup and reduced-motion bypass.
- [ ] Migrate remaining control icons to Phosphor using `currentColor`, then remove `lucide-react`.
- [ ] Run authentication, viewer, library unit tests, lint, and build; commit as `feat(web): redesign authentication and brand`.

### Task 3: Canvas Focus Admin Shell

**Files:**
- Modify: `apps/web/src/pages/AdminPage.tsx`
- Modify: `apps/web/src/components/library/AppRail.tsx`
- Modify: `apps/web/src/components/library/LibraryNavigator.tsx`
- Modify: `apps/web/src/components/library/LibraryToolbar.tsx`
- Modify relevant library view, filter, dialog, details, quick-view, and selection components only where structure or theme integration requires it.
- Rewrite: `apps/web/src/library.css`
- Modify: `apps/web/src/test/library-explorer.test.tsx`
- Modify: `apps/web/e2e/library-responsive.spec.ts`

**Interfaces:**
- Persistent rail exposes All Slides, Upload, Processing, Failed, Trash, navigator, account, and sign-out actions.
- Overlay navigator contains folders, collections, saved views, and quick views; Escape closes it and restores focus.
- Details inspector overlays from the right; it never permanently consumes grid width.
- All existing query parameters and action callbacks remain unchanged.

- [ ] Add failing tests for the narrow rail, overlay navigator, integrated quick views, right overlay inspector, theme control, and preserved focus/inert contracts.
- [ ] Add failing responsive checks for Canvas Focus at 320, 390, 600, 768, 901, 1251, 1440, and 1920 pixels.
- [ ] Implement the new shell and clean semantic light/dark styles without stacking overrides on the old dark-library CSS.
- [ ] Verify upload, search, filter, sort, grid/list/table, selection, processing, failure, publishing, sharing, Trash, folders, collections, saved views, pagination, dialogs, and mobile dock behavior.
- [ ] Run library unit/E2E tests, lint, and build; commit as `feat(web): implement Canvas Focus library`.

### Task 4: Private, Public, and Shared Viewer Chrome

**Files:**
- Modify: `apps/web/src/pages/ViewerPage.tsx`
- Modify: `apps/web/src/pages/SharedViewerPage.tsx`
- Modify: `apps/web/src/styles.css`
- Rewrite: `apps/web/src/shared-viewer.css`
- Modify: `apps/web/src/shared-message.css`
- Modify: `apps/web/src/test/viewer.test.tsx`
- Modify: `apps/web/src/test/shared-viewer.test.tsx`
- Modify: `apps/web/e2e/shared-viewer-responsive.spec.ts`

**Interfaces:**
- Theme-aware headers, rails, captions, and controls consume semantic tokens.
- `.viewer-stage`, `.osd-surface`, posters, and tiles remain warm-black/natural-color and never use color inversion or theme filters.
- Existing viewer handle, loading mode, scale bar, keyboard, persistent OpenSeadragon, session position, retry, and privacy-safe missing-state contracts remain unchanged.

- [ ] Add failing tests for theme control availability and invariant unfiltered viewer imagery.
- [ ] Verify focused tests fail for missing viewer integration.
- [ ] Implement warm cream viewer chrome and complete dark equivalents while leaving the tile stage behavior untouched.
- [ ] Verify private, individual public, folder, and collection routes at desktop/mobile widths and both themes.
- [ ] Run viewer/shared unit and E2E tests, lint, and build; commit as `feat(web): retheme viewer surfaces`.

### Task 5: Full QA, Visual Review, and Delivery

**Files:**
- Modify test assertions that intentionally referenced the discarded dark-only palette.
- Update `apps/web/DESIGN.md` only with exact tokens and responsive behavior that survived implementation.
- Do not modify deployment configuration.

- [ ] Run `pnpm --dir apps/web lint`, `pnpm --dir apps/web test`, and `pnpm --dir apps/web build`.
- [ ] Run the full Playwright matrix and verify no overflow, focus loss, inaccessible controls, or WSI filtering in light/dark desktop/mobile scenarios.
- [ ] Run `python scripts/check_public_repository.py` and `git diff --check`.
- [ ] Capture and inspect auth, admin, private viewer, and shared viewer screenshots at desktop/mobile in both themes.
- [ ] Run Impeccable detector once over changed web UI, then dispatch its independent finish reviewer and address material findings.
- [ ] Run final whole-branch code review, fix one consolidated wave if needed, rerun affected tests, and prepare a reviewable PR. Do not merge or deploy without separate authorization.
