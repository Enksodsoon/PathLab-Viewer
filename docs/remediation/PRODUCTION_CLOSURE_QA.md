# Production closure qualification — 2026-09-27

## Scope and evidence

The parent qualification operator exercised deployed commit `cf0d2d2b0b6a298185a676988ffae69a6d01dd3c` in signed-in Edge on Windows using disposable synthetic pixels, a synthetic folder, two slides and a classroom. No real learners were used. The durable receipt is `var/remediation-evidence/production-closure-qa.json`; screenshots are retained alongside it. This document separates those production observations from local repairs and does not qualify unmerged changes as deployed.

## Observed production passes

- Authenticated library loading and synthetic folder persistence across navigation.
- Synthetic 12 MiB and 27 MiB OME uploads reaching ready state, upload dock retention across Classroom navigation, and measured bytes/speed/ETA during multi-chunk upload.
- Completion Open action opening the actual admin viewer; authenticated DZI and seven JPEG tiles downloading without failures; patterned synthetic tissue rendering.
- Rectangle annotation acknowledging Saved and surviving reload; adjacent-slide navigation returning to the original folder and resetting rotation; uncalibrated synthetic slides avoiding physical magnification claims.
- Classroom rejecting unpublished slides, explicit deidentification acknowledgment publishing both synthetic slides, folder shortcut selecting the intended folder, and prepared classroom starting live with the existing expiry policy.
- Teacher navigator rendering the patterned synthetic slide, upload dock minimizing in the live classroom, and a synthetic teaching rectangle receiving server acknowledgment.
- Teacher question Show pinned field successfully navigates to the pinned field, and Mark answered acknowledges the mutation with the pending count returning to zero.
- Synthetic learner review-code admission/live join, anchored centre pin acknowledgment, keyboard question acknowledgment, and local capture plus synthetic note surviving reload at 1/100 entries.
- A fresh offline HTML notebook export independently verified with the exact synthetic note and one decodable 1600x690 WEBP image. The automation download waiter timed out, but the fresh file was present and verified; this was not an export failure.

## Confirmed production defects and local qualification

A newly completed library card lacked its thumbnail until library reload. The closure patch adds the authoritative thumbnail URL to the existing status response and updates only the corresponding card while retaining current selection. Local backend/frontend regressions are tracked by the parent. The added native library scenario passed Chromium, Firefox, WebKit and mobile Chromium: a converting card receives its late ready thumbnail, the 256x256 image actually decodes, another card stays selected, the search/folder remain intact, and the items endpoint is fetched only once. This uses the existing synthetic browser transport and qualifies frontend status handling separately from the production observation. Receipt: `var/remediation-evidence/library-late-thumbnail-matrix`.

With Guide off, selecting slide B and acknowledging a teaching mark returned the teacher to presenter slide A. The screenshot `production-classroom-mark-slide-reset.png` records the observed result. Current-code investigation found that every teacher snapshot unconditionally selected the server presenter slide, including annotation-triggered refresh. The actual native OSD regression reproduced the acknowledged mark followed by an unwanted tile-source change. The patch preserves a valid teacher selection during snapshot refresh while continuing to follow an active participant controller. The final native scenario passed Chromium, Firefox, WebKit and mobile Chromium, including unforced teacher/student drawing controls at 320px portrait, tablet and short landscape sizes. A separate mobile overlap discovered during qualification was repaired by moving the active teacher drawing activity tray away from the bottom drawing toolbar. No deployment claim is made here.

The anchored question Send button also failed in production while Ctrl+Enter succeeded. A real OSD browser regression reproduced zero requests after clicking Send. The canvas tracker consumed overlay presses before the portal received a click. The shared composer now contains pointer/click/wheel gestures at its native overlay container and shares one guarded submit function across button, form and keyboard paths. The final native click/tap plus keyboard scenario passed all four browser targets; keyboard propagation and native default focus remain intact.

## Unqualified paths

Partial upload pause/resume was not proved: the transfer finished before the pause attempt. The requested one-day review expiry was not proved in production: controlled input filling and immediate submission retained the default seven-day value. The local normal-browser fill/Prepare regression submitted the exact chosen ISO timestamp in all four browser targets, so no user-facing expiry defect was confirmed and no expiry product change was made. A separate learner tab was obstructed by another Edge extension panel; serial learner flows succeeded in the original working tab, without proving concurrent teacher/learner browsers. The deployed `/admin/study` route returns `STUDY_MODE_DISABLED`: Study Packs and courses are not available under the current deployed policy. The gate was preserved; no activation was attempted. Study synthetic learner workflows therefore remain unqualified in production. Physical mobile/tablet devices, sustained soak, and production behavior of new closure repairs also remain unverified.

Local receipts: `var/remediation-evidence/teacher-local-slide-red-native` (failing native source assertion), `teacher-local-slide-responsive-final` (four native passes), `classroom-send-button-red` (failing native click), `classroom-send-button-final-matrix` (four native passes), and `classroom-expiry-fill-matrix` (four requested-expiry passes). The native browser transport is synthetic; these are not real-server authorization or new production-deployment receipts. Scoped Classroom unit checks passed 18 tests across three files; ESLint and TypeScript completed successfully.

These receipts qualify the listed exercised paths only; they do not claim exhaustive controls, device coverage, or deployment of the local patch.
