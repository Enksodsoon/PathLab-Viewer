# Governed Product Workflows

This contract composes the product and governance decisions recorded in ADRs 0102 through 0115. It defines who may create durable truth, which workflow states carry evidence, and how data leaves or is removed from an Institution without weakening the ownership boundaries in the Context Map. The executable grants and approval pairs are frozen in the [Role and Approval Matrix](./ROLE_APPROVAL_MATRIX.md), the bounded offline deployment in the [Edge Node Profile](./EDGE_NODE_PROFILE.md), and the cross-context acceptance sequence in the [Golden Institution Journey](./GOLDEN_INSTITUTION_JOURNEY.md).

## Institution, roles, and external identity

`Institution` is the canonical public and domain term. The current `organization_id` name is a temporary internal migration field and must not create a second Organization concept in APIs, user-facing language, exchange schemas, or portable packages.

Role Bindings are Institution-scoped and composable. The governed role names are:

- Owner;
- Administrator;
- Instructor;
- Teaching Assistant;
- Assessor;
- Moderator;
- Researcher;
- EQA Manager;
- Clinical Privacy Steward;
- WSI Reviewer;
- Publication Officer;
- Auditor;
- Operator; and
- Key Custodian.

A person may hold more than one compatible Role Binding, but composing roles never satisfies a two-person requirement. Two distinct authenticated people must authorize each root recovery, clinical admission, anonymous Public Release, high-stakes grade change, and credential-bearing outcome. One authorized educator may publish an ordinary non-clinical Lesson or formative Item Version. Capability identifiers, binding incompatibilities, initiator/approver pairs, self-approval exclusions, Step-Up Authentication freshness, and pending-decision expiry are normative in the Role and Approval Matrix; an implementation may narrow a grant but may not silently broaden one.

An external subject is mapped by the tuple of external registration or issuer, `client_id`, and `sub`. A `deployment_id` binds and authorizes one launch but is not part of the person's canonical identity. Email is never an identity join key, and an ambiguous or conflicting assertion remains quarantined until explicit resolution.

PathLab may run applicable official self-tests and independent conformance checks. The Zero-Cash Production Profile does not purchase 1EdTech certification and must not claim certified status or use a certification mark on the strength of self-conformance evidence.

## Learners, guests, and minors

Any workflow that creates durable learner evidence requires an active Institution Membership and a purpose-specific Purpose Identity. This includes durable Attendance Intervals, Assessment Attempts and Grades, credential-bearing outcomes, and retained learner interactions.

A pseudonymous guest may join only a non-credit Class Session. Guest activity creates no durable learner evidence and cannot later be silently converted into an Enrollment, Attempt, Grade, attendance claim, or credential subject.

Processing a minor requires a current Processing Grant that records the Institution's applicable guardian rule. PathLab stores only the required age band or Minor Status; a full date of birth is not collected by default.

## Retention ceilings

An Institution may select shorter periods in its Retention Schedule, but it cannot exceed these workflow ceilings:

| Governed data | Named lifecycle trigger | Maximum retention after trigger |
| --- | --- | --- |
| Authoring Draft | Draft Disposition is recorded as approved, rejected, or abandoned | 90 days |
| Generation Record | The associated Draft Disposition is recorded | One year |
| Ordinary Integration Gateway or quarantined exchange payload | First trusted Gateway receipt of the payload; unresolved quarantine does not pause the clock | 30 days |
| Integration delivery receipt | The Delivery Attempt reaches its final delivered, rejected, failed, or abandoned outcome | One year |
| Course Enrollment | The Enrollment ends by completion, withdrawal, cancellation, or Course closure | Two years |
| Roster Snapshot | The scheduled Class Session, Exam Session, or EQA Round for which it was captured closes | Two years |
| Published Learning Provenance | The associated published Course Version, Lesson version, or Achievement Definition Version is archived and has no open governed reference | Seven years |
| Edge conflict evidence | The owning context records the Conflict Record's final resolution | Two years |
| Edge rejection evidence | The Platform records the final rejection in an Acceptance Receipt | Two years |
| Credential status evidence | The Achievement Credential expires or is revoked | Seven years |

