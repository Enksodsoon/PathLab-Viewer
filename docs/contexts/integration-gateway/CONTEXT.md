# Integration Gateway

This context governs exchanges with external learning, credential, institutional, imaging, clinical, EQA, media, and notification systems without transferring domain ownership to those systems.

## Language

**External Registration**:
An Institution-approved relationship with one identified external system, exact protocol profile, permitted direction, and activation evidence.
_Avoid_: Integration account, connector config

**Adapter Credential**:
A secret or key authorized only for one External Registration and its permitted exchanges.
_Avoid_: API key, shared secret

**Exchange Profile**:
The exact protocol version, role, direction, capabilities, mappings, data classes, and constraints accepted for an External Registration.
_Avoid_: Integration type, compatibility mode

**Registration Activation**:
The Institution decision that one External Registration has passed its synthetic, conformance, authorization, failure, and revocation evidence and may exchange governed data.
_Avoid_: Connector enabled, credentials saved

**Inbound Proposal**:
A validated external assertion offered to its owning context for explicit acceptance without becoming authoritative merely because the exchange succeeded.
_Avoid_: Imported record, synchronized data

**Delivery Attempt**:
One recorded effort to deliver an outbound exchange without changing the owning context's authoritative state.
_Avoid_: Sync, webhook event

**Deferred Exchange**:
An authorized exchange waiting for its permitted operating window or an unavailable external endpoint, without being represented as delivered or accepted.
_Avoid_: Pending sync, retry job

**Exchange Receipt**:
Immutable evidence of one accepted, rejected, quarantined, deferred, or delivered exchange outcome that does not replace the owning context's domain receipt.
_Avoid_: Success response, integration log

**Quarantined Exchange**:
An inbound or outbound exchange withheld from domain processing because its identity, authorization, integrity, mapping, or conformance is unresolved.
_Avoid_: Failed message, ignored message

**Authoritative Notice**:
A durable in-app message or downloadable receipt committed by its owning product context and available without an external delivery provider.
_Avoid_: Email, alert, toast

**External Notification Adapter**:
An optional Exchange Profile that attempts email or another institution-supplied notification channel without becoming evidence that the Authoritative Notice exists or was accepted.
_Avoid_: Email service, notification system
