# One-Chat Task Index

This index is the smallest entry point for selecting work. The detailed phase files define 371 stable task or gate IDs. Every ID is a backlog item until its own current receipt proves a stronger Delivery State Ledger state.

## Current starting point

The next executable package is `P0-T01`: publish the ratified plan as the canonical review. It is the only task that may start from the planning branch. All later packages must begin only after their declared dependency state has been verified on the default branch.

Do not interpret the existence of this index, a plan commit, or a pull request as implementation. At plan publication, all 371 execution packages remain `PLANNED`.

## Task inventory

| Phase | IDs | Count | Detailed plan | Terminal milestone |
| --- | --- | ---: | --- | --- |
| 0 | `P0-T01`–`P0-T12`; `T01A`, `T02A`, `T03A`, `T05A`, `T09A`, `T10A`–`T10F` | 23 | [Canonical plan, freedom, rights, and supply chain](./PHASE_0_CANONICAL_AND_FREEDOM.md) | Authority, precedence, freedom, rights, toolchain, evidence, and zero-cash admission closed |
| 1 | `P1-T01`–`P1-T25`; `T11A`, `T22A` | 27 | [Resident runtime and context data plane](./PHASE_1_RESIDENT_FOUNDATION.md) | Resident clean-host and foundational recovery gate closed |
| 2 | `P2-T01`–`P2-T27`; `T02A`–`T02B`, `T16A`, `T18A`–`T18C` | 33 | [Trust, governance, operations, and protection](./PHASE_2_TRUST_AND_OPERATIONS.md) | Trust, protection, backup, release control, and foundational restore gates closed |
| 3 | `P3-T01`–`P3-T18` | 18 | [Imaging migration and re-admission](./PHASE_3_IMAGING.md) | Single SQLite authority cutover and Imaging requalification complete |
| 4 | `P4-T00`–`P4-T30`; `T06A`, `T12A`, `T13A`–`T13I`, `T19A`, `T20A`–`T20B`, `T22A`–`T22I`, `T29A`–`T29C` | 57 | [Learning foundation](./PHASE_4_LEARNING.md) | Catalog, Authoring, Live Learning, media, and Assessment vertical slice closed |
| 5 | `P5-T00`–`P5-T40`; `T01A`, `T02A`–`T02J`, `T04A`–`T04B`, `T09A`–`T09S`, `T15A`–`T15E`, `T20A`–`T20C`, `T25A`–`T25B`, `T26A`–`T26Q`, `T27A`, `T30A`–`T30C`, `T39A`–`T39E` | 109 | [Standards and specialist contexts](./PHASE_5_SPECIALIST_CONTEXTS.md) | Integration, credentials, EQA, Clinical Shadow, Research, and Edge closed |
| 6 | `P6-T01`–`P6-T36`; `T24A`, `T34A`–`T34D` | 41 | [Portability and complete operations](./PHASE_6_PORTABILITY_AND_RECOVERY.md) | Portability, full recovery, two 35-day cycles, and 90-day campaign closed |
| 7 | `P7-T01`–`P7-T20`; `P7-G01`–`P7-G20`; `G09A`–`G09B`, `G12A`–`G12B`, `G14A`–`G14B`, `G15A`–`G15D` | 50 | [Exact-release prequalification](./PHASE_7_PREQUALIFICATION.md) | Exact candidate soak, all gates, accessibility, and Golden Journey current `SUCCESS` |
| 8 | `P8-T01`–`P8-T12`; `T12A` | 13 | [Pilot, qualification, activation, and suspension](./PHASE_8_PRODUCTION.md) | Pilot, qualification, separate activation, suspension, and recurring review operating |
| **Total** | 341 task packages plus 30 exact-release gate/start/monitor/closure packages | **371** | [Traceability](./TRACEABILITY.md) | No compressed table task or hidden feature backlog remains |

## Selecting the next chat

