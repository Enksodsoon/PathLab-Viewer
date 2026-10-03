# Combined remaining release candidate

Status: candidate, not deployed. Base main: 0d11f2d7bfb8cd6a3c05f185bc3dd43ac8db8295.

Integrate the reviewed changes from PRs 281, 282, 283 and 284 with merge commits, preserving immutable inventory subjects and individual review history. No dependency source or notice-material inputs change during integration; receipts remain bound to ancestor implementation commits 3598ea7359bdbe57c57c9e59f945d233aa12145a and caeb2f90ca701ea042ae6dce1b1f52f84f786ebd.

The candidate includes: publication-aware menu qualification and bounded/redacted failure diagnostics; closed-output deployment recovery; three remaining OCI advisory pins and complete lock audit; obsolete annotation queue cancellation and old-workspace failure isolation. Upload cancellation shipped to main through PR 276 but is not deployed.

Local evidence: 28 dependency/software inventory regression passes; 29 focused annotation test passes; two held-response navigation scenarios pass across Chromium, Firefox, WebKit and mobile Chromium; deployment recovery regressions passed before integration. WebKit's fixture waits for workspace removal, since URL change alone precedes completed navigation.

Require all nine fresh combined functional/security checks, reviewed merge, exact-main checks, then protected deployment retaining Classroom=true, annotations=false, admin annotation canary=true. Verify terminal deployment success, deployed SHA, readiness, tiles, and authenticated persistence/failure paths. Do not cancel a deployment in maintenance or bypass its lock.

Keep unresolved facts separate: application secret rotation, OneDrive sharing/synchronization, specific permanent cleanup of the incomplete synthetic reservation, physical-device/native browser zoom qualification, production distinct-identity admissions and selected invitation expiry. Study activation remains gated. License admission is not inferred from vulnerability or inventory validation.
