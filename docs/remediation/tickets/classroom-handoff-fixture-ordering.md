# Classroom handoff fixture ordering

Labels: wayfinder:decision
Status: verified local; release checks pending
Owner: root

## Question and evidence

Does the fresh-main WebKit no-echo failure prove a product dispatch defect? The retained PR291 main trace shows an owner publication dispatched at 5675ms before the atomic handoff boundary at 5738ms, but received by the mock after it set learner control. The mock accurately lets an owner publication reclaim control; its returned control event therefore makes the later publication legitimate. The fixture contradicts its assumed learner authority.

## Resolution

Serialize the mocked authoritative learner grant behind completion of owner requests already dispatched before the handoff. Keep the browser-task dispatch count/control boundary, held snapshot, publication assertions, native OSD, reconnect burst and all deadlines unchanged. No application, API, scoring, data, feature flag or permission changes.

## Verification

Canonical native test passes in Chromium, Firefox, WebKit and mobile Chromium: four passed in 52.4s, two workers and zero retries. Changed-file ESLint and diff checks pass. A separate ignored WebKit probe holds a real owner request until 100ms after the boundary: the old fixture fails the same no-echo assertion (expected five dispatches, received six), while the corrected fixture passes. Probe run: one expected failure, one pass, 39.7s. Retain both artifacts rather than reporting that combined probe as an all-pass run.

Receipts under var/remediation-evidence: classroom-handoff-owner-barrier-four-engines.log and artifacts; classroom-handoff-delayed-probe.log, generated old/fixed probe files and classroom-handoff-delayed-results artifacts. An abandoned native-clock experiment failed in initial OSD resource sampling; it is removed from the tracked test and retained separately.

Fresh protected checks and combined-main delivery remain required. Previously released folder and 320px annotation production checks, Cancel approval and external secret/OneDrive facts remain open independently.
