# Remaining campaign closure

Labels: wayfinder:decision
Status: in progress
Owner: root

## Decision

Continue the explicitly authorized repair and production campaign from deployed main `3cb26bc14ec64bc3dad85a29a6da823082615d6c`. Preserve source report aliases, private files, bounded resource limits and protected release checks.

## Evidence and dependencies

- PRs 267–270 and 272 merged. [Protected deployment 36381707062](https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/36381707062) succeeded at `3cb26bc` after all nine exact-main checks passed. Its restore drill reported 69 tables, 105,586 files and schema `20260907_0037`; the deployment log reported health-checked success. The first [exact-main full-stack run](https://github.com/Enksodsoon/PathLab-Viewer/actions/runs/36379279574) failed in the route-coverage menu sweep; rerun attempt 2 passed. Keep this intermittent test result visible.
- Signed-in Edge checks at the earlier `cf0d2d2` release showed synthetic upload tiles, annotation persistence after reload, adjacent navigation and rejection of unpublished Classroom slides. These checks have not yet been repeated at `3cb26bc`.
- Fresh thumbnail reproduction showed terminal status polling omitted the newly available thumbnail. PR 270 extended the existing status contract while preserving selection and pagination; native rendered regression failed before the fix and passed afterward.
- Study purger database failure, cached IndexedDB draft-open rejection, pseudonym collision and Classroom expiry/grant race were independently reproduced and repaired in PR 270. Native regression checks and the reviewed release passed; individual post-release production checks remain open.
- Production Classroom exposed teacher slide reset after mark acknowledgment and a mouse Send failure. Shared fixes passed native Chromium, Firefox, WebKit and mobile Chromium, with responsive drawing controls at 320px, tablet and short landscape sizes, then shipped in PR 270. Teacher actions still need post-release authenticated checks.
- Valid folder moves can combine fresh roots with cached children into a client cycle. Shared tree and breadcrumb guards shipped in PR 270 after native regression; production interaction remains unchecked.
- The deployed public Study entry returned `STUDY_MODE_DISABLED` to a format-valid synthetic invitation code. Preserve the current feature gate; local engineering qualification does not constitute production activation.
- All 125 hardening mechanisms retaining 328 source aliases were reviewed; see HARDENING_REVIEW.md. The OneDrive synchronization/sharing question remains substantive unresolved work, and deployed status does not answer it.
- Dependency admission requires actual notice material and accountable receipts; see INVENTORY_CLOSURE.md. No automatic admission or inferred license grant.
- The pinned Forge runtime passed the recorded synthetic Viewer pairing checks; see FORGE_QUALIFICATION.md. This does not establish physical-device or real-WSI quality qualification.
- After deployment of `3cb26bc`, a disposable synthetic Classroom invitation reloaded and slide B tiles rendered in Edge. The administrator tab still shows a failed sign-in, so current Library, upload and teacher workflows have not been checked against this release. Activated Study workflows remain gated. Earlier signed-in checks apply to `cf0d2d2`, not to `3cb26bc`.

## Closure gates

Every source claim has a supported disposition; confirmed defects have regressions; four journeys pass applicable failure, persistence and responsive checks; reviewed batches pass fresh protected checks and deployment; deployed workflows pass authenticated verification. Credential rotation and OneDrive sharing scope still require external facts. Physical-device and bounded soak evidence remain distinct from browser emulation.
