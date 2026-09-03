# Role and Approval Matrix

This contract converts Institution Role Bindings into deny-by-default capabilities and executable approval pairs. It is the minimum Full-Surface v1 authorization surface: an Institution may narrow a grant, but neither configuration nor role composition may broaden it without a new governed decision.

## Enforcement model

Every mutating API, command handler, scheduled job, operator command, and imported proposal must name one capability identifier from this document. Authorization resolves the authenticated Principal, active Institution Membership, active Role Binding, purpose, target aggregate and policy version on the server. Client claims, email, display role, external role vocabulary, possession of a URL, and a different Purpose Identity for the same Principal confer no capability.

The default result is deny. A capability grant expires when the Membership or Role Binding expires, is disabled, changes Institution, changes purpose, or is superseded by policy. Read access remains purpose- and data-class-bound even where this matrix summarizes it as read or review.

The sole pre-Membership mutation is the one-time `platform.bootstrap.commit` ceremony. It is available only on an empty, freshly installed deployment with no Institution, Principal, prior bootstrap receipt, or imported state. A named Operator presents the signed installation manifest; two different install-time Root Recovery Share Custodians named by that manifest authorize it through the quorum but do not yet act through Institution Role Bindings; and the intended first Owner completes a local WebAuthn enrollment bound into the immutable proposal. For this ceremony only, `svc-platform` authenticates as the installation-scoped service identity pinned by that manifest, not as an Institution Service Principal. It atomically creates exactly one Institution, Principal, Owner Membership, Role Binding, bootstrap outbox event, and `BootstrapReceipt`; any pre-existing state, remote invocation, missing person, reused share, or changed proposal rejects it permanently. Afterward, every person—including those custodians—requires an ordinary current Membership and Role Binding, and `svc-platform` uses the newly established Institution trust boundary for Institution-scoped actions.

## Role capability grants

