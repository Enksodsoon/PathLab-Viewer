# P0-T02 relicensing disposition receipt

This receipt is effective only when its containing commit is authored by the
accountable GitHub identity, carries a valid GitHub web-flow signature, and the
canonical payload recomputes to `artifact_sha256`. A missing confirmation,
invalid signature, identity mismatch, or hash mismatch invalidates the receipt.

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

## Signed disposition

The substantive payload records the accountable person's supplied decision and
the immutable repository evidence to which it applies.

```yaml
schema: pathlab.relicensing-disposition/1
prerequisite_id: P0-T02-RELICENSING-AUTHORITY
disposition: APPROVED
accountable_role: copyright-and-relicensing-authority
accountable_legal_name: Piyakawin Sodsoon
authority_basis: >-
  I, Piyakawin Sodsoon, represent that I am the repository owner and the sole
  human contributor identified by the frozen P0-T02A ledger, that I personally
  authored or otherwise own or control the rights necessary to license the
  covered material under Apache-2.0, and that no employer, client, contractor,
  or joint-owner claim limits that authority. This representation excludes the
  third-party and excluded material listed below. For covered tool-assisted
  material, I represent that I reviewed the applicable tool terms and control
  the rights required to use, modify, sublicense, and distribute the resulting
  material under the proposed license.
decision_timestamp: 2026-09-03T23:00:22+07:00
ledger_commit: 7816671b0d9e531158868d820d132ed8808c0b76
ledger_tree: 9949c859cf5e96d20a3c2162b3de224604c96af4
proposed_license: Apache-2.0
covered_paths:
  - "P0-T02A-ledger-rule-2: 44 current PR-55 paths bound by path-list SHA-256 a07ac58be3aaa76e1799c61c43e231b751264570320184d9a5b817b416032508"
  - "P0-T02A-ledger-rule-5: docs/superpowers/**"
  - "P0-T02A-ledger-rule-7: every remaining tracked path after first-match rules 1-5, bound by ledger tree 9949c859cf5e96d20a3c2162b3de224604c96af4"
excluded_paths:
  - packages/viewer-ui/**
  - apps/web/src/assets/*.webp
  - docs/design/*.png
  - docs/evidence/*.png
  - docs/architecture/PATHLAB_FREE_CLASSROOM_SYSTEM_DESIGN.docx
third_party_paths:
  - "pnpm-lock.yaml: generated dependency metadata; retain exact upstream licenses and notices"
  - "deploy/backend-requirements.txt: generated dependency metadata; retain exact upstream licenses and notices"
  - "deploy/oci-cli-requirements.txt: generated dependency metadata; retain exact upstream licenses and notices"
  - "P0-T02A-ledger-rule-6: dependency names, versions, URLs, hashes, action/container pins, and other external-work metadata retain upstream licenses and notices"
  - "assets-listed-in-docs/supply-chain/ASSET_RIGHTS_LEDGER.json: retain OFL-1.1 or MIT as recorded"
generated_material:
  claude_canvas_pr_55: >-
    APPROVED_WITH_BASIS — the accountable signer represents that the applicable
    tool terms were reviewed, that the resulting covered material may be used,
    modified, sublicensed, and distributed under Apache-2.0, and that no
    third-party work is relicensed by this disposition.
  other_tool_assisted_material: >-
    APPROVED_WITH_BASIS — the accountable signer makes the same reviewed-terms
    and controlled-rights representation for other covered tool-assisted
    expressive material; generated dependency facts and third-party works stay
    under their recorded upstream terms.
viewer_ui:
  current_license: AGPL-3.0-or-later-at-audit-subject
  disposition: CLEAN_ROOM_REQUIRED
  covered_blob_tree: b27cc56e01475061ab2168131cb174a57d2347981b1a11d96debb00556e96e65
  release_boundary_resolution: removed-by-P0-T05A-PR-199-not-relicensed
asset_rights_boundary: docs/supply-chain/ASSET_RIGHTS_LEDGER.json-at-subject-929e561db7820e48b24f26fda165ffcaabfb0049
employer_client_contractor_joint_owner_claims: NONE
representations:
  owns_or_controls_listed_rights: true
  authority_to_grant_proposed_license: true
  third_party_works_not_relicensed: true
  generated_material_terms_reviewed: true
human_confirmation: I_HAVE_REVIEWED_AND_APPROVE_THIS_FINAL_RECEIPT
signature_method: github-web-flow-signed-commit
signature_identity: "github:Enksodsoon (authenticated platform identity)"
signature: embedded-github-web-flow-commit-signature
artifact_hash_scope: "SHA-256 of canonical JSON for fields schema through representations, YAML scalar strings, UTF-8, sorted keys, compact separators"
artifact_sha256: a079277066576dfa07740e3e757f6d08094ec568e2b55b418efd479e934fcd05
```

## Verification

The immutable receipt is the final GitHub-verified commit containing this file.
Verification must confirm the author identity, GitHub signature status, exact
confirmation/signature values, canonical payload hash, ledger subject, and
unchanged third-party/exclusion boundaries before P0-T02 begins.
