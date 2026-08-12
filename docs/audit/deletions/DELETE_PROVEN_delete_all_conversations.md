# DELETE_PROVEN: scripts/delete_all_conversations.py → archive

**Status:** HARDENED then ARCHIVED (SEC-017)  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg  
**Agent:** A5

## Former path

`scripts/delete_all_conversations.py`

## New path

`archive/scripts/delete_all_conversations.py`

## Former purpose

Destructive ops CLI: stream-delete **all** Firestore conversations under
`artifacts/linas-ai-bot-backend/users/*/conversations` and all
`live_chat_index` docs. Invalidates live_chat cache after execute.

## Hardening applied before move (SEC-017)

| Guard | Behavior |
|---|---|
| Default mode | **Dry-run** (no `--execute` → no deletes) |
| Legacy `--confirm` | **Insufficient** alone; forces dry-run + warning |
| Execute | Requires `--execute` **and** `--i-understand-delete-all-conversations I_UNDERSTAND_DELETE_ALL_CONVERSATIONS` |
| Prod / real creds | Refuse unless `LINAS_ALLOW_DESTRUCTIVE_CONVERSATION_DELETE=1` **and** typed phrase |
| Dry-run vs execute both set | Dry-run wins |

## Caller proof (no HTTP / runtime callers)

| Check | Result |
|---|---|
| `rg delete_all_conversations` excluding `docs/audit/**` + `archive/**` | **Only** `tests/test_delete_all_conversations_guards.py` (unit guards) |
| `.github/workflows` | **None** |
| `modules/` `handlers/` `services/` `main.py` | **None** |
| HTTP / FastAPI route registration | **None** — shell CLI only |
| Makefile / docker entrypoints | **None** |

Historical inventory / SECURITY_FINDINGS SEC-017 rows remain as audit evidence; they are not runtime callers.

## Tests

```text
.venv/bin/python -m pytest tests/test_delete_all_conversations_guards.py -q
# 9 passed
```

## Action

1. Harden in place (commit theme: sec-017 harden).
2. `git mv scripts/delete_all_conversations.py archive/scripts/delete_all_conversations.py`
3. Point unit test loader at archive path; fix `_REPO_ROOT` for `archive/scripts/`.

**Do not run against production.** Prefer never executing; dry-run only for forensics.
