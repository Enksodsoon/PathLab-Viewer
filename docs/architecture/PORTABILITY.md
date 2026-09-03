# Institution Portability

A Portable Institution Package is produced and consumed only in a protected import/export Mode Reservation.

## Package contents

- A signed top-level manifest names the source Institution, release, schema contract version, export purpose, creation and expiry, record and byte totals, context sections, encryption recipients, and every file hash.
- Each bounded context exports canonical UTF-8 JSONL records under a versioned published schema plus an identifier map and event/provenance references; no database implementation detail becomes the interchange contract.
- Original imaging objects, non-rebuildable annotations and artifacts, signed manifests, issued receipts/reports, retention and deletion state, and applicable Audit Checkpoints travel as content-addressed bytes.
- Valid governed Achievement Credentials may travel with their Achievement Definition Version, evidence snapshot, signature, status, expiry, supersession/revocation history, and a custody-transfer receipt. The destination verifies them as records issued by the source Institution; importing them cannot turn the destination into their issuer or restart validity or retention.
- Authentication Credentials, Adapter Credentials, Service Credentials, session state, private signing or encryption keys, root-recovery material, status-service secrets, host state, caches, temporary workspaces, and deterministically rebuildable derivatives are prohibited.
- The complete package is encrypted to Institution-supplied age recipients in an Approved Data Location and signed by the PathLab release key.

## Export and import gates

1. Admission reserves staging, authoritative destination, temporary verification, and safety headroom through the Storage Admission Ledger.
2. Export takes immutable per-context snapshots, verifies all object hashes and audit heads, writes canonical sections, and signs only after totals reconcile.
3. Import first performs a no-write dry run, verifies signature/decryption, rejects unsupported or ambiguous schema versions, resolves identifiers without collision, enforces current Residency and Retention policies, and reports every proposed change.
4. Accepted import writes only through context-owned commands and outboxes; a partial failure rolls the new import transaction set back or leaves it resumably quarantined, never half-authoritative.
5. Source and destination round-trip tests reconcile canonical record hashes and all non-rebuildable object hashes. N, N-1, and N-2 packages must pass or the claimed Compatibility Window is reduced and launch remains blocked.
6. External subject and system mappings arrive disabled, every integration is manually registered again, and every human or node authenticator is enrolled again. Expired records are omitted, Legal Holds are revalidated by the destination authority, and retained material follows the stricter authorized source or destination schedule without extending a source clock.

A raw PostgreSQL dump or filesystem copy remains a disaster-recovery artifact for the same deployment and is never called a portable Institution export.
