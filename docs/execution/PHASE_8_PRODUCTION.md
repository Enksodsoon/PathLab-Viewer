# Phase 8 — Pilot, Qualification, Activation, and Suspension

Phase 8 runs a supervised bounded Institution pilot, emits a separate pilot lifecycle receipt, reviews every current gate, aggregates a no-waiver Qualification Claim and only then permits a distinct two-person activation ceremony. All tasks inherit [README](./README.md).

## P8-T01 — Ratify the supervised pilot charter

- **Outcome:** Sign the exact pilot Institution/release/profile/host/current deployment-selection head, bounded participant/data/duration scope, non-clinical or already-deidentified fixtures, consent/privacy/support/incident team, monitoring, deletion, rollback and measurable admission/exit criteria.
- **Depends on:** `P7-T20=SUCCESS` and current `P7-T12=DEPLOYED`, with its matching `DeploymentSelectionReceipt(SELECTED)` head current.
- **External prerequisites:** label=P8-EXT-PILOT-INSTITUTION; kind=HUMAN_AUTHORITY; requires=INSTITUTION_AND_ACCOUNTABLE_TEAM_COMMITTED; accountable=Pilot Governance Owner; validity=exact candidate charter and full pilot window; evidence=signed immutable Pilot Institution Commitment Receipt | label=P8-EXT-PILOT-PARTICIPANTS; kind=HUMAN_AUTHORITY; requires=NONZERO_APPROVED_PARTICIPANT_COHORT_RESERVED; accountable=Pilot Institution Owner; validity=exact consent scope roles and full pilot window; evidence=signed immutable Pilot Participant Reservation Receipt | label=P8-EXT-PILOT-DATA; kind=DATA_OR_CORPUS; requires=NONCLINICAL_OR_ALREADY_DEIDENTIFIED_FIXTURES_APPROVED; accountable=Pilot Data Owner; validity=exact dataset roots privacy class and pilot window; evidence=signed immutable Pilot Data Admission Receipt
- **Read first:** Production Qualification Pilot and Activation, Delivery State Ledger.
- **Change surface:** immutable pilot manifest/governance approvals only.
- **Implement:** none; ratify and sign the exact bounded charter, counters, support, rollback and cleanup terms without product, configuration, deployment-selection or lifecycle mutation.
- **Prove:** named accountable people; explicit non-zero minimum unique human participants, elapsed duration, supported pilot roles, representative workflows per claimed capability, attempted/successful transactions and data exposure; participant/data ceilings; current evidence heads; support/escalation; safe suspension/rollback and cleanup. Each floor has accountable Institution rationale and a machine-checkable counter.
- **Stop/hand off:** zero admitted participants, zero complete representative journeys, an omitted claimed workflow/role, clinical-purpose use, unbounded scope, missing accountable team or candidate change blocks admission.
- **Unlocks:** `P8-T02`.

## P8-T02 — Run pilot preflight and admission

- **Outcome:** Verify deployed digest/config/migrations/host/target/client/current-selection equality, current backup/cost/capacity/security/standards evidence, isolated rollback mechanics and complete operational readiness, then emit a typed Pilot Admission Gate Result before one participant is admitted.
- **Depends on:** current exact-subject `P8-T01=SUCCESS` and `P7-T20=SUCCESS`; every `P7-G01`–`P7-G20` parent gate result current exact-subject `=SUCCESS`; and the current matching `DeploymentSelectionReceipt(SELECTED)` head.
- **External prerequisites:** label=P8-EXT-PILOT-PREFLIGHT-HOST; kind=HARDWARE; requires=ISOLATED_ROLLBACK_TARGET_AND_DECLARED_CLIENTS_RESERVED; accountable=Pilot Operations Owner; validity=exact candidate and preflight window; evidence=signed immutable Pilot Preflight Resource Receipt | label=P8-EXT-PILOT-OPERATORS; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_OPERATORS_RESERVED; accountable=Pilot Operations Owner; validity=preflight and full pilot window; evidence=signed immutable Pilot Operator Reservation Receipt
- **Read first:** pilot manifest, candidate fingerprint/invalidation and operator runbooks.
- **Change surface:** preflight/admission evidence only.
- **Implement:** none; execute exact-subject preflight, synthetic transactions and isolated rollback and emit the typed admission result without production routing or product mutation.
- **Prove:** every head/currentness/equality check, synthetic user journey, alerts/on-call/backup/restore and rollback execution in an isolated non-production target with zero production routing change.
- **Stop/hand off:** any deployment-selection-head change, including a real production reversion, invalidates P6-T30 admission and requires a new P6-T30 before pilot re-admission; drift, stale gate, unavailable target/operator, unresolved Critical/High or missing rollback returns gate result `NEGATIVE` or `NOT_EVALUABLE`, never an unregistered `READY`/`NO_GO` state.
- **Unlocks:** `P8-T03`.

