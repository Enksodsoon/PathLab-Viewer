# Copyright and Relicensing Authority Ledger

## Status and boundary

This is the `P0-T02A` audit record for repository commit
`7816671b0d9e531158868d820d132ed8808c0b76`. It inventories submission history
and provenance signals; it is not legal advice, a copyright assignment, a
license grant, or permission to relicense any file.

The audit result is **NOT_EVALUABLE for relicensing authority**. Git proves who
submitted content, but the repository has no contributor license agreement,
developer certificate of origin, copyright assignment, authorship declaration,
or signed relicensing disposition. The root has no `LICENSE` or `NOTICE`, the
Python and root JavaScript metadata do not declare a license, and
`packages/viewer-ui/package.json` declares `AGPL-3.0-or-later`. ADR 0046 is a
ratified destination, not evidence that the necessary rights are held.

No file may be treated as proven PathLab-authored or admitted to the proposed
Apache-2.0 release from this ledger alone. [P0-T02](../execution/PHASE_0_CANONICAL_AND_FREEDOM.md#p0-t02--establish-root-license-and-notice-policy)
requires a current immutable signed disposition from the accountable copyright
and relicensing authority.

## Frozen audit subject

| Field | Value |
| --- | --- |
| Repository | `Enksodsoon/PathLab-Viewer` |
| Visibility at audit | public |
| Commit | `7816671b0d9e531158868d820d132ed8808c0b76` |
| Git tree | `9949c859cf5e96d20a3c2162b3de224604c96af4` |
| Tracked files | 655 |
| Unique paths in reachable history | 672 (655 current, 17 historical-only) |
| Reachable commits | 213 |
| `git ls-tree -r --full-tree HEAD` SHA-256 | `43028dbd2d689ff04d0b03be2576f54e61313ab76fb5eacb2413861e4e8b5253` |
| Ordered history inventory SHA-256 | `a6454fb7f462b82a38b04cd6d1bc8408bc7e937588b5e353b2e149d7e3f0c884` |
| Dependency receipt | P0-T01 PR #190, merge `c62b11172e95f2246def92aabf77ff7925413eb7` |

The tree-listing digest binds every current path and blob. File rules 1-5 and 7
below classify all 655 entries. A path matching more than one file rule takes
the first matching rule; rule 6 is a content-level overlay for third-party
facts embedded in otherwise repository-authored files.

## Disposition vocabulary

| Disposition | Meaning |
| --- | --- |
| `PROVEN_PATHLAB_AUTHORED` | An accountable rights holder has supplied an immutable authorship and relicensing attestation. |
| `PATHLAB_SUBMISSION_UNRESOLVED` | Git links the content to the repository owner account, but ownership and relicensing authority are not proved. |
| `GENERATED` | Tool output whose generator/input provenance and third-party notices must be preserved; generation is not independent relicensing authority. |
| `THIRD_PARTY` | External work or metadata describing external work; it retains its own license and notices. |
| `CLEAN_ROOM_REQUIRED` | Replacement or isolation is required unless a later signed disposition establishes sufficient rights. |
| `UNRESOLVED` | Creator, source, permission, or derivation is missing or ambiguous. |

## Complete file disposition rules

| Priority | Current paths | Count | Disposition | Evidence and required treatment |
| ---: | --- | ---: | --- | --- |
| 1 | `packages/viewer-ui/**` | 9 | `CLEAN_ROOM_REQUIRED` | The package declares `AGPL-3.0-or-later`; no assignment or relicensing receipt exists. Preserve the AGPL boundary until P0-T05A. A signed disposition may replace the clean-room requirement only if it covers each blob and its derivation. |
| 2 | 45 current paths changed by PR #55, excluding the overlapping generated `pnpm-lock.yaml` | 44 | `CLEAN_ROOM_REQUIRED` | PR #55 explicitly records a Claude-inspired/Claude Canvas redesign. Git records only the repository owner as submitter and provides no generator terms, prompt/source provenance, or authorship attestation. Replace or isolate unless the accountable authority supplies sufficient provenance and rights. |
| 3 | `apps/web/src/assets/*.webp`, `docs/design/*.png`, `docs/evidence/*.png`, and `docs/architecture/PATHLAB_FREE_CLASSROOM_SYSTEM_DESIGN.docx` | 10 | `UNRESOLVED` | Binary content has no embedded repository rights record. P0-T05 owns the asset-rights decision. Do not admit it as PathLab-authored source. |
| 4 | `pnpm-lock.yaml`, `deploy/backend-requirements.txt`, `deploy/oci-cli-requirements.txt` | 3 | `GENERATED` | Package-manager or `pip-compile` output. Preserve generator inputs, exact dependencies, upstream licenses, and notices. These files do not grant rights in dependencies. |
| 5 | `docs/superpowers/**` | 2 | `GENERATED` | Tool-workflow plans/specifications. No authorship or tool-terms attestation is present; keep outside an authorship claim pending a signed disposition. |
| 6 | Dependency names, versions, URLs, hashes, and action/container pins embedded in package manifests, requirements inputs, Dockerfiles, workflows, and Terraform | content overlay | `THIRD_PARTY` | Factual dependency metadata points to external works. P0-T03 must determine exact licenses/provenance; no dependency is relicensed by PathLab. The containing file's PathLab-authored arrangement or glue remains unresolved under its applicable file rule. |
| 7 | Every other tracked path in the frozen tree | remainder | `PATHLAB_SUBMISSION_UNRESOLVED` | Reachable history attributes authored commits to the owner account or Dependabot, but no rights attestation exists. Submission identity is not ownership proof. |

There are zero `PROVEN_PATHLAB_AUTHORED` files at this audit head. Rules 1 and
2 are deliberately fail-closed: if the evidence remains unavailable, their
release paths require clean-room replacement or isolation. Rule 3 is separately
blocked on the Asset Rights Ledger.

## Contributor and submission ledger

| Observed identity | Evidence | Scope | Authority disposition |
| --- | --- | --- | --- |
| `Enksodsoon` / `EnkSodsoon` | Git history, GitHub user ID `U_kgDODbOzvQ`, repository owner, 205 GitHub-counted contributions, 158 PRs at the snapshot; email values intentionally omitted from this public ledger | All human-authored commits and merges reachable from the audit head | **Accountable candidate, authority unverified.** The account owner is the only observed human contributor and repository owner, but those facts do not prove personal authorship, employer/contractor clearance, or the ability to relicense generated or third-party material. |
| `dependabot[bot]` | Eight reachable authored commits; 30 PRs at the snapshot | Dependency declarations, locks, workflow/container pins, and several repairs/tests squashed into PR #91 | Bot metadata is not a copyright authority. Third-party dependency rights remain upstream; any expressive fixes in the squash remain unresolved absent a human attestation. |
| `github-actions[bot]` | Co-author trailer in commit `408e376d6c4eb5ba6ef5b7bcfb3e98c9a5c`; no authored commit reachable from the audit head | Generated lock refresh within PR #91 | Automation only; no relicensing authority. |

No other author identity is present in `git log HEAD`. There is no `.mailmap`,
`AUTHORS`, `CODEOWNERS`, CLA, DCO policy, or signed-off-by requirement that
turns these observations into a rights grant. Branch names containing `codex/`
are workflow metadata and are not enough to determine which content was
AI-generated.

The 22 current paths ever touched by a Dependabot-authored commit are listed in
[the evidence record](./P0_T02A_EVIDENCE.md#dependabot-touched-current-paths).
Their sorted path-list SHA-256 is
`4557532ef4105c1c89decc44fec9f87e6dba3b9f4531351fa6255b9d74bc31eb`.

## `packages/viewer-ui` file ledger

The complete package tree-list SHA-256 is
`b27cc56e01475061ab2168131cb174a57d2347981b1a11d96debb00556e96e65`.
Every source line currently blames to `EnkSodsoon`; two metadata lines in
`package.json` blame to Dependabot. This remains submission evidence only.

| File | Current Git blob | Introduction/lineage | Disposition |
| --- | --- | --- | --- |
| `README.md` | `9e934d403b11b93613c0f34eb942524624dbfc3b` | Added by PR #70 / merge `a7875dd478a15211e3fa0ff19db02439a5f59b46` | `CLEAN_ROOM_REQUIRED` |
| `package.json` | `78606d9342aa55a05add6feed711b51a51320fad` | Added by PR #70 with AGPL metadata; later dependency lines from PR #91 | `CLEAN_ROOM_REQUIRED` |
| `src/AnnotationToolbar.tsx` | `62bcf078a3684a68f81152c494c952a040b2ae88` | Added by PR #70 | `CLEAN_ROOM_REQUIRED` |
| `src/PathLabProductRail.tsx` | `e5ea6d3fdd234ed77f009aa6588618962c06e75c` | PR #70 copied it at 60% similarity from `apps/web/src/components/library/AppRail.tsx`; that source was created at `b76a59fff44e9d3cf1d662fcbcb8a5c07d787c89` and changed by Claude Canvas PR #55 | `CLEAN_ROOM_REQUIRED` |
| `src/ViewerCanvasShell.tsx` | `344e2c6f1b077b3a3c3b28e09fba37a6b46c3998` | Added by PR #70 | `CLEAN_ROOM_REQUIRED` |
| `src/adapters.ts` | `7e3553e42ffb07eabcf24cd916c6376d77705816` | Added by PR #70 | `CLEAN_ROOM_REQUIRED` |
| `src/index.ts` | `64e6b953371e570ced988d14fbeac7cc800b4038` | Added by PR #70 | `CLEAN_ROOM_REQUIRED` |
| `src/styles.css` | `475ed3400251860067a6e51bf6bca44945b061d4` | Added by PR #70 | `CLEAN_ROOM_REQUIRED` |
| `src/theme.css` | `c9aba9700e3dcc353796ecc9915c2e275ba9ab6a` | Added by PR #70 | `CLEAN_ROOM_REQUIRED` |

The package contains no copyright header, SPDX header, upstream URL, or copied
source attribution. Absence of an attribution marker is not proof of original
authorship. Merely changing its `license` field would not relicense it.

## Generated and copied-material findings

- PR #55, merge `f94c4a1b424f912e4ae2f307444704e08704a731`,
  describes a Claude-inspired design and commits “Claude theme” and “Canvas
  Focus” work. Forty-five PR paths remain in the tree, including the generated
  lockfile; the sorted current path-list SHA-256 is
  `a07ac58be3aaa76e1799c61c43e231b751264570320184d9a5b817b416032508`.
- PR #70, merge `a7875dd478a15211e3fa0ff19db02439a5f59b46`,
  extracted the shared viewer package. The recorded `C060` copy lineage for
  `PathLabProductRail.tsx` is internal Git lineage, not proof that its earlier
  design source is clear.
- The two authentication WebP files, seven PNG design/evidence files, and one
  DOCX have no creator, source-license, permission, or generation receipt in the
  repository. Their exact blob inventory is in the evidence record and its
  SHA-256 is
  `88b05eded55c3489fcc5d4c6701e25db23ed1c19e5c37c0afe805c1b0560c238`.
- `pnpm-lock.yaml` and the two compiled requirements files are generated. They
  carry dependency facts and hashes, not a blanket license grant.
- No vendored source directory or source-level third-party copyright/SPDX
  notice was found outside dependency/evidence material. This negative search
  is a triage signal only, not proof of originality.
- Reachable history contains 17 deleted paths, including the earlier
  `auth-histology.webp`, Claude Canvas work reports, and generated planning
  documents. They are not in the current release tree, but this ledger makes no
  Apache-2.0 claim over their historical Git objects. No rights-file path existed
  anywhere in reachable history. The only reachable package `license` field was
  the AGPL field introduced with `packages/viewer-ui`.

## Accountable authority and required decision

The accountable role is `copyright-and-relicensing-authority`. The only named
human candidate supported by repository evidence is **EnkSodsoon**, GitHub
account `Enksodsoon` (`U_kgDODbOzvQ`), because that account owns the repository
and is the sole observed human submitter. The candidate's legal identity and
authority remain unverified; this ledger does not appoint them or infer rights.

P0-T02 may start only after that role (or a replacement authority documented by
the repository owner) emits an immutable signed disposition using
[the required fields](./RELICENSING_DISPOSITION_TEMPLATE.md). It must bind the
exact ledger commit/tree and proposed license and explicitly decide:

1. whether the authority owns or controls relicensing rights for every path
   claimed as PathLab-authored;
2. whether employer, client, contractor, institutional, or joint-owner claims
   exist;
3. the provenance and permitted use of AI/tool-generated work, especially PR
   #55 and its descendants;
4. whether each `packages/viewer-ui` blob may be relicensed from AGPL, must
   remain a separate AGPL work, or requires clean-room replacement;
5. which binary assets are excluded pending P0-T05; and
6. whether Apache-2.0 is approved for the exact admitted PathLab-authored set.

Until that receipt exists, the release admission is blocked, the current
license metadata stays unchanged, and no downstream task may convert
`PATHLAB_SUBMISSION_UNRESOLVED`, `UNRESOLVED`, or `CLEAN_ROOM_REQUIRED` into
`PROVEN_PATHLAB_AUTHORED`.

## Reproduction

The exact commands and immutable source references are recorded in
[P0-T02A evidence](./P0_T02A_EVIDENCE.md). Re-run them against the frozen commit,
not a later working tree. A later change requires a new tree digest and
incremental disposition audit.
