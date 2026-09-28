# Independent hardening review

Review base `cf0d2d2` plus explicitly identified repairs. All 328 source identities were reviewed as 125 exact canonical groups; classifications count mechanisms, not bugs. The disposition names below preserve the audit-time state. The seven repairs shipped in PR 270 and deployed at `3cb26bc` after exact-main checks.

| Disposition | Canonical groups |
|---|---:|
| justified-non-applicable | 114 |
| actual-defect-repaired-local | 7 |
| upstream-addressed | 3 |
| substantive-unresolved-work | 1 |

Seven native-proven mechanisms were repaired: SQLite purge-task failure, rejected IndexedDB open, Study pseudonym collision, Classroom expiry read/grant race, Library stale-cache tree/breadcrumb loops, invitation modal keyboard escape, and Study delivery after owner trash. Each proof and scope is recorded below. No currently proven unrepaired product mechanism remains in these 125 groups.

One external substantive gap remains: whether any live database/WAL/data directory is synced by OneDrive. Operator confirmation is required. Exact-main PostgreSQL and protected deployment checks passed at `3cb26bc`; [signed-in synthetic production checks](PRODUCTION_CLOSURE_QA.md) cover selected Library, upload and Classroom paths. Other production behaviors, physical devices and external credential validity remain separate evidence.

## account.password-input-clearing

Disposition: **justified-non-applicable**.

84-100 clearSecrets on validation errors deliberately clears unsaved values before any changePassword call. This is usability policy, not persisted credential loss.

Affected current paths/callers: `apps/web/src/components/AccountSecurityDialog.tsx`.

Source identities: `BUG_REPORT.md:12675`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.boolean-degenerate

Disposition: **justified-non-applicable**.

toPolygon>=3 closes rings; fromMultiPolygon filters<3. Actual trusted polygon-clipping output fixture needed before malformed-result claim.

Affected current paths/callers: `apps/web/src/annotations/booleanCore.ts`.

Source identities: `BUG_REPORT.md:1468`, `BUG_REPORT.md:8026`, `BUG_REPORT.md:12114`, `docs/reports/BUG_REPORT_CODEX.md:1434`, `docs/reports/BUG_REPORT_CODEX.md:7992`, `docs/reports/BUG_REPORT_CODEX.md:12080`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:673`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:757`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.csv-orphan-layer

Disposition: **justified-non-applicable**.

1412 looks up layer by annotation FK; supported layer delete preserves rows/history rather than orphan. No supported request producing missing parent shown; corrupted data fallback separate.

Affected current paths/callers: `server/wsi_viewer/annotations.py`.

Source identities: `BUG_REPORT.md:10976`, `docs/reports/BUG_REPORT_CODEX.md:10942`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.draft-open-retry

Disposition: **actual-defect-repaired-local**.

Actual Chromium/native IndexedDB production storage class: abort first native upgrade once; initial and same-instance retry AbortError, exactly1 open; new instance succeeds. Workspace419-423 services memo omits resetKey, so Retry retains rejected storage promise. Mounted-slide draft save/ACK cannot recover; server annotations remain usable. Proposal reset rejected cached promise and close late successful blocked opens. No product patch yet.
Authorized repair clears only same rejected attempt and closes late blocked success. Native Chromium upgrade abort red1/green1 same-instance recovery; injected blocked notification + native success/delete proves late handle closure. Targeted ESLint clean.

Affected current paths/callers: `apps/web/src/annotations/drafts.ts`.

Source identities: `BUG_REPORT.md:2553`, `docs/reports/BUG_REPORT_CODEX.md:2519`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:339`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.export-ring-normalization

Disposition: **justified-non-applicable**.

1305 appends firstpoint; closed input can duplicate terminal coordinate. Current exporter produces closed ring, not automatically invalid GeoJSON. Actual consumer interoperability fixture needed before canonical endpoint normalization.
Exporter closes GeoJSON rings; duplicate terminal coordinate alone is not invalid ring or actual consumer failure. Endpoint normalization optional interoperability, no required geometry change.

Affected current paths/callers: `server/wsi_viewer/annotations.py`.

Source identities: `BUG_REPORT.md:6624`, `docs/reports/BUG_REPORT_CODEX.md:6590`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.first-vertex-editor

Disposition: **justified-non-applicable**.

2419 First vertex label edits index0 deliberately; geometry.ts requirePoints24 and server annotations95/121 enforce nonempty minimum2/3. Arbitrary vertex choice is feature expansion.

Affected current paths/callers: `apps/web/src/annotations/AnnotationWorkspace.tsx`.

Source identities: `BUG_REPORT.md:13016`, `docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md:299`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.gesture-buffer-limit

Disposition: **justified-non-applicable**.

Construction points grow until completion, geometry requirePoints rejects>8192 before store bound calculations. Early gesture cap/feedback can improve UX/resource limits, but stack-overflow persisted shape allegation blocked; actual oversized native gesture workload qualification absent.
Current geometry/store reject>8192 before bounds spread, preserving admitted shape limit. Native oversized gesture crash absent; early point cap/feedback optional UX/stress qualification.

Affected current paths/callers: `apps/web/src/annotations/AnnotationOverlay.ts`.

Source identities: `BUG_REPORT.md:3552`, `docs/reports/BUG_REPORT_CODEX.md:3518`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.history-affordance

Disposition: **upstream-addressed**.

2300-2308 Revision history has onClick browseRevisions plus revision browser/restore. Historical idle-button claim no longer current.

Affected current paths/callers: `apps/web/src/annotations/AnnotationWorkspace.tsx`.

Source identities: `BUG_REPORT.md:12927`, `docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md:246`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.import-order-collision

Disposition: **justified-non-applicable**.

1514-1523 rejects duplicate incoming layerIDs/orders;1629-1632 retains explicit imported order alongside existing layers. List1251 adds created_at tie-break. Relative reindexing is new ordering UX policy.

Affected current paths/callers: `server/wsi_viewer/annotations.py`.

Source identities: `BUG_REPORT.md:11197`, `docs/reports/BUG_REPORT_CODEX.md:11163`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.tombstone-retention

Disposition: **justified-non-applicable**.

delete_layer326 checks ANY row before purge332; annotations.py904-919 bounds expired tombstone purge,30day history. Nonexpired history protection intentional. ONLY expired tombstones may still409 until another mutation purges: native boundary fixture pending, not automatic purge-policy change.
Actual HTTP expired-only layer delete409 reproduced. Docs ADMIN_ANNOTATIONS.md54-56 explicitly preserves persisted tombstones until later successful write, at most100/write. Layer delete requires physically empty layer. >100 naive prepurge409 rolls back/no progress; cascade would violate bound, partial-ACK adds new semantics. Parent confirmed preserve contract; optional prune workflow distinct, no mandatory defect.
Native HTTP expired-only layer delete returns409. docs/architecture/ADMIN_ANNOTATIONS.md54-56 explicitly specifies30-day retention and at most100 persisted tombstones purged on a later write. Purge100 then409 rolls back; CASCADE of >100 breaks bound. Parent agreed preserve persisted-empty deletion and bounded cleanup; explicit prune workflow remains optional feature. No annotation product change.

Affected current paths/callers: `server/wsi_viewer/annotation_routes.py`.

Source identities: `BUG_REPORT.md:6391`, `BUG_REPORT.md:6965`, `BUG_REPORT.md:8812`, `BUG_REPORT.md:8921`, `docs/reports/BUG_REPORT_CODEX.md:6357`, `docs/reports/BUG_REPORT_CODEX.md:6931`, `docs/reports/BUG_REPORT_CODEX.md:8778`, `docs/reports/BUG_REPORT_CODEX.md:8887`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotation.trash-contract

Disposition: **justified-non-applicable**.

69-74 returns persisted slide regardless trash; routes require active owner/admin. Uniform read/mutation trash policy requires restore/history contract, not inferred privilege bypass.
Authorized owner/admin inspection of persisted annotations remains available during trash recovery. No public tile authorization bypass or documented blanket trash-read denial is established; uniformly denying recovery/history would change the current contract.

Affected current paths/callers: `server/wsi_viewer/annotation_routes.py`.

Source identities: `BUG_REPORT.md:11015`, `docs/reports/BUG_REPORT_CODEX.md:10981`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## annotation.viewport-count

Disposition: **justified-non-applicable**.

getItems only198 service wrapper,644 reconcile and730 load; viewer viewport use1289 fits bounds. No getItems in pan handler, so historical per-pan count storm lacks this supported caller.

Affected current paths/callers: `apps/web/src/annotations/AnnotationWorkspace.tsx`.

Source identities: `BUG_REPORT.md:11108`, `docs/reports/BUG_REPORT_CODEX.md:11074`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotations.ack-fail-closed

Disposition: **justified-non-applicable**.

Acknowledgement callback awaited before dropping inFlight/advancing version; failure marks ANNOTATION_ACKNOWLEDGEMENT_FAILED and retains edits. Deliberate durable recovery requirement; silent batch drop weakens it. Draft open poisoned retry separately proven/repaired, not generic ACK-contract failure.

Affected current paths/callers: `apps/web/src/annotations/autosave.ts`.

Source identities: `BUG_REPORT.md:4457`, `BUG_REPORT.md:8777`, `BUG_REPORT.md:11646`, `docs/reports/BUG_REPORT_CODEX.md:4423`, `docs/reports/BUG_REPORT_CODEX.md:8743`, `docs/reports/BUG_REPORT_CODEX.md:11612`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:944`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotations.client-error-recovery