## P8-T03 — Start the bounded pilot

- **Outcome:** Admit only approved participants/data to the exact candidate, emit immutable start evidence including every non-zero exposure floor/counter and begin continuous operational/incident/cost/capacity/backup/standards/deletion observations.
- **Depends on:** current exact-subject `P8-T02=SUCCESS` with the same current `DeploymentSelectionReceipt(SELECTED)` head.
- **External prerequisites:** label=P8-EXT-PILOT-OPERATORS; kind=HUMAN_AUTHORITY; requires=NAMED_PRIMARY_AND_ALTERNATE_OPERATORS_PRESENT_AND_AUTHORIZED; accountable=Pilot Operations Owner; validity=exact pilot manifest and full pilot window; evidence=signed immutable Pilot Operator Reservation Receipt | label=P8-EXT-PILOT-PARTICIPANTS; kind=HUMAN_AUTHORITY; requires=APPROVED_COHORT_READY_FOR_ADMISSION; accountable=Pilot Institution Owner; validity=exact consent scope roles and full pilot window; evidence=signed immutable Pilot Participant Reservation Receipt | label=P8-EXT-PILOT-DATA; kind=DATA_OR_CORPUS; requires=APPROVED_FIXTURE_ROOTS_AVAILABLE; accountable=Pilot Data Owner; validity=exact dataset roots and full pilot window; evidence=signed immutable Pilot Data Admission Receipt
- **Read first:** pilot charter/runbook and last preflight receipt.
- **Change surface:** live pilot operation/evidence only; no feature or configuration edits.
- **Implement:** none; admit only approved participants/data, initialize frozen counters and start receipt-driven observations without feature, configuration or selection mutation.
- **Prove:** exact start tuple, participant/data boundary, floor counters at zero-before-admission, and active worker/receipt/alert progress.
- **Stop/hand off:** authority/privacy/data-loss/clinical boundary breach, positive required cost, Critical incident or evidence invalidation invokes defined safe suspension/rollback.
- **Unlocks:** `P8-T04`.

## P8-T04 — Monitor and operate the pilot

- **Outcome:** Continue pilot through separate low-context chats/heartbeat checks using immutable receipt cursors and notify only on material change, failure, completion or required human action.
- **Depends on:** active `P8-T03` pilot.
- **Read first:** pilot manifest, latest handoff/receipt cursor, open incidents only.
- **Change surface:** operational/pilot evidence and incident records.
- **Implement:** none; continue the exact pilot from immutable cursors, monitor every floor and incident and execute only chartered operations without product or configuration mutation.
- **Prove:** monotonic progress toward every minimum participant/duration/role/workflow/transaction/data floor, alerts/support/deletion/backup/cost/standards/capacity receipts, live process activity and no silent candidate/config change.
- **Stop/hand off:** dashboard RUNNING is insufficient; stopped worker, missing receipt, drift or incident follows frozen pilot disposition.
- **Unlocks:** `P8-T05` after planned duration/exit criteria.

## P8-T05 — Close pilot operations, incidents, and cleanup

