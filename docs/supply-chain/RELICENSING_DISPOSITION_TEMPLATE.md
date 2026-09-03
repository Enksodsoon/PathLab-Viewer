# Relicensing Disposition Receipt Template

This template defines the human receipt required by the `P0-T02` external
prerequisite `P0-T02-RELICENSING-AUTHORITY`. Filling this file in the repository
without a verifiable signature does not satisfy that prerequisite.

The accountable signer must review the
[Copyright and Relicensing Authority Ledger](./COPYRIGHT_AUTHORITY_LEDGER.md),
resolve every listed ambiguity, and emit an immutable signed artifact containing
all fields below.

```yaml
schema: pathlab.relicensing-disposition/1
prerequisite_id: P0-T02-RELICENSING-AUTHORITY
disposition: APPROVED | REJECTED | PARTIAL
accountable_role: copyright-and-relicensing-authority
accountable_legal_name: required
authority_basis: required-description-of-ownership-assignment-or-authorization
decision_timestamp: required-iso-8601
ledger_commit: required-full-sha
ledger_tree: required-git-tree
proposed_license: Apache-2.0
covered_paths:
  - exact-path-or-non-overlapping-pattern
excluded_paths:
  - exact-path-or-non-overlapping-pattern
third_party_paths:
  - exact-path-or-non-overlapping-pattern-and-retained-license
generated_material:
  claude_canvas_pr_55: APPROVED_WITH_BASIS | CLEAN_ROOM_REQUIRED | EXCLUDED
  other_tool_assisted_material: required-disposition-and-basis
viewer_ui:
  current_license: AGPL-3.0-or-later
  disposition: RELICENSE_APPROVED | REMAIN_SEPARATE_AGPL | CLEAN_ROOM_REQUIRED
  covered_blob_tree: required-sha256
asset_rights_boundary: required-reference-to-P0-T05-dispositions-or-explicit-exclusion
employer_client_contractor_joint_owner_claims: NONE | required-details
representations:
  owns_or_controls_listed_rights: true-or-false
  authority_to_grant_proposed_license: true-or-false
  third_party_works_not_relicensed: true-or-false
  generated_material_terms_reviewed: true-or-false
signature_method: required-verifiable-method
signature_identity: required-key-certificate-or-platform-identity
signature: required-detached-or-embedded-signature-reference
artifact_sha256: required
```

Validity is `current-for-the-P0-T02A-authority-ledger-and-proposed-license`.
Changing the ledger subject tree, covered files, proposed license, authority,
or any stated rights basis invalidates the receipt. A `PARTIAL` or `REJECTED`
disposition does not satisfy P0-T02's required `APPROVED` prerequisite; excluded
or clean-room paths must first be removed from the proposed Apache release
boundary or replaced with independently evidenced work.