| Role Binding | Granted capability families | Explicit limits |
| --- | --- | --- |
| Owner | `trust.institution.govern`, `trust.membership.administer`, `trust.policy.approve`, `trust.break-glass.initiate`, `trust.break-glass.approve`, `trust.legal-hold.approve`, `trust.deletion.approve`, `platform.activation.approve` | May establish the first Administrator after bootstrap but does not recover keys, admit clinical data, publish anonymously, grade, moderate, issue Achievement Credentials, or operate production by role name alone. |
| Administrator | `trust.membership.administer`, `trust.policy.configure`, `trust.break-glass.approve`, `trust.legal-hold.initiate`, `trust.deletion.initiate`, `catalog.cohort.administer`, `catalog.enrollment.administer`, `catalog.roster.capture`, `integration.registration.administer`, `credential.status.initiate`, `credential.custody.transfer`, `portability.execute`, `edge.enrollment.administer` | Cannot grant a capability the administrator does not hold; cannot remove or disable the last active Owner; cannot satisfy a second-person decision alone. `credential.custody.transfer` authorizes only a verified transfer between the exact named Institution-controlled custodians and never exports an issuer/status private key. `edge.enrollment.administer` is limited to the finite enroll, rotate, revoke, and retire operation enum; it is not a namespace grant. |
| Instructor | `catalog.author`, `catalog.publish.ordinary`, `catalog.progress.confirm`, `catalog.achievement-definition.initiate`, `catalog.achievement.initiate`, `imaging.upload.initiate`, `imaging.annotation.author`, `imaging.restricted-layer.initiate`, `live.session.manage`, `teacher.draft.approve` | Cannot independently approve an Achievement Definition Version, admit an imaging asset, publish anonymous imaging, finalize a high-stakes Grade, moderate their own work, or issue an Achievement Credential. |
| Teaching Assistant | `catalog.draft.contribute`, `live.session.facilitate`, `assessment.response.support` | Cannot publish, archive, grade, moderate, transfer an Attempt, establish Completion Evidence, seal EQA work, or initiate a credential-bearing outcome. |
| Assessor | `assessment.item.author`, `assessment.session.manage`, `assessment.attempt.transfer`, `assessment.grade.ordinary`, `assessment.high-stakes.initiate`, `credential.assessment.initiate` | Cannot independently finalize their own high-stakes change or credential-bearing outcome. |
| Moderator | `assessment.moderate`, `assessment.high-stakes.approve`, `catalog.achievement-definition.approve`, `credential.course-outcome.approve`, `credential.assessment-outcome.approve`, `credential.status.approve` | Cannot moderate or approve a definition or outcome they authored, assessed, initiated, or materially edited. Course-completion and assessment outcomes are separate exact grants; no generic credential-outcome grant exists. |
| Researcher | `research.project.manage`, `research.job.execute`, `research.artifact.propose` | Cannot admit an artifact into Imaging Control, Learning Catalog, Assessment, Clinical Shadow, or production model activation. |
| EQA Manager | `eqa.scheme.manage`, `eqa.draft.contribute`, `eqa.submission.seal`, `eqa.score`, `eqa.report`, `eqa.appeal` | Sealing is a single named submitter action; no AI scoring, learner authority, or post-seal edit is granted. |
| Clinical Privacy Steward | `clinical.quarantine.review`, `clinical.admission.initiate`, `clinical.grant.manage`, `clinical.snapshot.manage` | Cannot provide the independent WSI review or publish the admitted material. `clinical.snapshot.manage` is limited to `AUTHORIZE`, `WITHDRAW`, or an explicit expiry request for an exact admitted bundle, destination, purpose and audience; owner deletion remains a separate deterministic obligation. |
| WSI Reviewer | `imaging.asset.review`, `imaging.annotation.review`, `edge.local-acquisition.capture`, `clinical.admission.approve`, `publication.public.initiate` | Local Acquisition requires a current Node and User Authorization Lease and remains provisional Edge truth; this role cannot supply the final anonymous Public Release approval for a release it reviewed or initiated. |
| Publication Officer | `publication.public.approve`, `publication.withdraw` | Cannot alter source assets, bypass privacy review, approve their own proposal, or claim recovery of downloaded public copies. |
| Auditor | `audit.read`, `audit.verify`, `qualification.evidence.review` | Read-and-attest only. An Auditor signature is invalid for a context and evidence window in which that Principal performed a governed mutation or operated the measured system. |
| Operator | `platform.install`, `platform.deployment.select`, `platform.deployment.revert`, `platform.mode.operate`, `platform.backup.operate`, `platform.recovery.command`, `platform.activation.initiate`, `edge.wipe.operate` | Cannot create product-domain truth, approve activation, provide a Key Custodian share, authorize Edge retirement, or turn operational access into a domain capability. Deployment selection accepts only the exact `SELECT` or `REVERT` operation; active-release reversion requires a preceding suspension, and neither operation changes lifecycle state. `edge.wipe.operate` can execute only an already authorized bounded wipe. |
| Key Custodian | `keys.custody`, `keys.root-recovery.execute` | May act only inside a current Root Recovery Quorum; cannot command recovery, approve activation, or use recovered Service Credentials as a domain actor. |

## Owning service capability grants

Each owning context uses a distinct non-human Service Principal, database role, Service Credential, filesystem grant, and outbox identity. A Service Principal can commit only the listed deterministic family after all human approvals and policy preconditions are present; it can never initiate or satisfy a human approval, acquire another context's grant, or act through a shared database role.

