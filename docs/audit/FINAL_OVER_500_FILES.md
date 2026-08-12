# Final over-500 LOC scan (C4)

**Branch:** `chore/project-cleanup-reorg`  
**Generated:** 2026-08-12  
**FINAL_APPLICATION_CANDIDATE_SHA:** `72d1d439b589f4d111b0a4cc7cd61030ceaca677`  
**FINAL_FREEZE_DOCS_SHA:** `a73373b2791024c91aafecb74ff64fd79c9abb09`  
**Agent:** remediation C4

## Scope

Hand-written source under:

- `modules/`, `services/`, `handlers/`
- `dashboard/src/`, `mobile/linas-ai/src/`
- `tests/` (reported separately)
- `scripts/`
- root `config.py`, `main.py`

Extensions: `*.py`, `*.js`, `*.jsx`, `*.ts`, `*.tsx`

**Excluded:** `.git`, `archive/`, `node_modules/`, `.venv*`, `**/site-packages/**`, `mobile/**/.android-sdk/**`, `dist/`, `build/`, `coverage/`

## Result

| Bucket | Files >500 LOC |
|---|---:|
| App source (modules/services/handlers/dashboard/mobile/scripts + config/main) | **0** |
| Tests | **0** |
| **Total in-scope** | **0** |

No KEEP_SPLIT work required this pass. Hard rule satisfied: no hand-written app source over 500; none approach 1000.

## Near miss (≤500, watch list — not split)

Closest app files (400–500), for regression awareness only:

| LOC | Path |
|---:|---|
| 497 | `modules/auth_api.py` |
| 493 | `services/model_policy.py` |
| 483 | `services/sentiment_escalation_keywords.py` |
| 483 | `dashboard/src/components/LiveChat/MobileLiveChatThreadPane.jsx` |
| 483 | `dashboard/src/pages/Settings.jsx` |
| 476 | `services/owner_ai_orchestrator.py` |
| 475 | `services/missed_paused_campaign_service.py` |
| 474 | `modules/event_handlers_monitor_jobs.py` |
| 453 | `config.py` |

## Related C4 remediation (not LOC)

W12-A4 / S13 lab leftovers: stripped unreachable bodies from `modules/dashboard_api_lab_{message,voice,upload}.py` to refuse-only stubs; `/api/stats` now refuses (aligned with `is_disabled_api_path`).

## Policy reminder

Any future edit that would push a retained hand-written app file over 500 LOC must split first (same LOC-split pattern already used in-repo). Do not grow any file past 1000.
