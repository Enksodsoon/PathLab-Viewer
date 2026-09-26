# Classroom dispatch boundary

Labels: wayfinder:ticket
Status: in progress

## Dependency and reproduction

PRs267 and268 are merged. Main9fa4a66 has eight successful deployment-required checks; its browser matrix has208 passes, three skips and one failure. Production deployment is blocked by that exact-head failure.

The retained mobile Chromium native OSD trace proves a third local presenter POST about65ms after a control event, before the authoritative control snapshot request completed. Its viewport remains the local home field; the remote .7/.3 field event occurs later. This is queued traffic crossing an unresolved control handoff, rather than remote viewport echo.

## Repair and verification

Check current authorization, live state and snapshot readiness at dispatch, preserving existing pointer/control semantics, server authorization and bounded sender cadence. Trace every sender caller; add a deterministic queued-handoff regression and bounded native browser repeats. Fresh reviewed PR, required checks, merged-main checks, protected deployment and authenticated production qualification remain required.

Local repair is complete. All three queued sender callers were traced. Current-ref dispatch guards preserve live phase, snapshot readiness, control lease, guide/drawing/tool state and source session identity. Pointer publication remains allowed while a participant controls the field. The dedicated actual-page suite and updated performance contracts pass16cases; final native OSD matrix passes all4browser targets. Broader Classroom tests and bounded mobile repeats are running.

Final source tracing confirms Teacher presenter POST intentionally reclaims participant control and returns200 with presenterSequence. A queued stale Teacher field can therefore reclaim unexpectedly; this is not an authorization bypass. The earlier403 native fixture is retained only as attempted-request evidence, not real server-policy evidence. The corrected fixture models actual reclaim; final corrected native qualification passed all4projects plus3mobile repeats. The full Classroom scope passed96tests, and the mobile repeat passed3cases.

Final checks:96Classroom unit tests passed; corrected native OSD/synthetic transport matrix4/4passed39.3s and mobile3/3passed23.5s; lint and TypeScript pass. Exact-head protected release checks remain required.

The bc36d0b WebKit failure was a fixture timing error: a legitimate presenter request started during an awaited dynamic import before the control event. The fixture now binds the native viewer first and counts browser dispatch attempts synchronously at the handoff boundary. All four browser targets passed three repetitions each (12/12). Removing the dispatch guard through test-only compiled response interception produced the expected failure; the exact fixture was restored. Both native viewers assert slide 2 tile sources. Product code remained unchanged. These checks use real native viewers with synthetic transport; protected CI and production verification remain pending.
