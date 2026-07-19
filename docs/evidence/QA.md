# Local acceptance evidence — 2026-07-19

Status: **BLOCKED for public-production readiness**. The implementation and local evidence are complete enough for PR review, but live OCI, external load, shaped-network, physical-device, and clean-restore gates have not been run.

## Browser method and core workflow

The in-app Browser tool was unavailable in this session, so the documented Playwright fallback was used with Chromium. The browser exercised the real local FastAPI and `tusd v2.9.2` services—no API response mocks:

1. Signed in as the seeded administrator through `POST /api/v1/auth/session`.
2. Selected a real synthetic OME-TIFF in the upload control.
3. Reserved the slide, created and completed a tus upload, received both HTTP hooks, and observed `Upload complete. Processing is queued.` with no console errors.
4. Opened the 24,970 × 31,087 real converter example through OpenSeadragon. Ten sampled DZI/tile requests returned HTTP 200; zero returned non-200.
5. Activated zoom and home controls on the phone viewport.

Native screenshots:

- `admin-desktop.png` — 1440 × 1000
- `admin-mobile.png` — 390 × 844
- `viewer-desktop.png` — 1440 × 1000
- `viewer-mobile.png` — 390 × 844
- `viewer-tablet.png` — 820 × 1180

All three viewport classes had zero horizontal page overflow. These are emulated Chromium viewports, not the required physical phone/tablet evidence.

## Reference fidelity ledger

The accepted concepts and final screenshots were inspected side by side with the image viewer in the same QA pass.

1. **Information architecture:** retained the quiet white header, left upload operation, right slide inventory, and tissue-first viewer canvas.
2. **Color:** retained deep navy text, teal active/safe actions, cool gray surfaces, and coral only for deletion/failure.
3. **Density:** final admin uses fewer columns and a compact row card so long names and lifecycle errors survive phone widths; this intentionally differs from the concept table.
4. **Viewer controls:** retained zoom, home, fullscreen, navigator, dark surround, and scale bar. Phone controls move to a bottom floating rail to protect tissue visibility.
5. **Typography and icons:** used system UI typography for zero external font requests and Lucide stroke icons throughout; no emoji or generated raster controls are used.
6. **Responsive behavior:** the two admin columns collapse in document order, while the viewer remains a fixed-height app surface at desktop, tablet, and phone sizes.
7. **Privacy cues:** final copy makes the concept's implied boundary explicit: `The original remains private. Public links serve sanitized JPEG tiles only.`

Copy differences are deliberate: `Upload OME-TIFF` became `Add a slide`, `Slides` became `Your slides`, and `Ready to publish` became the state-machine label `Ready — private`. The final viewer omits the concept's fake magnification readout and onboarding overlay because neither can be truthful without calibrated objective metadata or first-run state.

## Administrator password recovery acceptance — 2026-07-19

The complete local candidate passed these checks:

- Backend: 196 pytest tests passed.
- Python quality: Ruff passed and mypy reported no issues in 13 source files.
- Frontend: 21 Vitest tests passed, ESLint passed, and the production Vite build completed.
- Deployment configuration: `docker compose -f deploy/compose.yaml config --quiet` passed with disposable interpolation values.
- Repository hygiene: `git diff --check` passed.

The production backend image was then built and run in an isolated container with two API workers, a disposable SQLite database, and generated in-process credentials. Alembic upgraded the empty database, the API readiness check returned HTTP 200, the first recovery returned HTTP 204, reuse of the consumed code returned HTTP 400, and sign-in with the replacement password returned HTTP 201. The generated recovery code, passwords, and application secret were not printed or recorded, and the disposable container and data directory were removed after the check.

Live production recovery is intentionally unconsumed. The deployed administrator password must not be rotated until the owner separately authorizes that action.
