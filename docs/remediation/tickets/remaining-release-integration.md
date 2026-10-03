# Combined remaining release candidate

Status: candidate, not deployed. Base main: 0d11f2d7bfb8cd6a3c05f185bc3dd43ac8db8295.

Integrate the reviewed changes from PRs 281, 282, 283 and 284 with merge commits, preserving immutable inventory subjects and individual review history. No dependency source or notice-material inputs change during integration; receipts remain bound to ancestor implementation commits 3598ea7359bdbe57c57c9e59f945d233aa12145a and caeb2f90ca701ea042ae6dce1b1f52f84f786ebd.

The candidate includes: publication-aware menu qualification and bounded/redacted failure diagnostics; closed-output deployment recovery; three remaining OCI advisory pins and complete lock audit; obsolete annotation queue cancellation and old-workspace failure isolation. Upload cancellation shipped to main through PR 276 but is not deployed.

Local evidence: 28 dependency/software inventory regression passes; 29 focused annotation test passes; two held-response navigation scenarios pass across Chromium, Firefox, WebKit and mobile Chromium; deployment recovery regressions passed before integration. WebKit's fixture waits for workspace removal, since URL change alone precedes completed navigation.

Require all nine fresh combined functional/security checks, reviewed merge, exact-main checks, then protected deployment retaining Classroom=true, annotations=false, admin annotation canary=true. Verify terminal deployment success, deployed SHA, readiness, tiles, and authenticated persistence/failure paths. Do not cancel a deployment in maintenance or bypass its lock.

Keep unresolved facts separate: application secret rotation, OneDrive sharing/synchronization, specific permanent cleanup of the incomplete synthetic reservation, physical-device/native browser zoom qualification, production distinct-identity admissions and selected invitation expiry. Study activation remains gated. License admission is not inferred from vulnerability or inventory validation.

The integrated 1244da346ce17e72597fdb9a1cd8f798215d1260 head passed all nine checks (CI 37089243504, Security 37089243518). PR281 separately failed its route explorer with a Grid view / disabled-after-state-change outcome on the fallback route. The explorer restored that route without waiting for the synthetic Library card; Grid view itself has no disabled property. Add the missing server-data readiness check and include the observed label in disabled-state diagnostics, without allowing unexplored outcomes. The full real-backend route explorer then passed 29 route patterns in 366.3 seconds with zero skips, retries or unexpected results. This is a test-readiness repair, not a reproduced application defect. The first local attempt failed fixture setup after an editing encoding mistake; it was corrected before the passing receipt. Fresh exact-head CI is required after this follow-up.