| Service Principal | Owning context and capability families | Required precondition |
| --- | --- | --- |
| `svc-platform` | Platform Governance — `platform.bootstrap.commit`, `platform.install.commit`, `platform.deployment-selection.commit`, `platform.mode.commit`, `platform.portability.commit`, `platform.journey.record`, `platform.delivery-state.commit`, `platform.activation.commit` | Exact ceremony or Approval Receipts and state prerequisites from this matrix, the Delivery State Ledger, and Receipt Schema Registry. `platform.deployment-selection.commit` accepts only `SELECT` or `REVERT`, requires the exact current Operator command and deployment/health/predecessor heads, and records `FAILED` attempts without changing the projection. It records transitions but cannot supply a human authorization or product-domain decision. |
| `svc-trust` | Trust and Governance — `trust.institution.commit`, `trust.membership.commit`, `trust.policy.commit`, `trust.break-glass.commit`, `trust.legal-hold.commit`, `trust.deletion.commit`, `trust.root-recovery.commit`, `trust.approval.record`, `trust.deletion.coordinate` | Exact current policy and required Approval Receipts; deletion fans out through owner commands rather than direct foreign-table access. |
| `svc-catalog` | Learning Catalog — `catalog.cohort.commit`, `catalog.enrollment.commit`, `catalog.snapshot.commit`, `catalog.content.commit`, `catalog.publication.commit`, `catalog.progress.commit`, `catalog.progress.evaluate`, `catalog.completion.commit`, `catalog.achievement-definition.commit`, `catalog.eligibility.propose` | Immutable Catalog inputs, deterministic rule version, current Purpose Identity and accepted human publication/confirmation where required. |
| `svc-audit` | Audit and Operations — `audit.backup-operation.commit`, `audit.recovery-command.commit`, `audit.project`, `audit.checkpoint.sign`, `qualification.evidence.record` | Named source event, bounded operator command, or evidence package; projection never mutates source-domain truth. |
| `svc-gateway` | Integration Gateway — `integration.registration.commit`, `integration.receive`, `integration.quarantine`, `integration.deliver` | Active or proposed External Registration, exact Adapter Credential and frozen protocol/profile policy. |
| `svc-imaging` | Imaging Control — `imaging.upload.commit`, `imaging.annotation.commit`, `imaging.restricted-layer.commit`, `imaging.object.protect`, `imaging.asset.admit`, `imaging.derivative.publish`, `publication.public.commit`, `publication.withdraw.commit` | Validated manifest, Protection Receipt, privacy state and any required reviewer/publication approvals. |
| `svc-live` | Live Learning — `live.session.commit`, `live.interaction.commit`, `live.attendance.derive`, `live.session.recover` | Active or proposed Class Session lease, immutable snapshots, current participant authority and deterministic derivation rule. |
| `svc-authoring` | Teacher Authoring — `teacher.generation.record`, `teacher.draft.transition` | Admitted local bundle or deterministic template result; publication still requires an authorized educator. |
| `svc-assessment` | Assessment — `assessment.response-support.commit`, `assessment.item.commit`, `assessment.session.commit`, `assessment.attempt-transfer.commit`, `assessment.revision.accept`, `assessment.submission.seal`, `assessment.score.deterministic`, `assessment.grade.commit`, `assessment.high-stakes.commit`, `assessment.moderation.commit` | Active session/Attempt Lease/deadline and the required Assessor/Moderator evidence for manual or high-stakes outcomes. |
| `svc-credential` | Credential Ledger — `credential.course-outcome.commit`, `credential.assessment-outcome.commit`, `credential.issue.commit`, `credential.status.commit`, `credential.custody.commit`, `credential.verify.local` | Exact Achievement Definition Version and accepted eligibility/evidence snapshot; required dual Approval Receipts for issuance, supersession, or revocation. `credential.custody.commit` accepts only `TRANSFER`, `REJECT`, or trusted-time `EXPIRE`, binds both Institution-controlled custodians and cannot export issuer/status private keys; automatic expiry follows the frozen validity rule without inventing a human decision. |
| `svc-clinical` | Clinical Shadow — `clinical.quarantine.record`, `clinical.grant.commit`, `clinical.admission.commit`, `clinical.snapshot.commit`, `clinical.snapshot.delete` | Exact validation package, current Purpose Grant and independent privacy/WSI approvals; no writeback capability exists. `clinical.snapshot.commit` accepts only `AUTHORIZE`, `WITHDRAW`, or trusted-time `EXPIRE`; `clinical.snapshot.delete` accepts only `DELETE` from an exact owner-addressed deletion obligation. |
| `svc-research` | Research — `research.project.commit`, `research.job.dispatch`, `research.artifact-proposal.commit`, `research.artifact.receive`, `research.workspace.expire` | Signed Environment Manifest, immutable Dataset Snapshot and current quota/purpose grant. |
| `svc-eqa` | EQA — `eqa.scheme.commit`, `eqa.draft.commit`, `eqa.submission.seal`, `eqa.score.commit`, `eqa.report.release`, `eqa.appeal.commit` | Named submitter seal or frozen Scoring Version and human adjudication evidence as applicable. |
| `svc-edge` | Edge Federation — `edge.node-lifecycle.commit`, `edge.node-wipe.commit`, `edge.local-acquisition.commit`, `edge.batch.accept`, `edge.conflict.record` | Current or proposed Node identity/lease, signed ordered batch, owner-context decision and exact checkpoint. Node lifecycle accepts only `ENROLL`, `ROTATE`, `REVOKE`, or `RETIRE`; wipe requires a separately authorized retirement/emergency command and Operator execution. |

