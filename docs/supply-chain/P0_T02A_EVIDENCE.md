# P0-T02A Copyright Authority Evidence

This evidence record supports the
[Copyright and Relicensing Authority Ledger](./COPYRIGHT_AUTHORITY_LEDGER.md).
It is bound to commit `7816671b0d9e531158868d820d132ed8808c0b76` and tree
`9949c859cf5e96d20a3c2162b3de224604c96af4`.

## Reproduction commands

Run from a clean checkout of the frozen commit:

```powershell
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
git rev-list --count HEAD
git ls-files
git ls-tree -r --full-tree HEAD
git log HEAD --format='%H%x09%aN%x09%aE%x09%aI%x09%s'
git shortlog -sne HEAD
git log --follow --name-status -- packages/viewer-ui/src/PathLabProductRail.tsx
git log --follow --name-status -- packages/viewer-ui/src/ViewerCanvasShell.tsx
git log -p --follow -- packages/viewer-ui/package.json
git blame --line-porcelain HEAD -- packages/viewer-ui/src/PathLabProductRail.tsx
git log HEAD --author='dependabot\[bot\]' --format='%H'
git log HEAD --regexp-ignore-case --grep='github-actions\[bot\]'
rg -n -i --glob '!pnpm-lock.yaml' --glob '!deploy/*requirements.txt' 'copyright|license|SPDX|generated|do not edit|copied from|derived from|third-party|vendor' .
gh repo view Enksodsoon/PathLab-Viewer --json nameWithOwner,owner,visibility,createdAt,url
gh api repos/Enksodsoon/PathLab-Viewer/contributors?per_page=100
gh pr view 55 --repo Enksodsoon/PathLab-Viewer --json url,title,body,author,mergedAt,mergeCommit,commits,files,reviews,comments
gh pr view 70 --repo Enksodsoon/PathLab-Viewer --json url,title,body,author,mergedAt,mergeCommit,commits,files,reviews,comments
```

The inventory digest is calculated over the byte stream from:

```powershell
git ls-tree -r --full-tree HEAD | sha256sum
git log HEAD --format='%H%x09%aN%x09%aE%x09%aI%x09%s' | sha256sum
```

On the audited Windows host, `sha256sum` was the executable bundled with Git for
Windows. The resulting digests are:

- tree listing: `43028dbd2d689ff04d0b03be2576f54e61313ab76fb5eacb2413861e4e8b5253`;
- ordered history: `a6454fb7f462b82a38b04cd6d1bc8408bc7e937588b5e353b2e149d7e3f0c884`.

Digests of derived path lists use paths sorted by Unicode code point, encoded as
UTF-8, separated by LF, with one trailing LF. This avoids shell-specific pipe
encoding.

## Repository observations

- GitHub repository owner: `Enksodsoon`, user ID `U_kgDODbOzvQ`.
- Reachable Git author identities: `Enksodsoon`/`EnkSodsoon` and
  `dependabot[bot]` only.
- GitHub contributor endpoint: 205 contributions for `Enksodsoon`, eight for
  `dependabot[bot]`.
- Pull-request inventory at the snapshot: 158 authored by `Enksodsoon`, 30 by
  `app/dependabot`.
- Root rights files: no `LICENSE`, `COPYING`, `NOTICE`, `AUTHORS`, `.mailmap`,
  `CODEOWNERS`, CLA, or DCO record.
- Reachable history contains 672 unique paths: 655 current paths and 17
  historical-only paths. No rights-file path existed in that reachable history.
- `CONTRIBUTING.md` contains workflow and security expectations but no copyright
  assignment, license grant, DCO attestation, or sign-off requirement.
- Root `package.json` is private and has no license field; `pyproject.toml` has no
  license metadata; `apps/web/package.json` is private and has no license field;
  `packages/viewer-ui/package.json` declares `AGPL-3.0-or-later`.

## Historical-only reachable paths

These 17 paths occur in the history reachable from the audit head but not in
its current tree:

```text
.superpowers/sdd/2026-07-26-claude-canvas-redesign/task-3-report.md
.superpowers/sdd/2026-07-26-claude-canvas-redesign/task-4-report.md
.superpowers/sdd/2026-07-26-claude-canvas-redesign/task-5-report.md
apps/web/src/assets/auth-histology.webp
apps/web/src/test/delete-confirmation.test.tsx
deploy/scripts/rollback-capacity-candidate.sh
docs/superpowers/plans/2026-07-19-admin-password-recovery.md
docs/superpowers/plans/2026-07-19-ome-tiff-wsi-viewer.md
docs/superpowers/plans/2026-07-26-admin-annotations.md
docs/superpowers/plans/2026-07-26-claude-canvas-redesign.md
docs/superpowers/plans/2026-07-28-compact-library-shell.md
docs/superpowers/plans/2026-07-30-ome-shared-tile-cache.md
docs/superpowers/specs/2026-07-19-admin-password-recovery-design.md
docs/superpowers/specs/2026-07-19-ome-tiff-wsi-viewer-design.md
docs/superpowers/specs/2026-07-26-admin-annotations-design.md
docs/superpowers/specs/2026-07-28-compact-library-shell-design.md
docs/superpowers/specs/2026-07-30-ome-shared-tile-cache-design.md
```

They are excluded from the current release-file classification but remain
published Git history. The audit makes no relicensing claim for them. Searching
reachable package-metadata diffs found only the AGPL license field introduced
with `packages/viewer-ui` at merge `a7875dd478a15211e3fa0ff19db02439a5f59b46`.

## Dependabot-touched current paths

Eight Dependabot-authored commits touched these 22 paths that still exist at
the audit head. The sorted path-list SHA-256 is
`4557532ef4105c1c89decc44fec9f87e6dba3b9f4531351fa6255b9d74bc31eb`.

```text
.github/workflows/capacity-certification.yml
.github/workflows/ci.yml
.github/workflows/deploy-production.yml
.github/workflows/public-capacity-load.yml
.github/workflows/security.yml
apps/web/e2e/shared-viewer-responsive.spec.ts
apps/web/package.json
apps/web/src/components/AuthPanel.tsx
apps/web/src/components/library/LibraryNavigator.tsx
apps/web/src/components/library/QuickViewRail.tsx
apps/web/src/pages/ClassroomStudentPage.tsx
apps/web/src/test/viewer.test.tsx
apps/web/vite.config.ts
deploy/Dockerfile.web
deploy/oci-cli-requirements.in
deploy/oci-cli-requirements.txt
packages/viewer-ui/package.json
pnpm-lock.yaml
pyproject.toml
scripts/check_public_repository.py
tests/backend/test_deploy_config.py
tests/backend/test_public_repository_history.py
```

Commit `408e376d6c4eb5ba6ef5b7bcfb3e98c9a5c` also contains co-author trailers for
the repository owner and `github-actions[bot]`. Because GitHub squash commits
collapse mixed changes, the bot author field cannot be treated as a rights
classification for every line.

## Claude Canvas PR #55 current paths

Forty-five paths changed by PR #55 remain at the audit head. The sorted
path-list SHA-256 is
`a07ac58be3aaa76e1799c61c43e231b751264570320184d9a5b817b416032508`.
`pnpm-lock.yaml` receives the higher-priority `GENERATED` file disposition; the
other 44 receive the conditional `CLEAN_ROOM_REQUIRED` disposition.

