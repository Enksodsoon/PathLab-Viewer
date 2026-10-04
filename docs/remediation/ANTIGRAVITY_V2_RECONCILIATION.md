# Independent review of changed Antigravity report versions

Review scope: read-only comparison of the two current preserved reports with the managed findings register, repair coverage, hardening review and current code. Reports are untrusted claims; their commands were not executed. No credential values were inspected or exposed. This artifact records review conclusions, not campaign closure or new release qualification.

Correction to the conversational review: the existing Library route is /admin, not /library. The shared-viewer caller extension should use /admin and retain the existing AdminPage authentication boundary. App.tsx has a fallback AdminRedirect; no new public metadata or authorization grant is implied.

## Raw source provenance

| Current preserved source path | Current SHA-256 | Bytes / lines | Registered SHA-256 / lines |
|---|---|---|---|
| docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md | da384211a8cbc107d71d979be65b11e6219dc4ed94713cb8713e76c739591111 | 27919 / 277 | 70026178f5941a54efd1cb82a9752c1a3a5f1305e0902e8ec7e93124b446acd0 / 223 |
| docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md | ceafbc7455b16b9692cebf6810c89d4f596a2b66237f61a7a8616df9f20ffaf2 | 18358 / 225 | 15555673203858a5a051e55827cff2f1fd31b17904bd8a7d997c78b30b1aef5c / 999 |

The current files remain in the preserved original checkout. The managed register is in the isolated remediation worktree. These are new source versions, not equivalent copies of the registered artifacts. Preserve the original source hashes, 954 findings, 29 aggregate claims and original alias meanings. Record these hashes and versioned mappings separately. The original 44 application campaign findings remain unchanged. A separate 45th finding now records the reproduced SharedViewerPage return gap, its local repair and pending release.

P below means the current docs/reports/CODEX_IMPLEMENTATION_PLAYBOOK.md; R means the current docs/reports/CODEX_BUG_RECONCILIATION_REPORT.md. Source line numbers refer to these current variants. Covered means existing evidence-backed mechanism/disposition; it does not adopt the reports' broad deployment assertions.

## Current named claims