## Generated owner-handler registry

The following finite table is the canonical generator input for the machine-readable owner-handler registry. Each listed human capability resolves to exactly one owning context, one Service Principal, and one exact handler capability. Multiple human capabilities may converge on one handler only where they are the initiator/approver pair or deliberately share the same authoritative transition. Prefix, namespace, glob, regular-expression, suffix, and `*` capability grants are invalid.

| Human capability or exact pair | Owning context | Service Principal | Exact owner handler capability |
| --- | --- | --- | --- |
| `trust.institution.govern` | Trust and Governance | `svc-trust` | `trust.institution.commit` |
| `trust.membership.administer` | Trust and Governance | `svc-trust` | `trust.membership.commit` |
| `trust.policy.configure`, `trust.policy.approve` | Trust and Governance | `svc-trust` | `trust.policy.commit` |
| `trust.break-glass.initiate`, `trust.break-glass.approve` | Trust and Governance | `svc-trust` | `trust.break-glass.commit` |
| `trust.legal-hold.initiate`, `trust.legal-hold.approve` | Trust and Governance | `svc-trust` | `trust.legal-hold.commit` |
| `trust.deletion.initiate`, `trust.deletion.approve` | Trust and Governance | `svc-trust` | `trust.deletion.commit` |
| `keys.root-recovery.execute` | Trust and Governance | `svc-trust` | `trust.root-recovery.commit` |
| `platform.install` | Platform Governance | `svc-platform` | `platform.install.commit` |
| `platform.deployment.select`, `platform.deployment.revert` | Platform Governance | `svc-platform` | `platform.deployment-selection.commit` |
| `platform.mode.operate` | Platform Governance | `svc-platform` | `platform.mode.commit` |
| `platform.activation.initiate`, `platform.activation.approve` | Platform Governance | `svc-platform` | `platform.activation.commit` |
| `portability.execute` | Platform Governance | `svc-platform` | `platform.portability.commit` |
| `platform.backup.operate` | Audit and Operations | `svc-audit` | `audit.backup-operation.commit` |
| `platform.recovery.command` | Audit and Operations | `svc-audit` | `audit.recovery-command.commit` |
| `catalog.cohort.administer` | Learning Catalog | `svc-catalog` | `catalog.cohort.commit` |
| `catalog.enrollment.administer` | Learning Catalog | `svc-catalog` | `catalog.enrollment.commit` |
| `catalog.roster.capture` | Learning Catalog | `svc-catalog` | `catalog.snapshot.commit` |
| `catalog.author`, `catalog.draft.contribute` | Learning Catalog | `svc-catalog` | `catalog.content.commit` |
| `catalog.publish.ordinary` | Learning Catalog | `svc-catalog` | `catalog.publication.commit` |
| `catalog.progress.confirm` | Learning Catalog | `svc-catalog` | `catalog.progress.commit` |
| `catalog.achievement-definition.initiate`, `catalog.achievement-definition.approve` | Learning Catalog | `svc-catalog` | `catalog.achievement-definition.commit` |
| `integration.registration.administer` | Integration Gateway | `svc-gateway` | `integration.registration.commit` |
| `imaging.upload.initiate` | Imaging Control | `svc-imaging` | `imaging.upload.commit` |
| `imaging.annotation.author`, `imaging.annotation.review` | Imaging Control | `svc-imaging` | `imaging.annotation.commit` |
| `imaging.restricted-layer.initiate` | Imaging Control | `svc-imaging` | `imaging.restricted-layer.commit` |
| `imaging.asset.review` | Imaging Control | `svc-imaging` | `imaging.asset.admit` |
| `publication.public.initiate`, `publication.public.approve` | Imaging Control | `svc-imaging` | `publication.public.commit` |
| `publication.withdraw` | Imaging Control | `svc-imaging` | `publication.withdraw.commit` |
| `live.session.manage`, `live.session.facilitate` | Live Learning | `svc-live` | `live.session.commit` |
| `teacher.draft.approve` | Teacher Authoring | `svc-authoring` | `teacher.draft.transition` |
| `assessment.response.support` | Assessment | `svc-assessment` | `assessment.response-support.commit` |
| `assessment.item.author` | Assessment | `svc-assessment` | `assessment.item.commit` |
| `assessment.session.manage` | Assessment | `svc-assessment` | `assessment.session.commit` |
| `assessment.attempt.transfer` | Assessment | `svc-assessment` | `assessment.attempt-transfer.commit` |
| `assessment.grade.ordinary` | Assessment | `svc-assessment` | `assessment.grade.commit` |
| `assessment.high-stakes.initiate`, `assessment.high-stakes.approve` | Assessment | `svc-assessment` | `assessment.high-stakes.commit` |
| `assessment.moderate` | Assessment | `svc-assessment` | `assessment.moderation.commit` |
| `catalog.achievement.initiate`, `credential.course-outcome.approve` | Credential Ledger | `svc-credential` | `credential.course-outcome.commit` |
| `credential.assessment.initiate`, `credential.assessment-outcome.approve` | Credential Ledger | `svc-credential` | `credential.assessment-outcome.commit` |
| `credential.status.initiate`, `credential.status.approve` | Credential Ledger | `svc-credential` | `credential.status.commit` |
| `credential.custody.transfer` | Credential Ledger | `svc-credential` | `credential.custody.commit` |
| `clinical.quarantine.review` | Clinical Shadow | `svc-clinical` | `clinical.quarantine.record` |
| `clinical.grant.manage` | Clinical Shadow | `svc-clinical` | `clinical.grant.commit` |
| `clinical.admission.initiate`, `clinical.admission.approve` | Clinical Shadow | `svc-clinical` | `clinical.admission.commit` |
| `clinical.snapshot.manage` | Clinical Shadow | `svc-clinical` | `clinical.snapshot.commit` |
| `research.project.manage` | Research | `svc-research` | `research.project.commit` |
| `research.job.execute` | Research | `svc-research` | `research.job.dispatch` |
| `research.artifact.propose` | Research | `svc-research` | `research.artifact-proposal.commit` |
| `eqa.scheme.manage` | EQA | `svc-eqa` | `eqa.scheme.commit` |
| `eqa.draft.contribute` | EQA | `svc-eqa` | `eqa.draft.commit` |
| `eqa.submission.seal` | EQA | `svc-eqa` | `eqa.submission.seal` |
| `eqa.score` | EQA | `svc-eqa` | `eqa.score.commit` |
| `eqa.report` | EQA | `svc-eqa` | `eqa.report.release` |
| `eqa.appeal` | EQA | `svc-eqa` | `eqa.appeal.commit` |
| `edge.enrollment.administer` | Edge Federation | `svc-edge` | `edge.node-lifecycle.commit` |
| `edge.local-acquisition.capture` | Edge Federation | `svc-edge` | `edge.local-acquisition.commit` |
| `edge.wipe.operate` | Edge Federation | `svc-edge` | `edge.node-wipe.commit` |

