# Phase 0B — Complete problems report (all tracked files)

_Source: `docs/audit/FILE_INVENTORY.csv` after full Phase 0B + false-orphan correction + late agent reconcile._

**Audit-only.** Do **not** delete, fix, migrate, Meta-cutover, or deploy until Mahmoud approves Phase 1.

- **Inventory parity:** 1544 / 1544
- **Review status:** all `COMPLETE`
- **Fully read:** YES for text sources; NOT_APPLICABLE for binaries
- **Quality:** seq 1–205 careful hand/agent forensic; later rows import-rechecked; late agents 206–520 merged where available.

## Disposition totals

| Disposition | Count |
|---|---:|
| KEEP_AS_IS | 1190 |
| MOVE_TO_ARCHIVE | 130 |
| BINARY_ASSET_REVIEW | 81 |
| KEEP_FIX | 49 |
| LANDING_KEEP | 35 |
| DELETE_CANDIDATE | 23 |
| KEEP_MOBILE_API | 16 |
| KEEP_SECURITY_FIX | 15 |
| KEEP_PERFORMANCE_FIX | 3 |
| GENERATED_SKIP | 2 |

---

## Top priority — `KEEP_SECURITY_FIX`

- **Seq 6** `.github/workflows/dashboard-auth-secret-apply.yml` — Missing confirmation string gate on high-impact secret apply | NO confirmation input unlike sibling secret-apply workflows — anyone with Actions write on repo can rotate dashboard auth. Secret passed via envs to SSH (expected). | Fails if apply script missing
- **Seq 7** `.github/workflows/deploy.yml` — Pin/update ssh-action version consistency; harden data backup path permissions; keep confirmation for emergency | Emergency bypass skips gate verification (documented). Uses appleboy/ssh-action@v1.0.3 while siblings use v1.2.0 (supply-chain version skew). data/ backup to /tmp/linasbot_data_backup_$$ then restore after hard reset — /tmp world-readable risk window if perms loose. | Restores data/ after reset so local data survives; relies on dep...
- **Seq 8** `.github/workflows/instagram-login-secrets-apply.yml` — Secret apply without confirmation string | No typed confirmation; secrets via SSH envs; never logs values (stated) | Checks out script from origin/main each run
- **Seq 21** `.github/workflows/meta-webhook-nginx-setup.yml` — Verify-token apply without typed confirmation | No confirmation string; rotates verify token — webhook auth impact | Requires non-empty META_WEBHOOK_VERIFY_TOKEN
- **Seq 23** `.github/workflows/openai-api-key-apply.yml` — OpenAI key apply without typed confirmation | No confirmation; applies billing-critical API key | Runs verify script after apply
- **Seq 27** `.github/workflows/subscription-exempt-probe.yml` — Logs entitlement raw + tenant env values + all user display rows to CI logs | Prints SUBSCRIPTION_EXEMPT_TENANT_IDS value, TOKEN_WALLET_UNLIMITED value, linas.json entitlement raw[:400], and per-user tenant/role/status/display names into Actions logs (no emails but business display names + tenant map). Firestore stream of all dashboard_users unbounded. | Exits 0 even when Firestore import fails; legacy APP_DIR linaslaserbot-2.7.22 | Unbounded ...
- **Seq 30** `.github/workflows/whatsapp-cloud-phase1-apply.yml` — Production git reset --hard inside workflow | Resets entire deploy tree to main as side effect of flag apply
- **Seq 95** `dashboard/src/App.jsx` — Mobile live-chat route missing requiredPermission | Register redirects to /#get-app; analytics/smart-messaging/social-posts/testing redirect away; Training still lazy-imported route /training | 300ms artificial LoadingScreen delay; many lazy routes good; framer motion on shell
- **Seq 126** `dashboard/src/components/UserManagement/RoleManager.jsx` — Active in UserManagement; custom roles in localStorage create cross-admin authorization inconsistency | Custom roles persisted only in browser localStorage (dashboard/src/utils/permissions.jsx CUSTOM_ROLES_KEY) — not shared across admins/devices; assigning custom roleId to server users may not resolve on other browsers | RoleCard tolerates permissions as array via fallback to {} | loads custom roles once on mount — fine
- **Seq 152** `dashboard/src/contexts/AuthContext.helpers.js` — Default role=admin and tenantId=linas in buildUserData when fields absent | agent also flags admin/tenantId defaults as correctness risk | buildUserData defaults role to admin and tenantId to linas when missing — privilege/tenant spoof risk if backend omits fields | emailVerified defaults true when missing
- **Seq 153** `dashboard/src/contexts/AuthContext.jsx` — Session fail-open on errors + debug console.log of auth payloads; active AuthProvider | Fail-open: keeps cached auth_session on transient session errors and catch; console.log of login/session response shapes; CSRF stored in localStorage | 5s safety timeout forces loading=false; 24h local session TTL; validate throttle 10min | session fetch on mount with 5s abort
- **Seq 168** `dashboard/src/hooks/useLiveChatMediaComposer.jsx` — operator_001 hardcoded in sendVoiceMessage and sendImageMessage | hardcoded operator_001; agent KEEP_FIX — elevated as attribution/authz risk | Hardcodes operatorId "operator_001" for voice/image sends — wrong attribution / authz risk | _onAppendMessage unused; relies on SSE for echo | base64 in memory for media
- **Seq 192** `dashboard/src/pages/LiveChatSidebar.jsx` — simulateWebhook and rebuildLiveChatIndex buttons visible in operator sidebar | UI exposes Rebuild index and Test flow (simulateWebhook phone 9613000000) to any liveChat user — high-impact ops without elevated gate | god-object unused vars | list virtualization absent — OK for page_size 30
- **Seq 197** `dashboard/src/pages/MobileLiveChat.jsx` — Active mobile route wrapper | App.jsx ProtectedRoute for /mobile/live-chat omits requiredPermission=liveChat (agent + prior App audit) | route permission gap tracked on App.jsx | Route may be reachable without liveChat permission if URL known; Sidebar gates nav but route does not
- **Seq 203** `dashboard/src/pages/Settings.jsx` — Missing tenantId defaults to linas enabling ops settings tabs | Missing tenantId defaults to linas enabling ops settings tabs | also loads unused botName/enableVoice/humanTakeoverNotifyMobiles (agent KEEP_FIX debt) | (user?.tenantId || "linas") === "linas" unlocks general/notifications when tenantId missing — same default-tenant risk | loads unused fields botName/enableVoice etc. but saves only defaultLanguage | Loads unused general fields but...

---

## Performance — `KEEP_PERFORMANCE_FIX`

