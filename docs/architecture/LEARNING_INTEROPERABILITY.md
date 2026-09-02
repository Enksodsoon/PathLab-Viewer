# Learning and Credential Interoperability

PathLab keeps complete local learning, identity, assessment, and credential workflows while offering bounded Institution-supplied exchange profiles. An LMS, SIS, framework service, analytics endpoint, wallet, or other external system is never a mandatory runtime dependency and never becomes PathLab's domain authority.

## Authority boundaries

| Concern | PathLab authority | External role |
| --- | --- | --- |
| Courses, modules, lessons, cohorts, enrollments, achievement definitions, and immutable event rosters | Learning Catalog | OneRoster and CASE submit reviewed proposals or referenced frameworks |
| Principals, Memberships, Role Bindings, Learner Identifiers, and External Subject Mappings | Trust and Governance | LTI and OneRoster provide assertions that must resolve to existing governed identities |
| Item Versions, Exam Sessions, Attempts, Submission Receipts, scoring versions, and educator-approved Grades | Assessment | QTI exchanges declared item content; LTI launches and AGS delivers approved outcomes |
| Achievement Credential issuance, supersession, expiry, revocation, and verification status | Credential Ledger | Open Badges and CLR carry the Ledger's Institution-authorized assertions |
| External registrations, protocol credentials, validation, retries, and delivery evidence | Integration Gateway | Institution-supplied systems exchange only through an exact approved profile |

No adapter reads or writes another context's database. Valid inbound data becomes a context-owned proposal or command, and an outbound failure never changes the authoritative source record.

## Deterministic Study production boundary

- Existing Study Courses and `pathlab.study-pack/1` Study Packs are migration inputs, not a second production course, content, roster, item, or grade authority. Their course and lesson structure moves into immutable Learning Catalog Course Versions, while assessable tasks and scoring move into Assessment Item Versions and Exam Sessions.
- The learner Study journey is deterministic: immutable lesson ordering, source references, hints, response rules, scoring, progress, and completion produce the same result for the same accepted inputs. Learner-visible generation, adaptive sequencing, autonomous scoring, and model-dependent credential eligibility are prohibited.
- SmolLM2 Model Bundles remain bounded Teacher Authoring draft assistants. A model may propose material only before teacher approval and cannot publish, launch, grade, define an achievement, or request an Achievement Credential.
- TRACE-SIM remains explicitly unapproved. No production feature flag, Mode Reservation, release claim, Study path, grading path, or credential path may activate or rely on it; dormant implementation may be removed only by a separate approved change.

## External registration and identity

- Every learning integration starts with a manually approved External Registration that fixes the Institution, external issuer and endpoints, protocol and profile versions, deployment or tenant identity, scopes, mappings, Adapter Credential, data classes, retry limits, and revocation procedure.
- External subjects are exact issuer-and-subject mappings to existing Principals or Memberships. LTI launches and roster imports cannot create, merge, recover, or authenticate an identity just in time, and email is never a join key.
- Local authentication remains complete. General OIDC single sign-on is outside v1; the OIDC initiation and response used by the frozen LTI Core launch are protocol-scoped and do not create a general PathLab identity-provider dependency.
- Unknown registrations, issuers, deployments, keys, versions, scopes, roles, resource links, return targets, or subject mappings fail closed before a product context receives a command.

## LTI Tool profile

- PathLab implements **LTI Core 1.3.0** as a Tool only. Each Platform registration is manual; PathLab does not implement the Platform role or dynamic registration.
- **Deep Linking 2.0** may select only an immutable Lesson or WSI learning case, an explicitly scheduled Assessment, or an explicitly scheduled Class Session that the current Institution is authorized to expose. Clinical Shadow, administration, Teacher Authoring, Research, EQA, and arbitrary URLs cannot be launch targets.
- **Names and Role Provisioning Services 2.0** is read-only and bounded to the current context membership. Its response verifies or proposes a launch roster; it cannot silently replace Learning Catalog Enrollments or an immutable Roster Snapshot.
- **Assignment and Grade Services 2.0** supports the required read and write operations for PathLab-managed line items and results. Only an educator-approved Grade tied to a Submission Receipt and scoring version may request delivery; drafts, provisional journals, AI scores, attendance alone, and failed attempts never produce grade return.
- Every login and message validates the exact issuer, client, deployment, target link, message type and version, signature and key, audience, nonce, state, timestamps, roles, scopes, and replay boundary. Browser sessions still use PathLab Session Grants after a successful mapped launch.

## OneRoster Consumer profile