The generated registry has one record per exact human capability with fields `human_capability`, `mutation_class`, `owner_context`, `service_principal`, `owner_handler_capability`, and any finite `operation_enum`; comma-grouped cells above expand into separate records. `audit.read`, `audit.verify`, and `qualification.evidence.review` are the exhaustive read/attest-only exceptions. `keys.custody` is the sole non-committing quorum-participation exception: it may contribute a share only inside a `trust.root-recovery.commit` proposal and cannot invoke the handler by itself. `platform.bootstrap.commit` is the sole pre-Membership internal ceremony; every other service capability not targeted by a human row is explicitly classified as an internal deterministic handler and still has one owner context and Service Principal. The registry freezes `platform.deployment-selection.commit={SELECT,REVERT}`, `credential.custody.commit={TRANSFER,REJECT,EXPIRE}`, `clinical.snapshot.commit={AUTHORIZE,WITHDRAW,EXPIRE}`, and `clinical.snapshot.delete={DELETE}`; an omitted, unknown or broadened operation is denied.

Generation and CI reconciliation fail closed unless: (1) the distinct mutating capability set in the Role Binding table equals the registry's human-capability key set; (2) each key has exactly one non-empty owner context, Service Principal, and handler; (3) each handler appears in exactly that Service Principal's finite grant; (4) every mutating API route, command, scheduled job, operator command, and imported-proposal entrypoint declares an exact registry key and its resolved handler; (5) implementation entrypoints and registry rows reconcile in both directions with no missing, duplicate, stale, or unreferenced entry; (6) each dual-authorization row resolves to its named handler, including `publication.public.commit`, `catalog.achievement-definition.commit`, `assessment.high-stakes.commit`, `credential.course-outcome.commit`, and `credential.assessment-outcome.commit`; (7) Deployment Selection, Credential Custody Transfer and Clinical Snapshot source transitions resolve respectively to `platform.deployment-selection.commit`, `credential.custody.commit`, and the exact `clinical.snapshot.commit`/`clinical.snapshot.delete` operation; (8) every operation-enum value equals one frozen value above; and (9) seeded unknown, wrong-owner, wrong-handler, wildcard and unknown-operation grants are rejected. Runtime authorization performs exact-string equality against the generated registry digest bound into the release and never expands a capability family.