Clinical material in quarantine reaches its trigger at the first trusted receipt of the clinical payload and must be removed or admitted within 24 hours even when it entered through Integration Gateway. A general integration rule, unresolved quarantine, retry, appeal, or Legal Hold can never restart a clock or extend a stricter destination-context ceiling. A valid Legal Hold follows its separate governed package or live-record policy, while ordinary backup expiry remains unchanged.

## Deletion and Legal Hold

Trust and Governance coordinates deletion as one fail-closed Deletion Saga. Each owning context must remove or make irrecoverable its authoritative records, derivatives, indexes, synchronization or export copies under PathLab control, and must identify any remaining backup-expiry obligation. It then returns a Deletion Receipt; the saga cannot report completion while any required context receipt is missing or failed.

Revocation is the truthful deletion boundary for an issued credential whose status must remain verifiable. PathLab must not describe revocation as erasing every recipient-held copy. Likewise, an anonymous Public Release may be withdrawn or de-indexed at the PathLab origin, but externally downloaded or cached copies cannot be recovered or erased by PathLab.

A Legal Hold preserves either the live governed records or a separately encrypted hold package with its own authority, scope, expiry, and access evidence. It never prolongs the ordinary backup rotation; ordinary backups continue to expire on schedule.

## Learning Catalog and Teacher Authoring

Learning Catalog is the only authority for the hierarchy:

```text
Course -> immutable Course Version -> Module -> Lesson
```

Learning Catalog is also the sole authority for immutable Achievement Definition Versions and for versioned Learner Progress Evidence and Completion Evidence produced by the deterministic learning journey. A Learner Progress Evidence version binds one learner Purpose Identity, Enrollment, exact Course Version and completed activity references. Completion Evidence freezes the deterministic rule, accepted Learner Progress Evidence versions, decision time, and accountable actor or service version. It is evidence, not a Grade or an Achievement Credential.

An Achievement Definition is the enduring Institution learning achievement. Only an approved immutable Achievement Definition Version may be evaluated. That version names its eligible Course Versions, deterministic completion rule, permitted Assessment evidence where applicable, issuer, validity policy, and minimum Credential Evidence Snapshot. Learning Catalog may emit an eligibility proposal only after the exact rule succeeds; Credential Ledger independently authorizes issuance, and Assessment remains the sole authority for Grades.

A Lesson may reference an authorized WSI asset or publication, a Class Session definition, and formative or summative Assessment material. The references preserve the authority and exact version of the owning context rather than copying its mutable state into the Catalog.

An authorized educator may publish or archive learning material. Published learning content is immutable: every edit produces a new Course Version or Lesson version with its approval and source provenance. Adaptive prerequisites are outside this contract, and the legacy Study surface cannot own a parallel Course, Enrollment, roster, or progress authority.

Learner Progress Evidence and Completion Evidence expire no later than two years after the associated Enrollment ends. An Achievement Definition Version and its approval provenance expire no later than seven years after it is archived and has no open governed reference. A separately admitted Credential Evidence Snapshot follows Credential Ledger policy rather than extending the Catalog record's clock.

Teacher Authoring owns mutable Authoring Drafts and Generation Records only. A Teacher-Approved Draft may request creation of a new Lesson or Item Version, but neither an Authoring Draft nor local model output becomes Catalog or Assessment truth directly.

## Assessment

Assessment supports these explicit Item Version response contracts:

- single choice;
- multiple choice;
- true/false;
- numeric;
- short text;
- essay;
- hotspot;
- shared stimulus; and
- native WSI point or region.

Scoring is deterministic and tied to an immutable scoring version, with manual evaluation where the response contract requires it. AI scoring and adaptive testing are prohibited, and there is no default negative marking.

An Exam Session binds its immutable content, roster, per-learner accommodations, and deterministic randomization rules. One device may hold the active Attempt binding at a time; moving an Attempt to another device requires an audited staff authorization and does not create a second Attempt. High-stakes outcomes require moderation, and a high-stakes grade change or credential-bearing outcome requires two distinct authorizers.

