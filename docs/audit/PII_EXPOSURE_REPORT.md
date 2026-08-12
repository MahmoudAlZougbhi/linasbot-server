# PII / secret exposure report (tracked candidates)

**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg  
**Scope:** First ~20 lines only of junk candidates; pattern **types** recorded — **no values**.  
**Action:** Files below remain **tracked** until owner decision. Do not rewrite git history.

## Method

- Scanned ≤20 lines per file for emails, phone-like digit runs, WhatsApp JIDs, credential assignments, JWT/API-key shapes, and free-text message fields.
- Cross-checked JSON keys / nested keys without printing field values.
- Runtime: these paths are **append/write targets** under process cwd (and durable state via `LINASBOT_DATA_ROOT` in deploy), **not** git seed content.

## Findings (leave tracked)

| Path | Exposure type(s) | Notes |
|---|---|---|
| `data/reports_log.jsonl` | Phone-like identifiers (`details.to`); `user_id`; display `user_name`; `user_gender`; nested API payload/params metadata | ~5.3MB operational report log; written via `services/api_integrations.py` (`REPORT_LOG_FILE`). Not a seed. |
| `data/analytics_events.jsonl` | Phone-like `user_id` identifiers | Written by `services/analytics_events.py`. Not a seed. (`tokens` field name is usage counts, not API secrets.) |
| `data/conversation_log.jsonl` | Free-text conversational content (`question` / `answer`) | Appended by utils training helpers; `config.py` notes it is historical and no longer loaded. Not a seed. |
| `logs/content_violations.jsonl` | Phone-like `user_id`; free-text `content` (flagged user text) | Written by `services/moderation_service.py` under `logs/`. Not a seed. |

## Explicitly not listed as credential dumps

- No private-key blocks or JWT-shaped tokens observed in the scanned windows.
- Digit runs of length 13–19 in `reports_log` aligned with phone-like identifiers, not confirmed payment-card data.

## Owner decision needed

1. Purge from git index (`git rm --cached`) + `.gitignore` (preferred; keep local/runtime copies under data root), **or**
2. Rotate/redact and replace with empty placeholders, **or**
3. Keep tracked temporarily with access controls only (not recommended).

**Do not** force-push or `git filter-repo` without an explicit owner-approved history-rewrite plan.
