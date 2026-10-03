# Assessment import save boundary

Labels: wayfinder:decision
Status: confirmed; separate candidate under qualification

At33a4462, change the title and import questions before the750ms autosave debounce. The backend imports from the persisted destination at expectedRevision1; the builder replaces its local document with that response. An independent component red expects Unsaved local title and receives Original title. This is current-code data loss, not a report-only claim.

Require All changes saved in both the import action guard and its submit control. Display the existing-styled save-first hint. Preserve question selection while the held save completes; import uses the acknowledged revision. Existing route, API, scoring and publication policies are unchanged.

Initial37affected tests pass. Four zero-retry browser cases pass17.7seconds across Chromium, Firefox, WebKit and mobile Chromium: held PATCH keeps import disabled, acknowledgment enables import at expectedRevision2, and the edited title/imported question survive reload. Lint and build7.32seconds pass. Final extended affected suite and renewed independent review remain pending. Complete hosted gates and protected delivery are required after parent recovery and save batches merge.

This repairs importing before acknowledgment. It does not qualify newer edits after closing an in-flight import, stale route completions, cache transaction ordering, or the historical generic production save failure. Those investigations remain visible; no broader offline/publication or clinical claim follows.

Ignored receipts: var/assessment-import-save-boundary-red.log, var/assessment-import-save-boundary-green.log, var/assessment-import-save-boundary-final-tests.log, var/assessment-import-save-boundary-browser.log and var/assessment-import-save-boundary-build.log.

Final46affected tests pass79.56seconds. Review finds no product Critical/Important issues; its browser minor lacked explicit PATCH handler-entry evidence. Add that signal before releasing the held response. The corrected four-browser matrix passes17.1seconds with zero retries and lint passes. Renewed correction review and complete frontend qualification remain pending.