- **Seq 13** `.github/workflows/meta-comment-webhooks-reconcile.yml` — Full requirements install for thin reconcile script; consider lean deps later | Installs full requirements.txt in CI for a script — heavy but correct isolation | pip install full reqs each run (slow)
- **Seq 102** `dashboard/src/components/Common/LoadingScreen.jsx` — Expensive splash + outdated feature copy | feature cards still say AI Testing/Smart Training — outdated copy | heavy framer animations on every auth load
- **Seq 160** `dashboard/src/hooks/useApi.jsx` — Primary dashboard API hook; LOC-split under 500 | App.jsx calls useApi() mainly for botStatus but instantiates all API sub-hooks (agent) | spread merge may overwrite keys if modules collide — currently partitioned | instantiates all API modules even when page needs one — extra hook closures | useApi() on AppContent mount loads testing/QA/training/liveChat/content hooks even when only botStatus needed

---

## Correctness / product — `KEEP_FIX`

- **Seq 2** `.env.example` — Required template; needs product-aligned reordering/deprecation notes for Monty vs Meta Cloud (no secret leak; fix is documentation clarity) | Documents dual WhatsApp stacks (Monty section + WA Cloud flags). Comments say Cloud never falls back to Monty; product intent is Meta Cloud—template still educates Monty as primary 'WhatsApp provider' section.
- **Seq 10** `.github/workflows/meta-app-a-scope-audit.yml` — Stale feature-branch checkout dependency | HARDCODES git fetch/checkout of branch fix/ig-fb-comments-capability-gates — brittle if branch deleted/renamed; may run stale scripts
- **Seq 12** `.github/workflows/meta-comment-runtime-probe.yml` — Hardcoded feature branch for probe script | Same brittle checkout from fix/ig-fb-comments-capability-gates as seq10
- **Seq 22** `.github/workflows/model-routing-policy-apply.yml` — Unlike copilot-v2 workflow, does not always refresh script from main when present | Installs script from origin/main if missing else chmod only — may leave stale script if file exists but outdated
- **Seq 29** `.github/workflows/wa-cloud-webhook-readonly-probe.yml` — Stale hardcoded date windows and soft exit 0 | Redacts long digit runs in event_key; sources full .env into shell | Hardcoded TIMESTAMPTZ windows 2026-08-11 — stale after that day; many failures exit 0 (silent soft-fail) | LIMIT 50 on events
- **Seq 31** `.gitignore` — Keep; clean obsolete PHP ignores and finish jsonl untrack after owner approval | Some CodeIgniter/PHP legacy ignore patterns remain (user_guide_src, vendor/, php_errors) — copied heritage
- **Seq 40** `README-LOCAL.md` — Env filename mismatch and legacy dashboard-centric flow | Instructs real EXTERNAL_API_TOKEN use locally | References cp .env.local.example .env.local but repo documents .env.example as only env file — mismatch
- **Seq 47** `api_config.py` — Duplicate config surface; misleading path comment | Duplicates config.py LINASLASER_* vars; comment says data/api_config.py but path is repo root api_config.py
- **Seq 50** `backend/Dockerfile.simple` — Port 8000 vs project standard 8003 | --reload in image unsuitable for prod | HEALTHCHECK curls :8000/health but other Dockerfiles use 8003 — port inconsistency | reload overhead
- **Seq 51** `backend/requirements.txt` — Dual requirements files can drift | Pins older openai/fastapi etc may diverge from root requirements.txt | Duplicate dependency source of truth risk vs root requirements.txt
- **Seq 52** `config.py` — Central config must stay; fix identity/defaults/state scaling in later phases | In-memory state not tenant-isolated for multi-instance; FIRESTORE path hardcoded data/firebase_data.json | WELCOME_MESSAGES still brand Marwa / Lina Laser (CM cutover risk); DEFAULT_*_ID=1 silent defaults; BOOKING flags env-driven | unbounded per-user deques except MAX_CONTEXT_MESSAGES; load files at import
- **Seq 56** `dashboard/Dockerfile.prod` — Standard SPA prod image | Node 20 image vs engines>=22.19.0 mismatch (agent forensic) | Uses package-lock via npm ci; Builder FROM node:20-alpine but package.json engines require node>=22.19.0 | multi-stage good
- **Seq 94** `dashboard/public/manifest.json` — Stale purple theme + emoji icon vs current brand | theme_color #d946ef purple leftover; emoji robot data-URI icon not brand SVG
- **Seq 96** `dashboard/src/App.routes.test.jsx` — Useful regression for analytics redirect | Useful redirect test but does not exercise real App router | does not import real App — partial route mirror; Does not import App.jsx — tests stub routes only
- **Seq 101** `dashboard/src/components/Common/ErrorBoundary.jsx` — Silent network error passthrough may mask outages | logs errors only in development | ERR_NETWORK / Network Error silently returns children — can hide failures
- **Seq 106** `dashboard/src/components/Layout/Header.jsx` — Hardcoded sample notifications present false Live alerts | shows user email in UI (expected); hardcoded fake notifications not from API | botStatus prop unused (_botStatus); notifications are sample data misleading as Live | framer animations
- **Seq 109** `dashboard/src/components/Layout/Sidebar.jsx` — Missing tenantId defaults to linas unlocking ops surfaces | tenantId||linas default can wrongly expose ops surface | Live Chat/Activity Flow/APK gated to tenantId===linas client-side; admin sees all permitted items; Missing tenantId defaults to linas unlocking Live Chat/Activity Flow/APK ops surfaces | default tenantId linas if missing — could wrongly show ops surface | health poll 60s OK
- **Seq 114** `dashboard/src/components/LiveChat/MobileLiveChatThreadPane.jsx` — Unreachable status copy branch; media URL trust boundary | renders image_url/audio_url from API — SSRF/XSS depends on URL allowlisting server-side; accept=image/* client only | dead branch text currentStatus===human inside else of currentStatus===human (unreachable copy) | maps full history; no windowing
- **Seq 118** `dashboard/src/components/LiveChat/ModernAudioPlayer.jsx` — 8 Live Chat importers; widely used. Minor play-state desync on failed audio.play() | Client sends arbitrary audioUrl to GET /api/media/audio?url=…; SSRF mitigated server-side in modules/media_api.py (_fetch_with_ssrf_guard, tests/test_wave1_security.py). Player does not sanitize URL display in console.error. | handlePlayPause sets isPlaying via toggle before audio.play() resolves; failed play can leave UI out of sync until onError fires | Sing...
- **Seq 125** `dashboard/src/components/UserManagement/PermissionMatrix.jsx` — Imported by UserForm and RoleManager on active Settings users tab; double-toggle bubble risk | Active PermissionMatrix; double-toggle risk on card click | Card onClick and inner checkbox onChange both call handleToggle — click on toggle may double-fire (bubble); Card onClick and checkbox onChange may double-toggle on click bubble | 11 animated cards with staggered delay — negligible
- **Seq 147** `dashboard/src/constants/permissions.jsx` — Central RBAC map used by ProtectedRoute and permissions utils; tests assert live-chat + FAQ routes | FEATURE_METADATA exported with zero importers; TRAINING legacy naming (agent) | ANALYTICS and DASHBOARD both map path /app; FEATURES.TRAINING path /training but PATH maps /training to contentManagers — intentional FAQ single-entry | FEATURE_METADATA unused export; ANALYTICS.path same as DASHBOARD (/app)
- **Seq 149** `dashboard/src/constants/productFeatures.js` — SAAS_NAV_ITEMS active on Dashboard; DISABLED_FRONTEND_ROUTES + isDisabledFrontendRoute have zero callers | Disabled routes listed but not enforced by this helper (dead) — App.jsx may still route separately | isDisabledFrontendRoute unused — disabled surface gating may be incomplete vs constants
- **Seq 157** `dashboard/src/contexts/OperatorStatusContext.jsx` — Active provider in App; silent fallback violates fail-loud preference | agent KEEP_AS_IS but silent no-op outside provider remains KEEP_FIX | useOperatorStatus silently falls back to no-op setter when outside provider — hidden fallback
- **Seq 158** `dashboard/src/contexts/PermissionsContext.jsx` — Core permissions context mounted in App | App wraps PermissionsProvider but usePermissions() has zero consumers; migrateUsers on mount is sole active behavior (agent) | roles memo empty deps — OK static
- **Seq 165** `dashboard/src/hooks/useApiQA.js` — Still part of useApi; product surface disabled but API client retained | submitFeedback used by live chat; ~15 legacy QA/local-qa methods have zero page consumers (agent) | getQACategories returns hardcoded mock categories offline | Large dead QA CRUD surface still exported via useApi; getQACategories hardcoded offline fallback
- **Seq 166** `dashboard/src/hooks/useApiTesting.js` — Offline mock success:true replies for testText/image/voice/webhook; route disabled but code live in facade | test endpoints can drive bot with arbitrary phone — server must auth+entitle | Many ERR_NETWORK paths return success:true mock bot replies — can look like real AI when offline
- **Seq 174** `dashboard/src/index.jsx` — Application entrypoint | Dev console.error/unhandledrejection suppress ERR_NETWORK — masks backend-down failures (agent) | dev suppresses Network Error console noise and unhandledrejection ERR_NETWORK | DEV patches console.error and unhandledrejection to hide Network Error / ERR_NETWORK
- **Seq 183** `dashboard/src/pages/Dashboard.jsx` — Shows all SAAS_NAV_ITEMS regardless of user permissions | Shows all SAAS_NAV_ITEMS regardless of user permissions | agent: thin hub but tiles not permission-filtered | links not filtered by user permissions in this page — Sidebar/ProtectedRoute gate destinations | no permission filter on nav tiles
- **Seq 189** `dashboard/src/pages/LiveChatBotOverlay.jsx` — God-object prop dump; already <500 but needs prop narrowing | God-object unused destructuring/imports (eslint-disable); functional overlay in LiveChatThread | massive unused destructuring (eslint-disable) | eslint-disable no-unused-vars; 60+ unused controller fields and dead imports (FeedbackModal, ModernAudioPlayer, etc.) | duplicates sidebar list UI
- **Seq 190** `dashboard/src/pages/LiveChatDetails.jsx` — Dead Transfer/Priority buttons mislead operators | Transfer to Another Operator and Mark as Priority buttons are no-ops (no onClick handlers)
- **Seq 191** `dashboard/src/pages/LiveChatModals.jsx` — Active modals; prop dump pattern like siblings | Active modals; duplicate fragment wrappers + unused-import LOC-split debt | FAQ save-all-languages actions — server must authz | god-object destructure; duplicate fragment wrappers | duplicate nested fragments; god-object unused destructure
- **Seq 194** `dashboard/src/pages/LiveChatThreadHeader.jsx` — Active header; same full-controller prop pattern | Active header; unused-import / full-controller destructuring debt from LOC split | god-object destructure
- **Seq 196** `dashboard/src/pages/Login.jsx` — Dev connection help embeds personal absolute paths | Hardcodes personal laptop paths /Users/mahmoudalzougbhi/linas ai bot in connection error UI — wrong for other machines and leaks local layout
- **Seq 305** `deploy/nginx-api-include.conf` — Active deploy snippet per README; drift vs full config on /oauth/ routes. | access_log off + crit-only error_log on webhook/data-deletion/integrations; owner-ai SSE has 300s timeout and proxy_buffering off. | Snippet lacks /oauth/ and /meta/deauthorize present in full nginx-linasaibot.conf—include-only installs may miss OAuth routes. | SSE location disables buffering—correct for streaming.
- **Seq 310** `docker-compose.yml` — Hardcoded tradershubs API URL in dashboard service env (line 65) diverges from prod nginx same-origin design. | Dev compose exposes Redis 6379 and mounts repo—dev only. | REACT_APP_API_URL=https://bot.tradershubs.site/api is stale/wrong for linasaibot.com local dev—conflicts with vite same-origin pattern.
- **Seq 313** `docs/ANALYTICS_LOGIC.md` — Accurate event logic but references removed /analytics dashboard route. | Documents user_id masking ...XXXX for privacy. | Stale: dashboard Analytics sidebar route redirected to /app in App.jsx:141; doc line 113 outdated.
- **Seq 318** `docs/CLAUDE_MEMORY.md` — Useful but 495 lines with version-specific claims that may be outdated. | States v2.7.22 and deprecated conversation_log—partially stale vs CM cutover and current branch; use with caution.
- **Seq 456** `firestore.indexes.json` — rg: live_chat_index query paths in live_chat_service_*; doc drift on index #3 collection | docs/FIRESTORE_INDEXES.md item 3 mentions conversations collection_group human_takeover_active but JSON defines live_chat_index.human_takeover_active — doc/index mismatch | required for ordered/filtered live_chat_index queries at scale
- **Seq 457** `handlers/VERSION.py` — rg: only handlers/text_handlers.py imports VERSION; stale build notes | Stale: BUILD_ID NAME_COLLECTION_v1, LAST_MODIFIED 2025-01-24, CHANGES claims 5 modular files while tree has 20+ handler modules | print_version_info() runs on every text_handlers import (noisy logs)
- **Seq 462** `handlers/text_handlers_firestore.py` — rg: _delayed_processing_tasks imported by webhook dedupe, dashboard lab, social processor | misnamed file (re-exports many non-firestore symbols) — maintainability debt | in-memory task dict per worker
- **Seq 463** `handlers/text_handlers_message.py` — rg: 7+ importers; tests enforce LOC split | verbose DEBUG prints include user_id, phone, message preview — log PII risk | text_turn_epoch prevents duplicate sends; training mode delegation; MAX_TEXT_LINES guard | sentiment + optional Firestore sentiment update per message; per-user asyncio.Lock in greeting module
- **Seq 472** `handlers/text_handlers_respond_phase12.py` — rg: terminal phase; dead _pack block after halt return | unreachable _pack after return _PHASE_HALT (dead code) | analytics + optional training log per turn
- **Seq 482** `handlers/text_handlers_start.py` — rg: exported from text_handlers; webhook_process comments removed direct call | webhook start_command_whatsapp no longer calls start_command directly — possible dead export
- **Seq 484** `handlers/voice_handlers.py` — rg: webhook_handlers_voice + dashboard lab import handle_voice_message | uses synchronous conv_doc_ref.get() inside async handler (blocks event loop); skip_firestore_save prevents double-save | pydub transcode + Whisper API per voice message
- **Seq 1175** `services/montymobile_template_service.py` — No importers found via module path patterns
- **Seq 1176** `services/montymobile_template_service_payload.py` — No importers found via module path patterns
- **Seq 1302** `services/whatsapp_adapters/montymobile_adapter.py` — No importers found via module path patterns
- **Seq 1303** `services/whatsapp_adapters/montymobile_adapter_parse.py` — No importers found via module path patterns
- **Seq 1319** `services/whatsapp_cloud/legacy_isolation.py` — No importers found via module path patterns

---

## Delete candidates — `DELETE_CANDIDATE`

Zero external importers after module-path recheck (or orphan cluster / orphan test).

- **Seq 53** `config/montymobile_templates.json` — Confirmed zero-import orphan from manual Phase 0B audit | Commits api_id, tenant UUID, source phone 96178974402; api_key empty (good). Template wa_message_id/record_guid are provider IDs. | No importers found via module path patterns
- **Seq 100** `dashboard/src/components/BotInstructionsTab.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | restore by filename from API — server must validate path | No importers found via module path patterns | loads instructions+stats+backups on mount
- **Seq 103** `dashboard/src/components/ContentFilesPanel.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | delete/create via API; auth assumed in useApi | No importers found via module path patterns | loads full file content on select
- **Seq 104** `dashboard/src/components/DynamicMessagesPanel.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | No importers found via module path patterns | JSON.stringify dirty check entire tree
- **Seq 119** `dashboard/src/components/SystemPromptKnowledgeStylePanel.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | Would allow unauthenticated write only if mounted without ProtectedRoute; currently unreachable. updateTrainingFile requires authenticated api client when used. | No importers found via module path patterns | Loads three large text files in parallel on mount — fine if wired
- **Seq 120** `dashboard/src/components/TrainingFileEditor.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | restore uses window.confirm only; would POST restore with auth if mounted | No importers found via module path patterns | findTrainingSearchMatches rescans full content per match index; document keydown listener on every open-search state
- **Seq 121** `dashboard/src/components/TrainingFileEditor.locSplit.test.js` — Test for orphaned TrainingFileEditor cluster; no production import
- **Seq 122** `dashboard/src/components/TrainingFileEditor.meta.js` — Confirmed zero-import orphan from manual Phase 0B audit | No importers found via module path patterns | findTrainingSearchMatches O(n*m) with content.split per match
- **Seq 123** `dashboard/src/components/TrainingFileEditorBackups.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | restore delegated to parent handleRestore (confirm + API) | No importers found via module path patterns | max-h-64 scroll list — fine
- **Seq 124** `dashboard/src/components/TrainingFileEditorSearch.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | No importers found via module path patterns | slices results to 10 in UI — good
- **Seq 131** `dashboard/src/components/landing/LinasBotMascot.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | No importers found via module path patterns | If mounted: 12s wander interval, 14s bored interval, window pointermove listener, framer-motion infinite repeat — non-trivial JS thread load
- **Seq 146** `dashboard/src/constants/linasBrand.js` — Confirmed zero-import orphan from manual Phase 0B audit | No importers found via module path patterns
- **Seq 172** `dashboard/src/hooks/usePermissions.jsx` — Confirmed zero-import orphan from manual Phase 0B audit | No importers found via module path patterns
- **Seq 577** `mobile/linas-ai/src/features/chat/GuestBanner.tsx` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 579** `mobile/linas-ai/src/features/chat/HistoryDrawer.tsx` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 875** `scripts/montymobile_manual_probe.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 970** `services/bot_data_service.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 1090** `services/dynamic_model_selector.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 1092** `services/enhanced_message_handler.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 1098** `services/faq_translation_service.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 1123** `services/live_monitoring.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 1139** `services/message_queue_service.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns
- **Seq 1140** `services/message_sync_service.py` — No importers after module-path recheck; orphan candidate | No importers found via module path patterns

---

## Archive candidates — `MOVE_TO_ARCHIVE` (130)

| Area | Count | Examples |
|---|---:|---|
| `scripts` | 74 | `scripts/appointment_api_manual_probe.py`, `scripts/audit/line_count_gate.py`, `scripts/audit_meta_app_a_scopes.py`, `scripts/audit_meta_bindings_readonly.py` |
| `docs/cm_phase_evidence` | 11 | `docs/cm_phase_evidence/PHASE0.md`, `docs/cm_phase_evidence/PHASE1.md`, `docs/cm_phase_evidence/PHASE2.md`, `docs/cm_phase_evidence/PHASE3.md` |
| `docs/evidence` | 9 | `docs/evidence/customer_reply_ai_v2/01_baseline_audit.md`, `docs/evidence/customer_reply_ai_v2/02_dod_evidence_report.md`, `docs/evidence/mobile_design_handoff/02_dod_evidence_report.md`, `docs/evidence/phase2_load_simulation.json` |
| `.planning` | 7 | `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/INTEGRATIONS.md` |
| `docs/design` | 6 | `docs/design/MAHMOUD_MOBILE_PROMPT.md`, `docs/design/MAHMOUD_MOBILE_PROMPT_content_management.md`, `docs/design/MAHMOUD_MOBILE_PROMPT_guest_chat.md`, `docs/design/MAHMOUD_MOBILE_PROMPT_live_chat.md` |
| `data` | 4 | `data/analytics_events.jsonl`, `data/conversation_log.jsonl`, `data/qa_pairs.jsonl`, `data/reports_log.jsonl` |
| `dashboard` | 1 | `dashboard/README.md` |
| `docs/CM_FULL_CORPUS_LEDGER.md` | 1 | `docs/CM_FULL_CORPUS_LEDGER.md` |
| `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md` | 1 | `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md` |
| `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md` | 1 | `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md` |
| `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_runtime.md` | 1 | `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_runtime.md` |
| `docs/LIVE_CHAT_FIX_SUMMARY.md` | 1 | `docs/LIVE_CHAT_FIX_SUMMARY.md` |
| `docs/META_VERIFIED_APP_CUTOVER_RUNBOOK.md` | 1 | `docs/META_VERIFIED_APP_CUTOVER_RUNBOOK.md` |
| `docs/PHASE2_FINAL_REPORT.md` | 1 | `docs/PHASE2_FINAL_REPORT.md` |
| `docs/PHASE2_FIREBASE_MOBILE_AUTH_AUDIT.md` | 1 | `docs/PHASE2_FIREBASE_MOBILE_AUTH_AUDIT.md` |
| `docs/PHASE2_IAP_EXTERNAL_CHECKLIST.md` | 1 | `docs/PHASE2_IAP_EXTERNAL_CHECKLIST.md` |
| `docs/PHASE2_MOBILE_BETA_REPORT.md` | 1 | `docs/PHASE2_MOBILE_BETA_REPORT.md` |
| `docs/PHASE2_MOBILE_BETA_STATUS.md` | 1 | `docs/PHASE2_MOBILE_BETA_STATUS.md` |
| `docs/PHASE2_PRE_RELEASE_REPORT.md` | 1 | `docs/PHASE2_PRE_RELEASE_REPORT.md` |
| `docs/PHASE2_PRODUCTION_RECONCILE.md` | 1 | `docs/PHASE2_PRODUCTION_RECONCILE.md` |
| `docs/PHASE2_TESTFLIGHT_GATE.md` | 1 | `docs/PHASE2_TESTFLIGHT_GATE.md` |
| `docs/PHASE2_TIKTOK_SNAP_CAPABILITY_AUDIT.md` | 1 | `docs/PHASE2_TIKTOK_SNAP_CAPABILITY_AUDIT.md` |
| `docs/PHASE2_WAVE0_STATUS.md` | 1 | `docs/PHASE2_WAVE0_STATUS.md` |
| `docs/PHASE2_WEB_STORE_LINKS.md` | 1 | `docs/PHASE2_WEB_STORE_LINKS.md` |
| `docs/whatsapp_cloud` | 1 | `docs/whatsapp_cloud/WHATSAPP_CLOUD_COEXISTENCE.md` |

<details><summary>Full MOVE_TO_ARCHIVE list</summary>

- Seq 32: `.planning/codebase/ARCHITECTURE.md`
- Seq 33: `.planning/codebase/CONCERNS.md`
- Seq 34: `.planning/codebase/CONVENTIONS.md`
- Seq 35: `.planning/codebase/INTEGRATIONS.md`
- Seq 36: `.planning/codebase/STACK.md`
- Seq 37: `.planning/codebase/STRUCTURE.md`
- Seq 38: `.planning/codebase/TESTING.md`
- Seq 57: `dashboard/README.md`
- Seq 282: `data/analytics_events.jsonl`
- Seq 284: `data/conversation_log.jsonl`
- Seq 292: `data/qa_pairs.jsonl`
- Seq 293: `data/reports_log.jsonl`
- Seq 319: `docs/CM_FULL_CORPUS_LEDGER.md`
- Seq 321: `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md`
- Seq 322: `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md`
- Seq 324: `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_runtime.md`
- Seq 330: `docs/LIVE_CHAT_FIX_SUMMARY.md`
- Seq 342: `docs/META_VERIFIED_APP_CUTOVER_RUNBOOK.md`
- Seq 343: `docs/PHASE2_FINAL_REPORT.md`
- Seq 344: `docs/PHASE2_FIREBASE_MOBILE_AUTH_AUDIT.md`
- Seq 345: `docs/PHASE2_IAP_EXTERNAL_CHECKLIST.md`
- Seq 346: `docs/PHASE2_MOBILE_BETA_REPORT.md`
- Seq 347: `docs/PHASE2_MOBILE_BETA_STATUS.md`
- Seq 348: `docs/PHASE2_PRE_RELEASE_REPORT.md`
- Seq 349: `docs/PHASE2_PRODUCTION_RECONCILE.md`
- Seq 350: `docs/PHASE2_TESTFLIGHT_GATE.md`
- Seq 351: `docs/PHASE2_TIKTOK_SNAP_CAPABILITY_AUDIT.md`
- Seq 352: `docs/PHASE2_WAVE0_STATUS.md`
- Seq 353: `docs/PHASE2_WEB_STORE_LINKS.md`
- Seq 374: `docs/cm_phase_evidence/PHASE0.md`
- Seq 375: `docs/cm_phase_evidence/PHASE1.md`
- Seq 376: `docs/cm_phase_evidence/PHASE2.md`
- Seq 377: `docs/cm_phase_evidence/PHASE3.md`
- Seq 378: `docs/cm_phase_evidence/PHASE4.md`
- Seq 379: `docs/cm_phase_evidence/PHASE5.md`
- Seq 380: `docs/cm_phase_evidence/PHASE6.md`
- Seq 381: `docs/cm_phase_evidence/PHASE7.md`
- Seq 382: `docs/cm_phase_evidence/PHASE8.md`
- Seq 383: `docs/cm_phase_evidence/phase0_fixture_inventory.json`
- Seq 384: `docs/cm_phase_evidence/phase4_migration_conflict_report.json`
- Seq 386: `docs/design/MAHMOUD_MOBILE_PROMPT.md`
- Seq 387: `docs/design/MAHMOUD_MOBILE_PROMPT_content_management.md`
- Seq 389: `docs/design/MAHMOUD_MOBILE_PROMPT_guest_chat.md`
- Seq 390: `docs/design/MAHMOUD_MOBILE_PROMPT_live_chat.md`
- Seq 392: `docs/design/MAHMOUD_MOBILE_PROMPT_quality_and_verification.md`
- Seq 419: `docs/design/pdf_text/handoff.txt`
- Seq 420: `docs/evidence/customer_reply_ai_v2/01_baseline_audit.md`
- Seq 421: `docs/evidence/customer_reply_ai_v2/02_dod_evidence_report.md`
- Seq 423: `docs/evidence/mobile_design_handoff/02_dod_evidence_report.md`
- Seq 444: `docs/evidence/phase2_load_simulation.json`
- Seq 445: `docs/evidence/plan_economics_wave0.json`
- Seq 448: `docs/evidence/system_copilot_diagnosis_faq.json`
- Seq 449: `docs/evidence/system_copilot_v2/01_baseline_audit.md`
- Seq 450: `docs/evidence/system_copilot_v2/02_dod_evidence_report.md`
- Seq 451: `docs/evidence/system_copilot_v2/capability_manifest.json`
- Seq 455: `docs/whatsapp_cloud/WHATSAPP_CLOUD_COEXISTENCE.md`
- Seq 856: `scripts/appointment_api_manual_probe.py`
- Seq 857: `scripts/audit/line_count_gate.py`
- Seq 858: `scripts/audit_meta_app_a_scopes.py`
- Seq 859: `scripts/audit_meta_bindings_readonly.py`
- Seq 860: `scripts/backfill_live_chat_index.py`
- Seq 861: `scripts/check_copilot_v2_manifest.py`
- Seq 862: `scripts/check_message_flow.py`
- Seq 864: `scripts/check_source_line_limit.mjs`
- Seq 865: `scripts/cm/inventory_snapshot.py`
- Seq 866: `scripts/cm/run_migration_dry.py`
- Seq 867: `scripts/cm_prepare_remove_linas_bridge.py`
- Seq 868: `scripts/cm_publish_tenant.py`
- Seq 869: `scripts/debug_firestore_chats.py`
- Seq 870: `scripts/delete_all_conversations.py`
- Seq 871: `scripts/diagnose_outbound_dedupe.py`
- Seq 872: `scripts/manage_meta_page_subscription.py`
- Seq 873: `scripts/meta_webhook_contract.py`
- Seq 874: `scripts/migrate_phone_identity.py`
- Seq 876: `scripts/npm_audit_gate.mjs`
- Seq 877: `scripts/phase2_load_simulation.py`
- Seq 878: `scripts/plan_economics_simulation.py`
- Seq 879: `scripts/prod_apply_copilot_v2_flags.sh`
- Seq 880: `scripts/prod_apply_dashboard_auth.sh`
- Seq 881: `scripts/prod_apply_instagram_login_secrets.sh`
- Seq 882: `scripts/prod_apply_meta_app_a_login_config.sh`
- Seq 883: `scripts/prod_apply_meta_multi_app.sh`
- Seq 884: `scripts/prod_apply_meta_social_secrets.sh`
- Seq 885: `scripts/prod_apply_model_routing_policy.sh`
- Seq 886: `scripts/prod_apply_openai_api_key.sh`
- Seq 887: `scripts/prod_apply_whatsapp_cloud_phase1_flags.sh`
- Seq 888: `scripts/prod_cm_apply_flags.sh`
- Seq 889: `scripts/prod_cm_backup.sh`
- Seq 890: `scripts/prod_cm_bridge_readiness.sh`
- Seq 891: `scripts/prod_cm_corpus_inventory.sh`
- Seq 892: `scripts/prod_cm_cutover.sh`
- Seq 893: `scripts/prod_cm_generic_tenant_proof.sh`
- Seq 894: `scripts/prod_cm_import_prices.sh`
- Seq 895: `scripts/prod_cm_linas_content_audit.sh`
- Seq 896: `scripts/prod_cm_migrate_and_validate.sh`
- Seq 897: `scripts/prod_cm_preserve_durable_flags.sh`
- Seq 898: `scripts/prod_cm_price_line_shape_probe.sh`
- Seq 899: `scripts/prod_cm_price_source_ledger.sh`
- Seq 900: `scripts/prod_cm_publish.sh`
- Seq 901: `scripts/prod_cm_publish_faq_only.sh`
- Seq 902: `scripts/prod_cm_repair_linas_prices_publish.sh`
- Seq 903: `scripts/prod_cm_rollback.sh`
- Seq 904: `scripts/prod_cm_rollback_version.sh`
- Seq 905: `scripts/prod_cm_runtime_proof.sh`
- Seq 906: `scripts/prod_cm_set_linas_bridge_flag.sh`
- Seq 907: `scripts/prod_cm_sot_audit.sh`
- Seq 908: `scripts/prod_cm_verify_durable_bridge.sh`
- Seq 909: `scripts/prod_cutover_meta_social.sh`
- Seq 910: `scripts/prod_meta_comment_runtime_probe.py`
- Seq 911: `scripts/prod_meta_dm_live_watch.sh`
- Seq 912: `scripts/prod_preflight_readonly.sh`
- Seq 913: `scripts/prod_restore_meta_social_rollback.sh`
- Seq 914: `scripts/prod_rollback_meta_social.sh`
- Seq 915: `scripts/prod_set_meta_verify_token.sh`
- Seq 916: `scripts/prod_snapshot_meta_social_rollback.sh`
- Seq 917: `scripts/prod_upsert_model_routing_env.py`
- Seq 918: `scripts/prod_verify_canonical_social_ai.sh`
- Seq 919: `scripts/prod_verify_webhook_challenge.sh`
- Seq 920: `scripts/prod_whatsapp_cloud_migrate.sh`
- Seq 921: `scripts/prod_whatsapp_cloud_phase1_ops.sh`
- Seq 922: `scripts/provision_dashboard_admin.py`
- Seq 923: `scripts/reconcile_meta_app_webhooks.py`
- Seq 924: `scripts/reconcile_meta_comment_webhooks.py`
- Seq 925: `scripts/run_queue_worker.py`
- Seq 926: `scripts/scan_mobile_bundle_secrets.mjs`
- Seq 927: `scripts/scan_tracked_secrets.sh`
- Seq 928: `scripts/seed_meta_app_a_registry.py`
- Seq 929: `scripts/validate_meta_social_token.py`
- Seq 930: `scripts/verify_agent_api_contracts.py`
- Seq 931: `scripts/wa_app_review_temp_bind.py`

</details>

---

## Binary / asset review — `BINARY_ASSET_REVIEW` (81)

| Prefix | Count |
|---|---:|
| `docs/evidence/mobile_design_handoff` | 20 |
| `dashboard/public/brand` | 17 |
| `docs/design/landing` | 12 |
| `mobile/linas-ai/docs` | 11 |
| `docs/design/pdf_pages` | 9 |
| `mobile/linas-ai/assets` | 8 |
| `docs/evidence/public-landing` | 2 |
| `docs/design/LINAS_AI_SCREEN_BY_SCREEN_MOBILE_DESIGN_HANDOFF.pdf` | 1 |
| `mobile/releases/linas-live-chat-android.apk` | 1 |

<details><summary>Full BINARY_ASSET_REVIEW list</summary>

- Seq 77: `dashboard/public/brand/landing/screenshots/linas-landing-01-hero.jpg`
- Seq 78: `dashboard/public/brand/landing/screenshots/linas-landing-02-features.jpg`
- Seq 79: `dashboard/public/brand/landing/screenshots/linas-landing-03-how-it-works.jpg`
- Seq 80: `dashboard/public/brand/landing/screenshots/linas-landing-04-app-tour.jpg`
- Seq 81: `dashboard/public/brand/landing/screenshots/linas-landing-05-pricing.jpg`
- Seq 82: `dashboard/public/brand/landing/screenshots/linas-landing-06-resources.jpg`
- Seq 83: `dashboard/public/brand/landing/screenshots/linas-landing-07-download.jpg`
- Seq 84: `dashboard/public/brand/landing/screenshots/linas-landing-08-contact.jpg`
- Seq 85: `dashboard/public/brand/landing/screenshots/linas-landing-09-guest-ai.jpg`
- Seq 86: `dashboard/public/brand/linas-auth-hero.png`
- Seq 87: `dashboard/public/brand/linas-avatar-chat.png`
- Seq 88: `dashboard/public/brand/linas-avatar-circle.png`
- Seq 89: `dashboard/public/brand/linas-empty-state.png`
- Seq 90: `dashboard/public/brand/linas-state-idle.png`
- Seq 91: `dashboard/public/brand/linas-state-thinking.png`
- Seq 92: `dashboard/public/brand/linas-state-typing.png`
- Seq 93: `dashboard/public/brand/linas-state-welcome.png`
- Seq 385: `docs/design/LINAS_AI_SCREEN_BY_SCREEN_MOBILE_DESIGN_HANDOFF.pdf`
- Seq 397: `docs/design/landing/LINAS_AI_LANDING_PAGE_DESIGN_IMAGES.zip`
- Seq 398: `docs/design/landing/LINAS_AI_LANDING_PAGE_DESIGN_OVERVIEW.jpg`
- Seq 400: `docs/design/landing/implemented-screenshots/01-hero.png`
- Seq 401: `docs/design/landing/implemented-screenshots/design-01-hero.jpg`
- Seq 402: `docs/design/landing/implemented-screenshots/design-02-features.jpg`
- Seq 403: `docs/design/landing/implemented-screenshots/design-03-how-it-works.jpg`
- Seq 404: `docs/design/landing/implemented-screenshots/full-page.png`
- Seq 405: `docs/design/landing/implemented-screenshots/slice-bottom.png`
- Seq 406: `docs/design/landing/implemented-screenshots/slice-lower.png`
- Seq 407: `docs/design/landing/implemented-screenshots/slice-mid.png`
- Seq 408: `docs/design/landing/implemented-screenshots/slice-top.png`
- Seq 409: `docs/design/landing/linas-ai-landing-page-full-design.jpg`
- Seq 410: `docs/design/pdf_pages/page-1.png`
- Seq 411: `docs/design/pdf_pages/page-2.png`
- Seq 412: `docs/design/pdf_pages/page-3.png`
- Seq 413: `docs/design/pdf_pages/page-4.png`
- Seq 414: `docs/design/pdf_pages/page-5.png`
- Seq 415: `docs/design/pdf_pages/page-6.png`
- Seq 416: `docs/design/pdf_pages/page-7.png`
- Seq 417: `docs/design/pdf_pages/page-8.png`
- Seq 418: `docs/design/pdf_pages/page-9.png`
- Seq 424: `docs/evidence/mobile_design_handoff/screenshots/dark_archived.png`
- Seq 425: `docs/evidence/mobile_design_handoff/screenshots/dark_cm_overview.png`
- Seq 426: `docs/evidence/mobile_design_handoff/screenshots/dark_drawer.png`
- Seq 427: `docs/evidence/mobile_design_handoff/screenshots/dark_guest_chat.png`
- Seq 428: `docs/evidence/mobile_design_handoff/screenshots/dark_guest_gate.png`
- Seq 429: `docs/evidence/mobile_design_handoff/screenshots/dark_live_chat.png`
- Seq 430: `docs/evidence/mobile_design_handoff/screenshots/dark_owner_empty.png`
- Seq 431: `docs/evidence/mobile_design_handoff/screenshots/dark_proposal.png`
- Seq 432: `docs/evidence/mobile_design_handoff/screenshots/dark_rtl_mixed.png`
- Seq 433: `docs/evidence/mobile_design_handoff/screenshots/dark_settings.png`
- Seq 434: `docs/evidence/mobile_design_handoff/screenshots/light_archived.png`
- Seq 435: `docs/evidence/mobile_design_handoff/screenshots/light_cm_overview.png`
- Seq 436: `docs/evidence/mobile_design_handoff/screenshots/light_drawer.png`
- Seq 437: `docs/evidence/mobile_design_handoff/screenshots/light_guest_chat.png`
- Seq 438: `docs/evidence/mobile_design_handoff/screenshots/light_guest_gate.png`
- Seq 439: `docs/evidence/mobile_design_handoff/screenshots/light_live_chat.png`
- Seq 440: `docs/evidence/mobile_design_handoff/screenshots/light_owner_empty.png`
- Seq 441: `docs/evidence/mobile_design_handoff/screenshots/light_proposal.png`
- Seq 442: `docs/evidence/mobile_design_handoff/screenshots/light_rtl_mixed.png`
- Seq 443: `docs/evidence/mobile_design_handoff/screenshots/light_settings.png`
- Seq 446: `docs/evidence/public-landing/landing-desktop.png`
- Seq 447: `docs/evidence/public-landing/landing-mobile.png`
- Seq 499: `mobile/linas-ai/assets/android-icon-background.png`
- Seq 500: `mobile/linas-ai/assets/android-icon-foreground.png`
- Seq 501: `mobile/linas-ai/assets/android-icon-monochrome.png`
- Seq 502: `mobile/linas-ai/assets/favicon.png`
- Seq 503: `mobile/linas-ai/assets/icon.png`
- Seq 505: `mobile/linas-ai/assets/splash-icon.png`
- Seq 506: `mobile/linas-ai/assets/splash-native.png`
- Seq 507: `mobile/linas-ai/assets/splash.png`
- Seq 508: `mobile/linas-ai/docs/mockups/linas-dashboard-active-populated-approx.png`
- Seq 509: `mobile/linas-ai/docs/mockups/linas-dashboard-arabic-rtl-approx.png`
- Seq 510: `mobile/linas-ai/docs/mockups/linas-dashboard-dms-ok-comments-blocked-approx.png`
- Seq 511: `mobile/linas-ai/docs/mockups/linas-dashboard-empty-usage-approx.png`
- Seq 512: `mobile/linas-ai/docs/mockups/linas-dashboard-offline-error-approx.png`
- Seq 514: `mobile/linas-ai/docs/subscription-mockups/sub-mock-arabic-rtl.png`
- Seq 515: `mobile/linas-ai/docs/subscription-mockups/sub-mock-current-growth.png`
- Seq 516: `mobile/linas-ai/docs/subscription-mockups/sub-mock-current-lite.png`
- Seq 517: `mobile/linas-ai/docs/subscription-mockups/sub-mock-current-max.png`
- Seq 518: `mobile/linas-ai/docs/subscription-mockups/sub-mock-no-subscription.png`
- Seq 519: `mobile/linas-ai/docs/subscription-mockups/sub-mock-store-unavailable.png`
- Seq 769: `mobile/releases/linas-live-chat-android.apk`

</details>

---

## Other substantive security notes (not KEEP_SECURITY_FIX)

Owner may elevate later. Excludes doc/planning/PII-jsonl boilerplate.

- **Seq 3** `.github/workflows/cm-linas-content-audit.yml` [KEEP_AS_IS] — Uses SSH secrets; masks phones to last4; avoids FAQ/customer bodies. Loads prod .env via setdefault (does not override existing env). Risk: Actions actors with workflow run + secrets can read CM structure summaries.
- **Seq 4** `.github/workflows/cm-production-cutover.yml` [KEEP_AS_IS] — High-impact prod mutations; mitigated by confirmation string + concurrency group. generic_tenant_proof fetches origin/main script mid-run.
- **Seq 9** `.github/workflows/meta-app-a-login-config-apply.yml` [KEEP_AS_IS] — Uses GH environment protection; fails if secret empty; hardcoded redirect https://www.linasaibot.com/oauth/meta/callback
- **Seq 14** `.github/workflows/meta-multi-app-secrets-apply.yml` [KEEP_AS_IS] — Large secret surface (App A/B + encryption key) over SSH envs; advanced access hardcoded false
- **Seq 16** `.github/workflows/meta-social-atomic-cutover.yml` [KEEP_AS_IS] — Highest-impact Meta cutover; confirmation + environment; rollback encryption key required
- **Seq 18** `.github/workflows/meta-social-rollback-snapshot.yml` [KEEP_AS_IS] — No confirmation; creates encrypted archive — lower risk than restore but still prod access
- **Seq 28** `.github/workflows/wa-app-review-connection-source-migrate.yml` [KEEP_AS_IS] — Blocks if public availability not false or App Review bind token set; flock lock; prints db host/name not password
- **Seq 52** `config.py` [KEEP_FIX] — In-memory state not tenant-isolated for multi-instance; FIRESTORE path hardcoded data/firebase_data.json
- **Seq 97** `dashboard/src/MobileLiveChat.auth.test.jsx` [KEEP_AS_IS] — tests requiredPermission liveChat — App.jsx currently omits it (gap)
- **Seq 98** `dashboard/src/components/Auth/ProtectedRoute.jsx` [KEEP_AS_IS] — requiredPermission bypass when user.role===admin; client-only — server auth required. Path checks via canAccessPath.
- **Seq 106** `dashboard/src/components/Layout/Header.jsx` [KEEP_FIX] — shows user email in UI (expected); hardcoded fake notifications not from API
- **Seq 119** `dashboard/src/components/SystemPromptKnowledgeStylePanel.jsx` [DELETE_CANDIDATE] — Would allow unauthenticated write only if mounted without ProtectedRoute; currently unreachable. updateTrainingFile requires authenticated api client when used.
- **Seq 120** `dashboard/src/components/TrainingFileEditor.jsx` [DELETE_CANDIDATE] — restore uses window.confirm only; would POST restore with auth if mounted
- **Seq 129** `dashboard/src/components/UserManagement/UserManagement.jsx` [KEEP_AS_IS] — Relies on AuthContext client permission check before API; server must enforce on /users endpoints
- **Seq 130** `dashboard/src/components/landing/GuestChatPanel.jsx` [LANDING_KEEP] — Guest session ID in localStorage (linas_guest_session_id); no auth; input maxLength 2000; handles GUEST_INPUT_TOO_LARGE and GUEST_MEDIA_BLOCKED codes; rate limit via server session.limit_reached
- **Seq 162** `dashboard/src/hooks/useApiClient.js` [KEEP_AS_IS] — 401 hard redirect; CSRF from localStorage; withCredentials true
- **Seq 164** `dashboard/src/hooks/useApiLiveChat.js` [KEEP_AS_IS] — simulateWebhook debug endpoint exposed via hook — UI must gate
- **Seq 166** `dashboard/src/hooks/useApiTesting.js` [KEEP_FIX] — test endpoints can drive bot with arbitrary phone — server must auth+entitle
- **Seq 179** `dashboard/src/pages/ActivityFlowCard.jsx` [KEEP_AS_IS] — Show technical JSON dumps full entry (phones/messages/CM) to any operator with activityFlow — intentional observability but high PII surface
- **Seq 183** `dashboard/src/pages/Dashboard.jsx` [KEEP_FIX] — links not filtered by user permissions in this page — Sidebar/ProtectedRoute gate destinations
- **Seq 186** `dashboard/src/pages/LiveChat.jsx` [KEEP_AS_IS] — permission via route (mobile missing requiredPermission noted in App audit)
- **Seq 191** `dashboard/src/pages/LiveChatModals.jsx` [KEEP_FIX] — FAQ save-all-languages actions — server must authz
- **Seq 195** `dashboard/src/pages/LiveChatThreadMessages.jsx` [KEEP_AS_IS] — renders image_url/audio_url from server — trust media URLs; media send via composer operator_001 issue upstream
- **Seq 201** `dashboard/src/pages/ResetPassword.jsx` [KEEP_AS_IS] — token in URL query (email link pattern); no client min-length beyond required — server must enforce
- **Seq 306** `deploy/nginx-linasaibot.conf` [KEEP_AS_IS] — HTTP redirect strips query string (line 12); sensitive endpoints use linasbot_safe log format via access_log directive; webhook/oauth/data-deletion logging minimized.
- **Seq 307** `deploy/nginx-privacy-log.conf` [KEEP_AS_IS] — Deliberately excludes $request_uri/$args—reduces OAuth/webhook token leakage into access logs.
- **Seq 308** `deploy/systemd/linasbot-worker@.service` [KEEP_AS_IS] — Runs as root; loads EnvironmentFile .env—ensure file permissions restricted.
- **Seq 463** `handlers/text_handlers_message.py` [KEEP_FIX] — verbose DEBUG prints include user_id, phone, message preview — log PII risk
- **Seq 477** `handlers/text_handlers_respond_phase6.py` [KEEP_AS_IS] — coerces unauthorized human_handover after post-release cooldown
- **Seq 489** `main.py` [KEEP_AS_IS] — access_log=False to avoid webhook query secrets in logs; APK route requires auth+liveChat permission

_Extra security notes listed: 30_

---

## Surface keeps (informational)

- `LANDING_KEEP`: 35
- `KEEP_MOBILE_API`: 16
- `KEEP_AS_IS`: 1190
- `GENERATED_SKIP`: 2

---

## Gate — STOP for owner approval

Phase 0B inventory complete for all tracked files.

**Before Phase 1**, Mahmoud must approve which of the following to execute:
1. Deletes (`DELETE_CANDIDATE`)
2. Security fixes (`KEEP_SECURITY_FIX`)
3. Performance fixes (`KEEP_PERFORMANCE_FIX`)
4. Correctness/product fixes (`KEEP_FIX`)
5. Archive moves (`MOVE_TO_ARCHIVE`)
6. Binary asset decisions (`BINARY_ASSET_REVIEW`)

No application source changes, Meta cutover, DB migration, or deploy from this phase.