Disposition: **justified-non-applicable**.

Nonretryable4xx stops/retains batch and exposes error;409 conflict explicit choices. Fix auth/layer/input cause before Retry/reload; blindly discarding rejected mutations causes edit loss.

Affected current paths/callers: `apps/web/src/annotations/autosave.ts`.

Source identities: `BUG_REPORT.md:7411`, `docs/reports/BUG_REPORT_CODEX.md:7377`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotations.close-durability-window

Disposition: **justified-non-applicable**.

845-855 draft debounce250ms;cleanup cancels timer. Unsaved edits can disappear if browser terminates before persistence. Immediate-draft/navigation-guard UX contract qualification remains, not falsely committed Saved data loss.
Visible unsaved mutations debounce local250ms and server independently; termination before persistence does not claim committed Saved status. Immediate persistence/navigation guard optional UX contract, not committed data loss.

Affected current paths/callers: `apps/web/src/annotations/AnnotationWorkspace.tsx`.

Source identities: `BUG_REPORT.md:3668`, `docs/reports/BUG_REPORT_CODEX.md:3634`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## annotations.trashed-admin-policy

Disposition: **justified-non-applicable**.

get_slide69-74 lacks trash rejection but each route depends authorized admin/CSRF. Existing owner inspection/history contract must specify mutation behavior; no outsider disclosure.
Owner/admin authorization and CSRF remain required. A stricter trash mutation policy is an optional lifecycle change, not an evidenced missing authorization check.

Affected current paths/callers: `server/wsi_viewer/annotation_routes.py`.

Source identities: `BUG_REPORT.md:3216`, `docs/reports/BUG_REPORT_CODEX.md:3182`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:437`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## auth.account-throttle

Disposition: **justified-non-applicable**.

648-659 shared admission checksIP+normalizeduser before password hash; admission policies5/5min/global1000. Subject lockout tradeoff intentional anti-stuffing resource policy; old thread-local throttle obsolete.

Affected current paths/callers: `server/wsi_viewer/main.py`.

Source identities: `BUG_REPORT.md:2166`, `docs/reports/BUG_REPORT_CODEX.md:2132`, `docs/reports/DEEP_SYSTEM_BUG_AUDIT.md:254`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:304`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## auth.operator-recovery-instructions

Disposition: **justified-non-applicable**.

222 operator CLI instruction contains no credential; host/container authority still required.

Affected current paths/callers: `apps/web/src/components/AuthPanel.tsx`.

Source identities: `BUG_REPORT.md:928`, `docs/reports/BUG_REPORT_CODEX.md:894`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:136`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## auth.verification-length

Disposition: **justified-non-applicable**.

16,50-59: verification caps1024 while new passwords cap128; invalid hashes fail closed. Password length does not set Argon2 work parameters.

Affected current paths/callers: `server/wsi_viewer/security.py`.

Source identities: `BUG_REPORT.md:3608`, `docs/reports/BUG_REPORT_CODEX.md:3574`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## capacity.bounded-admission

Disposition: **justified-non-applicable**.

Perrole pools/maxoverflow0/timeouts plus Classroom mutation gate503/RetryAfter preserve frozen resource limits. Unmeasured claimed saturation is not authorization to enlarge pools.

Affected current paths/callers: `server/wsi_viewer/database.py`.

Source identities: `BUG_REPORT.md:6861`, `docs/reports/BUG_REPORT_CODEX.md:6827`, `docs/reports/DEEP_SYSTEM_BUG_AUDIT.md:308`, `docs/reports/DEEP_SYSTEM_BUG_AUDIT.md:688`, `docs/reports/FULL_SYSTEM_QA_REPORT.md:217`, `docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md:48`, `docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md:57`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:968`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.control-expiry-transaction

Disposition: **actual-defect-repaired-local**.

Actual native SQLite/validHTTP barrier paused student GET after expired row read, teacher freshgrant200, staleGET200 cleared new lease/rolledback epoch. Native regression red1/green1+existing stalelease2pass. Authorized CAS exact observed epoch/stateVersion/participant/lease/deadline refreshes loser and suppresses stale publish; current successful transition commit before event. No live PostgreSQL execution claim.

Affected current paths/callers: `server/wsi_viewer/classroom_routes.py`.

Source identities: `BUG_REPORT.md:7746`, `docs/reports/BUG_REPORT_CODEX.md:7712`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.control-snapshot-burst

Disposition: **justified-non-applicable**.

314 control event requests authoritative recover;shared reconciler coalesces requests/3stale bound. Fanout needed lease rights; no current60client outage measurement, resource expansion declined.

Affected current paths/callers: `apps/web/src/pages/ClassroomStudentPage.tsx`.

Source identities: `docs/reports/DEEP_SYSTEM_BUG_AUDIT.md:764`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.grace-retirement

Disposition: **justified-non-applicable**.

16 reconnect grace60s; stale reservations completed only after DB participant deletion. Old retired token fails intentionally; new join can acquire identity once seat free. Longer identity preservation is lifecycle policy.

Affected current paths/callers: `server/wsi_viewer/classroom_hub.py`.

Source identities: `BUG_REPORT.md:7565`, `docs/reports/BUG_REPORT_CODEX.md:7531`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.hub-terminal-history

Disposition: **justified-non-applicable**.

888-932 clear_session removes live maps but retains terminal UUID and event-sequence history. close clears terminal set. Safe compaction must prove ended-room denial and quantify lifetime cardinality.
Retained ended-session IDs reject subsequent stale admission; sequence history preserves event identity. No measured process-lifetime exhaustion exists. Pruning requires a supported resumption/denial policy and is not a mandatory repair.

Affected current paths/callers: `server/wsi_viewer/classroom_hub.py`.

Source identities: `BUG_REPORT.md:3508`, `BUG_REPORT.md:5742`, `docs/reports/BUG_REPORT_CODEX.md:3474`, `docs/reports/BUG_REPORT_CODEX.md:5708`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## classroom.invite-modal-focus

Disposition: **actual-defect-repaired-local**.

95-119 InviteDialog div aria-modal, autofocus Close; no native showModal/inert/trap/restore. Concrete keyboard/background modality proof still needed; accessibility work candidate retained.
Valid resumed preview native Chromium keyboard proof: Close initially focused but Tab traversal reaches background DOM controls outside aria-modal div (RED). Authorized repair uses existing AccountSecurityDialog native showModal/close cleanup pattern, explicit Close focus, captured connected opener focus restore and native cancel callback. Native Chromium/Firefox/WebKit/mobileChromium4/4 passed26.7s: keyboard open, both Tab boundaries, background programmatic focus denied, Escape and Close unmount, opener restored. Browser chrome/body traversal is allowed; background DOM controls remain inert. No changes to teaching/viewer logic.

Affected current paths/callers: `ClassroomTeacherPage preview/review InviteDialog`; `ClassroomTeacherPage live InviteDialog`.

Source identities: `BUG_REPORT.md:3576`, `docs/reports/BUG_REPORT_CODEX.md:3542`.

Next step: Local native keyboard matrix qualified; protected exact-head gates/deployment owned by parent.

## classroom.join-pressure-policy

Disposition: **justified-non-applicable**.

1259-1278 bounded queue wait+mutation lock,503 RetryAfter. Invalid credential lookup active/live/indexed. IP policy needs authorized workload evidence; reported starvation unproved.

Affected current paths/callers: `server/wsi_viewer/classroom_routes.py`.

