# Phase 1 — Re-inspection report

**Branch:** `chore/project-cleanup-reorg`  
**Lead:** Phase 1 FULL REMEDIATION  
**Generated:** 2026-08-12  
**HEAD (at report write):** see `git rev-parse HEAD` on branch (ahead of `origin/main`).

## Summary

Executable Waves **1–13** largely applied on this branch (Wave 0 already DONE). Eight re-inspection agents were launched with disjoint coverage; lead merged evidence + a second-pass fix for remaining clear STILL_BROKEN items.

| Wave | Status |
|---|---|
| 0 Verify | DONE (Phase 0C) |
| 1 Deletes | DONE except `config/montymobile_templates.json` **reclassified KEEP** (live callers) |
| 2 Security | DONE (+ second-pass `liveChatApi` operator default) |
| 3 Tenant A+C | DONE (+ second-pass session load/revoke) |
| 4 Handlers | DONE; `start_command` still exported → **BLOCKED** (barrel wired) |
| 5 Dashboard product | DONE (plan defaults) |
| 6 GHA in-repo | DONE |
| 7 Performance | DONE (`LoadingScreen`; `useApi` all-hooks park) |
| 8 Monty harden | DONE inventory + adapter fail-closed; template service follow-on may still land |
| 9 Archive | PARTIAL (`archive/planning`, `archive/docs/cm_phase_evidence`); more MOVE_TO_ARCHIVE remain |
| 10 Docs/root | PARTIAL (`ANALYTICS_LOGIC`, `CLAUDE_MEMORY` banner, `api_config` comment); infra parked |
| 11 Mobile KEEP_FIX | PARTIAL (`guestSession`, `tokenStore`); Theme/Register/etc residual |
| 12 API modules | PARTIAL (auth tenant, debug elevation, adapters logging); CORS/content_files ASKs remain |
| 13 Services | PARTIAL (`import os` fixes); Redis rate limit **PARKED**; `legacy_isolation` ASK |

## Re-inspect results (merged)

### FIXED_CLEAN (high confidence)

- Mobile live-chat route `requiredPermission="liveChat"`
- AuthContext fail-closed missing role/tenant; 401 clears; no admin cache restore
- RoleManager client custom roles hidden
- Live-chat media uses authenticated operator (composer)
- Debug rebuild/simulate UI removed from LiveChatSidebar
- Settings / Sidebar missing tenant ≠ linas
- live_chat_api_debug admin/platform_owner elevation
- guestSession CSPRNG
- Wave 3 owned services fail-closed tenant
- Wave 1 orphan deletes (dashboard panels, mobile orphans, dead services/scripts, live-chat-android **tracked** sources)
- Wave 5 product defaults (hide Transfer/Priority, throw OperatorStatus, remove Testing mock success, etc.)
- Wave 6 typed confirmation / ssh pin / probe harden / no reset --hard
- LoadingScreen lightened
- Monty isolation check fail-closed on exception
- api_integrations_* `import os`
- tokenStore Zod validate stored user

### STILL_BROKEN → fixed in second pass

| Item | Fix commit theme |
|---|---|
| `dashboard_session_service` load/revoke `or "linas"` | fail closed empty tenant |
| `handlers/voice_handlers.py` tenant default linas | refuse without tenant |
| `liveChatApi.jsx` default `operator_001` | require operatorId |
| `modules/whatsapp_adapters.py` full response JSON print | redact status-only log |

### BLOCKED / OWNER_ASK / PARKED

| Item | Disposition | Why |
|---|---|---|
| `config/montymobile_templates.json` | **KEEP** (Wave 1 STOP) | Loaded by `montymobile_template_service` / preview settings; SEC-026 residual until Monty cutover |
| `handlers/text_handlers_start.start_command` | **BLOCKED** | Still exported from `handlers/text_handlers.py`; WhatsApp path uses separate adapter |
| Redis distributed rate limit (`rate_limit_service.py`) | **PARKED** | Known concern #9 — needs Redis/infra approval |
| `config.py` defaults / welcome copy | **PARKED** | Infra/lock — owner approval |
| Docker/nginx/compose/firestore index deploy | **PARKED** | Infra — not changed |
| SSE CORS `*` on live_chat_api | **OWNER_ASK** | Exact origin policy unanswered |
| content_files_api / instructions_api SaaS scope | **OWNER_ASK** | archive vs tenant-scope |
| `legacy_isolation` fail-closed on DB error | **OWNER_ASK** | May block Monty sends |
| APK in git / `data/*.jsonl` | **OWNER_ASK** | keep vs LFS vs untrack |
| SEC-017 `delete_all_conversations.py` | **OWNER_ASK** | harden+archive vs archive-only; **never ran** |
| Remaining MOVE_TO_ARCHIVE (~scripts/docs) | **PARTIAL** | First archive batches done; more batches remain |
| Wave 11 ThemeContext/Register/SideDrawer/i18n | **PARTIAL** | Not all KEEP_FIX mobile paths completed |
| SEC-028 admin ProtectedRoute bypass | **KEEP_AS_IS** | Wave 14 — left documented |
| Untracked `mobile/live-chat-android/{.gradle,.jdk,...}` | **NOTE** | Local build caches not in git; empty leftover dirs OK to ignore |

## Tests run (lead)

- `npx vitest run` AuthContext + Settings integrations + MobileLiveChat.auth + ProtectedRoute → **16 passed**
- Full pytest auth matrix: environment missing sqlalchemy in default python — use project venv when available

## Mahmoud test steps

1. Dashboard login as **linas** admin (explicit tenant from server) — ops tabs work.
2. Mock/local session **without** tenantId/role — must not unlock ops; redirect/login.
3. User without `liveChat` — `/mobile/live-chat` redirects.
4. Operator role — `GET /api/live-chat/debug-firestore` and `POST /api/live-chat/rebuild-index` → **403**.
5. Live chat sidebar — no Rebuild index / Test webhook buttons.
6. Settings with missing tenantId — no General/Notifications linas-only tabs.
7. Header notifications empty (no fake Live events).
8. LiveChat details — no Transfer/Priority buttons.
9. Mobile guest chat still starts; guest ids use CSPRNG.
10. Do **not** expect Redis distributed rate limit or Meta cutover.

## Commits

Prefer `git log --oneline origin/main..HEAD --grep='wave'` for the full Phase 1 commit list on this branch (~50+ wave commits). Key SHAs evolve; do not push unless asked.
