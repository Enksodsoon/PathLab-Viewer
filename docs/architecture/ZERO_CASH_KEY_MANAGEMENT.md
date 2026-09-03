# Zero-Cash Key Management

## Pinned toolchain

| Component | Pin | License | Purpose |
| --- | --- | --- | --- |
| SOPS | 3.13.3, Linux ARM64 SHA-256 `53b0abacd38ef1b12a66d6c100956691b9cefce018d91f81e73ddf7438b94d77` | MPL-2.0 | Authenticated encrypted credential documents and two-of-three Shamir reconstruction across key groups. |
| age | 1.3.2, Linux ARM64 SHA-256 `6b8dc4333c53a5a57c9e5834e3a48f92605d7154014cd07269ff3327db5d37f4` | BSD-3-Clause | Three independent passphrase-protected offline custodian identities. |
| systemd credentials | Distribution-patched systemd 250 or later, pinned through the host-image SBOM | LGPL-2.1-or-later | Host-bound, per-service credential delivery from volatile storage. |

Release admission verifies SOPS checksums, Sigstore and SLSA provenance, age checksums and Sigsum proof, and the exact distribution systemd package. Raw multi-recipient age encryption is prohibited because it grants each recipient independent decrypt authority rather than enforcing a threshold.

## Threshold structure

- Use three SOPS key groups with exactly one age recipient per group and `shamir_threshold: 2`.
- Store one opaque SOPS binary document per service credential or narrowly scoped key ring.
- Identify every data-encryption and private signing key with an immutable purpose-bound Key Version.
- Keep previous data keys decrypt-only and previous public signing keys verify-only for only the applicable retention period.
- Never persist, expose to one operator, or place two custodian identities in the same filesystem object or operator-visible process. Each custodian maintains redundant protected copies of only their own identity and supplies it independently at recovery time.

Before any Institution exists, the installation manifest may name exactly one installation-scoped, one-use `svc-platform` bootstrap public credential and its trust root. Its signed scope binds the repository identity, exact release fingerprint, installation identifier, bootstrap purpose, expiry, and non-Institution discriminator. The private half is held only in the threshold SOPS bundle and delivered as a volatile credential solely to the bootstrap controller. Bootstrap is a single atomic transaction: verify the pinned trust root and unused nonce, establish the first Institution, create a fresh Institution-bound `svc-platform` Principal/Purpose Identity and Key Version, consume the nonce, revoke and destroy the bootstrap credential, and emit the linked replacement receipt. The bootstrap credential cannot authorize ordinary governed mutations, cannot be reused or shared by installations, and leaves Institution nullable only on this pre-Institution receipt. A failed transaction creates no Institution, identity, consumption, revocation, or replacement receipt; a committed nonce can never be replayed.

## Boot and restart flow

1. Protected services remain stopped behind `pathlab-credentials.target`; a credential-free local maintenance endpoint may report that unlock is required.
2. Two custodians independently present separate protected media and passphrases to the quorum helper through distinct anonymous file descriptors; neither custodian nor the operator receives the other's identity.
3. The helper verifies `/run` is tmpfs and creates a sealed, anonymous in-memory identity bundle that is inaccessible to the operator shell. It never writes either identity or their combination to a regular file and never places private material in arguments, environment values, shell tracing, or journald.
4. The helper exposes the sealed bundle only as the `SOPS_AGE_KEY_FILE` input for its child SOPS process, reconstructs each document, and pipes its plaintext directly to `systemd-creds encrypt --with-key=host --name=<purpose>` under a versioned `/run/pathlab-credentials` directory. It closes and zeroizes every identity-bearing descriptor immediately after SOPS exits.
5. The operator verifies every expected credential by non-secret fingerprint, atomically selects the version, the helper proves descriptor zeroization, custodians unmount their own media, and the operator starts the protected target.
6. Units use `LoadCredentialEncrypted=` and receive only their own read-only credential file. Same-boot restarts reuse host-wrapped `/run` blobs; reboot or host loss clears them and requires a fresh two-custodian unlock.

The systemd host key is not recovery authority. A replacement host generates a new host key and rewraps credentials from SOPS after quorum recovery.

## Rotation and recovery gates

1. Add a replacement recipient to the affected key group.
2. Test all still-authorized custodian pairs.
3. Remove the retired recipient.
4. Run the equivalent of `sops updatekeys`, then rotate the SOPS data key.
5. Rotate affected application credentials and Key Versions when compromise is possible; wrapping-key rotation alone is insufficient.
6. Preserve only ciphertext, recipient configuration, manifests, public verification keys, pinned recovery binaries, checksums, SBOMs, and non-secret test vectors in backups.

Every rotation and at least one annual isolated replacement-host drill must prove AB, AC, and BC recovery. A failed pair, insecure credential classification, plaintext leak, weak systemd credential report, or unavailable pinned recovery binary blocks production readiness.

## Primary-data encryption

- PostgreSQL, private object files, WAL staging, and authoritative audit data reside only on an operator-unlocked LUKS2 Encrypted Data Volume.
- The volume key is recovered through the same SOPS two-of-three hierarchy and never delegated to provider-managed encryption as its authority.
- Every deletion-bound governed plaintext is envelope-encrypted before database or object persistence under an Institution-, owning-context-, purpose-, and retention-bound Key Version. Independently deletable content uses a random per-object DEK; content with the same Institution, purpose, and retention deadline may share an Institution-bound purpose-and-retention-epoch DEK. Neither a Key Version nor a DEK may cross Institution boundaries. Clinical Shadow or quarantine data, recovery material, Adapter Credentials, Provisional Journals, assessment answers, and clinical identifiers are minimum examples, not an exhaustive high-risk-only boundary.
- Decrypt privileges belong only to the owning context, and plaintext may exist only in its bounded process memory or root-controlled volatile credential path.
- Provider-side block encryption remains enabled when available as defense in depth but cannot satisfy recovery, rotation, cryptographic deletion, or portability evidence.