Source identities: `BUG_REPORT.md:2248`, `docs/reports/BUG_REPORT_CODEX.md:2214`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:697`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.pool-telemetry-sorting

Disposition: **justified-non-applicable**.

249 deque maxlen2048;433 sorts bounded sample for telemetry in sync dependency. No measured starvation; periodic aggregation optional optimization declined as mandatory repair.

Affected current paths/callers: `server/wsi_viewer/main.py`.

Source identities: `docs/reports/FULL_SYSTEM_QA_REPORT.md:195`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.prewarm-shutdown-contract

Disposition: **justified-non-applicable**.

149-158 close clears pending,cancels/awaits task, removes loop; request130-142 captures current loop. Late request after native lifecycle shutdown remains unsupported unless a surviving caller is proved.

Affected current paths/callers: `server/wsi_viewer/classroom_prewarm.py`.

Source identities: `BUG_REPORT.md:12556`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.restart-seat-reservation

Disposition: **justified-non-applicable**.

485-519 explicitly preserves persisted live member across restart before current-epoch reconnect. Grace retirement requires current-epoch presence evidence, preventing stolen seat. Forced startup eviction conflicts current lifecycle test.

Affected current paths/callers: `tests/backend/test_classroom.py`.

Source identities: `BUG_REPORT.md:9548`, `docs/reports/BUG_REPORT_CODEX.md:9514`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.roster-failure

Disposition: **justified-non-applicable**.

471-480 roster callback catches failure and resolves after visible handleAdminFailure. Later stream-ready/roster event retries; isolated transient/no-event drift needs actual consumer proof.
Current roster notify always schedules even duplicate versions; it has no last-processed-version suppression. Teacher callback catches and displays errors; subsequent roster notifications and stream-ready reconciliation retry. Autonomous retry without any subsequent event is optional resilience, not the alleged permanently poisoned version.

Affected current paths/callers: `apps/web/src/pages/ClassroomTeacherPage.tsx`.

Source identities: `BUG_REPORT.md:5914`, `BUG_REPORT.md:12155`, `docs/reports/BUG_REPORT_CODEX.md:5880`, `docs/reports/BUG_REPORT_CODEX.md:12121`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:549`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## classroom.roster-query-plan

Disposition: **justified-non-applicable**.

1595-1606 participant session token/alias uniqueness and session presence index; scoped roster keyset/limit. Severe global sequential-scan claim not proved by FK alone; workload index tuning optional.

Affected current paths/callers: `server/wsi_viewer/models.py`.

Source identities: `BUG_REPORT.md:12313`, `docs/reports/BUG_REPORT_CODEX.md:12279`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.snapshot-retry

Disposition: **justified-non-applicable**.

31-39 bounds stale responses3 before apply; finally resets inFlight permitting later requests. Unlimited automatic retries are not promised.

Affected current paths/callers: `apps/web/src/classroom/snapshotReconciler.ts`.

Source identities: `BUG_REPORT.md:5885`, `BUG_REPORT.md:9698`, `BUG_REPORT.md:12188`, `docs/reports/BUG_REPORT_CODEX.md:5851`, `docs/reports/BUG_REPORT_CODEX.md:9664`, `docs/reports/BUG_REPORT_CODEX.md:12154`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.storage-persistence-request

Disposition: **justified-non-applicable**.

63 requests storage.persist deliberately and returns grant; passive persisted query changes durable notebook qualification.

Affected current paths/callers: `apps/web/src/classroom/notebook.ts`.

Source identities: `BUG_REPORT.md:3648`, `docs/reports/BUG_REPORT_CODEX.md:3614`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.teacher-attachment-refresh

Disposition: **justified-non-applicable**.

187-192 optional attachment detach/attach independent viewer instance lifecycle. Teacher classroom setup/resume state not every roster/pointer event; callback churn != full viewer recreation.

Affected current paths/callers: `apps/web/src/components/OpenSeadragonViewer.tsx`.

Source identities: `docs/reports/DEEP_SYSTEM_BUG_AUDIT.md:784`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## classroom.teacher-stream-error-ui

Disposition: **justified-non-applicable**.

EventSource effect reconnects roster on stream-ready but no error listener observed. Explicit offline feedback needs UX qualification; not proven permanent stale data.
Native EventSource reconnect plus stream-ready roster reconciliation is the current behavior. Explicit offline status is an optional UX enhancement; no permanent stale-data reproduction supports mandatory repair.

Affected current paths/callers: `apps/web/src/pages/ClassroomTeacherPage.tsx`.

Source identities: `BUG_REPORT.md:3678`, `BUG_REPORT.md:6587`, `docs/reports/BUG_REPORT_CODEX.md:3644`, `docs/reports/BUG_REPORT_CODEX.md:6553`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## classroom.terminated-participant-token

Disposition: **justified-non-applicable**.

require_live_classroom rejects ended/revoked state before live mutation; persisted participant credential can support review. Blanket token revocation alters review policy, not existing live bypass.

Affected current paths/callers: `server/wsi_viewer/classroom_routes.py`.

Source identities: `BUG_REPORT.md:12249`, `docs/reports/BUG_REPORT_CODEX.md:12215`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## config.production-secret-validation

Disposition: **justified-non-applicable**.

Production validator rejects combined role, short/placeholder keys and insecure cookies; Classroom singleton and Assessment PostgreSQL/identity enforced. Explicit development allowances do not establish a production bypass.

Affected current paths/callers: `server/wsi_viewer/config.py`.

Source identities: `BUG_REPORT.md:3259`, `docs/reports/BUG_REPORT_CODEX.md:3225`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:444`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## conversion.color-profile

Disposition: **justified-non-applicable**.

No actual profile inventory or fidelity receipt. Absence cannot justify invented sRGB. Source profile/pixel semantics and measured fixture required before transformation.
Missing source ICC cannot justify invented sRGB/clinical fidelity. Current converter transforms only present ICC profiles. Without measured source/pixel fixture no forced profile repair is justified.

Affected current paths/callers: `server/wsi_viewer/conversion.py`.

Source identities: `docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md:70`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## conversion.native-sandbox

Disposition: **justified-non-applicable**.

18 USER pathlab UID10001 and pinned/hashes native dependencies. Additional native parser sandbox requires declared threat model and actual parser exploit/containment fixture; no public RCE proof.
Container runs UID10001 with pinned hashed native dependencies. Additional parser isolation is defense in depth requiring an explicit threat model; no reachable parser exploit or broken existing isolation contract was established.

Affected current paths/callers: `deploy/Dockerfile.backend`.

Source identities: `BUG_REPORT.md:580`, `docs/reports/BUG_REPORT_CODEX.md:546`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:854`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## conversion.sequential-thumbnail-read

Disposition: **justified-non-applicable**.

156-180 sequential native image produces DZI then releases image and reloads thumbnail. Added read is true; memory/fidelity/latency benchmark required before shared decode optimization.
A second bounded serial image read is deliberate release-before-thumbnail behavior. No memory/fidelity/latency evidence requires sharing the full native image; mandatory optimization declined.

Affected current paths/callers: `server/wsi_viewer/conversion.py`.

Source identities: `docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md:32`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## conversion.serial-contract

Disposition: **justified-non-applicable**.

Temporary workspace cleanup lives synchronous serial conversion; deployment worker one process. Unsupported same-destination parallel writers need distinct contract.

Affected current paths/callers: `server/wsi_viewer/conversion.py`.

Source identities: `BUG_REPORT.md:3112`, `docs/reports/BUG_REPORT_CODEX.md:3078`, `docs/reports/DEEP_SYSTEM_BUG_AUDIT.md:107`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:872`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## database.bounded-pool

Disposition: **justified-non-applicable**.

45-72: role-specific bounded pools, zero overflow and timeouts. Enlarging pools is outside the resource contract. Stale connections require separate qualification.

Affected current paths/callers: `server/wsi_viewer/database.py`.

Source identities: `BUG_REPORT.md:12536`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## database.foreign-key-index-qualification

Disposition: **justified-non-applicable**.

Session.user_id59 FK lacks own index; workload PostgreSQL EXPLAIN/latency absent. Index candidate legitimate but deletion/logout stall not demonstrated.
A missing standalone FK index is a workload-dependent optimization. No supported PostgreSQL EXPLAIN/latency reproduction establishes a logout/deletion outage; frozen resource limits do not justify speculative index changes.

Affected current paths/callers: `server/wsi_viewer/models.py`.

Source identities: `BUG_REPORT.md:3618`, `docs/reports/BUG_REPORT_CODEX.md:3584`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:908`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## database.secret-reload

Disposition: **justified-non-applicable**.

84-91 cache key includes password path, not contents. Existing engine retains credential. Qualify supported rotation/restart caller before asserting hot-rotation failure.
Engine cache keys secret-file path; current settings/engine construction reads configured credential, hot reread not promised. Restart/credential rotation requires operator lifecycle qualification; no supported seamless hot-rotation guarantee violated.

Affected current paths/callers: `server/wsi_viewer/database.py`.

Source identities: `BUG_REPORT.md:6712`, `docs/reports/BUG_REPORT_CODEX.md:6678`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## delivery.shared-boundary

Disposition: **justified-non-applicable**.

16 direct FileResponse bypasses helper root validation;22-27 internal delivery validates roots. Caller-by-caller target provenance still needed before declaring attacker-controlled target. No unauthorized-file path proven.
All seven current callers constrain target provenance: main private_tile/private_static_target and public_tile/storage.public_tile; library private thumbnail resolved root+basename, public share thumbnail generated public ID, share tiles storage.public_tile; Study approved model asset release path and study tile private_static_target. Direct FileResponse receives no request-controlled arbitrary path. Centralizing checks is optional defense in depth.