- **Outcome:** After every ratified minimum exposure floor and exit criterion is met, stop admissions, drain modes, reconcile participant/data/use/support/evidence, classify and close incidents, delete/retain all pilot material under policy and produce a terminal cleanup/review report.
- **Depends on:** completed `P8-T03`/`P8-T04` operation.
- **External prerequisites:** label=P8-EXT-PILOT-REVIEWERS; kind=HUMAN_AUTHORITY; requires=ACCOUNTABLE_INCIDENT_PRIVACY_AND_DATA_OWNERS_AVAILABLE; accountable=Pilot Governance Owner; validity=exact pilot closure and review window; evidence=signed immutable Pilot Closure Reviewer Receipt
- **Read first:** charter exit/cleanup criteria and Delivery State pilot receipt requirements.
- **Change surface:** pilot/incident/deletion evidence only.
- **Implement:** none; stop admissions, drain, reconcile floors/incidents/data obligations and complete cleanup review without product, configuration or selection mutation.
- **Prove:** complete per-context cleanup/backup obligations, exact candidate/time/boundary, every incident disposition and accountable review. An ordinary resolved incident is acceptable only when the frozen charter says so and no invariant was breached.
- **Stop/hand off:** any authority/privacy/data-loss/clinical-boundary/required-positive-cost invariant breach makes this pilot `NEGATIVE` even if the incident is later closed and requires affected remediation/new candidate/new pilot. Any unmet minimum floor is `PARTIAL` or `NOT_EVALUABLE`; missing cleanup or unresolved critical incident blocks validation.
- **Unlocks:** `P8-T06`.

## P8-T06 — Emit the `PILOT_VALIDATED` lifecycle receipt

- **Outcome:** Perform only the adjacent `DEPLOYED -> PILOT_VALIDATED` transition for the exact release when the approved manifest, boundaries, incident review, expiry and accountable signatures are complete.
- **Depends on:** current exact-subject `P8-T05=SUCCESS`, `P7-T20=SUCCESS`, the unchanged complete `P7-T12` fingerprint, and its current matching `DeploymentSelectionReceipt(SELECTED)` head.
- **Read first:** Delivery State Ledger and Delivery Lifecycle Receipt schema.
- **Change surface:** Platform Governance lifecycle transition/evidence only.
- **Implement:** none; append only the adjacent `DEPLOYED -> PILOT_VALIDATED` lifecycle receipt for the exact subject and perform no product, configuration or deployment-selection mutation.
- **Prove:** exact prior head, no skip, subject equality, signatures, blockers empty and expiry/invalidation rules.
- **Stop/hand off:** pilot cannot substitute for capacity/security/restore/standards/zero-cash gates and does not qualify or activate.
- **Unlocks:** `P8-T07`.

## P8-T07 — Perform the final recency and claim-boundary review

- **Outcome:** Re-evaluate drift, expiry, zero-cash/capacity/security/backup/standards/clinical boundaries, pilot incidents and every mandatory gate head after the pilot.
- **Depends on:** current exact-subject `P8-T06=PILOT_VALIDATED` and `P7-T20=SUCCESS`; every `P7-G01`–`P7-G20` parent gate result current exact-subject `=SUCCESS`; and an unchanged complete `P7-T12` release fingerprint with its current matching `DeploymentSelectionReceipt(SELECTED)` head.
- **External prerequisites:** label=P8-EXT-FINAL-REVIEWERS; kind=HUMAN_AUTHORITY; requires=SECURITY_BACKUP_COST_STANDARDS_AND_CLAIM_OWNERS_RESERVED; accountable=Qualification Governance Owner; validity=exact post-pilot review window and candidate; evidence=signed immutable Final Review Authority Receipt
- **Read first:** Production Qualification complete gate register/decision rules.
- **Change surface:** read-only release/pilot-readiness gate evidence.
- **Implement:** none; re-evaluate recency, drift, incidents and claim boundaries from immutable heads and emit the review result without product, selection or evidence mutation.
- **Prove:** every gate remains current `SUCCESS`, tuple equality, no new cost/incident/finding/claim expansion and pilot receipt matches.
- **Stop/hand off:** stale/non-success/mixed input, new positive cost, reachable Critical/unmitigated High or invalidated claim blocks aggregation.
- **Unlocks:** `P8-T08`.

