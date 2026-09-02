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
- Never store two custodian identities together; each custodian maintains redundant protected copies of only their own identity.

## Boot and restart flow

1. Protected services remain stopped behind `pathlab-credentials.target`; a credential-free local maintenance endpoint may report that unlock is required.
2. Two custodians present separate protected media and passphrases through the console or a controlled root session.
3. The operator verifies `/run` is tmpfs, creates a root-only staging directory with `umask 077`, and decrypts only the two selected identities into a regular temporary file. Private material is never placed in arguments, environment values, shell tracing, or journald.
4. SOPS reads the identity file through `SOPS_AGE_KEY_FILE`, reconstructs each document, and pipes its plaintext directly to `systemd-creds encrypt --with-key=host --name=<purpose>` under a versioned `/run/pathlab-credentials` directory.
5. The operator verifies every expected credential, atomically selects the version, removes the temporary identities, unmounts custodian media, and starts the protected target.
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
- Clinical identifiers, recovery material, adapter credentials, Provisional Journals, and any later classified high-risk data use additional application-level envelope encryption under distinct purpose-bound Key Versions.
- Decrypt privileges belong only to the owning context, and plaintext may exist only in its bounded process memory or root-controlled volatile credential path.
- Provider-side block encryption remains enabled when available as defense in depth but cannot satisfy recovery, rotation, cryptographic deletion, or portability evidence.
