# Platform repair checkpoint — 2026-09-05

This is an implementation and test checkpoint, not a signed lifecycle receipt or Full-Surface qualification. The accepted execution playbook still contains 371 packages. A change below does not complete every task card that it touches.

## Delivered for review

[PR #218](https://github.com/Enksodsoon/PathLab-Viewer/pull/218) merged as `da501ff9533e476e9ceff4278469260c144fee6d`. It corrects effective Caddy route ordering so internal admission/hooks and direct dynamic-tile paths are denied before proxy handling. A real isolated edge reproduced the prior bypass and verifies denial after the fix; the adapted-configuration validator protects that ordering in CI. Required checks passed before merge. Production deployment and verification are separate and remain outstanding at this checkpoint.

[PR #219](https://github.com/Enksodsoon/PathLab-Viewer/pull/219) contains independently separated repair commits:

- Shared database admission for login, recovery, and anonymous Desktop pairing; atomic pairing redemption; bounded periodic pairing expiry; streaming JSON limits with resumable binary upload exemptions.
- Terminal campaign reports for missing reports, timeout, worker failure, cancellation, and failed cleanup. A valid-looking health document cannot override a failed restoration command.
- Application and viewer recovery actions, private-slide sign-in return, scoped operator diagnostics, searchable paginated Classroom setup, timezone-correct setup, submission guards, and authenticated owner-based fresh-tab recovery.
- Migration `20260905_0027` records Classroom ownership. Ambiguous legacy ownership stays inaccessible rather than assigning a session to an arbitrary teacher. Global operator capacity inventory remains global.
- A disposable complete stack and real browser imaging/Classroom/security journeys, plus broader existing responsive browser coverage in CI.
- ADR 0132 and the versioned combined-capacity evidence foundation. Historical v2 evidence cannot qualify the new target. The v3 verifier never grants runtime admission or activation.

## Current local evidence

The integrated repair tree, including the approved UI restoration and merged edge fix, passed 826 backend tests with 19 environment/platform skips, 303 web unit tests, and all three real-stack browser tests. The capacity contract suite passed 396 tests with one skip. These commands exited successfully:

```text
python -m pytest tests/backend -q
pnpm --dir apps/web exec vitest run --maxWorkers=2
python scripts/run_fullstack_tests.py --pnpm <absolute-pnpm> --tusd <absolute-tusd> --caddy <absolute-caddy>
python -m pytest tests/load -q
```

The full-stack launcher reports success only after removing owned services and temporary storage. It does not target production. See [real-stack testing](./REAL_STACK_TESTING.md) for prerequisites and coverage boundaries. Earlier responsive browser validation passed 145 tests with three expected skips; current protected checks must validate the integrated head. PostgreSQL passed protected CI at repair commit `3792a12f875d2ec260de9fec26a2f92d30ac4205`; later heads require their own current check result.

Independent v3 review found and corrected five false-pass paths: insufficient reservation duration/bytes, an unbound receiver cohort, compounded accounting freshness, a reservation from the wrong allowance period, and impossible unique-learner counts. The reviewer independently passed all 132 v3 tests. These are synthetic protocol tests, not observed media delivery or capacity.

## Runtime and qualification boundary

Read-only inspection observed the existing 2-OCPU/12-GB host, six running services, readiness, watchdog, and release `a4b04786c15374b7ad3c40c3f9462724276e3404`. Those observations are a dated checkpoint, not ongoing health or restoration proof. The operating Classroom limit was 300; it was not raised by this repair.

The separate campaign `33936129541` reconciled the exact old run `33903034760` and passed its global Classroom-empty preflight before creating new fixtures. Its own worker failures and terminal restoration require separate current evidence. Neither campaign establishes a measured ceiling or qualifies the combined target. This repair task launched no production load campaign.

Still outstanding: native parser isolation from authority and secrets; complete capability/institution boundaries; receiver-observed live media and runtime allowance reservations; real Assessment and specialist journeys; full accessibility/device testing; clean-host install/recovery and independent backup; 90-day campaigns; and the remaining dependency-ordered platform roadmap. The security inventory, scanners, and control verification remain distinct. No comprehensive ASVS or WCAG qualification is claimed.

The 3,000-learner, 60-minute combined target remains unmet. A short run or a configured limit of 300 is not a qualified fallback. TRACE-SIM remains excluded, and no production qualification or activation is granted here.
