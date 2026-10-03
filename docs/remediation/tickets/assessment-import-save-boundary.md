# Assessment import save boundary

Labels: wayfinder:decision
Status: confirmed; separate candidate under qualification

At33a4462, change the title and import questions before the750ms autosave debounce. The backend imports from the persisted destination at expectedRevision1; the builder replaces its local document with that response. An independent component red expects Unsaved local title and receives Original title. This is current-code data loss, not a report-only claim.

Require All changes saved in both the import action guard and its submit control. Display the existing-styled save-first hint. Preserve question selection while the held save completes; import uses the acknowledged revision. Existing route, API, scoring and publication policies are unchanged.

Initial37affected tests pass. Four zero-retry browser cases pass17.7seconds across Chromium, Firefox, WebKit and mobile Chromium: held PATCH keeps import disabled, acknowledgment enables import at expectedRevision2, and the edited title/imported question survive reload. Lint and build7.32seconds pass. Final extended affected suite and renewed independent review remain pending. Complete hosted gates and protected delivery are required after parent recovery and save batches merge.

This repairs importing before acknowledgment. It does not qualify newer edits after closing an in-flight import, stale route completions, cache transaction ordering, or the historical generic production save failure. Those investigations remain visible; no broader offline/publication or clinical claim follows.

Ignored receipts: var/assessment-import-save-boundary-red.log, var/assessment-import-save-boundary-green.log, var/assessment-import-save-boundary-final-tests.log, var/assessment-import-save-boundary-browser.log and var/assessment-import-save-boundary-build.log.

Final46affected tests pass79.56seconds. Review finds no product Critical/Important issues; its browser minor lacked explicit PATCH handler-entry evidence. Add that signal before releasing the held response. The corrected four-browser matrix passes17.1seconds with zero retries and lint passes. Renewed correction review and complete frontend qualification remain pending.

Renewed correction review is clear. Complete final-source frontend539tests across84files pass297.96seconds. Parent save/recovery delivery and fresh hosted exact-head checks remain required.

## Extended confirmed import lifecycle repairs

The earlier in-flight and stale-route exclusions above were historical qualification limits. Independent corrected red at073c0c3 proves newer title loss after dismissing a held import and allowing autosave debounce. A separate old-source navigation red proves A import acknowledgment replaces B draft. Retain the initial cache-mock reset error; restore the candidate after the old-source run.

Reuse the generation-scoped pending token for import and autosave. On acknowledgment, preserve latest local content and append the server-created imported IDs according to existing first-section policy; then save against the acknowledged revision. Preserve local removals, edited prompts, new items and section ordering. When the current sectioned document is empty, retain imported items in an Imported questions section using the server-supplied section identity. Ignore old generations and reset import modal/submission state when loading another draft. On rejection, release the token and reschedule newer local edits against the original revision.

50affected tests95.55seconds,12zero-retry browser cases50.2seconds across four projects, lint and build9.68seconds pass. Browser cases cover native Escape, edits during held legacy/sectioned imports, no competing PATCH, acknowledged revision2 drain and title/question reload. Independent review has no Critical/Important issues; its failed-import-drain Minor is covered with six passing component/helper tests32.74seconds and lint. Complete frontend and renewed correction review remain pending.

Response-lost imports that committed server-side, exhaustive cross-operation cases, cache transaction ordering and complete offline behavior remain unqualified. This does not establish live learner publication or clinical safety.

Final candidate qualification: focused deleted-section-context red reproduced resurrection of old slideId/description/viewport. Construct only required section identity/title/imported items when no local section remains. Seven exact-source import component/helper controls pass23.22seconds; renewed failed-import and fallback review corrections are clear. The earlier544pass complete run predates the fallback correction. Final545tests across85files pass294.44seconds;12zero-retry browser cases54.6seconds, build12.51seconds and lint pass. Asset-rights16ADMITTED and deterministic software612BLOCKED validators pass with rights and strict admission unchanged. Fresh hosted checks and protected delivery remain required.