```text
apps/web/DESIGN.md
apps/web/PRODUCT.md
apps/web/e2e/library-responsive.spec.ts
apps/web/e2e/shared-viewer-responsive.spec.ts
apps/web/index.html
apps/web/package.json
apps/web/public/theme-init.js
apps/web/src/components/AccountSecurityDialog.tsx
apps/web/src/components/AuthPanel.tsx
apps/web/src/components/AuthPanels.tsx
apps/web/src/components/Brand.tsx
apps/web/src/components/library/AppRail.tsx
apps/web/src/components/library/FilterPanel.tsx
apps/web/src/components/library/FolderTree.tsx
apps/web/src/components/library/LibraryDialog.tsx
apps/web/src/components/library/LibraryNavigator.tsx
apps/web/src/components/library/LibraryToolbar.tsx
apps/web/src/components/library/QuickViewRail.tsx
apps/web/src/components/library/SelectionActionBar.tsx
apps/web/src/components/library/ShareDialog.tsx
apps/web/src/components/library/SlideDetailsPanel.tsx
apps/web/src/components/library/SlideViews.tsx
apps/web/src/library.css
apps/web/src/main.tsx
apps/web/src/pages/AdminPage.tsx
apps/web/src/pages/SharedViewerPage.tsx
apps/web/src/pages/ViewerPage.tsx
apps/web/src/shared-message.css
apps/web/src/shared-viewer.css
apps/web/src/styles.css
apps/web/src/test/admin.test.tsx
apps/web/src/test/auth-performance-contract.test.ts
apps/web/src/test/auth-responsive-contract.test.ts
apps/web/src/test/library-explorer.test.tsx
apps/web/src/test/library-performance-contract.test.ts
apps/web/src/test/setup.ts
apps/web/src/test/shared-viewer.test.tsx
apps/web/src/test/slide-details-panel.test.tsx
apps/web/src/test/theme.test.tsx
apps/web/src/test/viewer.test.tsx
apps/web/src/theme/ThemeControl.tsx
apps/web/src/theme/ThemeProvider.tsx
apps/web/src/theme/theme.css
apps/web/src/theme/theme.ts
pnpm-lock.yaml
```

## Binary provenance candidates

The complete binary-candidate tree subset has SHA-256
`88b05eded55c3489fcc5d4c6701e25db23ed1c19e5c37c0afe805c1b0560c238`.

| Path | Git blob | First reachable introduction |
| --- | --- | --- |
| `apps/web/src/assets/auth-histology-solace-dark.webp` | `fea057a24012abffb348f1fd3a61d723adbb0894` | `63966f39e070d6bb54507dea13376d94017f01cd` |
| `apps/web/src/assets/auth-histology-solace-light.webp` | `250560c7c1da6a6d6aeb7518f6c4b05d2a9c0b7c` | `63966f39e070d6bb54507dea13376d94017f01cd` |
| `docs/architecture/PATHLAB_FREE_CLASSROOM_SYSTEM_DESIGN.docx` | `0a022c616999fc3047fc323214d55599e9b3d728` | `78c873101e455f8f384b32e10b5bde7c1732358f` |
| `docs/design/admin-concept.png` | `99f85412e2d7f1e4780b81ae4c5b9e475345e748` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |
| `docs/design/viewer-concept.png` | `ecb89e568b05e3a2deb8ab5c353d458f5dc7d349` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |
| `docs/evidence/admin-desktop.png` | `f7f2eb7f737d5a696d844ade757da9b2187e0dd2` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |
| `docs/evidence/admin-mobile.png` | `d174d08cdf75ac67bd77a6c6873d80dd8be21b6c` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |
| `docs/evidence/viewer-desktop.png` | `e8057526ddc01605a9f06f1bbaaf5bf53dbac858` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |
| `docs/evidence/viewer-mobile.png` | `80b354f485497ed655964fcfab2db076c28ba174` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |
| `docs/evidence/viewer-tablet.png` | `e833f82fb7a4c43c298f4acbabc30925dad5d865` | `8e52c27710b89c344cd2f3574e6fa76b2df399bb` |

These are inventory observations only. P0-T05 must determine creator, source,
license/permission, permitted use, privacy class, and release disposition.

## Immutable web references

- P0-T01 receipt: [PR #190](https://github.com/Enksodsoon/PathLab-Viewer/pull/190), merge `c62b11172e95f2246def92aabf77ff7925413eb7`.
- Claude Canvas lineage: [PR #55](https://github.com/Enksodsoon/PathLab-Viewer/pull/55), merge `f94c4a1b424f912e4ae2f307444704e08704a731`.
- Shared viewer extraction: [PR #70](https://github.com/Enksodsoon/PathLab-Viewer/pull/70), merge `a7875dd478a15211e3fa0ff19db02439a5f59b46`.

## Limits

Git and GitHub metadata do not prove authorship, employment clearance,
contractor assignment, AI-provider terms, originality, or absence of copying.
Text search cannot prove that unmarked source is original. The audit therefore
fails closed and supplies facts for a human decision rather than a Codex legal
conclusion.