## P8-T08 — Aggregate the no-waiver Qualification Claim

- **Outcome:** Emit the adjacent `PILOT_VALIDATED -> PRODUCTION_QUALIFIED` Delivery Lifecycle Receipt by hash-comparing the complete immutable `P7-T12` release/deployment fingerprint and current deployment-selection head, while displaying the short release/profile/host/target/client/corpora tuple, accepted claim text, all current gate heads, expiry/review and invalidation rules.
- **Depends on:** `P8-T07=SUCCESS`.
- **Read first:** Delivery State Ledger `PRODUCTION_QUALIFIED`, Production Qualification.
- **Change surface:** qualification-controller execution and evidence only against already merged code; any controller/schema/code fix requires a new implementation task, candidate and affected requalification.
- **Implement:** none; hash-compare the complete mandatory set and append only the adjacent `PILOT_VALIDATED -> PRODUCTION_QUALIFIED` lifecycle receipt, excluding code, configuration, deployment-selection or gate-result mutation.
- **Prove:** complete mandatory set, exact equality, no waiver/stale/non-success/missing result and separate clinical-purpose status.
- **Stop/hand off:** claim cannot exceed evidence or imply activation, another host, HA, free forever, diagnosis/patient care or certification.
- **Unlocks:** `P8-T09`.

## P8-T09 — Execute the exact-candidate activation and suspension rehearsal

- **Outcome:** Against a non-production subject running the exact frozen controller code, prove immutable activation proposal, Operator initiation, independent Owner approval, WebAuthn freshness, expiry, changed-hash rejection, rollback, suspension and new-receipt reactivation.
- **Depends on:** `P2-T18C` `MERGED`, current exact-subject `P8-T08=PRODUCTION_QUALIFIED`, the unchanged complete `P7-T12` fingerprint, and its current matching `DeploymentSelectionReceipt(SELECTED)` head.
- **External prerequisites:** label=P8-EXT-ACTIVATION-REHEARSAL-PEOPLE; kind=HUMAN_AUTHORITY; requires=DISTINCT_OPERATOR_AND_OWNER_RESERVED; accountable=Activation Governance Owner; validity=exact rehearsal proposal and window; evidence=signed immutable Activation Rehearsal Authority Receipt | label=P8-EXT-ACTIVATION-REHEARSAL-TARGET; kind=HARDWARE; requires=ISOLATED_NONPRODUCTION_EXACT_CODE_TARGET_RESERVED; accountable=Release Infrastructure Owner; validity=exact controller hash and rehearsal window; evidence=signed immutable Activation Rehearsal Target Receipt
- **Read first:** Role Matrix Full-Surface activation pair, Activation Receipt schema, Delivery State suspension rules.
- **Change surface:** rehearsal manifest and evidence only; controller/CLI/UI/test changes require a new implementation task, candidate and affected requalification.
- **Implement:** none; execute activation, rejection, suspension and reactivation cases only on the isolated exact-code subject and never mutate production activation.
- **Prove:** same-person/service/stale-role/stale-step-up/>4-hour/changed tuple/missing rollback attacks; historical receipts stay append-only.
- **Stop/hand off:** rehearsal must not mutate production activation; any code/config fix invalidates the current candidate rather than being folded into this chat.
- **Unlocks:** `P8-T10`.

## P8-T10 — Perform the separate real two-person activation