Affected current paths/callers: `server/wsi_viewer/delivery.py`.

Source identities: `BUG_REPORT.md:598`, `docs/reports/BUG_REPORT_CODEX.md:564`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:80`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## desktop.disconnect-deterministic-close

Disposition: **upstream-addressed**.

876 now uses native FileResponse. Existing native TCP test_desktop_content_disconnect tracks opened descriptor closure before GC; bespoke generator removed.

Affected current paths/callers: `server/wsi_viewer/desktop_routes.py`.

Source identities: `BUG_REPORT.md:3245`, `docs/reports/BUG_REPORT_CODEX.md:3211`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## desktop.finalizer-single-process

Disposition: **justified-non-applicable**.

62: general API uses workers1; its lifespan owns finalizer. Extra competing writers are outside this topology.

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `BUG_REPORT.md:10449`, `docs/reports/BUG_REPORT_CODEX.md:10415`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## desktop.ome-cross-volume

Disposition: **justified-non-applicable**.

197-199 atomically renames admitted raw source under same configured storage.root. Quarantine failures preserve source. Separate-volume fallback would expand supported deployment contract.

Affected current paths/callers: `server/wsi_viewer/ome_ingest.py`.

Source identities: `BUG_REPORT.md:4494`, `docs/reports/BUG_REPORT_CODEX.md:4460`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## desktop.partial-stream-retention

Disposition: **justified-non-applicable**.

1310-1359 with spool guarantees close; HTTPException truncates but other stream exceptions may retain unacknowledged suffix. Retry native-lock/reread test handles aborted stream offset. Exact physical suffix retention/expiry remains fault hygiene, not installed corruption.
Unacknowledged suffix is bounded by charged transfer and retry overwrites durable offset under native lock. Existing actual stream-abort/retry test restores admitted offset; no installed corruption/permanent descriptor leak. Immediate suffix pruning optional fault hygiene.

Affected current paths/callers: `server/wsi_viewer/desktop_routes.py`.

Source identities: `BUG_REPORT.md:7971`, `docs/reports/BUG_REPORT_CODEX.md:7937`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:612`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## desktop.range-contract

Disposition: **upstream-addressed**.

852-876 delegates current content delivery to native FileResponse. Historical bespoke range restriction no longer describes this caller; existing range/auth contract tests govern exact accepted forms.

Affected current paths/callers: `server/wsi_viewer/desktop_routes.py`.

Source identities: `BUG_REPORT.md:10891`, `docs/reports/BUG_REPORT_CODEX.md:10857`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## desktop.result-memory-ceiling

Disposition: **justified-non-applicable**.

MAX_RESULT_BYTES2GiB/objects2million and1MiB perline/read bounds; tar members materialized, perrowflush. Peak parser/ORM/native memory and event-loop latency need valid bounded result fixture; no measured OOM.
Current archive/line/object/mask caps and per-row flush bound accepted work. The reported exact OOM/event-loop outage has no valid workload receipt. Resource/latency benchmarking optional; do not enlarge frozen limits or remove validation.

Affected current paths/callers: `server/wsi_viewer/desktop_routes.py`.