- PathLab is a **OneRoster 1.2 REST read-only Consumer** for the bounded organizations, academic sessions, courses, classes, users, and enrollments required by the External Registration. It never calls OneRoster write or delete operations.
- **OneRoster CSV 1.2.1** is the administrator-controlled offline fallback. A complete signed import set enters quarantine together, validates cross-file identifiers and enumerations, and is rejected atomically if it is partial, ambiguous, oversized, duplicated, or outside the registered Institution.
- A valid REST or CSV exchange creates an Inbound Proposal showing additions, changes, removals, conflicts, and identity mappings. An authorized Catalog action accepts the proposal as new Course, Cohort, Enrollment, and Course Version state; active Course Versions and Roster Snapshots never mutate in place.
- NRPS context membership cannot outrank an accepted OneRoster-derived Catalog version. A mismatch blocks the launch or routes to reviewed reconciliation rather than silently adding or removing a learner.
- OneRoster result and grade writeback is excluded. Approved grade delivery uses only the registered LTI AGS 2.0 profile.

## QTI and CASE profiles

- PathLab imports and exports **QTI 3.0 Assessment, Section, and Item** content using the corrected **3.0.1 artifacts** for its declared Basic auto-scoreable, hotspot, and shared-stimulus profile. Every package is quarantined, schema- and manifest-validated, rights-checked, resource-bounded, previewed, and accepted only as new immutable Assessment versions.
- The QTI claim excludes native essay and other manually evaluated text, PathLab WSI interactions, unsupported interactions or response processing, Results Reporting, Usage Data, Computer Adaptive Testing, and Portable Custom Interactions. Such native material remains usable in PathLab but cannot be labeled, silently flattened, omitted, or approximated as QTI.
- PathLab is a **CASE 1.1 read-only Consumer** of registered framework packages, documents, items, and associations. Accepted frameworks are immutable versioned references used by Learning Catalog achievement and lesson definitions; PathLab never edits the external framework or silently retargets existing content when it changes.
- Unknown extensions, executable content, unsafe URLs, unresolved dependencies, external identity fields, or a construct outside either declared profile fail closed with an exact report.

## Credential Ledger and 1EdTech credentials

- Credential Ledger is a distinct bounded context co-deployed in `pathlab-control` with its own database authority, roles, migrations, and outbox. Learning Catalog supplies immutable Institution-approved achievement definitions and Assessment supplies approved outcome evidence; neither can issue or change an Achievement Credential directly.
- Credential Ledger implements the bounded **Open Badges 3.0 Issuer and local document Verifier** and **CLR 2.0 Issuer and local document Verifier** behavior. The v1 exchange unit is an immutable JSON-LD credential document delivered or submitted through PathLab's authenticated product boundary; PathLab implements no Open Badges or CLR REST API and makes no public Host, Displayer, wallet, blockchain, hosted-network, paid-certification, or official 1EdTech role-certification claim.
- An Open Badges document's ordered `@context` begins with `https://www.w3.org/ns/credentials/v2` and `https://purl.imsglobal.org/spec/ob/v3p0/context-3.0.3.json`. A CLR document begins, in order, with that W3C context, `https://purl.imsglobal.org/spec/clr/v2p0/context-2.0.1.json`, and the same Open Badges context; exact mirrored bytes and SHA-256 digests are part of the release evidence.
- Every credential uses a W3C `DataIntegrityProof` with cryptosuite `eddsa-rdfc-2022`, RDFC-1.0 canonicalization, SHA-256 hashing, an Ed25519 `Multikey`, and `proofPurpose=assertionMethod`. JWT, JOSE, COSE, alternate proof suites, mutable key resolution, and network-fetched verification material are outside v1 and fail closed.
- The only v1 credential classes are **Course Completion** and **Assessment Achievement**. Issuance requires a currently authorized Institution and educator, Step-Up Authentication, an immutable Course Version or approved Grade and Submission Receipt, the frozen achievement definition, an opaque purpose-specific subject, an issuance purpose, and a successful policy and duplicate check.
- An issued Achievement Credential is immutable. A correction produces a superseding credential; expiry uses `validUntil`, while revocation uses a `BitstringStatusListEntry` with `statusPurpose=revocation` and an Institution-signed `BitstringStatusListCredential` under W3C Bitstring Status List v1.0. The v1 profile fixes `statusSize=1`; after safe decompression the bitstring contains at least 131,072 one-bit status entries, and `statusListIndex` is a canonical nonnegative decimal integer strictly inside that expanded bound. An undersized, oversized-beyond-policy, out-of-range, noncanonical, malformed, decompression-bomb, or wrong-purpose list is rejected. The optional status context `https://www.w3.org/ns/credentials/status/v1` is mirrored with its normative SHA-256 digest `fda5add353231e6a6884a46b12e6c75464281900cb348284d9c360f62381d9f7`; its terms are already available through the frozen VC v2 context, so processors neither require an extra context entry nor fetch it. Status changes never rewrite the signed original, and supersession remains an explicit Ledger relationship rather than an invented interoperable status.
- Verification uses an offline JSON-LD document loader that recognizes only the exact prehashed W3C, Open Badges, CLR, and status-list contexts and validates the frozen official Open Badges 3.0 and CLR 2.0 JSON schemas in safe mode. An unknown or reordered required context, unknown term, remote context or evidence fetch, schema violation, unsupported proof, key mismatch, invalid canonicalization, signature failure, absent or stale required status evidence, or malformed status-list index fails closed without returning a partial success.
- Authenticated export may include a signed Verification Snapshot containing the credential document, the exact issuer public-key material, frozen contexts and schemas, and the signed status-list snapshot with its as-of time. Local verification proves signature, schema, authority, expiry, and revocation state only as of that snapshot; it never promises current status without a newer Institution-authorized snapshot and exposes no email, public roster, complete transcript, or unrelated achievement history.
- Each credential has at most seven years of PathLab validity and verification custody. A longer-lived Institution award requires a verified custody transfer to an Institution-controlled issuer and status service before PathLab expiry; PathLab makes no indefinite-verification promise after its governed records are deleted.
- Credential signing uses a distinct Institution credential-issuer Key Version rather than a release, session, adapter, manifest, or audit key. Rotation preserves verification only for the bounded validity and custody interval, while compromise revokes affected issuance authority and invokes the audited incident process.

