# Trust and Governance

This context owns who may act in PathLab, the institution under which they act, and identities separated for a specific governed purpose.

## Language

**Principal**:
The canonical human or service identity that can authenticate to PathLab.
_Avoid_: User, account, email identity

**Institution**:
An organization operating or participating in a governed PathLab deployment.
_Avoid_: Tenant, customer, organization account

**Membership**:
The relationship permitting a Principal to act within one Institution.
_Avoid_: User record, enrollment

**Role Binding**:
An institution-scoped assignment of named responsibilities and capabilities to a Membership.
_Avoid_: User type, global role

**Dual Authorization**:
Approval by two distinct authenticated people holding the required current Role Bindings for one governed high-risk decision.
_Avoid_: Two roles, second click, four-eyes flag

**Capability Grant**:
The purpose- and Institution-bound permission derived from a current Role Binding for one named class of governed action.
_Avoid_: Role access, permission flag, admin right

**Approval Request**:
An immutable, expiring proposal naming one governed decision, target, evidence hash, initiator and required independent approval.
_Avoid_: Pending action, confirmation dialog, approval task

**Approval Receipt**:
Immutable evidence that the exact Approval Request reached an approved, rejected or expired result under its Role Binding, independence and Step-Up Authentication rules.
_Avoid_: Audit log, second click, success message

**Purpose Identity**:
A context-specific identifier that prevents a learner, research participant, or EQA participant from being correlated beyond an authorized purpose.
_Avoid_: Alias, username, global learner ID

**Guest Participation**:
Pseudonymous participation in a non-credit Class Session that creates no durable learner evidence and does not establish a Membership or Purpose Identity.
_Avoid_: Guest learner, temporary account, anonymous enrollment

**External Subject Mapping**:
A verified relationship between a Principal or Membership and the registration-or-issuer, client, and subject identity asserted by an optional external system.
_Avoid_: Email match, imported user

**Residency Policy**:
A versioned Institution declaration naming the jurisdictions and physical or logical locations approved for each governed data class, including primary storage, processing, backup, and export.
_Avoid_: Deployment region, server location

**Approved Data Location**:
A verified storage or processing target that satisfies the current Residency Policy and has an auditable operator, jurisdiction, purpose, and transfer path.
_Avoid_: Free cloud region, available bucket

**Transfer Grant**:
An explicit, purpose-bound authorization to move a governed data class between Approved Data Locations.
_Avoid_: Network access, export permission

**Retention Schedule**:
A versioned Institution selection of retention periods by governed data class that may not exceed PathLab's enforced Retention Ceilings.
_Avoid_: Cleanup setting, archive policy

**Retention Ceiling**:
The longest period PathLab permits a governed data class to remain after its named lifecycle event.
_Avoid_: Default retention, suggested duration

**Legal Hold**:
An explicit, scoped, expiring, and audited suspension of scheduled deletion for named records held in live governed storage or a separate encrypted hold package under a documented authority. It never extends ordinary backup retention.
_Avoid_: Keep forever, protected flag

**Deletion Receipt**:
Immutable evidence identifying the governed records, derivatives, caches, indexes, synchronization or export copies, and backup-expiry obligations removed or made irrecoverable by a deletion operation.
_Avoid_: Deleted flag, trash entry

**Deletion Saga**:
The fail-closed Institution deletion process that remains incomplete until every owning context returns its required Deletion Receipt.
_Avoid_: Cascade delete, cleanup job, account deletion

**Root Recovery Quorum**:
The offline two-of-three operator custody required to recover the encrypted production key hierarchy after host loss.
_Avoid_: Master password, recovery file

**Credential Bundle**:
An encrypted, versioned package of least-privilege service credentials that an authorized operator unlocks into root-controlled volatile storage after boot.
_Avoid_: Environment file, secrets folder

**Key Version**:
An immutable identity for one data-encryption, token-signing, manifest-signing, or audit-integrity key together with its purpose and lifecycle state.
_Avoid_: Secret, current key

**Key Rotation**:
A governed transition that activates a new Key Version, preserves only the bounded decrypt/verify path required by retention, and produces authoritative audit evidence.
_Avoid_: Replace secret, regenerate key

**Encrypted Data Volume**:
The operator-unlocked LUKS2 filesystem containing PostgreSQL, private objects, WAL staging, and authoritative audit data, keyed through the Root Recovery Quorum.
_Avoid_: Encrypted disk, provider encryption

**Field Encryption Policy**:
The purpose-specific envelope-encryption rule for high-risk application fields or artifacts, naming their Key Version, authorized decrypting context, rotation, and cryptographic-deletion behavior.
_Avoid_: Encrypted column, sensitive flag

**Privileged Authentication**:
The password-plus-WebAuthn ceremony required for an administrator or educator Membership to exercise privileged capabilities.
_Avoid_: Login, MFA enabled

**Recovery Code Set**:
A sealed, hashed, single-use set of recovery grants issued to one Principal when a second platform authenticator is unavailable.
_Avoid_: Backup codes, reset token

**Break-Glass Grant**:
A time-bounded privileged recovery authorized by two distinct Institution officers, restricted to a named incident and captured in authoritative audit evidence.
_Avoid_: Super-admin login, emergency password

**Learner Identifier**:
An opaque, Institution-scoped identifier assigned to one learner Membership without requiring an email address or exposing a purpose-specific identity.
_Avoid_: Email, student number, username

**Activation Grant**:
A single-use, expiring Institution issuance that permits one Learner Identifier to establish its first local credential.
_Avoid_: Invite link, temporary password

**Recovery Grant**:
A staff-issued, single-use, expiring authorization to replace a learner credential and revoke every existing session after identity verification.
_Avoid_: Password reset, recovery email

**Processing Grant**:
An Institution-declared legal or purpose basis naming the governed subject class, allowed processing, responsible authority, guardian requirement when applicable, effective period, and withdrawal behavior.
_Avoid_: Consent checkbox, terms accepted

**Minor Status**:
The minimum necessary age band or minor/non-minor classification required by a Processing Grant without collecting a full date of birth by default.
_Avoid_: Age, birthday, child account

**Session Grant**:
An opaque, server-side, revocable authentication state delivered only through a secure HttpOnly cookie and bounded by role-specific idle and absolute expiry.
_Avoid_: JWT, login cookie

**Step-Up Authentication**:
A fresh authentication ceremony required immediately before a named sensitive action regardless of an otherwise valid Session Grant.
_Avoid_: Confirm password, extra prompt
