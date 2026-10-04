# Return from unavailable shared links

Labels: wayfinder:ticket

The September 28 Antigravity reconciliation revision (SHA-256 ceafbc7455b16b9692cebf6810c89d4f596a2b66237f61a7a8616df9f20ffaf2, line 200, FE-89) identifies a caller missed by the original viewer.error-navigation repair. Unavailable public folders and collections render Retry without an exit. The original repair covers ViewerPage; this finding covers SharedViewerPage separately.

Add a native Go to library link to the existing /admin route. Keep Retry, authorization and invitation contracts. The existing AdminPage authentication boundary handles anonymous visitors. No library data is granted by a public share.

The two new unit cases fail against the original missing-link state and pass after repair; all eleven affected unit cases pass. Final browser qualification passes 32 cases across Chromium, Firefox, WebKit and mobile Chromium, both share types and four viewports (320x740, 768x1024, 900x420, 1584x992). It verifies Retry adds one request, keyboard focus/Enter, a 44px minimum target, viewport containment, real sign-in rendering and reload persistence. Light/dark and reduced-motion configurations are covered. Synthetic API fixtures deny private access; production is untouched.

The initial browser fixture incorrectly assumed one initial request under StrictMode. Preserve that failed run separately; the corrected fixture measures the initial count before Retry. An incidental Windows encoding change was restored from the exact UTF-8 Git blob before final qualification. Independent review of the final four-file diff is clear. Final full frontend passed573 tests across85 files in175.46seconds; lint and production build passed. Immutable distribution/inventory refresh and hosted release gates remain pending. Verified production remains c37cf81; this repair is not deployed yet.

Evidence: docs/remediation/evidence/shared-unavailable-return.json and docs/remediation/ANTIGRAVITY_V2_RECONCILIATION.md. Local detailed logs remain under var/shared-unavailable-return-*.log.
