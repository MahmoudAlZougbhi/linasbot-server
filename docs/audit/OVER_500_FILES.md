# Phase 0C — Files over 500 physical lines

Generated: 2026-08-12 (Phase 0C integrity reconciliation)

## Policy

- **In scope:** hand-written tracked source (`.py`, `.js`, `.jsx`, `.ts`, `.tsx`, `.mjs`, `.cjs`, `.sh`, `.yml`, `.yaml`, `.md` product/docs outside audit dumps, `.conf`, etc.).
- **Excluded (documented):**
  - Binaries / media: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.pdf`, `.zip`, `.apk`, fonts, audio/video
  - Generated lockfiles: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`
  - Data dumps: `*.jsonl` under `data/`
  - Audit working artifacts under `docs/audit/` (inventory CSVs / problem reports grow with the audit itself and are not application modules)
- Gate script: `python3 scripts/audit/line_count_gate.py` (same policy as residual status).

## Automated rescan (Phase 0C)

Command (equivalent):

```bash
git ls-files -z | … count physical lines … | filter exclusions above
```

**Result: `0` hand-written application/tracked product files currently exceed 500 physical lines.**

| Metric | Count |
|---|---:|
| Hand-written tracked files >500 (excl. docs/audit, lockfiles, binaries, jsonl) | **0** |
| `docs/audit/*` text artifacts >500 (inventory / reports only) | 3 |
| `data/*.jsonl` data dumps >500 | 3 |
| Generated lockfiles >500 | 2 (`dashboard/package-lock.json`, `mobile/linas-ai/package-lock.json`) |

### docs/audit artifacts >500 (excluded from KEEP_SPLIT matrix)

| LOC | Path | Note |
|---:|---|---|
| ~1545 | `docs/audit/FILE_INVENTORY.csv` | Audit SoT; not application code |
| ~1284 | `docs/audit/TRACKED_FILE_INVENTORY.csv` | Superseded W00 shell |
| ~524 | `docs/audit/ALL_PROBLEMS_FOUND.md` | Audit report |

### Data dumps >500 (excluded)

| LOC | Path |
|---:|---|
| 10621 | `data/reports_log.jsonl` |
| 1780 | `data/analytics_events.jsonl` |
| 1105 | `data/conversation_log.jsonl` |

## Why prior disposition totals had **zero KEEP_SPLIT**

Phase 0B inventory marked large historical god-files as already-split facades (`LiveChat.jsx` ~150 LOC, `chat_response_service.py` ~13 LOC facade, `utils/utils.py` ~129 LOC, `live_chat_service.py` ~115 LOC, etc.). The LOC gate (`scripts/audit/line_count_gate.py`) and residual note (`docs/audit/RESIDUAL_STATUS.md`) already reported **OK: 0 hand-written tracked files over 500 lines** before Phase 0C.

`docs/audit/FILES_OVER_500.csv` is a **stale W00 snapshot** (pre-split line counts). It must not be used as current truth. Phase 0C replaces it with this matrix.

## KEEP_SPLIT disposition rule

- Use `KEEP_SPLIT` only when a **retained hand-written** file is currently >500 LOC and must be split before further feature work.
- **Current count requiring KEEP_SPLIT: 0.**
- No file >500 may remain `KEEP_AS_IS` without an exception row here **and** in `FILE_INVENTORY.csv`. **N/A — none exceed 500.**

## Characterization tests still required (split debt, not LOC debt)

Even though LOC is under 500, prior splits need stronger characterization (noted in residual status):

| Former god-file | Current facade LOC | Split siblings | Characterization still needed |
|---|---:|---|---|
| `dashboard/src/pages/LiveChat.jsx` | ~150 | `LiveChatSidebar`, `LiveChatThread*`, `LiveChatModals`, … | Route/permission + SSE integration |
| `services/chat_response_service.py` | ~13 | `chat_response_runtime_*` | End-to-end reply path |
| `utils/utils.py` | ~129 | `utils_*` modules | Import surface / booking tools |
| `services/live_chat_service.py` | ~115 | `live_chat_service_*` | Index/rebuild/operator paths |
| `handlers/text_handlers_respond.py` | ~111 | `text_handlers_respond_phase*` | Phase pipeline |

## Final disposition

| Category | Disposition |
|---|---|
| Current hand-written >500 | **None** |
| Stale `FILES_OVER_500.csv` | Document-only historical; superseded by this file |
| Future regressions | Enforce via `scripts/audit/line_count_gate.py` in CI; new >500 → `KEEP_SPLIT` before Phase 1 feature edits |