- **Outcome:** A named human Operator identifies the exact deployed qualified tuple and an independent human Owner accepts the exact claims/review/rollback/suspension terms; emit Approval and Activation Receipts and only then `ACTIVATED`.
- **Depends on:** current exact-subject `P8-T08=PRODUCTION_QUALIFIED` and `P8-T09=SUCCESS`, the unchanged complete `P7-T12` fingerprint and its current matching `DeploymentSelectionReceipt(SELECTED)` head.
- **External prerequisites:** label=P8-EXT-ACTIVATION-OPERATOR; kind=HUMAN_AUTHORITY; requires=NAMED_OPERATOR_PRESENT_ROLE_CURRENT_WEBAUTHN_READY; accountable=Activation Governance Owner; validity=exact proposal and ceremony time; evidence=signed immutable Activation Operator Authority Receipt | label=P8-EXT-ACTIVATION-OWNER; kind=HUMAN_AUTHORITY; requires=INDEPENDENT_NAMED_OWNER_PRESENT_ROLE_CURRENT_WEBAUTHN_READY; accountable=Institution Owner; validity=exact proposal and ceremony time; evidence=signed immutable Activation Owner Authority Receipt
- **Read first:** exact Qualification Claim, Role Matrix and Activation Receipt.
- **Change surface:** production activation operation/evidence only.
- **Implement:** none; perform the separate two-person ceremony and append Approval/Activation Receipts only after exact checks, with no code, configuration or deployment-selection mutation.
- **Prove:** distinct current people, both WebAuthn step-ups <=5 minutes, proposal <=4 hours, exact head/tuple/claims/expiry/rollback and current prior state.
- **Stop/hand off:** Codex, service accounts or automation cannot impersonate either human. A rejection with every prerequisite still current leaves the release qualified but not active. On change or staleness, the historical `PRODUCTION_QUALIFIED` receipt remains immutable, its current validity becomes `INVALIDATED`, activation is rejected, and an effective-readiness view may show the last valid prerequisite only on a separate derived axis—never as a backward lifecycle transition.
- **Unlocks:** `P8-T11`.

## P8-T11 — Verify post-activation operation and suspension

- **Outcome:** Show the active receipt/claims/review date to operators, observe the defined production window and verify real trigger propagation, rollback readiness and append-only suspension behavior without manufacturing a destructive production incident.
- **Depends on:** `P8-T10=ACTIVATED`.
- **External prerequisites:** label=P8-EXT-ACTIVE-OPERATIONS; kind=HUMAN_AUTHORITY; requires=PRIMARY_AND_ALTERNATE_PRODUCTION_OPERATORS_RESERVED; accountable=Production Operations Owner; validity=exact active release and observation window; evidence=signed immutable Production Operator Reservation Receipt
- **Read first:** Delivery State suspension/reactivation rules and runbooks.
- **Change surface:** production observation/suspension evidence only.
- **Implement:** none; observe real operation and natural triggers, verify status/rollback presentation and append suspension evidence only when a real governed trigger occurs; do not manufacture a destructive incident.
- **Prove:** real health/evidence monitoring and status presentation match the pre-activation `P8-T09` trigger matrix; any naturally occurring expiry, invalidation, rollback or safety trigger appends `ACTIVATION_SUSPENDED`, names affected claims/safe state and requires new current Qualification/Activation Receipts.
- **Stop/hand off:** automatic or silent reactivation is prohibited; deliberately self-suspending the live release requires a separate explicitly approved production drill rather than being hidden in this verification task.
- **Unlocks:** `P8-T12` steady-state governance.

## P8-T12 — Operate recurring requalification and schedule mature zero-cash review

- **Outcome:** Schedule monthly patch/impact reviews, evidence expiry, backup/capacity/security/standards/cost checks and targeted requalification, and open `P8-T12A` only when an immediately preceding rolling 12-month accounting window and its immutable evidence are eligible for closure.
- **Depends on:** current exact-subject terminal `P8-T11=SUCCESS`.
- **External prerequisites:** label=P8-EXT-REQUALIFICATION-OPERATORS; kind=HUMAN_AUTHORITY; requires=NAMED_ONGOING_OWNERS_AND_ALTERNATES_RESERVED; accountable=Production Governance Owner; validity=current active release and recurring review horizon; evidence=signed immutable Requalification Operator Reservation Receipt
- **Read first:** Production Qualification invalidation and Zero-Cash claim limits.
- **Change surface:** governance schedule/heartbeat evidence and future remediation tasks.
- **Implement:** none; create and operate the bounded recurring review/heartbeat schedule and open separate remediation tasks on drift without automatically changing code, spend, qualification or activation.
- **Prove:** every drift/expiry opens targeted review; current status/claims update or suspend; supporting historical evidence remains auditable; mature Zero-Cash eligibility remains pending until `P8-T12A` independently verifies the full rolling window.
- **Stop/hand off:** this scheduling task emits no mature Zero-Cash result or claim; never treat the initial 90-day result as permanent, call the system free forever, or display a suspended release as active.
- **Unlocks:** continued bounded production operation and `P8-T12A` only when its exact prerequisites are current; no terminal “forever complete” state exists.

