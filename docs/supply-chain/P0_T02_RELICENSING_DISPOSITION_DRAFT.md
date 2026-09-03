# P0-T02 relicensing disposition draft

> **NON-EFFECTIVE DRAFT — DOES NOT SATISFY P0-T02.** This file is preparation
> material only. It is not a copyright representation, license grant,
> relicensing approval, or signed receipt. Every `PENDING_HUMAN_EDIT` value must
> be replaced by the accountable rights holder, the final artifact must be
> reviewed as a whole, and its signature and SHA-256 must be verified before the
> disposition may be recorded as `APPROVED`.

## Repository-derived preparation record

The following values were copied from immutable repository evidence and do not
depend on a legal conclusion:

- Repository: `Enksodsoon/PathLab-Viewer`.
- Proposed outbound license: `Apache-2.0`, as ratified by ADR 0046.
- P0-T02A audit subject commit: `7816671b0d9e531158868d820d132ed8808c0b76`.
- P0-T02A audit subject tree: `9949c859cf5e96d20a3c2162b3de224604c96af4`.
- P0-T02A current-tree digest: `43028dbd2d689ff04d0b03be2576f54e61313ab76fb5eacb2413861e4e8b5253`.
- P0-T02A ordered-history digest: `a6454fb7f462b82a38b04cd6d1bc8408bc7e937588b5e353b2e149d7e3f0c884`.
- P0-T02A receipt: PR #192, head `0c7da38bea5fd96be7d4dfecc3f7d6ef444ad146`, merge `79800a5d7f6ffaf0ef1280d4ef8a599a65fcbe1f`.
- The former `packages/viewer-ui/**` release boundary was removed by P0-T05A PR #199. Its retired nine-file tree remains bound by SHA-256 and is not proposed for relicensing by this draft.
- The asset ledger at P0-T05A subject `929e561db7820e48b24f26fda165ffcaabfb0049` is `ADMITTED`; it covers three OFL-1.1 fonts and the exact MIT Phosphor icon subset. It does not establish broader source-code ownership.
- Dependency names, external works, generated lock/requirements data, and their notices retain their upstream licenses and are not relicensed by PathLab.

## Prepared receipt

The invalid placeholder disposition prevents accidental use before human
completion. Replace it with exactly `APPROVED`, `REJECTED`, or `PARTIAL` only
after making the corresponding decision.

```yaml
schema: pathlab.relicensing-disposition/1
prerequisite_id: P0-T02-RELICENSING-AUTHORITY
disposition: PENDING_HUMAN_EDIT
accountable_role: copyright-and-relicensing-authority
accountable_legal_name: PENDING_HUMAN_EDIT
authority_basis: PENDING_HUMAN_EDIT_DESCRIBE_OWNERSHIP_ASSIGNMENT_OR_AUTHORIZATION
decision_timestamp: PENDING_HUMAN_EDIT_ISO_8601
ledger_commit: 7816671b0d9e531158868d820d132ed8808c0b76
ledger_tree: 9949c859cf5e96d20a3c2162b3de224604c96af4
proposed_license: Apache-2.0
covered_paths:
  - PENDING_HUMAN_EDIT_EXACT_NON_OVERLAPPING_PATHS
excluded_paths:
  - packages/viewer-ui/**
  - PENDING_HUMAN_EDIT_ANY_OTHER_EXCLUSIONS_OR_NONE
third_party_paths:
  - dependency-metadata-and-external-works: retain-exact-upstream-license-and-notices
  - assets-listed-in-docs/supply-chain/ASSET_RIGHTS_LEDGER.json: retain-OFL-1.1-or-MIT-as-recorded
  - PENDING_HUMAN_EDIT_OTHER_THIRD_PARTY_PATHS_OR_NONE
generated_material:
  claude_canvas_pr_55: PENDING_HUMAN_EDIT_APPROVED_WITH_BASIS_OR_CLEAN_ROOM_REQUIRED_OR_EXCLUDED
  other_tool_assisted_material: PENDING_HUMAN_EDIT_DISPOSITION_AND_TERMS_BASIS
viewer_ui:
  current_license: AGPL-3.0-or-later-at-audit-subject
  disposition: CLEAN_ROOM_REQUIRED
  covered_blob_tree: b27cc56e01475061ab2168131cb174a57d2347981b1a11d96debb00556e96e65
  release_boundary_resolution: removed-by-P0-T05A-PR-199-not-relicensed
asset_rights_boundary: docs/supply-chain/ASSET_RIGHTS_LEDGER.json-at-subject-929e561db7820e48b24f26fda165ffcaabfb0049
employer_client_contractor_joint_owner_claims: PENDING_HUMAN_EDIT_NONE_OR_REQUIRED_DETAILS
representations:
  owns_or_controls_listed_rights: PENDING_HUMAN_EDIT_TRUE_OR_FALSE
  authority_to_grant_proposed_license: PENDING_HUMAN_EDIT_TRUE_OR_FALSE
  third_party_works_not_relicensed: PENDING_HUMAN_EDIT_TRUE_OR_FALSE
  generated_material_terms_reviewed: PENDING_HUMAN_EDIT_TRUE_OR_FALSE
signature_method: PENDING_HUMAN_EDIT_VERIFIABLE_METHOD
signature_identity: PENDING_HUMAN_EDIT_KEY_CERTIFICATE_OR_PLATFORM_IDENTITY
signature: PENDING_HUMAN_EDIT_DETACHED_OR_EMBEDDED_SIGNATURE_REFERENCE
artifact_sha256: PENDING_AFTER_FINAL_CONTENT_AND_SIGNATURE
```

## Required human edits

Only the accountable rights holder can supply or decide these items:

1. Legal name and the factual basis for owning or controlling the covered rights.
2. Exact non-overlapping covered, excluded, and third-party path scope.
3. Whether the PR #55 Claude Canvas material is authorized with a documented terms basis, must be replaced clean-room, or is excluded.
4. The disposition and terms basis for all other tool-assisted expressive material.
5. Employer, client, contractor, or joint-owner claims and any required consents.
6. All four representations, the final disposition, and decision timestamp.
7. A verifiable signing identity/method, the signature, and the final artifact SHA-256.

Until all seven items are complete and independently verifiable, the observed
external-prerequisite disposition remains `UNAVAILABLE`; P0-T02 and its
downstream tasks must remain blocked.
