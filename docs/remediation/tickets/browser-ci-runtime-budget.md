# Browser CI runtime budget

Labels: wayfinder:decision

## Evidence

PR289 head556bd586 browser job111144479445 in run37102445873 attempt1 exceeded GitHub's15-minute job cap after starting case233of240. Its unchanged-head retry passed237cases/skipped3, with the browser phase taking13.0minutes. The original cancellation has no final test report and must not be counted as a passing run.

PR289 merged normally as e3f5d4403294819632416bc9b81486ab8afc183b after all nine exact-head checks passed. Fresh main browser job111149888893 in run37104359718 also exceeded the15-minute job cap, this time after starting case238of240. GitHub check annotations explicitly identify the maximum execution time. Retained logs are pr289-browser-timeout.log, pr289-browser-retry-success.log and pr289-main-browser-timeout.log in the local release evidence directory. No application defect is inferred from cancellation or incidental mocked-server proxy messages.

## Decision

Bound the complete browser job at20minutes and the browser test step at16minutes, leaving room for dependency setup and failure diagnostics. Retain diagnostics after failure or cancellation while job time remains. A hard whole-job timeout can still prevent artifact upload; keep GitHub job logs as independent evidence.

Keep all240matrix cases, all browser projects, existing per-test limits, zero test retries and two workers. Preserve the25-minute fullstack job, the1200-second normal fullstack launcher phase, stress budgets and all application capacity controls. Update the existing deployment contract check with the two bounded deadlines.

## Verification and delivery

Focused deployment-contract tests and static workflow validation precede PR review. Fresh exact-head and exact-main gates, protected production release retaining feature settings, and authenticated workflow checks remain required. Source report aliases and private source data remain unchanged. The full campaign remains open for live qualification and pending operator facts.