## Incompatibility and independence rules

Role composition is additive only for ordinary capabilities. The following capability uses are incompatible for the same decision, aggregate, evidence window, or recovery action even when one Principal holds both Role Bindings:

- initiator and approver;
- Assessor and Moderator for the same Item Version, Grade, appeal disposition, or credential outcome;
- Clinical Privacy Steward and WSI Reviewer for the same clinical admission;
- WSI Reviewer and Publication Officer for the same anonymous Public Release;
- Operator or recovery commander and Key Custodian for the same root-recovery action;
- Auditor and any actor or Operator whose actions or environment are covered by the Auditor's attestation; and
- source author, importer, or material editor and the independent reviewer where a row below requires independence.

Two Role Bindings, Purpose Identities, external subjects, authenticators, or sessions resolving to the same canonical Principal never count as two people. Two Principals known to represent the same human never count as two people. Delegation, service identities, shared authenticators, batch approval, and approval by an actor whose binding changed after initiation are prohibited.

## Dual-authorization pairs

| Governed decision and capability | Initiator | Independent approver or co-authorizer | Step-up age at each act | Pending decision expiry |
| --- | --- | --- | --- | --- |
| Root recovery — `trust.root-recovery.commit` | Key Custodian A with `keys.root-recovery.execute` presents one current quorum share | Key Custodian B with `keys.root-recovery.execute` presents a different current quorum share; a named Operator commands but cannot count as either custodian | 5 minutes | 15 minutes |
| Institution policy version — `trust.policy.commit` | Administrator proposes the exact Residency Policy, Retention Schedule, guardian rule, and effective time | Owner independent of the policy preparation and affected case work | 5 minutes | 1 hour |
| Break-Glass Grant — `trust.break-glass.commit` | Owner states the named incident, target Principal, least privilege and duration | A different current Owner or Administrator who is not the target or incident Operator | 5 minutes | 15 minutes; an issued grant lasts at most 30 minutes |
| Legal Hold create, extend or release — `trust.legal-hold.commit` | Administrator identifies exact authority, scope, encrypted package or live records, and expiry | Owner independent of the governed case work | 5 minutes | 1 hour |
| Deletion Saga start — `trust.deletion.commit` | Administrator supplies subject, scope, inventory and hold check | Owner independent of the affected case work | 5 minutes | 1 hour |
| Clinical admission — `clinical.admission.commit` | Clinical Privacy Steward | WSI Reviewer who did not prepare or submit the source package | 5 minutes | 24 hours, never beyond the 24-hour quarantine ceiling |
| Anonymous Public Release — `publication.public.commit` | WSI Reviewer | Publication Officer | 5 minutes | 24 hours |
| Achievement Definition Version — `catalog.achievement-definition.commit` | Instructor | Moderator independent of the Course, completion-rule and evidence authoring | 5 minutes | 24 hours |
| High-stakes Grade creation or change — `assessment.high-stakes.commit` | Assessor | Moderator independent of the item authoring and assessment | 5 minutes | 24 hours |
| Course-completion credential outcome — `credential.course-outcome.commit` | Instructor responsible for the accepted Completion Evidence | Moderator independent of authoring and completion confirmation | 5 minutes | 24 hours |
| Assessment credential outcome — `credential.assessment-outcome.commit` | Assessor responsible for the accepted Grade evidence | Moderator independent of item authoring and grading | 5 minutes | 24 hours |
| Credential supersession or revocation — `credential.status.commit` | Administrator states the governed cause and affected issuance | Moderator verifies evidence and minimum disclosure | 5 minutes | 24 hours |
| Full-Surface activation — `platform.activation.commit` | Operator identifies the exact deployed release, host and evidence heads | Owner accepts the claims, review date and rollback target | 5 minutes | 4 hours |

