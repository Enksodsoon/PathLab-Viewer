# Preserve browser shortcuts in annotation workspaces

Labels: wayfinder:decision
Status: local candidate qualified; independent review and protected delivery pending

## Confirmed trigger and root cause

At production `daa101e`, native Edge Ctrl+R selected Ruler instead of refreshing. The existing keydown handler handles explicit Ctrl/Cmd S/Z/C/V commands, then treats other modified tool keys as plain tools and cancels their defaults. It also cancels modified arrow/deletion keys. Retain this reproduced path as a separate campaign finding.

Six component keyboard regressions fail on the original handler because default actions are cancelled: Ctrl+R, Cmd+R, Ctrl+B, Alt+G, Alt+Left and Ctrl+Backspace. Eight controls for plain R and explicit annotation commands pass. An earlier fixture omitted the required attachment callback and caused14setup errors; its retained log is not root-cause evidence.

## Repair and verification

Return for remaining Ctrl/Meta/Alt combinations after supported annotation commands. Keep plain tool shortcuts, Shift movement and explicit Save/Undo/Copy/Paste. The complete affected workspace file passes23tests after the one-line guard. Full frontend qualification, changed-file lint, production build and browser matrix pass. Independent review and protected delivery remain pending. No new API, data transformation, dependencies or activation changes.

Ignored receipts: `var/annotation-browser-shortcuts-setup-failure.log`, `var/annotation-browser-shortcuts-red.log`, `var/annotation-browser-shortcuts-green.log`. Production remains `daa101e` without this local guard.


## Qualification checkpoint

The complete affected workspace file passed 23 tests. Changed-file ESLint and the production frontend build passed. The first full frontend run passed 508 tests and failed two existing tests: authentication chunk-boundary build exceeded its 30-second test timeout; the filtered-upload library case timed out while waiting for initial rendering. Both suites then passed all 48 tests in isolation. No test timeout, library implementation or authentication behavior was changed. The complete same-scope suite with four workers passed all510tests across81files. The default-run timing failures remain visible; hosted defaults still require fresh exact-head qualification.

A native browser-control Refresh click timed out during live verification. The subsequent observation still showed the synthetic title and Ruler selected, without accessible text; a fresh reload is not established. This tool outcome is retained separately from the confirmed Ctrl+R handler defect.

All four browser projects fail with the modifier guard demonstrably removed: Ctrl+R changes Pan to Ruler. The first browser probe accidentally retained the guard because of CRLF; its four passes are setup history, not red proof. The complete68-case browser matrix passed with the guard restored, across Chromium, Firefox, WebKit and mobile Chromium with zero retries. Native browser-control Refresh subsequently completed on released `daa101e`; the saved synthetic title and rectangle reloaded with NO CHANGES. The local shortcut repair remains undeployed.

## Independent review follow-up

Review found the overlay capture listener consumes modified drawing keys before the workspace sees them. Twelve independent attached-viewer cases reproduce this during polygon construction. Add the same modifier return to overlay keydown while keeping keyup cleanup able to release plain Space pan if a modifier is added before release. Both affected files now pass54tests. The complete frontend523tests and build passed before three added keyup controls; final full scope is pending. All72browser cases pass with zero retries across four projects, including real pointer construction and modified-key preservation. Renewed review and exact-head delivery are required.

Final local qualification: all526frontend tests across81files passed in202.08seconds with four workers; all54affected tests passed. Changed-file lint and diff checks pass. Product build passed10.70seconds; later test-only keyup controls do not change the product artifact. All72browser cases passed with zero retries.