Source identities: `BUG_REPORT.md:6908`, `BUG_REPORT.md:8949`, `BUG_REPORT.md:10064`, `docs/reports/BUG_REPORT_CODEX.md:6874`, `docs/reports/BUG_REPORT_CODEX.md:8915`, `docs/reports/BUG_REPORT_CODEX.md:10030`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:974`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## desktop.sync-log-retention

Disposition: **justified-non-applicable**.

DesktopSyncEvent durable revision history, no pruning caller located. Safe retention requires minimumsupported cursor/fullresync protocol; actual unbounded history acknowledged, no measured exhaustion. Do not prune offline client cursors blindly.
Durable revision history supports offline opaque cursors. No supported minimum-cursor/reset contract permits pruning safely, and no measured exhaustion exists. Retention redesign is optional policy work, not a proven broken current consumer.

Affected current paths/callers: `server/wsi_viewer/desktop_sync.py`.

Source identities: `BUG_REPORT.md:11972`, `docs/reports/BUG_REPORT_CODEX.md:11938`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## development.local-launcher-flags

Disposition: **justified-non-applicable**.

397-399 tracked launcher sets roleall,publictiles,Classroomtrue. Private untracked dev.ps1 is not clean checkout production launcher; qualify operator env separately.

Affected current paths/callers: `scripts/run_fullstack_tests.py`.

Source identities: `BUG_REPORT.md:12654`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## edge.headers

Disposition: **justified-non-applicable**.

12-22 supplies CSP/HSTS/no-referrer/nosniff/frame/noindex/permissions/COOP/CORP. Extra reporting is an operator monitoring decision, not demonstrated missing browser security boundary.

Affected current paths/callers: `deploy/Caddyfile`.

Source identities: `BUG_REPORT.md:3688`, `docs/reports/BUG_REPORT_CODEX.md:3654`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## edge.proxy-trust

Disposition: **justified-non-applicable**.

62/113 trust proxy headers but API/Classroom have internal expose only; public ports80/443 Caddy. Caddy official reverse_proxy docs states incoming forwarded values ignored by default; no trusted_proxies configured. Internal-container compromise is a separate boundary. Primary https://caddyserver.com/docs/caddyfile/directives/reverse_proxy

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `BUG_REPORT.md:634`, `BUG_REPORT.md:3882`, `docs/reports/BUG_REPORT_CODEX.md:600`, `docs/reports/BUG_REPORT_CODEX.md:3848`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## identity.corrupt-role

Disposition: **justified-non-applicable**.

63 role map indexes persisted role; identity_routes validates roles against same map before supported create. Bad persisted rows are out-of-band corruption qualification.

Affected current paths/callers: `server/wsi_viewer/identity.py`.

Source identities: `BUG_REPORT.md:6692`, `docs/reports/BUG_REPORT_CODEX.md:6658`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## identity.membership-reactivation

Disposition: **justified-non-applicable**.

Create adds membership unconditionally, uniqueness conflict409; disabled rows persist. No reactivation route located. Product lifecycle decision needed before role revival/upsert.
Create intentionally returns conflict for an existing unique membership, including disabled records. Automatic role revival would change authorization/lifecycle semantics; no existing reactivation promise was found.

Affected current paths/callers: `server/wsi_viewer/identity_routes.py`.

Source identities: `BUG_REPORT.md:7866`, `docs/reports/BUG_REPORT_CODEX.md:7832`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## learning.static-dzi-contract

Disposition: **justified-non-applicable**.

442 explicit static_dzi Classroom publication; Study delivery similarly checks static. Dynamic learning compatibility requires complete qualification, not implied universal OME support.

Affected current paths/callers: `server/wsi_viewer/classroom_routes.py`.

Source identities: `BUG_REPORT.md:6521`, `BUG_REPORT.md:7247`, `BUG_REPORT.md:8144`, `docs/reports/BUG_REPORT_CODEX.md:6487`, `docs/reports/BUG_REPORT_CODEX.md:7213`, `docs/reports/BUG_REPORT_CODEX.md:8110`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## library.authenticated-trash-metadata

Disposition: **justified-non-applicable**.

Authenticated trash details needed inspection/restore, tile private content eligibility separate. Metadata target hints not unauthenticated bytes disclosure; omit hints UX optional.

Affected current paths/callers: `server/wsi_viewer/library_routes.py`.

Source identities: `BUG_REPORT.md:8209`, `docs/reports/BUG_REPORT_CODEX.md:8175`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## library.client-cycle-defense

Disposition: **actual-defect-repaired-local**.

35-46 flatten recursively visits expanded cached child IDs without visited set. Backend cycle protection is separate; actual rooted stale-cache cycle reachability and response ordering remain unproved. Defensive guard reasonable only with bounded current consumer fixture.
Native Chromium actual AdminPage: coherent valid HTTP snapshots A root/B child, cache expanded A children, select A, then B root/A child, navigate All and expand B. Cached A->B plus fresh B->A recurse in FolderTree.flatten35-46: RangeError Maximum call stack size exceeded and ApplicationErrorBoundary replaces Library. No invalid backend hierarchy response required. Ignored runnable proof var/hardening-proof/library-cycle.cjs and receipt library-cache-cycle.json. Transport fixture, no native concurrent backend mutation claim.
Authorized FolderTree visited-ID guard now avoids recursion, preserves first occurrence and keyboard collapse/expand/focus;3existing drag tests pass. Actual subsequent keyboard Enter A exposes sibling AdminPage breadcrumbs674-679 unguarded parent traversal and browser main-thread hang. Parent notified; browser regression intentionally not declared green until sibling resolved.
Final authorized narrow repair: FolderTree flatten visited-ID set prevents repeated traversal; AdminPage breadcrumb parent walk stops at repeated ID. Both keep first occurrence and existing handlers. Native actual AdminPage valid sequential HTTP snapshots regression4/4 passed Chromium, Firefox, WebKit and mobile Chromium23.9s; unique visible rows/levels, collapse/expand/focus/Enter selection checked. Existing folder-drag3/3, targeted ESLint clean, diff check clean. Fixtures model valid response ordering; no native backend concurrent actor claim.

Affected current paths/callers: `AdminPage.loadNavigation (preserves folderChildren/expandedFolders)`; `AdminPage.expandFolder (caches children once)`; `LibraryNavigator -> FolderTree.flatten`; `AdminPage.breadcrumbs useMemo parent traversal`.

Source identities: `BUG_REPORT.md:11756`, `docs/reports/BUG_REPORT_CODEX.md:11722`.

Next step: Local repair qualified by actual browser matrix; parent owns exact-head protected gates/deployment.

## library.folder-count-query-plan

Disposition: **justified-non-applicable**.

1436-1513 existing real10000slide/2000folder navigation test <=11queries/256KiB. SQL aggregate join not evidence of outage; optional representative PostgreSQL tuning not mandatory resourcechange.

Affected current paths/callers: `tests/backend/test_library_v2.py`.

Source identities: `BUG_REPORT.md:2520`, `docs/reports/BUG_REPORT_CODEX.md:2486`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## library.folder-shortcuts

Disposition: **justified-non-applicable**.

6-12 open-only surface; FolderTree onAction provides rename/move/trash. Extra shortcuts do not restore missing capability.

Affected current paths/callers: `apps/web/src/components/library/FolderViews.tsx`.

Source identities: `BUG_REPORT.md:12799`, `docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md:132`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## library.navigation-design

Disposition: **justified-non-applicable**.

Parallel navigational rail/tree/toolbar exposes destinations intentionally; duplication alone has no state or access failure. Product consolidation requires design brief, not defect repair.

Affected current paths/callers: `apps/web/src/components/library/LibraryToolbar.tsx`.

Source identities: `BUG_REPORT.md:12764`, `docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md:90`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## library.search-client-limit

Disposition: **justified-non-applicable**.

107 search no maxlength; library_routes q bound300, AdminPage488-496 catches visible retry error. Matching client input limit is concreteUX improvement; claimed crash false.
API rejects q>300, UI catches visible retry error. Matching maxlength improves UX but no page crash/state corruption; optional validation parity.

Affected current paths/callers: `apps/web/src/components/library/LibraryToolbar.tsx`.

Source identities: `BUG_REPORT.md:12695`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## library.trash-membership-policy

Disposition: **justified-non-applicable**.

1010-1048 owner collection organization accepts persistedtrashed Slide IDs; membership does not publish. Publication separate eligibility. Restore organization policy intentionally retains identity/history.

Affected current paths/callers: `server/wsi_viewer/library_routes.py`.

Source identities: `BUG_REPORT.md:11375`, `docs/reports/BUG_REPORT_CODEX.md:11341`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## migration.manifest-memory

Disposition: **justified-non-applicable**.

370-386 source/target full ordered rows and primary keys are materialized for immutable verification. Representative dataset peak memory and evidence format streaming qualification required; not live request OOM.
Manifest records full ordered keys/digests for offline verification. Changing evidence format is optional migration qualification; no current request or cutover OOM established.

Affected current paths/callers: `server/wsi_viewer/postgres_migration.py`.

Source identities: `BUG_REPORT.md:6742`, `docs/reports/BUG_REPORT_CODEX.md:6708`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## migration.metadata-identifiers

Disposition: **justified-non-applicable**.

304 sequence helpers use dialect quote_identifier; FK check328-354 interpolates trusted inspected column names with doublequotes but not escaping. Unusual schema names need offline native quoted-identifier fixture. No remote-request SQL injection caller.
Fresh actual Base.metadata inventory:68 current tables, zero column names containing double quote. migrate_sqlite_to_postgres upgrades target before reflecting and requires matching Alembic revisions and table sets. The alleged quote-escaping failure requires an operator-modified schema outside the current migration schema; no request-controlled identifier caller. Extending arbitrary identifier compatibility is optional hardening, not a current-schema defect.

Affected current paths/callers: `server/wsi_viewer/postgres_migration.py`.

Source identities: `BUG_REPORT.md:6732`, `docs/reports/BUG_REPORT_CODEX.md:6698`.

Next step: No mandatory repair for current schema; arbitrary operator-extended schemas require a separate supported migration contract.

## ome.channel-axis-support

Disposition: **justified-non-applicable**.

151-158 explicitly requires interleaved RGB three-sample S axis, uint8/uint16. C-axis support requires a new interpretation/fixture contract.

Affected current paths/callers: `server/wsi_viewer/ome.py`.

Source identities: `BUG_REPORT.md:12014`, `docs/reports/BUG_REPORT_CODEX.md:11980`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ome.ingest-full-quality-validation

Disposition: **justified-non-applicable**.

275-286 reads every indexed JPEG quality and validates layout/range/order/source invariant. Expensive offline serial qualification intentional; sampling loses assurance and needs new qualification contract.

Affected current paths/callers: `server/wsi_viewer/ome_tile_index.py`.

Source identities: `BUG_REPORT.md:7192`, `docs/reports/BUG_REPORT_CODEX.md:7158`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## operations.onedrive-workspace

Disposition: **substantive-unresolved-work**.

Production mounts operator-selected /srv/pathlab/data; Windows synced development checkout does not prove production WAL corruption. Actual OneDrive scope/operator evidence still external; do not close it.

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `BUG_REPORT.md:1059`, `docs/reports/BUG_REPORT_CODEX.md:1025`.

Next step: Operator must confirm whether any live SQLite database/WAL/data directory is synced by OneDrive; checkout location alone proves neither unsafe production storage nor a safe deployment.

## operations.proxy-upload-healthchecks

Disposition: **justified-non-applicable**.

Caddy depends tusd service_started while API/Classroom/tile service_healthy. No Caddy/tusd own check; transport failure detection qualification remains, not proven upload blackhole.
Compose currently uses service_started for tusd and service_healthy for API/Classroom/tile services. Additional proxy/tusd checks are operational qualification; no transport blackhole or health-contract violation was reproduced.

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `BUG_REPORT.md:3586`, `docs/reports/BUG_REPORT_CODEX.md:3552`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:902`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## operations.restore-local-permissions

Disposition: **justified-non-applicable**.

25-37 staged mkdir/copy inherits caller umask, later chown10001; unlike backup no own umask/lock. Actual local read permissions and overlapping operator restore need native Linux fixture before exposure claim; atomic rollback43-47 retains original data.
Operator restore uses validated allowed target, guarded archive extraction and activation rollback. Staging access inherits privileged deployment parent/umask. No actual unprivileged path or concurrent authorized restore failure; stricter lock/umask optional defense, not assumed exposure.

Affected current paths/callers: `deploy/scripts/restore.sh`.

Source identities: `BUG_REPORT.md:3708`, `docs/reports/BUG_REPORT_CODEX.md:3674`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ops.alembic-deprecation

Disposition: **justified-non-applicable**.

3 prepend_sys_path=server single unambiguous path; delimiter deprecation option is maintenance without runtime migration failure.

Affected current paths/callers: `alembic.ini`.

Source identities: `BUG_REPORT.md:1121`, `docs/reports/BUG_REPORT_CODEX.md:1087`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:655`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ops.backup-encryption

Disposition: **justified-non-applicable**.

3 restrictive umask077;17-23 backup root/destination700 and flock; backups plaintext. Encryption/key lifecycle requires explicit operator threat model and deployment storage assurance; no public data exposure proved.
Backup root/destination700, umask077 and exclusive flock restrict local access. Encryption/key rotation depends operator threat model; no unauthorized plaintext backup disclosure. Optional encryption policy separate from bug repair.

Affected current paths/callers: `deploy/scripts/backup.sh`.

Source identities: `BUG_REPORT.md:3596`, `docs/reports/BUG_REPORT_CODEX.md:3562`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ops.compose-image-default

Disposition: **justified-non-applicable**.

Compose manualdefaultlive; protected release474-478 explicitly tagsTARGET_SHA,450/472/664 exactcheckout checks. No floating production release bypass shown. Supplychain owner qualifies immutable ledger separately.

Affected current paths/callers: `deploy/scripts/deploy-release.sh`.

Source identities: `BUG_REPORT.md:3698`, `docs/reports/BUG_REPORT_CODEX.md:3664`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:926`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ops.migration-memory

Disposition: **justified-non-applicable**.

