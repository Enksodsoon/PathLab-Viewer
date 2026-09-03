# P0-T04 `combine-errors` removal

## Disposition

`combine-errors@3.0.3` is removed from the resolved dependency graph and release inventory. Its
only path was the Node file-backed URL-storage cleanup branch in `tus-js-client@4.3.1`; PathLab's
single tus consumer is the browser upload transport.

The stable upstream package remains pinned at the exact npm artifact already recorded by P0-T03
under the MIT license. A content-addressed pnpm patch removes the unresolved dependency and uses
the Node 18+ native `AggregateError` only when both the storage operation and lock release fail.
The patch preserves the prior callback contract used by that branch: the joined message,
`MultiError` name, both error objects, and both stacks. The normal release-failure and browser
upload behavior are unchanged.

The package-manager hook removes the dependency before resolution; the lock binds both the hook
checksum and exact patch SHA-256. No mutable fork, prerelease upgrade, hosted service, or new
runtime package is introduced. The upstream MIT license and existing tus source/notice evidence
continue to govern the patched distribution, and this document records the local modification.

## Validation

```text
pnpm install --frozen-lockfile
python scripts/validate_combine_errors_removal.py
node tests/supply-chain/test_tus_error_aggregation.mjs
python -m pytest -q tests/backend/test_combine_errors_removal.py
pnpm lint
pnpm test
pnpm build
```

The validator rejects a reintroduced resolution, inventory record, unbound patch, or changed
patch bytes. The Node characterization check covers the patched two-error and original-error
branches. Existing web tests cover the browser upload transport.

## Boundaries and rollback

This task changes only dependency resolution and the narrow third-party Node cleanup branch. It
does not change upload protocol behavior, production configuration, schemas, migrations,
deployment, qualification, or activation. Rollback is reversal of the P0-T04 merge commit.