## Optional Caliper boundary and excluded standards

- The **Caliper Analytics 1.2 Sensor** is optional and disabled by default. An Institution may activate it only through a separate External Registration, Processing Grant, Transfer Grant when required, approved destination, minimized event policy, and successful privacy and failure qualification.
- The v1 sensor emits only the implemented Session, Reading, Media, Assessment, and Tool Use profiles. It does not emit Tool Launch, WSI pixels or coordinates, answers, prompts, free text, hidden scoring inputs, clinical content, emails, or identity-rich payloads; a purpose-specific opaque subject is used where a subject is necessary.
- Caliper delivery is non-authoritative. An unavailable endpoint queues within its declared bound or produces a failed Delivery Attempt, while local Study, attendance, Assessment, grades, credentials, and audit evidence continue from PathLab authority.
- xAPI, SCORM, Common Cartridge, and general OIDC single sign-on are excluded from v1. Supporting one later requires a named production need, a non-duplicative authority contract, an exact version and profile, and complete privacy, zero-cash, security, and interoperability qualification.

## End-to-end integration journey

The production learning exchange fixture executes one complete authority-preserving journey:

1. A manually registered OneRoster source submits a bounded roster and course exchange, which becomes a reviewed Learning Catalog proposal and new immutable Course Version and Cohort state.
2. A registered CASE service supplies an immutable competency-framework reference, and a QTI package creates admitted Item Versions under the declared subsets.
3. A manually registered LTI Platform launches an already mapped learner into the exact immutable Lesson or scheduled Assessment; NRPS membership reconciles with the frozen Roster Snapshot.
4. Assessment accepts revisions and a Submission Receipt, applies the immutable scoring version, and an educator approves the Grade.
5. AGS idempotently receives the approved line-item result without becoming grade authority.
6. Credential Ledger receives approved Course Completion or Assessment Achievement evidence and, after Step-Up Authentication, issues and verifies an Open Badge 3.0 credential.
7. Credential Ledger packages the approved achievement into a CLR 2.0 credential without exposing unrelated learner records.
8. When separately enabled, the minimized Caliper Sensor emits only the permitted event profile to the registered endpoint.

Every step has positive, negative, replay, timeout, endpoint-unavailable, credential-revocation, restart, and cross-Institution isolation fixtures. An unavailable dependency queues within its bound or fails closed at that exchange boundary; it cannot roll back an already authoritative PathLab action, invent success, skip required approval, or transfer ownership to the external system.

## Qualification and claims

- Qualification uses frozen official schemas, contexts, examples, test suites, keys, and locally mirrored artifacts for every selected profile. Credential fixtures cover the exact context order and digests, Open Badges 3.0 and CLR 2.0 safe-schema validation, `eddsa-rdfc-2022` canonicalization and Ed25519 proof verification, Bitstring Status List `statusSize=1`, at least 131,072 expanded entries, in-bound canonical indices, undersized/out-of-range/bomb rejection, revocation, expiry and supersession, offline Verification Snapshots, and fail-closed unknown-context and remote-fetch attempts; the broader suite includes independent producer and consumer fixtures, hostile packages and messages, invalid signatures and mappings, duplicate and reordered delivery, unavailable endpoints, privacy inspection, exact round-trip fields, and the complete journey above on the production ARM64 envelope.
- Each External Registration passes a synthetic rehearsal before activation and records its exact supported profile rather than inheriting a generic protocol label. A change to a Platform, SIS, framework service, issuer, endpoint, key, scope, version, mapping, or optional profile suspends that registration until its affected gates pass again.
- PathLab publishes self-conformance evidence for the exact LTI, OneRoster, QTI, CASE, Open Badges, CLR, and optional Caliper profiles. It makes no paid or official 1EdTech certification claim, universal LMS or SIS compatibility claim, guaranteed external delivery claim, or learning-outcome claim.
- No paid certification, hosted identity provider, LMS, SIS, analytics service, credential host, wallet, blockchain, or terminology service is required by the Zero-Cash Production Profile. Institution-supplied external systems and their costs remain outside the PathLab zero-new-cash claim.