250 full source rows,262 bounded insertion batches;370-376 full verification. Offline stopped-writer cutover. Dataset/memory benchmark missing; streaming cannot omit resume/digest evidence.
Offline stopped-writer immutable cutover intentionally materializes verification rows and bounded inserts. No representative dataset memory failure; streaming evidence redesign is optional qualification.

Affected current paths/callers: `server/wsi_viewer/postgres_migration.py`.

Source identities: `BUG_REPORT.md:3638`, `docs/reports/BUG_REPORT_CODEX.md:3604`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:920`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ops.shutdown-cleanup

Disposition: **actual-defect-repaired-local**.

183-189: real SQLite BEGIN EXCLUSIVE killed purger permanently and close raised OperationalError through main.py sequential teardown. Authorized local repair catches with type-only warning; unchanged3600 cadence. Regression red then green proves native later purge succeeds and close completes. Independent teardown isolation remains root-owned.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:3784`, `docs/reports/BUG_REPORT_CODEX.md:3750`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## ops.watchdog-retention

Disposition: **justified-non-applicable**.

22-24 restart3/600s, diagnostic131072; lifetime incident history policy/volume qualification remains; per-record bound not history bound.
Incident history retention is an operator policy; restart rate and per-diagnostic bytes are bounded. No lifetime-volume evidence justifies destructive automatic history pruning.

Affected current paths/callers: `deploy/scripts/component_watchdog.py`.

Source identities: `BUG_REPORT.md:3718`, `docs/reports/BUG_REPORT_CODEX.md:3684`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:932`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## owner.trash-read-contract

Disposition: **justified-non-applicable**.

Owner-only metadata/history retains persisted slide; public tile eligibility separate. Explicit trash inspection/recovery versus mutation contract needed; no public unauthorized access proven.
Persisted owner-only metadata/history supports recovery. Public derivative eligibility separately rejects ineligible slides. The claim does not establish outsider access.

Affected current paths/callers: `server/wsi_viewer/annotation_routes.py`.

Source identities: `BUG_REPORT.md:4979`, `BUG_REPORT.md:9955`, `docs/reports/BUG_REPORT_CODEX.md:4945`, `docs/reports/BUG_REPORT_CODEX.md:9921`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:493`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## proxy.internal-delivery-root

Disposition: **justified-non-applicable**.

30-33 denies direct dynamic paths;77-90 only trusted backend response X-Accel-Redirect drives rewrite/file_server. delivery.py22-27 constrains resolved internal targets to private/public roots. Public request headers cannot select response header. Root narrowing remains additional defense.

Affected current paths/callers: `deploy/Caddyfile`.

Source identities: `BUG_REPORT.md:1864`, `docs/reports/BUG_REPORT_CODEX.md:1830`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:786`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## publication.admin-privacy-attestation

Disposition: **justified-non-applicable**.

1043 publication rejects absentdeidentifiedConfirmed;1051 admin attests privacypassed. Reviewedgrant contract is operatorattestation, no automatic clinical PHI classifier promised.

Affected current paths/callers: `server/wsi_viewer/main.py`.

Source identities: `BUG_REPORT.md:11803`, `docs/reports/BUG_REPORT_CODEX.md:11769`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## qa.parallel-cold-start-qualification

Disposition: **justified-non-applicable**.

fullyParalleltrue/retries0 deliberate CI failfast. Actual earlier browser failures were cardflow/chunk test workload repaired elsewhere; no unsupported generic coldstartup productbug claim. Extra repetition optional qualification.

Affected current paths/callers: `apps/web/playwright.config.ts`.

Source identities: `docs/reports/FULL_SYSTEM_QA_REPORT.md:276`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## router.unknown-route-ux

Disposition: **justified-non-applicable**.

Known /s,/f,/c viewer routes explicit; only unknown path goes AdminRedirect.404 page is UX expansion.

Affected current paths/callers: `apps/web/src/App.tsx`.

Source identities: `BUG_REPORT.md:3351`, `docs/reports/BUG_REPORT_CODEX.md:3317`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## runtime.guard-initialization

Disposition: **justified-non-applicable**.

_guard49-61 creates idle row and serializes update; worker181/329 protection_snapshot initializes/reconciles; upload read deliberately failclosed before initializer. Permanent boot brick not supported.

Affected current paths/callers: `server/wsi_viewer/runtime_protection.py`.

Source identities: `BUG_REPORT.md:3288`, `BUG_REPORT.md:4033`, `docs/reports/BUG_REPORT_CODEX.md:3254`, `docs/reports/BUG_REPORT_CODEX.md:3999`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## schema.default-parity

Disposition: **justified-non-applicable**.

Actual SQLAlchemy PostgreSQL compiler emits DEFAULT 'active' for server_default='active'; reported unquoted DEFAULT syntax failure counterexample. Current models.py ORM defaults populate supported app writes; migrations explicitly supply DB defaults. Raw SQL versus test metadata parity is optional tooling qualification, not proven deployed failure.

Affected current paths/callers: `server/wsi_viewer/models.py`.

Source identities: `BUG_REPORT.md:3628`, `docs/reports/BUG_REPORT_CODEX.md:3594`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:914`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## storage.accessible-capacity-design

Disposition: **justified-non-applicable**.

121-145 storage button accessible name includes byteamount; nested rolemeter percent may flatten in accessibilitytree. Separate meter semantics requires actual assistive/browser tree proof. StorageWorkspace props now onlyBack/Changed, no dropped themeprop.
Storage button accessible name includes usable bytes, meter also labeled. No inaccessible storage action; separating nested semantics optional assistive qualification, dropped theme prop obsolete.

Affected current paths/callers: `apps/web/src/components/library/AppRail.tsx`.

Source identities: `BUG_REPORT.md:13040`, `docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md:316`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## storage.offline-reconciliation-lock

Disposition: **justified-non-applicable**.

199-231 maintenance reconciler admission/BEGIN IMMEDIATE guard; thumbnail repair explicitly requires idle workers/Classroom/Assessment. Mid-walk release would break accounting snapshot. Online pressure allegation contradicts offline maintenance contract.

Affected current paths/callers: `server/wsi_viewer/storage_accounting.py`.

Source identities: `BUG_REPORT.md:6752`, `docs/reports/BUG_REPORT_CODEX.md:6718`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## storage.physical-walk-performance

Disposition: **justified-non-applicable**.

62-72 walks real physical bytes and tolerates disappearing files; logical accounting replacement changes quota. Representative latency/file-count benchmark absent.
Physical quota intentionally includes actual file bytes. No representative latency failure; logical database substitution alters admission contract, so mandatory optimization declined.

Affected current paths/callers: `server/wsi_viewer/storage.py`.

Source identities: `BUG_REPORT.md:9463`, `docs/reports/BUG_REPORT_CODEX.md:9429`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## storage.publish-parent-mkdir

Disposition: **justified-non-applicable**.

153 repeated parent mkdir idempotent; staging+hardlink publication preserved. Grouping calls is unmeasured optimization.

Affected current paths/callers: `server/wsi_viewer/storage.py`.

Source identities: `BUG_REPORT.md:9522`, `docs/reports/BUG_REPORT_CODEX.md:9488`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## storage.reconcile-fail-closed

Disposition: **justified-non-applicable**.

278 missing derivative errors only ready/published, other states clear accounting. Healthy declared slide missing canonical bytes fails closed intentionally; degraded mode requires recovery contract.

Affected current paths/callers: `server/wsi_viewer/storage_accounting.py`.

Source identities: `BUG_REPORT.md:3393`, `docs/reports/BUG_REPORT_CODEX.md:3359`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:451`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.asset-threadpool

Disposition: **justified-non-applicable**.

1356 def synchronous model asset route hashes read_bytes on cache miss; keymtime/size cached. Not async event-loop hashing. Artifact peak memory remains benchmark, not event-loop outage.
Synchronous FastAPI endpoint hashes in threadpool, caches by stat. Optional artifact-memory benchmark does not justify report asyncio starvation premise.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `docs/reports/SYSTEM_VULNERABILITY_AND_BUG_AUDIT.md:267`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.error-copy

Disposition: **justified-non-applicable**.

32-38 throttle/expired codes mapped; remaining controlledApiError enums maydisplaytechnicalcopy. Concrete friendly-copy enhancement; no secret disclosure.
Controlled throttle/expired messages mapped; other enum copy humanization optional UX. No secret or broken request promise proved.

Affected current paths/callers: `apps/web/src/pages/StudyPage.tsx`.

Source identities: `BUG_REPORT.md:12638`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.feature-schema-qualification

Disposition: **justified-non-applicable**.

feeds12 features/context32 does not prove semantic training schema; reasonForAction reads position1, not5. Pilot feature contract/known-vector qualification needed; no neural accuracy claim.
Qualified optional AI known-vector shape does not establish that tensor position5 must differ from1. Deterministic reasons do not read5. Training semantic schema belongs to pilot qualification; alleged neural distortion unproved.

Affected current paths/callers: `apps/web/src/study/traceSim.worker.ts`.

Source identities: `BUG_REPORT.md:10856`, `docs/reports/BUG_REPORT_CODEX.md:10822`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.invitation-rate-limit

Disposition: **justified-non-applicable**.

895 token24 =>192 random bits, bounded course invitations. Anonymous pressure/rate-policy measurement remains; valid credential guessing not shown.
Invitation secrets contain192 random bits and course issuance is bounded; redemptions retain admission checks. Additional anonymous pressure throttling requires measured workload/policy, not a valid-code guessing defect.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:1717`, `docs/reports/BUG_REPORT_CODEX.md:1683`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:248`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## study.invitation-revoke-feature

Disposition: **justified-non-applicable**.

Course end/purge/single-use governs credentials; no per-code revocation route located. Lost-code revoke workflow requires product lifecycle decision, not broken existing API promise.
Single-use, course end and purge govern existing invitation lifecycle. Per-code revocation is an optional feature with no broken existing API promise.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:10691`, `docs/reports/BUG_REPORT_CODEX.md:10657`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## study.lazy-expiration-pressure

