# Security-control and egress baseline

P0-T11 freezes the ownership and reconciliation baseline for security work. It does not remediate a control, certify ASVS compliance, assess an exact release, enforce host firewall policy, deploy, qualify, or activate PathLab.

## Authority and source receipt

- Starting default branch: `5f5b2cad86261b9172caa2ac862841f7e4c46828`.
- Dependencies: P0-T01 merged by `c62b11172e95f2246def92aabf77ff7925413eb7`; P0-T03 merged by `b35e48d25684fab9a5f09daef6bee7f26638c67e`.
- Ratified policy: ADR 0122 and `docs/architecture/PRODUCTION_QUALIFICATION.md`.
- ASVS source: OWASP ASVS 5.0.0 release tag `v5.0.0_release`, commit `5cf9b032440be53ce345ab3c130fda46ba1ce7a2`, flat-English JSON blob `f7ae2926598c4648ff7614a6968e4c8fd89524bd`, content SHA-256 `8201b20eec2908c3380ac600c91c8ba746346fbb808859366abb232027532311`, CC-BY-SA-4.0.

The machine-readable map in `asvs-5.0.0-l2-map.json` reconciles all 253 Level 1/2 controls by chapter. It assigns later-task owners to 217 applicable controls and carries control-level N/A evidence for 29 OAuth/OIDC and seven WebRTC controls because those surfaces do not exist in Full-Surface v1. Adding either surface invalidates its N/A disposition and requires remapping before exposure. The upstream standard text is not vendored here, and this receipt does not clear the separate offline-corpus admission gate.

## Surfaces and data flow

The current source reconciles 167 backend method/path registrations, including decorator and `add_api_route` registrations, and 14 frontend routes. `security-surface.json` binds those sets by SHA-256 and classifies them by first matching rule. A route change without an explicit class and owner task fails validation.

```text
Public or Institution browser
  -> public TLS / Caddy
     -> Web frontend
     -> API and public object delivery
     -> private tile service
     -> classroom and study session endpoints
        -> PostgreSQL and local object storage

Institution operator
  -> bounded OCI/Bastion control path
     -> deployment host and private service cell

Institution-owned Backup Target
  -> purpose-bound pull grant on Production
  <- signed protection/verification receipt
```

Trust boundaries are the public TLS edge, authenticated administrator session, capability-bearing public/invitation route, internal service cell, production persistence boundary, operator control plane, and independent Backup Target. The principal threats are injection and unsafe file handling, broken authentication/session/authorization, capability leakage, private-pixel or answer disclosure, request forgery and undeclared egress, dependency/build substitution, signing or encryption-key compromise, audit suppression, and backup credential inversion. Ownership is assigned in the ASVS map and route/egress inventories; implementation and exact-release evidence remain with those later tasks.

## Evidence exclusions

Security evidence is fail-closed and minimized:

- `SECRET`: no credential, private key, recovery material, session token, signing material, or complete authentication header.
- `PHI_PRIVATE_PIXEL`: no private pixels, clinical identifiers, unredacted metadata, or PHI-risk payloads.
- `ASSESSMENT_ANSWER`: no learner answer, answer key, provisional journal, grade, or accommodation beyond a synthetic canary.
- `TELEMETRY`: no third-party telemetry; local evidence uses minimized identifiers, bounded timestamps, reason codes, and content hashes.

These exclusions constrain evidence collection; they do not waive a control or permit an untested path.

## Finding rule

Every finding requires an accountable owner and owning task IDs. An unresolved reachable `Critical` result is immediately `NEGATIVE`. An unresolved `High` is acceptable for release readiness only when its status is `MITIGATED`, the mitigation is independently verified, and the mitigation expires after assessment but no more than 30 days later. Otherwise the result is `NEGATIVE`. A resolved finding is retained in the exact-release assessment record. The baseline registry is intentionally empty and therefore makes no assertion that an exact release has been assessed or is secure.

## Egress baseline

`egress-inventory.json` scans production, build, backup/restore, workflow, and development-tool source for network-capable paths. Every discovered file must map to exactly one environment class and a later-task default-deny target; stale rules and undeclared paths fail validation.

The only designed external exception classes are a bounded OCI control-plane operation, Institution-approved network-identity maintenance, and Backup-Target-initiated pull plus receipt return. They are design classes, not standing permits. Hosted CI, public package registries, third-party telemetry, hosted KMS or backup, remote AI, external notification services, and paid mandatory APIs cannot become mandatory production dependencies. P0-T09 owns offline input mirroring and P1-T20 owns system-level default-deny enforcement and proof.

## Validation and rollback

Run `python scripts/validate_security_baseline.py` and `python -m pytest -q tests/backend/test_security_baseline.py`. The tests seed an unmapped route, undeclared egress, reachable Critical, unacceptable High, and missing ownership. CI runs the validator, focused tests, and Ruff before the full backend suite.

Rollback is reverting the eventual P0-T11 merge commit. A rollback removes this planning/gate baseline only; it does not imply that any later security implementation or production state changed.
