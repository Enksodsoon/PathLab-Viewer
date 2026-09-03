# Credential Ledger

This context owns the authoritative lifecycle and verification status of Institution-issued portable learning achievements without owning learning definitions, assessment outcomes, or authentication secrets.

## Language

**Achievement Credential**:
An immutable Institution-issued assertion that one opaque subject satisfied one exact approved Achievement Definition Version using an accepted Achievement Eligibility Proposal and minimum Credential Evidence Snapshot.
_Avoid_: Credential, badge record, certificate, award row

**Credential Document**:
The immutable signed Open Badges or CLR JSON-LD representation of an Achievement Credential exchanged as a document rather than a hosted profile or API record.
_Avoid_: Badge URL, wallet record, credential endpoint

**Credential Evidence Snapshot**:
The immutable minimum evidence accepted from an owning context to support one Achievement Credential without copying its mutable workspace or complete learner history.
_Avoid_: Grade copy, transcript data, proof link

**Issuance Decision**:
The accountable Institution approval that authorizes one exact Achievement Credential for one opaque subject, immutable Achievement Definition Version, accepted Achievement Eligibility Proposal, Credential Evidence Snapshot, and validity period.
_Avoid_: Badge generation, completion event, auto-award

**Credential Status**:
The authoritative active, superseded, expired, or revoked disposition of an issued Achievement Credential.
_Avoid_: Valid flag, verification result

**Superseding Credential**:
A new Achievement Credential that corrects or replaces an earlier immutable issuance while preserving the earlier credential and their relationship.
_Avoid_: Edited badge, credential update

**Verification Grant**:
A purpose- and audience-bound authorization to disclose the minimum assertion and current Credential Status needed to verify an Achievement Credential.
_Avoid_: Public profile, badge URL, share token

**Verification Snapshot**:
A signed, time-bounded bundle of one Credential Document, issuer verification material, frozen interpretation artifacts, and status evidence sufficient to verify its state as of a stated time.
_Avoid_: Live status, credential backup, public verification page

**Local Verification Decision**:
The bounded result of checking one Credential Document against an authorized Verification Snapshot and local policy without claiming certification or current network status.
_Avoid_: Certified credential, globally valid badge, online verification

**Credential Custody**:
The Institution authority responsible for preserving an Achievement Credential's issuer identity, verification material, status, and governed lifecycle.
_Avoid_: Wallet, hosting, badge storage

**Custody Transfer Receipt**:
Immutable evidence that an Institution-controlled authority accepted continuing Credential Custody before PathLab's bounded validity or retention ends.
_Avoid_: Export complete, migration log, handoff flag