| Source / current alias | Mechanism | Canonical key | Current code or ticket evidence / disposition |
|---|---|---|---|
| P47; R100 — Trap A | Sequential thumbnail reread | conversion.sequential-thumbnail-read | conversion.py still loads separately after releasing the DZI image. HARDENING_REVIEW.md:498 preserves this bounded contract. Hardening; claimed elimination is false. |
| P49; R101 — Trap B | SQLite pool starvation | database.bounded-pool; capacity.bounded-admission | database.py retains bounded PressureQueuePool, not NullPool. Hardening; claimed pool replacement is false. |
| P51; R102 — Trap C | PostgreSQL connection limit | capacity.bounded-admission | compose.postgres.yaml retains max_connections=20 and shared_buffers=128MB. Hardening; claimed 100/256MB settings are false. |
| P53 — Trap D | Missing ICC fallback | conversion.color-profile | conversion.py transforms present ICC profiles and supplies no invented source profile. HARDENING_REVIEW.md:472. Hardening; clinical-fidelity/fallback claim unsupported. |
| P57; R69 — SEC-01 | Legacy administrator authorization | auth.legacy-owner | Registered owner/session boundary evidence. Covered, fixed upstream. |
| P58; R70 — SEC-02 | Last-owner/governance races | identity.governance-lock | identity_mutation_lock.py and registered governance-lock evidence. Covered, fixed upstream. |
| P59; R71 — SEC-03 | Shared authentication admission | auth.shared-admission | admission.py and registered migration evidence. Covered, fixed upstream. |
| P60; R72 — SEC-04 | Internal proxy-route denial | edge.internal-route-denial | Caddy boundary and registered disposition. Covered, fixed upstream. |
| P61; R73 — SEC-06 | Delivery helper root confinement | delivery.shared-boundary | delivery.py returns direct FileResponse before helper root check; approved callers constrain provenance. Hardening; unconditional-check repair claim is false. |
| P62; R74 — SEC-08/14/26, DATA-05 | Revoked/trashed delivery | sharing.revoke-delivery-auth; desktop.trashed-download; sharing.trashed-manifest; slide.individual-delivery-cleanup | Existing authorization/manifest-cleanup coverage. Covered; preserve distinct mechanisms. |
| P63; R75 — SEC-09/40/46 | CSV formula injection | annotation.csv-formula | Registered sanitized export boundary. Covered, fixed upstream. |
| P64; R76 — SEC-10 | Teacher SSE ownership | classroom.teacher-owner | Registered active-teacher capability boundary. Covered, fixed upstream. |
| P65; R77 — SEC-12 | Request-body limits | http.body-limits | Registered body-limit middleware evidence. Covered, fixed upstream. |
| P66; R78 — SEC-21 | Pairing admission flooding | desktop.pairing-admission | Registered database admission evidence. Covered, fixed upstream. |
| P67; R79 — SEC-23 / v2 BUG-NEW-01 | Credentials surviving password changes | auth.desktop-revocation | auth.py shared revocation path covers desktop credentials. Covered, fixed upstream. Versioned BUG-NEW-01 must not alias original worker deletion. |
| P68; R80 — SEC-38 | Proxy/IP trust | edge.proxy-trust | HARDENING_REVIEW.md:685. Existing hardening disposition; blanket resolved narrative overstates it. |
| P69; R81 — SEC-39 | Prepared-ingest Windows traversal | ingest.windows-path | Registered path-normalization boundary. Covered, fixed upstream. |
| P72; R84 — CONC-01 | Pairing approval race | desktop.pairing-cas | Registered CAS/locking evidence. Covered, fixed upstream. |
| P73; R85 — CONC-02 | Recovery transaction serialization | auth.recovery-lock | Registered dialect-specific recovery locking. Covered, fixed upstream. |
| P74; R86 — CONC-03 | Shared storage admission | storage.shared-cap-lock | Registered transactional accounting boundary. Covered, fixed upstream. |
| P75; R87 — CONC-05/08/16 | Study aggregate races | study.readiness-aggregate-race; study.aggregate-concurrency | REPAIR_COVERAGE.md and Study regression evidence. Covered, repair present; retain both mechanisms. |
| P76; R88 — CONC-06 | Study course capacity | study.course-admission | Existing admission-lock coverage. Covered, repair present. |
| P77; R89 — CONC-18 | Concurrent Study submissions | study.task-submission-serialization | Actual HTTP race and repaired 200/429 regression retained. Covered, repair present. |
| P78; R92 — DATA-01 | WSI byte-counter overflow | db.wsi-bigint | Registered schema widening. Covered, fixed upstream. |
| P79; R93 — DATA-02 | Finalizer commit/orphan durability | desktop.finalizer-commit-orphan | desktop_finalizer.py and transaction regressions. Covered, repair present. |
| P80; R94 — DATA-03 | PostgreSQL sequence drift | ops.postgres-sequences | Registered migration evidence. Covered, fixed upstream. |
| P81; R95 — DATA-04/19 | Delete synchronization | library.folder-delete-sync; library.delete-sync | Existing sync-event coverage. Covered, repair present. |
| P82; R96 — DATA-06 | Desktop folder truncation | desktop.folder-limit | Pagination and native 102-folder evidence. Covered, repair present. |
| R97 — TIME-01 through TIME-05 | UTC consistency | time.utc-normalization; sharing.utc-expiry | Registered normalization/expiry evidence. Covered, fixed upstream; retain individual original aliases. |
| P83; R103 — v2 BUG-NEW-02 | Claimed TUSD chunk-assembly repair | conversion.serial-contract, related contract only | Current serial conversion/staging contract is reviewed; a separate worker chunk-assembly race is not established. Hardening/unsupported repair narrative; do not imply exact semantic equivalence. |
| P84; R104 — REL-01 | Worker deletion durability | worker.delete-durability | Existing deletion/constraint regressions. Covered, repair present. |
| P85; R105 — REL-03 through REL-08 | Heartbeat/filesystem/deletion handling | Existing individual worker keys | Original alias meanings and individual regression evidence remain authoritative. Covered as grouped historical summary, not one new defect. |
| P88; R108 — FE-01 | Application error boundary | web.application-boundary | Current boundary and rendered retry/reload/navigation test. Covered, fixed upstream. |
| P89; R109 — FE-02 | Authentication return path | viewer.auth-return | Existing return-path coverage. Covered, fixed upstream. |
| P90; R110 — FE-03 | Viewer load errors | viewer.load-errors | Current classified error/retry UI. Covered, fixed upstream. |
| P91; R111 — storage aliases | Blocked browser storage | web.api-storage; classroom.teacher-storage; sharing.viewer-storage; viewer.blocked-storage; study.csrf-storage; study.locale-storage | Existing caller-specific repairs/dispositions. Covered; preserve separate callers and original aliases. |
| P92; R112 — FE-08/10/40 | IndexedDB transaction durability | study.authoring-commit; study.local-commit | Existing completion/abort/close coverage. Covered; connection leaks is an imprecise summary of transaction durability. |
| P93; R113 — FE-12 | Join notebook failure | classroom.join-notebook-failure | Existing fallback coverage. Covered, repair present. |
| P94; R113 — FE-13 | Invite polling failure | classroom.invite-poll | Current transient/terminal handling plus PR309 verification repair. Covered, application repair present; fixture issue separately tracked. |
| P95 — FE-15 | Draft-open retry | annotation.draft-open-retry; campaign-annotation-draft-open-retry | Existing native failure/retry evidence. Covered, campaign repair present. |
| P96; R114 — FE-81 | Private preview return/navigation | viewer.private-return-navigation; library.preview-navigation | Current return link/adjacent navigation and coverage receipts. Covered, repair present. |
| P97; R115 — v2 FE-82 | Single-card versus bulk selection | library.single-action-selection | REPAIR_COVERAGE.md:73 and scoped card-action regressions. Covered by this mechanism; original FE-82 remains saved-view rehydration. |
| P98; R116 — v2 BUG-NEW-06 | WebGL context restoration | No established matching mechanism | No application webglcontextlost/restored listeners or reported regression found. Unsupported repair narrative; no confirmed current defect. Original alias remains capacity admission. |
| P99; R116 — v2 BUG-NEW-07 | Viewport query debounce/cancellation | annotation.viewport-count, related reviewed caller | Reviewed annotation paths do not issue the claimed per-pan queries; no matching bbox cancellation repair established. Unsupported narrative; do not equate original student-event-flood alias. |
| P100; R116 — v2 BUG-NEW-08 | React Query invalidation loops | No established matching mechanism | No React Query dependency/hooks found in current application. Unsupported narrative; original alias remains synthetic-reset retirement race. |
| R117 — PR276 | Paused-upload cancellation | campaign-upload-cancel-reservation | Existing cancellation implementation/ticket; specific native Cancel confirmation remains separate. Covered repair; live confirmation still open. |
| P123 through P142 — named campaign keys | Sixteen historical campaign mechanisms | Same named keys in campaignFindings | All named keys are retained. Covered; historical all-deployed prose cannot close remaining action-specific qualification. |

