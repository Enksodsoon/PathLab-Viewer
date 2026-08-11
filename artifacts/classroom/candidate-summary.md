# Lightweight Classroom candidate summary

## Identity

- Base SHA: `ec97febbb9706f4b1109ba8fa45c3f807b3ff510`
- Branch: `codex/lightweight-classroom`
- Feature default: `PATHLAB_CLASSROOM_ENABLED=false`
- Merge/deployment/activation: not performed

## Validation

| Check | Candidate result |
| --- | --- |
| Backend suite | 444 collected; full run passed with 4 existing skips |
| Frontend suite | 35 files, 232 tests passed |
| Ruff | Passed |
| mypy strict | Passed, 36 source files |
| ESLint | Passed with zero warnings |
| TypeScript + production build | Passed |
| Docker Compose config | Passed with non-production placeholders |
| Disabled-mode browser check | Passed; no classroom request or page bundle |
| Screenshot unit checks | 3 passed |
| Screenshot browser matrix | Chromium, Firefox, WebKit, mobile Chromium: 4 passed |
| Screenshot network check | No screenshot/notebook upload request observed |

## Bundle comparison

| Asset | Baseline | Candidate | Change |
| --- | ---: | ---: | ---: |
| HTML-linked app JS raw | 222.31 kB | 223.31 kB | +1.00 kB (+0.45%) |
| HTML-linked app JS gzip | 70.88 kB | 71.08 kB | +0.20 kB (+0.28%) |
| OpenSeadragon lazy JS gzip | 90.72 kB | 88.91 kB | -1.81 kB |

Classroom-only lazy assets are not loaded during ordinary disabled-mode use:

- teacher page: 4.71 kB raw / 1.85 kB gzip;
- student page: 12.41 kB raw / 4.97 kB gzip;
- shared classroom API: 2.18 kB raw / 0.65 kB gzip;
- classroom CSS: 3.68 kB raw / 1.23 kB gzip.

Hashed chunk sizes can move slightly because Vite repartitions shared modules. The protected
comparison is the HTML-linked application chunk and the disabled-mode network test.

## Certification boundary

The protocol-level harness is `tests/load/classroom_sse.py`. The long 300-client restart,
churn, cold-tile, and two-hour release soak were intentionally not run in this bounded local
implementation pass. Production capacity is therefore **NOT CERTIFIED**. No result has been
inferred from the harness or from earlier viewer-only capacity work.