1. Start at the lowest phase with unfinished work, then consult [Dependency Waves](./DEPENDENCY_WAVES.md) for packages that may safely proceed in parallel.
2. Choose one task ID only. Verify every `Depends on` receipt against the current default-branch commit and required lifecycle or gate state.
3. Open the matching phase file and read that one card. Do not load every other card into the new chat.
4. Paste the starter from [Fresh-Chat Task Template](./CHAT_TASK_TEMPLATE.md), replacing its placeholders with the selected ID, exact dependency commit, and evidence paths.
5. End the chat with the structured handoff in the template. A follow-on chat independently verifies the result.

To locate a card from PowerShell without loading a whole phase, run:

```powershell
rg -n -A 12 "^## P4-T24\b" docs/execution/PHASE_4_LEARNING.md
```

For a compact inventory of all defined IDs, run:

```powershell
rg -n -g "PHASE_*.md" "^## P[0-8]-(T|G)[0-9]+[A-Z]?\b" docs/execution
```

## Program serialization points

These milestones must not be silently distributed across chats:

- `P0-T01` publishes the plan before implementation branches begin; `P0-T01A` then marks contradictory legacy plans as baseline-only or superseded.
- `P0-T12` closes authority, precedence, rights, freedom, supply-chain, exact-toolchain, evidence-schema, and zero-cash prerequisites.
- `P3-T17` performs the one and only SQLite-to-PostgreSQL authority cutover after both Imaging and all learning import preparations are ready.
- `P6-T29` freezes the operated-campaign contract before candidate integration. `P7-T09`–`P7-T11` integrate, check, merge, and freeze exactly one default-branch candidate; `P7-T12` builds, deploys, and selects it without activating it.
- Only then may `P6-T30` start the irreducible 90-day operated campaign. `P6-T32` and `P6-T33` close two complete independent 35-day expiry cycles; `P6-T35` waits for 90 elapsed days and every covering provider statement, and `P6-T36` closes Phase 6.
- `P7-T13`–`P7-T14` operate and close the exact-candidate 14-day soak inside that 90-day interval. The exact-release gates run only against the same complete fingerprint and current deployment-selection head; `P7-G17` and `P7-G19` wait for `P6-T36`.
- `P7-G09`, `P7-G12`, `P7-G14`, and `P7-G15` have separate start/monitor/closure cards so their two-hour, four-hour, seven-day, and 24-hour intervals never retain a chat context or report `RUNNING` as success.
- `P7-T20` closes prequalification; it does not authorize a production pilot or activation.
- `P8-T03`–`P8-T06` run and close the supervised pilot. `P8-T08` may confer `PRODUCTION_QUALIFIED`; only the separate two-person `P8-T10` ceremony may confer `ACTIVATED`.

## External prerequisites to reserve early

These are dependencies, not implied repository capabilities: copyright and relicensing authority; brand and asset-rights review; exact ARM64 production and replacement hosts; an independent backup target and disconnected media; two-of-three recovery custodians; accountable operators and two qualified AI reviewers; physical supported clients and teacher devices; lawful official standards artifacts and independent conformance tools; 100 deidentified clinical cases; 100 physical Edge nodes; and a supervised pilot institution/team.

If a required resource is unavailable before evaluation, its task reports `BLOCKED`, gate execution `NOT_STARTED`, and no gate result. `NOT_EVALUABLE` applies only after the frozen evaluation actually ran but could not produce an evaluable result. The plan does not permit substituting synthetic evidence, reducing a threshold, or rewording the production claim.

## Claim boundaries

- Zero-Cash means a completed observed 90-day window and later rolling 12-month windows with zero gross incremental charge, zero payment, and zero projected gross incremental charge at the frozen load. It never means “free forever.”
- Scalability is an admitted, measured ladder that preserves the lightweight resident profile; projections do not replace physical capacity and recovery evidence.
- Clinical Shadow remains read-only, deidentified, and non-diagnostic.
- Teacher AI remains local to the teacher device, review-gated, bounded by deterministic fallbacks, and outside grading authority.
- TRACE-SIM remains outside production qualification and activation. This execution plan neither activates nor removes it.
