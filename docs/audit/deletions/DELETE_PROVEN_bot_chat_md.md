# DELETE_PROVEN: `docs/bot-chat.md`

**Status:** PROVEN UNUSED AS SEEDS — removed from git in cleanup reorg  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg  
**Commit:** `270b079` (path removed); evidence expanded in follow-up LOC cleanup commit

## Path removed from git

- `docs/bot-chat.md` (815 lines)

## Former purpose

Runtime / ops log dump captured into markdown: smart-messaging scheduler prints, API call lines (`get_missed_appointments`, template send payloads), HTTP access log lines, and partial WhatsApp/API error bodies. Not product documentation and not a design doc.

## Evidence (no imports / no seeds)

| Check | Result |
|---|---|
| Python/JS `import` / `from` of this path | **None** (`rg` over repo excluding the file itself; only audit CSVs listed the path by name) |
| Code references to `docs/bot-chat` or `bot-chat.md` as a seed | **None** |
| `LINASBOT_DATA_ROOT` / durable CM seeds | **N/A** — not app_settings / templates / qa_pairs / knowledge / style / price |
| File content shape | Log dump (API Call / Statistics / Payload / Response / INFO HTTP lines); no module exports |

## Sensitivity note

Contained truncated API key display, phone numbers in payloads, and HTTP error bodies. Removing from git reduces residual PII/ops-secret surface; see also `docs/audit/PII_EXPOSURE_REPORT.md`.

## Replacement

None required. Local runs regenerate equivalent logs under ignored `logs/` (or operator terminals).

## Tests run

Not required for log-dump deletion; no application import of this file.