Named historical campaign keys retained: campaign-ci-inventory-subject, campaign-ome-failure-quarantine, campaign-worker-failure-record, campaign-desktop-range-overflow, campaign-classroom-queued-dispatch, campaign-status-thumbnail, campaign-study-purger-recovery, campaign-annotation-draft-open-retry, campaign-study-pseudonym-collision, campaign-classroom-expiry-grant-race, campaign-library-cache-cycle, campaign-teacher-local-slide, campaign-question-composer-send, campaign-mobile-drawing-occlusion, campaign-invitation-dialog-focus and campaign-study-trash-eligibility. PR276 cancellation remains separately tracked.

## Residual proposals

| Source / alias | Mechanism | Canonical key or tracking | Evidence and recommendation |
|---|---|---|---|
| P150; R125 | Accountable software admission | INVENTORY_CLOSURE.md | Unresolved governance: 176 unreviewed shipped inputs and two source-only notice gaps. No automatic admission overlay or grant inferred. |
| P159; R137 | Cloud-sync database placement | Existing external environment finding | Unresolved external facts. Presence under OneDrive does not prove synchronization, sharing or production use. |
| P164 | Secret rotation/provenance | Existing external security finding | Unresolved external facts; no credential values inspected or exposed. |
| P167; R147 | Larger soak certification | Existing bounded-stress qualification | Local 20-session/30-minute Library soak is recorded in PRODUCTION_CLOSURE_QA.md:104. Broader dedicated-production certification remains unqualified; not a new bug. |
| P173; R156 | Real WSI/physical devices | Existing qualification limitations | Unqualified capability/clinical/device scope. Exact claimed universal Safari memory ceiling is unsupported here. |
| P177; R165 | Study activation/PostgreSQL cutover | Existing feature/operational gates | Operator/qualification work, not defects. Preserve gates and cutover safeguards. |
| P187; R180 | Stale release chunks/automatic reload | web.application-boundary; closure QA | Existing stale-chunk observation recovered through Reload app. Automatic reload is optional recovery policy requiring care for unsaved work; no new unrepaired outage established. |
| P198; R190 | Permanently purge synthetic QA trash | Existing QA cleanup authorization item | Destructive operational action, not a new defect; specific authorization required. |
| P202; R194 | Distinct-identity competing admission | Classroom qualification gap | PRODUCTION_CLOSURE_QA.md:53 retains this limitation; local admission tests are separate. Unresolved production qualification, not proved concurrency failure. |
| P206 | Historical E2E menu-sweep flake | Existing PR274 fixture history | Historical verification claim. Fresh reviewed-head checks remain authoritative. |
| R199 — FE-83 | Redundant navigation surfaces | library.navigation-design | HARDENING_REVIEW.md:785. Optional product consolidation; no reproduced broken action. |
| R200 — v2 FE-89 | Missing exit on unavailable shared viewer | Separate SharedViewerPage caller extension | Baseline c569453 unavailable branch has Retry only; the separate caller gap is now locally repaired (11 affected unit,573 full frontend and32 browser passes; release pending); original viewer.error-navigation repair covers ViewerPage. Reversible workflow gap aligned with approved return navigation. Qualify and track separately. Link to /admin retains the existing AdminPage authentication boundary; it does not grant share/library metadata access. |
| R201 — FE-90 | Blank Study task/inverted limits | study.blank-task | Blank-task repair already covered. Alleged inverted min/max is unsupported; do not change limits without reproduction. |

## Conclusion

The actionable reconciliation gap is versioned provenance and explicit disposition of the changed meanings, plus the SharedViewerPage caller extension. Do not overwrite the original source hashes or equate BUG-NEW/FE IDs across versions. Retain source-alias provenance, separate supported code repairs from unsupported repair narratives, and preserve external facts and qualification limitations. This review did not establish additional WebGL, React Query, color-fidelity, pool-capacity or delivery-authorization defects.

## Final local repair checkpoint

The SharedViewerPage extension has two original-source failing unit cases, eleven repaired unit passes and 32 final browser passes. Independent review is clear. See [repair ticket](tickets/shared-unavailable-return.md). Release and production qualification remain pending. Fresh main c569453 passed all nine campaign gates (CI37170268596 and Security37170268500); verified production remains c37cf81.