A learner has 30 days after result issuance to lodge an Assessment Appeal. PathLab records governed attempt, timing, reconciliation, and change evidence but provides no webcam, screen-recording, or other surveillance proctoring.

## Live Learning

The following are Durable Interactions or durable evidence when committed:

- prompts and polls;
- submitted questions and responses;
- explicitly selected and submitted workspace actions; and
- Attendance Intervals derived from validated participation evidence.

Presence, pointers, viewports, presenter-control state, temporary pins, and teaching strokes are ephemeral and never become a historical behavior stream. A learner notebook remains local to the learner's device unless the learner explicitly submits selected content; only that submitted selection may become a Durable Interaction.

## Imaging, annotations, and anonymous shares

Existing publication identifiers and private asset or annotation data may survive migration. Before Full-Surface Launch, however, every anonymous share must be re-admitted through the current Public Release and Collection Manifest review. Preserving an identifier is not approval, and a share that has not passed re-admission remains non-anonymous and inactive.

A reviewed Private Annotation Draft may become an immutable Annotation Layer Version restricted to an authenticated Learning, Research, or EQA purpose and audience. Anonymous public annotation publication is outside v1 even when the underlying image has an approved Public Release.

## EQA

Two staff members of one EQA Participant may collaborate on a draft. One authorized submitter alone performs the irreversible seal that creates the Sealed Submission; the original is never reopened or replaced, and any requested correction proceeds through an Appeal.

A named Scoring Version drives deterministic scoring, with accountable human adjudication and no AI scoring. Each participant receives only its own EQA Report. Any aggregate derived from fewer than ten participants is suppressed, and the Appeal window closes 30 days after report issuance.

## Research

A Research Job is a signed, noninteractive Python batch selected by an approved offline Environment Manifest and run only against read-only Dataset Snapshots. Arbitrary package installation, interactive notebooks, production credentials, and default network egress are prohibited.

Research outputs remain private Research Artifacts until the appropriate owning context separately reviews and admits them. Producing an artifact never activates a model, publishes learning or imaging content, or creates a clinical or diagnostic claim.

## Edge and Desktop acquisition

Edge Federation owns Edge Node enrollment, offline Local Acquisition, Node and User Authorization Leases, Sync Batches, Acceptance Receipts, and Conflict Records. Integration Gateway owns the transport adapter, while Imaging Control becomes authoritative only for assets it accepts.

Existing Desktop ingest and synchronization protocols are compatibility profiles; their availability does not establish Edge conformance. While disconnected, an Edge Node may perform Local Acquisition and read approved Catalog and asset snapshots. It may not administer identity, alter grades, authorize Publication, or run EQA, Clinical Shadow, or Research workflows offline.

The Edge Node Profile is the only Full-Surface v1 offline deployment profile. It freezes the node processes, encrypted local stores, leases and keys, signed update and wipe paths, pending-acquisition recovery copy, resource envelope, and zero-cash accounting boundary. A Desktop Compatibility Profile or an unqualified local install cannot claim Edge conformance.

## End-to-end acceptance

The Golden Institution Journey is the normative exact-order cross-context campaign. Its actors use the Role and Approval Matrix, its Edge work uses the Edge Node Profile, and every step must emit the named receipt or invariant result before the next authority transition. Passing isolated context campaigns does not replace this journey, and passing the journey does not itself authorize pilot, deployment, qualification, or activation.

## Portable Institution import

A Portable Institution Package may create or populate only a new or empty Institution. v1 does not merge a package into an Institution that already holds authoritative records.

External Subject Mappings arrive disabled and require renewed verification. External integrations must be registered again, and human authenticators must be enrolled again; Authentication Credentials, Adapter Credentials, Service Credentials, sessions, private keys, and recovery material do not travel in the package. Governed Achievement Credentials may travel only with their status and custody evidence. Expired records are omitted, a Legal Hold is accepted only after its authority is revalidated at the destination, and every imported record follows the stricter applicable source or destination Retention Schedule and PathLab ceiling.
