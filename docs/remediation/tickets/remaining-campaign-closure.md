# Remaining campaign closure

Labels: wayfinder:decision
Status: in progress
Owner: root

## Decision

Continue the explicitly authorized repair and production campaign from deployed main `3cb26bc14ec64bc3dad85a29a6da823082615d6c`. Preserve source report aliases, private files, bounded resource limits and protected release checks.

## Evidence and dependencies

- PRs 267–270 and 272 merged. [Protected deployment 36381707062](https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/36381707062) succeeded at `3cb26bc` after all nine exact-main checks passed. Its restore drill reported 69 tables, 105,586 files and schema `20260907_0037`; the deployment log reported health-checked success. The first [exact-main full-stack run](https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/36379279574) failed in the route-coverage menu sweep; rerun attempt 2 passed. Keep this intermittent test result visible.
- Signed-in Edge checks at the earlier `cf0d2d2` release showed synthetic upload tiles, annotation persistence after reload, adjacent navigation and rejection of unpublished Classroom slides. The current-release checks below repeat Library, upload, annotation persistence, adjacent navigation and Classroom presenter paths; unpublished-slide rejection has not been repeated at `3cb26bc`.
- Fresh thumbnail reproduction showed terminal status polling omitted the newly available thumbnail. PR 270 extended the existing status contract while preserving selection and pagination; native rendered regression failed before the fix and passed afterward.
- Study purger database failure, cached IndexedDB draft-open rejection, pseudonym collision and Classroom expiry/grant race were independently reproduced and repaired in PR 270. Native regression checks and the reviewed release passed; individual post-release production checks remain open.
- Production Classroom exposed teacher slide reset after mark acknowledgment and a mouse Send failure. Shared fixes passed native Chromium, Firefox, WebKit and mobile Chromium, with responsive drawing controls at 320px, tablet and short landscape sizes, then shipped in PR 270. Current-release presenter slide navigation, guide mode, tray collapse and mark acknowledgment without slide reset passed in Edge; question Send still needs a post-release check.
- Valid folder moves can combine fresh roots with cached children into a client cycle. Shared tree and breadcrumb guards shipped in PR 270 after native regression; production interaction remains unchecked.
- The deployed public Study entry returned `STUDY_MODE_DISABLED` to a format-valid synthetic invitation code. Preserve the current feature gate; local engineering qualification does not constitute production activation.
- All 125 hardening mechanisms retaining 328 source aliases were reviewed; see HARDENING_REVIEW.md. The OneDrive synchronization/sharing question remains substantive unresolved work, and deployed status does not answer it.
- Dependency admission requires actual notice material and accountable receipts; see INVENTORY_CLOSURE.md. No automatic admission or inferred license grant.
- The pinned Forge runtime passed the recorded synthetic Viewer pairing checks; see FORGE_QUALIFICATION.md. This does not establish physical-device or real-WSI quality qualification.
- After deployment of `3cb26bc`, signed-in Edge loaded Library, filtered command search, rendered Quick Look and adjacent synthetic slide B tiles, and showed the explicit Library return. A 12 MiB synthetic OME-TIFF uploaded to Ready private, its dock Open action survived Classroom navigation, and its viewer URL persisted after reload. A private rectangle annotation on synthetic B persisted after Save and reload. Teaching Studio loaded its assessment dashboard. Disposable Classrooms rendered slide B on the live stage, switched guide mode, collapsed the activity tray and acknowledged a rectangle mark without resetting to A; both new invitations were revoked after testing. No real learner was used. The first viewer open from a stale cached bundle hit a removed lazy chunk and recovered through Reload app; fresh pages worked. See [production qualification](../PRODUCTION_CLOSURE_QA.md). Activated Study workflows remain gated; question acknowledgment, concurrent learner interaction and physical-device/soak checks remain open.

## Closure gates

Every source claim has a supported disposition; confirmed defects have regressions; four journeys pass applicable failure, persistence and responsive checks; reviewed batches pass fresh protected checks and deployment; deployed workflows pass authenticated verification. Credential rotation and OneDrive sharing scope still require external facts. Physical-device and bounded soak evidence remain distinct from browser emulation.
