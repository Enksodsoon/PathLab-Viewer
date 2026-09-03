# Contributing to PathLab Viewer

PathLab Viewer handles private pathology data. Changes must be focused, reviewable, tested, and explicit about privacy or deployment impact.

## Before making a change

1. Read [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) for the product and architecture contract.
2. Use [`docs/REPOSITORY_MAP.md`](docs/REPOSITORY_MAP.md) to identify the responsible files.
3. Confirm that the proposed change is within scope.
4. Check for an existing issue or pull request covering the same work.

Annotations, teams, galleries, raw public downloads, fluorescence controls, Z-stacks, and timepoints are outside the current product scope unless a reviewed proposal changes that contract.

## Branches and commits

Create a focused branch from the current default branch. Use a descriptive prefix such as:

- `feature/` for new behavior;
- `fix/` for defects;
- `docs/` for documentation;
- `chore/` or `cleanup/` for maintenance.

Do not rewrite shared history or force-push a branch after review has started. Keep commits narrow and explain the user-visible, operational, or security reason for each change.

Never commit credentials, recovery codes, source OME-TIFF files, generated tiles, databases, private screenshots, `.env` files, or patient information.

## Development workflow

Behavior changes require a regression test that fails before the implementation and passes afterward. Cover validation, security boundaries, state transitions, and file handling at the appropriate layer.

Documentation-only changes should still be checked for broken links, stale claims, formatting errors, and unintended disclosure of infrastructure details.

## Contribution provenance and licensing

Contributions intended for inclusion are submitted under Apache-2.0 unless a
clearly identified file or component states different terms. Add a
`Signed-off-by: Name <privacy-safe-address>` trailer to each commit to certify
the [Developer Certificate of Origin](https://developercertificate.org/).

Disclose copied, adapted, generated, or tool-assisted material in the pull
request. Identify its source and license or applicable terms, preserve required
copyright and attribution notices, and update the relevant record under
`docs/supply-chain/`. Do not submit work when ownership is unknown, the terms are
incompatible, or you lack authority to contribute it. Package names, generated
output, and repository presence are not evidence of permission. See the
[license and notice policy](docs/supply-chain/LICENSE_AND_NOTICE_POLICY.md).

Run the checks relevant to the change:

```bash
pytest tests/backend
ruff check server tests migrations
mypy server/wsi_viewer
pnpm --dir apps/web lint
pnpm --dir apps/web test
pnpm --dir apps/web build
docker compose -f deploy/compose.yaml config
```

## Pull requests

A pull request should describe:

- the problem and its user or operational impact;
- the implementation approach;
- tests and manual verification performed;
- deployment, migration, storage, or rollback considerations;
- any remaining acceptance gap.

Keep a pull request in draft while behavior is incomplete or CI is failing. A green CI run is required, but it does not replace real-file, browser, load, backup-and-restore, or infrastructure verification when those areas are affected.

## Documentation standards

Public repository documentation should be durable and product-focused. Do not commit private prompts, conversation transcripts, agent instructions, implementation scratchpads, hard-coded production addresses, temporary commit hashes, current pull-request status, or test counts that will quickly become stale.

Place durable system decisions in `docs/architecture`, operational procedures in `deploy/README.md`, and current verification evidence in `docs/evidence/QA.md`.

## Asset rights

Every committed or bundled image, icon, font, audio/video object, design source, screenshot,
derived visual, and media fixture must reconcile through
[`docs/supply-chain/ASSET_RIGHTS_LEDGER.json`](docs/supply-chain/ASSET_RIGHTS_LEDGER.json). Before
adding or changing one, record its creator, provenance, license or permission, attribution,
content hash, permitted use, privacy class, distribution scope, and release disposition in the
asset policy. Git history and repository presence are not rights evidence.

Run the frozen install, commit the asset-bearing change, regenerate the ledger against that exact
commit, and run `python scripts/validate_asset_rights_ledger.py`. Unknown assets, changed hashes,
prohibited uses, unresolved attribution, or PHI-risk must remain `BLOCKED_RELEASE`; do not mark an
asset admitted without an accountable immutable receipt. The stricter `--release` check must pass
for a release candidate. Test-only fixtures must be labeled `TEST_ONLY` and
`EXCLUDED_NON_RELEASE`, never silently treated as shipped assets.

## Security and privacy review

Before requesting review, confirm that the change cannot expose originals, temporary uploads, private derivatives, databases, logs, credentials, recovery codes, or patient data through the public web path.

Preserve generated identifiers, atomic publication, CSRF and session protections, throttling, storage admission controls, and audit redaction. Report suspected security issues privately rather than opening a public issue containing sensitive details.
