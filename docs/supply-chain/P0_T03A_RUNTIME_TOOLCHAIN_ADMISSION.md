# P0-T03A Runtime and Verification Toolchain Admission

## Result

`SUCCESS` for exact pin admission and offline-verification readiness. This result admits a
bounded Linux ARM64 runtime and verification toolchain; it does not assemble the production
mirror, select release-bound vulnerability databases, implement product behavior, deploy,
qualify, or activate anything.

The dependency receipt is P0-T03 merge `b35e48d25684fab9a5f09daef6bee7f26638c67e`.
The machine-readable ledger is `runtime-toolchain-inputs.json`. It records immutable upstream
artifacts, exact versions/revisions, SHA-256 digests, provenance evidence, license evidence,
ARM64 disposition, maintenance status, purpose, and deterministic mirror paths.

## Admitted set

- Runtime: PostgreSQL 18.6 source, PgBouncer 1.25.2 source, Caddy 2.11.4 Linux ARM64,
  and NATS Server 2.14.6 Linux ARM64 with JetStream.
- Canonical/signature/WebAuthn: `rfc8785==0.1.4`, `cryptography==50.0.1`, and
  `webauthn==3.0.0` with their full hash-locked Python closure.
- SBOM: Syft 1.51.1, CycloneDX CLI 0.33.1, and `spdx-tools==0.8.5`.
- Provenance and security: Cosign 3.1.3, SLSA Verifier 2.7.1, Grype 0.118.0, and
  OSV-Scanner 2.5.1.

Every admitted input is free software and has an ARM64 binary or an authoritative ARM64 source
build path. No paid or hosted verification service is mandatory. GitHub and PyPI are acquisition
origins only; production installation and verification consume the Institution-owned offline
mirror.

## Fail-closed controls

`runtime-toolchain-requirements.txt` freezes every Python root and transitive distribution with
hashes. `offline-scanner-policy.json` disables scanner network access and automatic database
promotion. A release must separately admit exact Grype and OSV database snapshots; a missing or
unhashed snapshot is `BLOCKED`, never silently refreshed.

The validator rejects missing members or fields, mutable source selectors, unresolved rights,
unsafe mirror paths, missing ARM64 evidence, unpinned or unhashed Python inputs, online scanner
updates, and missing release-bound database policy. With `--mirror-root`, it also rejects absent
or tampered mirrored artifacts.

## Reproduction

```text
python scripts/validate_runtime_toolchain_admission.py
python -m pytest -q tests/backend/test_runtime_toolchain_admission.py
python scripts/verify_runtime_toolchain_sources.py --cache <temporary-directory> --receipt <receipt.json>
python -m pip download --dest <temporary-wheelhouse> --require-hashes --only-binary=:all: --platform manylinux_2_34_aarch64 --platform manylinux_2_28_aarch64 --platform manylinux2014_aarch64 --implementation cp --python-version 312 --abi cp312 -r docs/supply-chain/runtime-toolchain-requirements.txt
```

The last command is intentionally networked acquisition-time verification. It downloads each
official artifact and license text to a caller-selected temporary cache, compares both hashes,
and emits only a compact receipt. Runtime validation remains offline.

## Boundaries and rollback

The repository receives documentation, exact manifests, validators, CI wiring, and tests only.
There are no product, schema, migration, runtime, deployment, or production mutations. Rollback
is reversal of the P0-T03A merge commit; any already assembled external mirror must independently
remove the corresponding manifest generation.