## P8-T12A — Close the mature rolling-12-month Zero-Cash result

- **Outcome:** Freeze one immediately preceding rolling 12-calendar-month window for the current active exact subject and emit one terminal mature Zero-Cash result after reconciling every account, tariff, tax, currency, allowance, invoice/provider statement, cash payment, workload and 12-month forward projection without a coverage gap or hidden required spend.
- **Depends on:** `P8-T12` `MERGED`; current exact-subject `P7-G19=SUCCESS`, `P7-T12=DEPLOYED` with an unchanged complete release fingerprint, `P8-T08=PRODUCTION_QUALIFIED`, `P8-T10=ACTIVATED`, and `P8-T11=SUCCESS`; current matching `DeploymentSelectionReceipt(SELECTED)` head, current exact-subject `ActivationReceipt(ACTIVATED)` head, and current ledger state `ACTIVATED`, all for the identical release/profile/host/account/tariff/workload tuple.
- **External prerequisites:** label=P8-EXT-MATURE-ZERO-CASH-STATEMENTS; kind=COST_OR_ALLOWANCE; requires=IMMUTABLE_STATEMENTS_COVER_IMMEDIATELY_PRECEDING_ROLLING_TWELVE_MONTHS_WITHOUT_GAP; accountable=Institution Finance Owner; validity=exact release host account tariff workload and frozen window-end tuple; evidence=signed immutable Mature Zero-Cash Cost Evidence Receipt
- **Read first:** Production Qualification Zero-Cash gate and decision rules, the current P7-G19 result, complete P6 cost ledger and the recurring-governance schedule.
- **Change surface:** read-only rolling-window statement/tariff/workload reconciliation, sanitized signed accounting evidence and terminal mature result only.
- **Implement:** none; freeze and aggregate immutable accounting heads and emit the terminal result without changing product, deployment selection, lifecycle, tariffs, workload, evidence or spend.
- **Prove:** under one frozen timezone/calendar, `window_start = window_end - P12M`; sorted immutable provider/invoice intervals have `min(coverage_start) <= window_start`, every `next.coverage_start <= prior.coverage_end`, and `max(coverage_end) >= window_end`, so their union covers every instant of `[window_start, window_end]`; an immutable, trusted-time-ordered selection/activation/Delivery-State/subject history covers every instant of that same closed interval and proves that the exact `DeploymentSelectionReceipt`, `ActivationReceipt(ACTIVATED)`, ledger projection and release/profile/host/account/tariff/tax/currency/allowance/workload tuple never changed; every PathLab-specific hardware/software/API/model/standard/support/domain/certificate/connectivity/utility obligation reconciles gross before credits; gross incremental charge, incremental cash payment and projected charge for the next 12 months under the frozen load are each exactly zero; contributed resources/labor remain separately disclosed; every closing fingerprint equals every dependency head.
- **Stop/hand off:** a missing/mutable/unverified statement or subject-history record, coverage gap, inactive instant, or stale or changed selection/activation/lifecycle/subject/account/tariff/workload head or tuple is `NOT_EVALUABLE`; any such head or tuple change resets mature-window eligibility from its effective trusted time, so an older accounting interval cannot be inherited by the new subject; positive gross charge, payment or projection, hidden mandatory spend, expiring allowance that makes the frozen projection positive, or claim expansion is `NEGATIVE`; this result supports only the named rolling window and never “free forever.”
- **Unlocks:** a current mature rolling-12-month Zero-Cash claim facet for this exact active subject and the next scheduled rolling review; no Delivery Lifecycle transition or perpetual claim follows.
