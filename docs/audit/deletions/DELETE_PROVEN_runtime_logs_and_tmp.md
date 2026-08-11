# DELETE_PROVEN: runtime logs + `.tmp_8010_*.json`

**Status:** PROVEN UNUSED AS SEEDS — untracked/removed from git in cleanup reorg  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg

## Paths removed from git

- `logs/local-backend.out`
- `logs/local-dashboard.out`
- `.tmp_8010_login.json`
- `.tmp_8010_test.json`

## Former purpose

- `logs/local-*.out` — local process stdout captures from backend/dashboard runs.
- `.tmp_8010_*.json` — one-off HTTP probe response dumps (port 8010).

## Sensitivity scan (≤20 lines)

| Path | Result |
|---|---|
| `logs/local-backend.out` | No email/phone/credential-assignment patterns |
| `logs/local-dashboard.out` | No email/phone/credential-assignment patterns |
| `.tmp_8010_login.json` | Keys `success`/`error` only; error string references password **as a word** (auth failure message), no credential value fields |
| `.tmp_8010_test.json` | Status/health-style JSON (`status`, `features`, short ASCII `message`); no auth fields |

## Runtime / seed check

| Check | Result |
|---|---|
| Required as repo seed | **No** — regenerate on local runs |
| `LINASBOT_DATA_ROOT` / durable CM seeds | **N/A** — not app_settings / templates / qa_pairs / knowledge / style / price |
| Imports of these exact tracked blobs | **None** (logs are append targets or incidental captures) |

## Replacement

- Ignore via `.gitignore` (`logs/*.out`, `.tmp_8010_*.json`).
- Sensitive runtime jsonl still tracked pending owner decision — see `docs/audit/PII_EXPOSURE_REPORT.md`.

## Tests run

Not required for log/tmp untrack; no application import of these files.
