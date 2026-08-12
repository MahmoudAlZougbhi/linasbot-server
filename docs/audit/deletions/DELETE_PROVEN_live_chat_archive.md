# DELETE_PROVEN: live_chat_archive/

**Status:** PROVEN UNUSED — deleted in W09  
**Date:** 2026-08-12  
**Branch:** chore/project-cleanup-reorg

## Former purpose

Frozen snapshot of an older Live Chat stack kept after reorg:

| Archived file | Role (historical) |
|---|---|
| `live_chat_api.py` | FastAPI live-chat endpoints + SSE |
| `live_chat_routes.py` | Alternate hybrid router (client cards, 6h filter) |
| `live_chat_service.py` / `live_chat_service_old.py` | Conversation/index service implementations |
| `live_chat_contracts.py` | Request/response contracts |
| `live_chat_sse_broadcaster.py` | SSE fan-out |
| `backfill_live_chat_index.py` | One-shot index backfill script |

Not on the runtime import graph; active Live Chat lives under `modules/` and `services/`.

## Checks performed

| Check | Result |
|---|---|
| Static imports (`rg live_chat_archive`, exclude self + deletions docs) | **Only** `ruff.toml` `extend-exclude` |
| Dynamic / string path refs (`'live_chat_archive'`, `live_chat_archive/`) | Same — ruff exclude only |
| `from live_chat_archive` / `import live_chat_archive` / `sys.path` | **None** |
| Route registrations (`include_router`, main wiring) | **None** referencing archive |
| CI / `.github` workflows | **None** |
| `tests/` / fixtures | **None** |
| `main.py` | Imports `modules.live_chat_api` only — **no** archive |
| Makefile / docker / pyproject / gitignore | **None** |
| `ruff.toml` excludes | Had `"live_chat_archive"` — **safe to remove** with the tree |

Historical inventory rows in `docs/audit/TRACKED_FILE_INVENTORY.csv` and `FILES_OVER_500.csv` list these paths as audit snapshots only; they are not runtime or CI consumers.

Broader name hits for `backfill_live_chat_index` / `live_chat_routes` resolve to **active** `scripts/backfill_live_chat_index.py` and live service comments — not the archive tree.

## Replacement (active live_chat paths)

| Concern | Active path |
|---|---|
| API / routes | `modules/live_chat_api.py` (loaded from `main.py`) |
| Service | `services/live_chat_service.py` |
| Contracts | `services/live_chat_contracts.py` |
| SSE | `services/live_chat_sse_broadcaster.py` |
| Index backfill | `scripts/backfill_live_chat_index.py` |

## Tests run

```text
pytest tests/test_product_modules_disabled.py -q
```

(Import smoke via `python -c "import main"` skipped as dep-sensitive; product-modules pytest used per W09.)

## Action

`git rm -r live_chat_archive/` and drop `live_chat_archive` from `ruff.toml` `extend-exclude`.