Disposition: **justified-non-applicable**.

learner_session checks session expiry then course; shortened course can trigger lazy ended/purge_after commit. Actual many-client concurrent pressure needs proof; no corruption inferred from idempotent status write.
Short idempotent lazy ended transition after shortened course is supported. No concurrent lock/latency failure; scheduler optimization optional, not inferred data corruption.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:10821`, `docs/reports/BUG_REPORT_CODEX.md:10787`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.optional-model-cache

Disposition: **justified-non-applicable**.

prepare verifies cache download/hash/re-read before inference. Optional AI unavailable if durable cache fails; uncached execution weakens explicit offline qualification.

Affected current paths/callers: `apps/web/src/study/traceSim.worker.ts`.

Source identities: `BUG_REPORT.md:7669`, `BUG_REPORT.md:10739`, `docs/reports/BUG_REPORT_CODEX.md:7635`, `docs/reports/BUG_REPORT_CODEX.md:10705`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.pseudonym-collision-retry

Disposition: **actual-defect-repaired-local**.

Actual valid HTTP course with2issued invitations/limit2; forced only token_hex4 same8hex models possible RNG collision: first201, second native IntegrityError (production500), invitation issued/sessioncount1. No double-spend; random fresh client retry can recover. Proposal bounded collision-specific retry preserving current admission/idempotence. Not patched. Repro temp cleanup encountered engine Windows file lock after results; dedicated pytest needs proper fixture disposal.
Authorized bounded8 preflight candidate lookups under existing courseadmissionlock match Classroomalias pattern; no arbitraryIntegrityErrorretry. Native2cases red2/green2 collision/exhaustion503/unconsumedinvitation/freshretry201/samecode404. Purger+collision3green/Ruffclean.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:3424`, `docs/reports/BUG_REPORT_CODEX.md:3390`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.readiness-telemetry-trust

Disposition: **justified-non-applicable**.

1303 POST learner_csrf then atomic counter counts reports, not unique learners. Dedup/telemetry semantics need policy; not unauthenticated.
Authenticated learner CSRF reports increment report counters atomically; they are not a unique-learner census. Changing dedup semantics is a telemetry policy decision, not an unauthenticated counter bypass.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:10342`, `docs/reports/BUG_REPORT_CODEX.md:10308`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## study.submission-rate-contract

Disposition: **justified-non-applicable**.

Submission rate keyed session and SUBMISSION_INTERVAL_SECONDS30, lock_admission study-session before validation/mutation. Per-task exemption would expand allowed work beyond bounded current contract.

Affected current paths/callers: `server/wsi_viewer/study_routes.py`.

Source identities: `BUG_REPORT.md:10783`, `docs/reports/BUG_REPORT_CODEX.md:10749`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## study.trash-review-policy

Disposition: **actual-defect-repaired-local**.

1400-1428 active session/course pack/static mode/privacy/state checks; no trashed_at. Existing review versus owner-trash contract needed, not outsider bypass.
Actual valid native HTTP published Study Pack, active course, redeemed learner: initial DZI200, admin trash200 persists trashedAt, subsequent Study DZI200 unchanged. Existing main private tile800/public tile1130 rejects trash; Library trash1258 withdraws all publication grants, Study authoring434 excludes trash. This is existing eligibility omission, not an undefined pack policy. One-line study_tile trashed_at guard native RED200->GREEN404. test_study_trash_eligibility asserts pack definition/course/learner/session and private descriptor retained; owner restore gives learner200. No immutable pack/history deletion or revoke-all.

Affected current paths/callers: `study_routes.study_tile`; `library_routes.trash_slide -> publication.delete_all_slide_grants`; `main.private_tile/public_slide_tile existing eligibility`.

Source identities: `BUG_REPORT.md:10272`, `docs/reports/BUG_REPORT_CODEX.md:10238`.

Next step: Local native regression qualified; no clinical/legal motivation is needed to establish existing delivery eligibility. Parent owns protected gates/deployment.

## tile-cache.hit-stat-lock

Disposition: **justified-non-applicable**.

get198-218 checks filesystem size/regularity under shared accounting lock; intentional eviction synchronization. Slow-filesystem contention requires measured workload before unlocked redesign.
Filesystem checks under accounting lock intentionally synchronize eviction/integrity. Unmeasured filesystem contention is not a demonstrated deadlock; mandatory unlocked redesign declined.

Affected current paths/callers: `server/wsi_viewer/tile_cache.py`.

Source identities: `BUG_REPORT.md:12072`, `docs/reports/BUG_REPORT_CODEX.md:12038`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tile-cache.reconcile-validation

Disposition: **justified-non-applicable**.

128-185 validates layout, regular file and bounded length; no restart JPEG decode. Trusted commit validates JPEG markers. Disk-corruption qualification and rebuild contract needed; no remote cache poisoning demonstrated.
Trusted commit validates JPEG markers; restart reconciliation checks layout, regular-file status and bounded size. A disk-corruption decode/rebuild drill is optional qualification, not remotely reachable cache poisoning.

Affected current paths/callers: `server/wsi_viewer/tile_cache.py`.

Source identities: `BUG_REPORT.md:3453`, `docs/reports/BUG_REPORT_CODEX.md:3419`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## tile-cache.replace-cleanup

Disposition: **justified-non-applicable**.

251-255 existing tracked digest returns without replacement; one-cache get_or_create coalesces identical producer. Target-unlink exception risk needs external/untracked second writer, not normal supported tracked replacement.

Affected current paths/callers: `server/wsi_viewer/tile_cache.py`.

Source identities: `docs/reports/FULL_SYSTEM_QA_REPORT.md:257`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tile-cache.startup-reconcile

Disposition: **justified-non-applicable**.

128-195 rglob collects entries, sorts and evicts to byte budget. Actual traversal cost scales file count; representative file-count startup latency still missing. No observed startup outage.
Startup walks bounded-byte cache, validates entries and evicts. No representative startup failure proved; incremental reconstruction needs qualification rather than weakening integrity.

Affected current paths/callers: `server/wsi_viewer/tile_cache.py`.

Source identities: `BUG_REPORT.md:12043`, `docs/reports/BUG_REPORT_CODEX.md:12009`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tiles.follower-timeout

Disposition: **justified-non-applicable**.

Follower waits unbounded but leader catches BaseException and signals in finally218-245. Hung native producer would hold follower; supported hang/workload qualification required before timeout/retry policy (retry cannot kill native leader).
Leader catches BaseException and signals followers in finally. No supported hung native producer was reproduced; adding follower timeout cannot terminate the leader and needs an explicit cancellation/retry contract.

Affected current paths/callers: `server/wsi_viewer/tile_cache.py`.

Source identities: `BUG_REPORT.md:3379`, `BUG_REPORT.md:9390`, `docs/reports/BUG_REPORT_CODEX.md:3345`, `docs/reports/BUG_REPORT_CODEX.md:9356`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:878`.

Next step: No mandatory product change established under the current caller/contract. Optional feature, operational qualification or measured optimization remains distinct.

## tiles.index-cache-performance

Disposition: **justified-non-applicable**.

196-208 renderer caches statkeyindex128LRU; tile_routes158 independently validates current authorization geometry/index. Preserve change detection; redundant parse optimization unmeasured, no required integrity weakening.

Affected current paths/callers: `server/wsi_viewer/ome_tiles.py`.

Source identities: `BUG_REPORT.md:6722`, `BUG_REPORT.md:7115`, `BUG_REPORT.md:11333`, `docs/reports/BUG_REPORT_CODEX.md:6688`, `docs/reports/BUG_REPORT_CODEX.md:7081`, `docs/reports/BUG_REPORT_CODEX.md:11299`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tiles.internal-network-boundary

Disposition: **justified-non-applicable**.