Both acts are required before the owning context commits the decision. The second act approves the exact immutable proposal hash; any change to subject, target, evidence, policy, release, host, key version, claim, or expiry invalidates prior approval. Failure, rejection, or expiry leaves the proposal non-authoritative and emits a terminal approval result; it never falls back to single-person execution.

## Single-person governed actions

These actions deliberately do not require a second person, but still require the named current Role Binding and an attributable receipt:

| Action | Actor | Step-up and expiry |
| --- | --- | --- |
| Publish or archive an ordinary non-clinical Lesson | Instructor | Authentication no older than 15 minutes; proposal expires after 24 hours or any source-version change |
| Publish an ordinary formative Item Version | Instructor or Assessor | Authentication no older than 15 minutes; proposal expires after 24 hours or any scoring-version change |
| Approve a Teacher Authoring Draft for submission | Instructor | Authentication no older than 15 minutes; approval ends when the Draft changes |
| Finalize an ordinary non-high-stakes Grade | Assessor | Step-up no older than 15 minutes; grading proposal expires after 24 hours |
| Transfer one active Attempt to another device | Assessor | Step-up no older than 5 minutes; authorization expires after 15 minutes or first use |
| Seal one EQA Participant submission | EQA Manager acting as the named EQA Submitter | Step-up no older than 5 minutes; seal authorization expires after 15 minutes |
| Execute one signed Research Job | Researcher | Step-up no older than 15 minutes; authorization is bound to one Environment Manifest and expires after 4 hours if unused |
| Enroll, rotate, revoke, or retire an Edge Node | Administrator | Step-up no older than 5 minutes; pending action expires after 1 hour |
| Execute a bounded Edge Node wipe after authorized retirement or emergency disposition | Operator | Step-up no older than 5 minutes; one target Node and one-use command; cannot authorize retirement or claim an unreachable wipe |
| Export or import a Portable Institution Package | Administrator | Step-up no older than 5 minutes; authorization expires after 4 hours and is bound to package and target hashes |

## Step-up and expiry enforcement

Step-Up Authentication uses a phishing-resistant, Institution-enrolled WebAuthn authenticator. Its age is measured from a successful server challenge against trusted server time. A password, remembered browser session, external LMS launch, API credential, user-presence-only gesture, or offline Edge lease cannot satisfy step-up.

Before commit, the owning context re-resolves both Memberships, required Role Bindings, authenticator state, Institution policy, target version, evidence hash, and separation rules. Revocation, withdrawal, role mutation, policy change, key rotation that invalidates a signature, clock uncertainty, or unavailable Trust authority rejects the action. Pending approvals are never extended automatically; a retry creates a new proposal and new approvals.

## Required evidence contract

Every governed proposal records a unique request identity, Institution, capability, target type and immutable target hash, initiator Principal and Role Binding versions, required approver role, policy and Key Versions, creation and expiry, and the reason. Each act records its server challenge, trusted time, Principal, Role Binding version, decision and signature reference without storing authenticator secrets.

The owning context commits the authoritative transition and its outbox event atomically. Audit and Operations receives the proposal and decision projection, separation result, step-up ages, expiry result and source event identity. An Approval Receipt identifies the completed or terminally rejected request; it cannot be synthesized from logs or an external provider response.
