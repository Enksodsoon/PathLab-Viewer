# Assessment dialog keyboard access

Labels: wayfinder:decision
Status: confirmed; local candidate under qualification

## Evidence and repair

Released daa101e native Edge Learner preview did not dismiss with Escape. Learner preview, Publish settings and Import questions use div role=dialog overlays without Escape or focus containment. Three independent component cases reproduce Escape leaving each dialog present; no publication/import writes occur. Replace the three shells with one native modal dialog, retaining existing drawers, routes and callbacks. Native cancel dismisses, explicit close remains available, background is inert, and focus returns to the opener.

An initial native-dialog implementation retained React autoFocus on close controls; focus-return assertions then failed. Moving initial focus after showModal and removing those three autoFocus attributes passes all21authoring tests. Four-engine browser qualification then found Tab leaving the native dialog in Chromium/WebKit; Firefox passed. Add an explicit boundary wrap over visible enabled tab stops. Preserve native Escape and modal semantics. The repeated browser run passed4cases but8failed during initial module loading or the combined four-viewport test budget, before dialog actions. Retain these failures separately; split each viewport into its own test with unchanged assertions and zero retries. Final browser/build/full-suite qualification is pending.

Build identified an unsupported Testing Library exact option in the new test. Remove it; its name matching is already exact by default. No API, publication policy, feature activation, dependency or database changes.

## Live scope

The synthetic draft saves1.251points with an observed200 acknowledgment and retains it after an actual browser-control refresh. The first save attempt showed the generic conflict label and reloaded1.25; its underlying error remains unresolved. This positive repetition does not classify that first failure or establish learner score persistence. Prepared Practice publication has a one-response limit, no assigned classes and manual feedback release; the specific user approval is pending. No real learner records are used.

Receipts in ignored var: assessment-dialog-keyboard-red.log, assessment-dialog-keyboard-green.log, assessment-dialog-keyboard-final-green.log, assessment-dialog-keyboard-browser.log, assessment-dialog-keyboard-browser-final.log, assessment-dialog-build.log, production-daa101e-assessment-native.json.


## Review and qualification follow-up

Independent review found the boundary selector omitted native summary controls. With Publish disabled after an unacknowledged save, Attempts became the last selected control and keyboard wrapping skipped both Collection settings and Learner release. Chromium reproduces this at the focus assertion before repair. The first mock used PUT whereas the real save method is PATCH; its focus failure is retained, and the corrected PATCH503 fixture independently reproduces the same focus failure. Include visible enabled summaries in the trap and preserve modified browser Tab chords. The added negative browser case requires one attempted synthetic save and zero publication calls; it does not classify the first live save failure.

The complete frontend passed529tests across81files in411.60seconds, and the build passed12.21seconds before this final selector change. Final52-case browser matrix, final build/affected-component check and renewed independent review are pending. No prior startup failures are erased.


## Final product qualification

The first52case run passed35andfailed17: four disabled-publication summary cases, twelve WebKit opener-focus cases, and one Firefox initial-load timeout. Diagnostics refute the tentative default-tabIndex hypothesis: all three engines report native summary tabIndex0. Hidden descendants of closed details nevertheless have layout rectangles; checkVisibility correctly reports them hidden. Use this visibility check with summary eligibility. Explicitly focus dialog launch controls for WebKit, capture the opener before showModal, and restore connected opener focus after close. Sectioned Import returns to Templates & import because Choose assessment unmounts when its starter panel closes.

The final52case matrix passes across Chromium, Firefox, WebKit and mobile Chromium with zero retries. Each dialog has independent320px, tablet, short-landscape and desktop cases, plus disabled-publication settings reachability after an injected503 save failure with no publication calls. Both authoring files pass36tests after the final product changes; build11.42seconds, changed-file ESLint and diff checks pass. Full529test qualification predates the final visibility/opener adjustments; fresh complete exact-head CI remains required. Eight sectioned preview/import browser controls are running separately. These are engineering checks, not actual production or physical-device qualification.