182 tile expose8090, readonly originals and internal network; Caddy denies direct/_pathlab_ome and relays trusted API response. Compromised peer is outside unauthenticated public tile claim.

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `BUG_REPORT.md:3201`, `docs/reports/BUG_REPORT_CODEX.md:3167`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:804`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tiles.readiness-cost

Disposition: **justified-non-applicable**.

75-89 readiness bounded stats plus next(glob) first known index, no full list. Parsing probe cost requires representative latency/size qualification before cache-by-stat design.
Probe chooses first index lazily and checks bounded cache. Actual expensive parse workload not reproduced; caching probe metadata is optional optimization and may weaken fresh validation.

Affected current paths/callers: `server/wsi_viewer/tile_service.py`.

Source identities: `BUG_REPORT.md:5774`, `docs/reports/BUG_REPORT_CODEX.md:5740`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tiles.single-process-cache-contract

Disposition: **justified-non-applicable**.

Tile service one instance with bounded cache/render settings and private mounts; independent process writers need a scaling contract.

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `BUG_REPORT.md:3466`, `docs/reports/BUG_REPORT_CODEX.md:3432`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## tus.admitted-upload-completion

Disposition: **justified-non-applicable**.

988 signature verified allow_expired only completion of admitted transfer; finalizer rechecks reservation/state/length/path. It neither issues new admission nor bypasses signature; hard completion expiry is lifecycle policy.

Affected current paths/callers: `server/wsi_viewer/main.py`.

Source identities: `BUG_REPORT.md:3097`, `docs/reports/BUG_REPORT_CODEX.md:3063`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:866`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## upload.invalid-spool-retry-retention

Disposition: **justified-non-applicable**.

finalize_upload869 validates admitted reservation/length/source signature before installation. Invalid spool remains charged UPLOADING for retry/cancel/expiry; eager release changes explicit recovery policy.

Affected current paths/callers: `server/wsi_viewer/main.py`.

Source identities: `BUG_REPORT.md:8843`, `docs/reports/BUG_REPORT_CODEX.md:8809`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## upload.partial-copy-recovery

Disposition: **justified-non-applicable**.

910-923 staging.partial/source-spool retained until durable job ACK; retry removes previouspartial. Fault cleanup/space qualification remains; no installed source-loss/unbounded free reservation claim.
Source retained until durable ACK, retry replaces staging.partial, reservation stays charged, deletion cleans slide directory. Immediate staging cleanup optional; no source-loss/unbounded free storage demonstrated.

Affected current paths/callers: `server/wsi_viewer/main.py`.

Source identities: `BUG_REPORT.md:9665`, `docs/reports/BUG_REPORT_CODEX.md:9631`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## viewer.buffered-network-window

Disposition: **justified-non-applicable**.

334-364 buffered samples drained with splice each interval. Possible first-window contamination needs measurement; not indefinite retention.
Buffered timing affects only initial interval because samples drain. No sustained wrong job limit demonstrated; start-time filtering optional telemetry qualification.

Affected current paths/callers: `apps/web/src/components/OpenSeadragonViewer.tsx`.

Source identities: `BUG_REPORT.md:11695`, `docs/reports/BUG_REPORT_CODEX.md:11661`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## viewer.manifest-cancel-privacy

Disposition: **justified-non-applicable**.

129-141 active guard prevents stale state on routechange; downloaded authorized URL visible to same browser. Abort cancels unused work but does not alter endpoint authorization; DOM hint not new privacy bypass.

Affected current paths/callers: `apps/web/src/pages/SharedViewerPage.tsx`.

Source identities: `BUG_REPORT.md:3334`, `docs/reports/BUG_REPORT_CODEX.md:3300`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## viewer.osd-error-box

Disposition: **justified-non-applicable**.

Existing loading/reconnect handling retains default OSD error UI. Actual occluded-action evidence needed before visual suppression.
Default OSD error UI coexists with explicit reconnect/error handling. No occluded actual action; visual suppression optional styling decision.

Affected current paths/callers: `apps/web/src/components/OpenSeadragonViewer.tsx`.

Source identities: `BUG_REPORT.md:12626`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## viewer.reconnect-budget

Disposition: **justified-non-applicable**.

223-239 single timer bounded delay/offline/disposed guards. Persistent descriptor retry UX needs qualification; no tight storm.
Single bounded-backoff timer preserves transient recovery, offline/disposed guards. A finite permanent-error budget is product policy; no current tight-loop outage.

Affected current paths/callers: `apps/web/src/components/OpenSeadragonViewer.tsx`.

Source identities: `BUG_REPORT.md:3542`, `docs/reports/BUG_REPORT_CODEX.md:3508`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:896`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## viewer.robots-scope

Disposition: **justified-non-applicable**.

119-122 noindex viewer; deploy/Caddyfile globalXRobotsTag noindex allpaths. No public indexablelanding contract; restoring previousmeta optional SPA hygiene.

Affected current paths/callers: `apps/web/src/pages/ViewerPage.tsx`.

Source identities: `BUG_REPORT.md:4182`, `BUG_REPORT.md:6812`, `docs/reports/BUG_REPORT_CODEX.md:4148`, `docs/reports/BUG_REPORT_CODEX.md:6778`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## web.dead-component

Disposition: **justified-non-applicable**.

rg allsrc finds only component declaration, no import/caller. Unused component cleanup has no current runtime failure.

Affected current paths/callers: `apps/web/src/components/DeleteSlideDialog.tsx`.

Source identities: `BUG_REPORT.md:12954`, `docs/reports/ROUTE_AND_MENU_WIRING_AUDIT.md:271`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## web.download-url-lifetime

Disposition: **justified-non-applicable**.

392-402 native blob detachedanchorclick/immediaterevoke. No annotationdownload failurenative receipt; earlier actualCSV all4browser successes counterexample to generic revoke failure. Annotation-specific portabilityproof pending, not assumedtimeout needed.
Actual generic CSV immediate revoke succeeded supported browser matrix; current annotation trigger clicks before revoke. No annotation download failure fixture; speculative delay declined, retain optional browser qualification.

Affected current paths/callers: `apps/web/src/annotations/AnnotationWorkspace.tsx`.

Source identities: `BUG_REPORT.md:3319`, `BUG_REPORT.md:3439`, `docs/reports/BUG_REPORT_CODEX.md:3285`, `docs/reports/BUG_REPORT_CODEX.md:3405`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## worker.serial-capacity-monitor

Disposition: **justified-non-applicable**.

65-101 advisory threshold monitor called synchronously run_due151-153. Separate storage admission enforces quota; unsupported concurrent check callers do not prove bypass.

Affected current paths/callers: `server/wsi_viewer/worker.py`.

Source identities: `BUG_REPORT.md:12466`, `docs/reports/BUG_REPORT_CODEX.md:12432`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## worker.serial-recovery-contract

Disposition: **justified-non-applicable**.

run_due recovery precedes synchronous process_job in same serial loop135-166. Long job cannot overlap same-loop recovery; external operator competing converter not supported default.

Affected current paths/callers: `server/wsi_viewer/worker.py`.

Source identities: `BUG_REPORT.md:4266`, `docs/reports/BUG_REPORT_CODEX.md:4232`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## worker.single-converter-stale-recovery

Disposition: **justified-non-applicable**.

135-147 scheduler recovery and process_next share serial loop. Parallel overwrite requires unsupported extra writer.

Affected current paths/callers: `server/wsi_viewer/worker.py`.

Source identities: `BUG_REPORT.md:5842`, `BUG_REPORT.md:8733`, `docs/reports/BUG_REPORT_CODEX.md:5808`, `docs/reports/BUG_REPORT_CODEX.md:8699`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## worker.stale-job-selection

Disposition: **justified-non-applicable**.

340-342 writes running+heartbeat together. No checkpointing writer found. NULL-heartbeat rows need legacy recovery policy, not inferred supported runtime corruption.

Affected current paths/callers: `server/wsi_viewer/worker.py`.

Source identities: `BUG_REPORT.md:832`, `BUG_REPORT.md:1291`, `docs/reports/BUG_REPORT_CODEX.md:798`, `docs/reports/BUG_REPORT_CODEX.md:1257`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:108`, `docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md:192`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

## worker.unsupported-parallel

Disposition: **justified-non-applicable**.

252: one pathlab-worker service. Serial scheduler and process_next do not support competing conversion writers.

Affected current paths/callers: `deploy/compose.yaml`.

Source identities: `docs/reports/FULL_SYSTEM_QA_REPORT.md:172`.

Next step: No mandatory product repair established beyond the explicitly recorded local repair; optional qualification is separate.

Final qualification: exact original InviteDialog function rerun with browser body/chrome focus allowed still fails background DOM containment; repaired function restored in finally. Collision local2passed/2PostgreSQLskipped; hosted qualification pending.
