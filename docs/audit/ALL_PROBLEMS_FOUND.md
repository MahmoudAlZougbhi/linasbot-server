# ALL PROBLEMS FOUND — Phase 0B + Phase 0C (complete owner file)

_Sources: `docs/audit/FILE_INVENTORY.csv` (post Phase 0C / commit `f2de99a` + follow-up elevations), `docs/audit/SECURITY_FINDINGS.md` (SEC-001…SEC-070), `docs/audit/KNOWN_SECURITY_CONCERNS.md`, `docs/audit/OVER_500_FILES.md`._

**This is the single owner-facing file Mahmoud should open** for every actionable audit finding. Detail SoTs remain `SECURITY_FINDINGS.md` (full SEC write-ups) and `FILE_INVENTORY.csv` (per-file columns).

---

## Gate — audit-only — STOP before Phase 1

**Audit-only.** Do **not** delete, fix, migrate, Meta-cutover, or deploy until Mahmoud approves Phase 1.

Before Phase 1, Mahmoud must approve which of the following to execute:
1. Security fixes (`KEEP_SECURITY_FIX` + official SEC findings)
2. Performance fixes (`KEEP_PERFORMANCE_FIX`)
3. Correctness / product fixes (`KEEP_FIX`)
4. Deletes (`DELETE_CANDIDATE`)
5. Archive moves (`MOVE_TO_ARCHIVE`)
6. Binary asset decisions (`BINARY_ASSET_REVIEW`)

No application source changes from this document alone.

---

## Inventory parity / review status

- **Inventory rows:** 1544 (`docs/audit/FILE_INVENTORY.csv`)
- **Current `git ls-files`:** 1548
- **Parity note:** inventory trails `git ls-files` by 4 audit-doc path(s) added in Phase 0C commit itself (not application code):
  - `docs/audit/KNOWN_SECURITY_CONCERNS.md`
  - `docs/audit/OVER_500_FILES.md`
  - `docs/audit/PHASE0C_RECONCILIATION.md`
  - `docs/audit/SECURITY_FINDINGS.md`
- Application/product inventory coverage for Phase 0B+0C review targets remains COMPLETE; these 4 are meta audit artifacts.
- **Review status:** all inventory rows `COMPLETE`
- **Fully read:** YES for text sources; NOT_APPLICABLE for binaries
- **Blocked rows:** 0

## Disposition totals

| Disposition | Count |
|---|---:|
| KEEP_SECURITY_FIX | 17 |
| KEEP_PERFORMANCE_FIX | 3 |
| KEEP_FIX | 100 |
| DELETE_CANDIDATE | 46 |
| MOVE_TO_ARCHIVE | 100 |
| BINARY_ASSET_REVIEW | 81 |
| KEEP_SPLIT | 0 |
| LANDING_KEEP | 35 |
| KEEP_MOBILE_API | 15 |
| KEEP_AS_IS | 1145 |
| GENERATED_SKIP | 2 |
| **TOTAL** | **1544** |

_Sum check: 1544 = inventory rows._

---

## Top priority — `KEEP_SECURITY_FIX` (all rows)

**Count: 17** — every inventory row with disposition KEEP_SECURITY_FIX:

- **Seq 6** `.github/workflows/dashboard-auth-secret-apply.yml` — Missing confirmation string gate on high-impact secret apply | NO confirmation input unlike sibling secret-apply workflows — anyone with Actions write on repo can rotate dashboard auth. Secret passed via envs to SSH (expected). | Fails if apply script missing
- **Seq 7** `.github/workflows/deploy.yml` — Pin/update ssh-action version consistency; harden data backup path permissions; keep confirmation for emergency | Emergency bypass skips gate verification (documented). Uses appleboy/ssh-action@v1.0.3 while siblings use v1.2.0 (supply-chain version skew). data/ backup to /tmp/linasbot_data_backup_$$ then restore after hard reset — /tmp world-readable risk window if perms loose. | Restores data/ after reset so local data survives; relies on deploy.sh for service reload. Does not deploy feature branches automatically (main only for workflow_run). | full data/ copy each deploy
- **Seq 8** `.github/workflows/instagram-login-secrets-apply.yml` — Secret apply without confirmation string | No typed confirmation; secrets via SSH envs; never logs values (stated) | Checks out script from origin/main each run
- **Seq 21** `.github/workflows/meta-webhook-nginx-setup.yml` — Verify-token apply without typed confirmation | No confirmation string; rotates verify token — webhook auth impact | Requires non-empty META_WEBHOOK_VERIFY_TOKEN
- **Seq 23** `.github/workflows/openai-api-key-apply.yml` — OpenAI key apply without typed confirmation | No confirmation; applies billing-critical API key | Runs verify script after apply
- **Seq 27** `.github/workflows/subscription-exempt-probe.yml` — Logs entitlement raw + tenant env values + all user display rows to CI logs | Prints SUBSCRIPTION_EXEMPT_TENANT_IDS value, TOKEN_WALLET_UNLIMITED value, linas.json entitlement raw[:400], and per-user tenant/role/status/display names into Actions logs (no emails but business display names + tenant map). Firestore stream of all dashboard_users unbounded. | Exits 0 even when Firestore import fails; legacy APP_DIR linaslaserbot-2.7.22 | Unbounded coll.stream() of all dashboard_users
- **Seq 30** `.github/workflows/whatsapp-cloud-phase1-apply.yml` — Production git reset --hard inside workflow | Confirmation-gated but runs git reset --hard origin/main on /opt/linasbot before ops — can discard server-local uncommitted state | Resets entire deploy tree to main as side effect of flag apply
- **Seq 95** `dashboard/src/App.jsx` — Mobile live-chat route missing requiredPermission | /mobile/live-chat ProtectedRoute WITHOUT requiredPermission=liveChat (tests cover with permission but App omits). Client-side guards only. | Register redirects to /#get-app; analytics/smart-messaging/social-posts/testing redirect away; Training still lazy-imported route /training | 300ms artificial LoadingScreen delay; many lazy routes good; framer motion on shell
- **Seq 126** `dashboard/src/components/UserManagement/RoleManager.jsx` — Active in UserManagement; custom roles in localStorage create cross-admin authorization inconsistency | Custom roles persisted only in browser localStorage (dashboard/src/utils/permissions.jsx CUSTOM_ROLES_KEY) — not shared across admins/devices; assigning custom roleId to server users may not resolve on other browsers | RoleCard tolerates permissions as array via fallback to {} | loads custom roles once on mount — fine
- **Seq 152** `dashboard/src/contexts/AuthContext.helpers.js` — Default role=admin and tenantId=linas in buildUserData when fields absent | agent also flags admin/tenantId defaults as correctness risk | buildUserData defaults role to admin and tenantId to linas when missing — privilege/tenant spoof risk if backend omits fields | emailVerified defaults true when missing
- **Seq 153** `dashboard/src/contexts/AuthContext.jsx` — Session fail-open on errors + debug console.log of auth payloads; active AuthProvider | Fail-open: keeps cached auth_session on transient session errors and catch; console.log of login/session response shapes; CSRF stored in localStorage | 5s safety timeout forces loading=false; 24h local session TTL; validate throttle 10min | session fetch on mount with 5s abort
- **Seq 168** `dashboard/src/hooks/useLiveChatMediaComposer.jsx` — operator_001 hardcoded in sendVoiceMessage and sendImageMessage | hardcoded operator_001; agent KEEP_FIX — elevated as attribution/authz risk | Hardcodes operatorId "operator_001" for voice/image sends — wrong attribution / authz risk | _onAppendMessage unused; relies on SSE for echo | base64 in memory for media
- **Seq 192** `dashboard/src/pages/LiveChatSidebar.jsx` — simulateWebhook and rebuildLiveChatIndex buttons visible in operator sidebar | UI exposes Rebuild index and Test flow (simulateWebhook phone 9613000000) to any liveChat user — high-impact ops without elevated gate | god-object unused vars | list virtualization absent — OK for page_size 30
- **Seq 197** `dashboard/src/pages/MobileLiveChat.jsx` — Active mobile route wrapper | App.jsx ProtectedRoute for /mobile/live-chat omits requiredPermission=liveChat (agent + prior App audit) | route permission gap tracked on App.jsx | Route may be reachable without liveChat permission if URL known; Sidebar gates nav but route does not
- **Seq 203** `dashboard/src/pages/Settings.jsx` — Missing tenantId defaults to linas enabling ops settings tabs | Missing tenantId defaults to linas enabling ops settings tabs | also loads unused botName/enableVoice/humanTakeoverNotifyMobiles (agent KEEP_FIX debt) | (user?.tenantId || "linas") === "linas" unlocks general/notifications when tenantId missing — same default-tenant risk | loads unused fields botName/enableVoice etc. but saves only defaultLanguage | Loads unused general fields but only saves defaultLanguage; stale Lina's Laser Bot default branding in local state
- **Seq 535** `mobile/linas-ai/src/auth/guestSession.ts` — Weak Math.random guest session id generation | ID entropy via Math.random filling Uint8Array — not crypto.getRandomValues; guest ids more guessable | clearGuestSessionId never called after login/register
- **Seq 801** `modules/live_chat_api_debug.py` — Authenticated+liveChat via middleware; insufficient authz for debug dump/rebuild; exposes Firestore conversation metadata | Routes registered in production via main→modules.live_chat_api→import live_chat_api_debug. NOT public: DashboardAuthMiddleware requires authenticated session + liveChat permission for /api/live-chat*. Non-linas tenants blocked from /api/live-chat*. Handler itself has no Depends/role check. GET /api/live-chat/debug-firestore streams all users' conversation metadata (ids, message_count, status, human_takeover, index last_message_text). GET /api/live-chat/status exposes index/users counts. POST /api/live-chat/rebuild-index triggers live_chat_service.rebuild_index_from_firestore (ops-level). Any liveChat operator can invoke — insufficient elevation → KEEP_SECURITY_FIX HIGH. | status/debug lack tenant scoping beyond middleware linas gate; rebuild uses optional max_users query caps | debug-firestore unbounded users_collection.stream + per-user conversations.stream — expensive under load

---

## Official security findings — `SECURITY_FINDINGS.md` (every finding ID)

All findings below are **OPEN**. Full evidence/tests live in `docs/audit/SECURITY_FINDINGS.md`.

| Severity | Count |
|---|---:|
| CRITICAL | 2 |
| HIGH | 15 |
| MEDIUM | 18 |
| LOW | 16 |
| INFO | 19 |
| **TOTAL** | **70** |

### CRITICAL (2)

- **SEC-010** — seq 152 `dashboard/src/contexts/AuthContext.helpers.js` · `KEEP_SECURITY_FIX` — If backend omits role/tenantId, client elevates to role=admin and tenantId=linas — privilege/tenant spoof.
- **SEC-017** — seq 870 `scripts/delete_all_conversations.py` · `MOVE_TO_ARCHIVE` — Anyone with shell access and working Firebase creds (data/firebase_data.json / get_firestore_db) runs --confirm and deletes ALL conversations + live_chat_index under artifacts/linas-ai-bot-backend. No RBAC, no typed phrase beyond --confirm, no structured audit log.

### HIGH (15)

- **SEC-001** — seq 6 `.github/workflows/dashboard-auth-secret-apply.yml` · `KEEP_SECURITY_FIX` — Anyone with Actions write can rotate DASHBOARD_AUTH_SECRET without typed confirmation.
- **SEC-002** — seq 7 `.github/workflows/deploy.yml` · `KEEP_SECURITY_FIX` — Emergency bypass skips Quality Gates; ssh-action@v1.0.3 version skew; data/ copied to world-readable /tmp during reset.
- **SEC-003** — seq 8 `.github/workflows/instagram-login-secrets-apply.yml` · `KEEP_SECURITY_FIX` — Actions write can apply Instagram app secret + webhook verify token without typed confirmation.
- **SEC-004** — seq 21 `.github/workflows/meta-webhook-nginx-setup.yml` · `KEEP_SECURITY_FIX` — Rotates META_WEBHOOK_VERIFY_TOKEN without typed confirmation — webhook auth impact.
- **SEC-005** — seq 23 `.github/workflows/openai-api-key-apply.yml` · `KEEP_SECURITY_FIX` — Billing-critical OpenAI key can be rotated without typed confirmation.
- **SEC-006** — seq 27 `.github/workflows/subscription-exempt-probe.yml` · `KEEP_SECURITY_FIX` — CI logs print entitlement env values, linas.json entitlement raw[:400], and all dashboard_users tenant/role/display rows; unbounded Firestore stream.
- **SEC-008** — seq 95 `dashboard/src/App.jsx` · `KEEP_SECURITY_FIX` — Authenticated user without liveChat permission can open /mobile/live-chat if URL known; tests expect requiredPermission but App omits it.
- **SEC-009** — seq 126 `dashboard/src/components/UserManagement/RoleManager.jsx` · `KEEP_SECURITY_FIX` — Custom roles in localStorage only — cross-admin/device authz inconsistency; custom roleId on server may not resolve elsewhere.
- **SEC-011** — seq 153 `dashboard/src/contexts/AuthContext.jsx` · `KEEP_SECURITY_FIX` — Fail-open keeps cached auth_session on transient session errors; console.log of auth payloads; CSRF in localStorage.
- **SEC-013** — seq 192 `dashboard/src/pages/LiveChatSidebar.jsx` · `KEEP_SECURITY_FIX` — Any liveChat operator sees Rebuild index and Test flow (simulateWebhook 9613000000) — high-impact ops without elevated gate.
- **SEC-014** — seq 197 `dashboard/src/pages/MobileLiveChat.jsx` · `KEEP_SECURITY_FIX` — Same permission gap as App.jsx — route reachable without liveChat if URL known.
- **SEC-015** — seq 203 `dashboard/src/pages/Settings.jsx` · `KEEP_SECURITY_FIX` — Missing tenantId defaults to linas, unlocking general/notifications ops tabs.
- **SEC-016** — seq 801 `modules/live_chat_api_debug.py` · `KEEP_SECURITY_FIX` — Authenticated liveChat operator (not necessarily admin) can GET debug-firestore (dumps all conversation metadata) and POST rebuild-index. Middleware requires auth+liveChat — NOT unauthenticated — but elevation is insufficient.
- **SEC-028** — seq 98 `dashboard/src/components/Auth/ProtectedRoute.jsx` · `KEEP_AS_IS` — requiredPermission bypass when user.role===admin; client-only — server auth required. Path checks via canAccessPath.
- **SEC-070** — seq 535 `mobile/linas-ai/src/auth/guestSession.ts` · `KEEP_SECURITY_FIX` — Guest session IDs filled via `Math.random` into `Uint8Array` instead of `crypto.getRandomValues` — more guessable guest ids across devices/sessions.

### MEDIUM (18)

- **SEC-007** — seq 30 `.github/workflows/whatsapp-cloud-phase1-apply.yml` · `KEEP_SECURITY_FIX` — Confirmation-gated but runs git reset --hard origin/main on /opt/linasbot — can discard server-local state.
- **SEC-012** — seq 168 `dashboard/src/hooks/useLiveChatMediaComposer.jsx` · `KEEP_SECURITY_FIX` — Hardcodes operatorId operator_001 — wrong attribution / authz risk on media sends.
- **SEC-025** — seq 52 `config.py` · `KEEP_FIX` — In-memory state not tenant-isolated for multi-instance; FIRESTORE path hardcoded data/firebase_data.json
- **SEC-027** — seq 97 `dashboard/src/MobileLiveChat.auth.test.jsx` · `KEEP_AS_IS` — tests requiredPermission liveChat — App.jsx currently omits it (gap)
- **SEC-030** — seq 109 `dashboard/src/components/Layout/Sidebar.jsx` · `KEEP_FIX` — Live Chat/Activity Flow/APK gated to tenantId===linas client-side; admin sees all permitted items; Missing tenantId defaults to linas unlocking Live Chat/Activity Flow/APK ops surfaces
- **SEC-036** — seq 164 `dashboard/src/hooks/useApiLiveChat.js` · `KEEP_AS_IS` — simulateWebhook debug endpoint exposed via hook — UI must gate
- **SEC-037** — seq 166 `dashboard/src/hooks/useApiTesting.js` · `KEEP_FIX` — test endpoints can drive bot with arbitrary phone — server must auth+entitle
- **SEC-038** — seq 179 `dashboard/src/pages/ActivityFlowCard.jsx` · `KEEP_AS_IS` — Show technical JSON dumps full entry (phones/messages/CM) to any operator with activityFlow — intentional observability but high PII surface
- **SEC-039** — seq 183 `dashboard/src/pages/Dashboard.jsx` · `KEEP_FIX` — links not filtered by user permissions in this page — Sidebar/ProtectedRoute gate destinations
- **SEC-040** — seq 186 `dashboard/src/pages/LiveChat.jsx` · `KEEP_AS_IS` — permission via route (mobile missing requiredPermission noted in App audit)
- **SEC-041** — seq 191 `dashboard/src/pages/LiveChatModals.jsx` · `KEEP_FIX` — FAQ save-all-languages actions — server must authz
- **SEC-047** — seq 463 `handlers/text_handlers_message.py` · `KEEP_FIX` — verbose DEBUG prints include user_id, phone, message preview — log PII risk
- **SEC-048** — seq 477 `handlers/text_handlers_respond_phase6.py` · `KEEP_AS_IS` — coerces unauthorized human_handover after post-release cooldown
- **SEC-054** — seq 1161 `services/meta_messaging.py` · `KEEP_FIX` — HMAC signature verification on webhooks; page tokens from env/registry
- **SEC-058** — seq 1171 `services/mobile_refresh_token_service.py` · `KEEP_FIX` — secrets/billing surface — server-side only; API authz required
- **SEC-059** — seq 1227 `services/owner_push_token_store.py` · `KEEP_FIX` — secrets/billing surface — server-side only; API authz required
- **SEC-065** — seq 1290 `services/token_wallet_models.py` · `KEEP_FIX` — linas default tenant reference; secrets/billing surface — server-side only; API authz required
- **SEC-067** — seq 1295 `services/user_service.py` · `KEEP_FIX` — bcrypt hashing; query timeouts; tenant-scoped collection paths

### LOW (16)

- **SEC-018** — seq 3 `.github/workflows/cm-linas-content-audit.yml` · `KEEP_AS_IS` — Uses SSH secrets; masks phones to last4; avoids FAQ/customer bodies. Loads prod .env via setdefault (does not override existing env). Risk: Actions actors with workflow run + secrets can read CM structure summaries.
- **SEC-019** — seq 4 `.github/workflows/cm-production-cutover.yml` · `KEEP_AS_IS` — High-impact prod mutations; mitigated by confirmation string + concurrency group. generic_tenant_proof fetches origin/main script mid-run.
- **SEC-020** — seq 9 `.github/workflows/meta-app-a-login-config-apply.yml` · `KEEP_AS_IS` — Uses GH environment protection; fails if secret empty; hardcoded redirect https://www.linasaibot.com/oauth/meta/callback
- **SEC-021** — seq 14 `.github/workflows/meta-multi-app-secrets-apply.yml` · `KEEP_AS_IS` — Large secret surface (App A/B + encryption key) over SSH envs; advanced access hardcoded false
- **SEC-022** — seq 16 `.github/workflows/meta-social-atomic-cutover.yml` · `KEEP_AS_IS` — Highest-impact Meta cutover; confirmation + environment; rollback encryption key required
- **SEC-023** — seq 18 `.github/workflows/meta-social-rollback-snapshot.yml` · `KEEP_AS_IS` — No confirmation; creates encrypted archive — lower risk than restore but still prod access
- **SEC-024** — seq 28 `.github/workflows/wa-app-review-connection-source-migrate.yml` · `KEEP_AS_IS` — Blocks if public availability not false or App Review bind token set; flock lock; prints db host/name not password
- **SEC-026** — seq 53 `config/montymobile_templates.json` · `DELETE_CANDIDATE` — Commits api_id, tenant UUID, source phone 96178974402; api_key empty (good). Template wa_message_id/record_guid are provider IDs.
- **SEC-029** — seq 106 `dashboard/src/components/Layout/Header.jsx` · `KEEP_FIX` — shows user email in UI (expected); hardcoded fake notifications not from API
- **SEC-031** — seq 119 `dashboard/src/components/SystemPromptKnowledgeStylePanel.jsx` · `DELETE_CANDIDATE` — Would allow unauthenticated write only if mounted without ProtectedRoute; currently unreachable. updateTrainingFile requires authenticated api client when used.
- **SEC-032** — seq 120 `dashboard/src/components/TrainingFileEditor.jsx` · `DELETE_CANDIDATE` — restore uses window.confirm only; would POST restore with auth if mounted
- **SEC-034** — seq 130 `dashboard/src/components/landing/GuestChatPanel.jsx` · `LANDING_KEEP` — Guest session ID in localStorage (linas_guest_session_id); no auth; input maxLength 2000; handles GUEST_INPUT_TOO_LARGE and GUEST_MEDIA_BLOCKED codes; rate limit via server session.limit_reached
- **SEC-035** — seq 162 `dashboard/src/hooks/useApiClient.js` · `KEEP_AS_IS` — 401 hard redirect; CSRF from localStorage; withCredentials true
- **SEC-042** — seq 195 `dashboard/src/pages/LiveChatThreadMessages.jsx` · `KEEP_AS_IS` — renders image_url/audio_url from server — trust media URLs; media send via composer operator_001 issue upstream
- **SEC-043** — seq 201 `dashboard/src/pages/ResetPassword.jsx` · `KEEP_AS_IS` — token in URL query (email link pattern); no client min-length beyond required — server must enforce
- **SEC-046** — seq 308 `deploy/systemd/linasbot-worker@.service` · `KEEP_AS_IS` — Runs as root; loads EnvironmentFile .env—ensure file permissions restricted.

### INFO (19)

- **SEC-033** — seq 129 `dashboard/src/components/UserManagement/UserManagement.jsx` · `KEEP_AS_IS` — Relies on AuthContext client permission check before API; server must enforce on /users endpoints
- **SEC-044** — seq 306 `deploy/nginx-linasaibot.conf` · `KEEP_AS_IS` — HTTP redirect strips query string (line 12); sensitive endpoints use linasbot_safe log format via access_log directive; webhook/oauth/data-deletion logging minimized.
- **SEC-045** — seq 307 `deploy/nginx-privacy-log.conf` · `KEEP_AS_IS` — Deliberately excludes $request_uri/$args—reduces OAuth/webhook token leakage into access logs.
- **SEC-049** — seq 489 `main.py` · `KEEP_AS_IS` — access_log=False to avoid webhook query secrets in logs; APK route requires auth+liveChat permission
- **SEC-050** — seq 1101 `services/guest_ai_service.py` · `KEEP_AS_IS` — FORBIDDEN_GUEST_TOOLS denylist blocks CM/tool writes; no tenant mutation by design
- **SEC-051** — seq 1145 `services/meta_app_registry_oauth.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-052** — seq 1157 `services/meta_instagram_login_oauth.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-053** — seq 1160 `services/meta_instagram_login_tokens.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-055** — seq 1163 `services/meta_oauth.py` · `KEEP_AS_IS` — tokens encrypted via meta_app_registry AES-GCM; state TTL 10min; scopes validated
- **SEC-056** — seq 1164 `services/meta_oauth_graph.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-057** — seq 1165 `services/meta_oauth_return.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-060** — seq 1254 `services/sensitive_request_logging.py` · `KEEP_AS_IS` — redacts tokens/secrets in logs — must remain installed at startup
- **SEC-061** — seq 1276 `services/store_iap_service.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-062** — seq 1277 `services/stripe_checkout_service.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-063** — seq 1288 `services/token_metering.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-064** — seq 1289 `services/token_package_catalog.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-066** — seq 1291 `services/token_wallet_service.py` · `KEEP_AS_IS` — InsufficientTokenBalance fail-closed; threaded RLock on wallet files
- **SEC-068** — seq 1297 `services/wallet_spend_analytics.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required
- **SEC-069** — seq 1315 `services/whatsapp_cloud/crypto.py` · `KEEP_AS_IS` — secrets/billing surface — server-side only; API authz required

---

## Performance — `KEEP_PERFORMANCE_FIX` (all rows)

**Count: 3**

- **Seq 13** `.github/workflows/meta-comment-webhooks-reconcile.yml` — Full requirements install for thin reconcile script; consider lean deps later | Confirmation-gated; optional page subscription reconcile boolean | Installs full requirements.txt in CI for a script — heavy but correct isolation | pip install full reqs each run (slow)
- **Seq 102** `dashboard/src/components/Common/LoadingScreen.jsx` — Expensive splash + outdated feature copy | feature cards still say AI Testing/Smart Training — outdated copy | heavy framer animations on every auth load
- **Seq 160** `dashboard/src/hooks/useApi.jsx` — Primary dashboard API hook; LOC-split under 500 | App.jsx calls useApi() mainly for botStatus but instantiates all API sub-hooks (agent) | inherits axios CSRF/credentials from useApiClient | spread merge may overwrite keys if modules collide — currently partitioned | instantiates all API modules even when page needs one — extra hook closures | useApi() on AppContent mount loads testing/QA/training/liveChat/content hooks even when only botStatus needed

---

## Correctness / product — `KEEP_FIX` (all paths)

**Count: 100** — grouped by theme; every path listed.

### CI / GitHub Actions (4)

- **Seq 10** `.github/workflows/meta-app-a-scope-audit.yml` — Stale feature-branch checkout dependency | Sources production .env into shell (tokens in process env). Read-only intent. | HARDCODES git fetch/checkout of branch fix/ig-fb-comments-capability-gates — brittle if branch deleted/renamed; may run stale scripts
- **Seq 12** `.github/workflows/meta-comment-runtime-probe.yml` — Hardcoded feature branch for probe script | Read-only SSH | Same brittle checkout from fix/ig-fb-comments-capability-gates as seq10
- **Seq 22** `.github/workflows/model-routing-policy-apply.yml` — Unlike copilot-v2 workflow, does not always refresh script from main when present | Confirmation-gated; readiness curl after apply | Installs script from origin/main if missing else chmod only — may leave stale script if file exists but outdated
- **Seq 29** `.github/workflows/wa-cloud-webhook-readonly-probe.yml` — Stale hardcoded date windows and soft exit 0 | Redacts long digit runs in event_key; sources full .env into shell | Hardcoded TIMESTAMPTZ windows 2026-08-11 — stale after that day; many failures exit 0 (silent soft-fail) | LIMIT 50 on events

### Repo / env / docs root (3)

- **Seq 2** `.env.example` — Required template; needs product-aligned reordering/deprecation notes for Monty vs Meta Cloud (no secret leak; fix is documentation clarity) | Placeholders only (no live secrets). Documents MONTY* and BOC LINASLASER tokens as first-class. SOCIAL_WHATSAPP_* include real E.164 business numbers (public contact routing, not API secrets). | Documents dual WhatsApp stacks (Monty section + WA Cloud flags). Comments say Cloud never falls back to Monty; product intent is Meta Cloud—template still educates Monty as primary 'WhatsApp provider' section.
- **Seq 31** `.gitignore` — Keep; clean obsolete PHP ignores and finish jsonl untrack after owner approval | Ignores .env and firebase_data.json; documents tracked jsonl still pending owner decision (PII_EXPOSURE_REPORT) | Some CodeIgniter/PHP legacy ignore patterns remain (user_guide_src, vendor/, php_errors) — copied heritage
- **Seq 40** `README-LOCAL.md` — Env filename mismatch and legacy dashboard-centric flow | Instructs real EXTERNAL_API_TOKEN use locally | References cp .env.local.example .env.local but repo documents .env.example as only env file — mismatch

### Config (2)

- **Seq 47** `api_config.py` — Duplicate config surface; misleading path comment | Prints warning if token missing (no secret leak); default base URL https://boc-lb.com/agent/ | Duplicates config.py LINASLASER_* vars; comment says data/api_config.py but path is repo root api_config.py
- **Seq 52** `config.py` — Central config must stay; fix identity/defaults/state scaling in later phases | In-memory state not tenant-isolated for multi-instance; FIRESTORE path hardcoded data/firebase_data.json | WELCOME_MESSAGES still brand Marwa / Lina Laser (CM cutover risk); DEFAULT_*_ID=1 silent defaults; BOOKING flags env-driven | unbounded per-user deques except MAX_CONTEXT_MESSAGES; load files at import

### Docker / backend image (3)

- **Seq 50** `backend/Dockerfile.simple` — Port 8000 vs project standard 8003 | --reload in image unsuitable for prod | HEALTHCHECK curls :8000/health but other Dockerfiles use 8003 — port inconsistency | reload overhead
- **Seq 51** `backend/requirements.txt` — Dual requirements files can drift | Pins older openai/fastapi etc may diverge from root requirements.txt | Duplicate dependency source of truth risk vs root requirements.txt
- **Seq 310** `docker-compose.yml` — Hardcoded tradershubs API URL in dashboard service env (line 65) diverges from prod nginx same-origin design. | Dev compose exposes Redis 6379 and mounts repo—dev only. | REACT_APP_API_URL=https://bot.tradershubs.site/api is stale/wrong for linasaibot.com local dev—conflicts with vite same-origin pattern.

### Dashboard (web) (22)

- **Seq 56** `dashboard/Dockerfile.prod` — Standard SPA prod image | Node 20 image vs engines>=22.19.0 mismatch (agent forensic) | REACT_APP_* baked at build; npm ci --legacy-peer-deps fallbacks; runs as nginx default user | Uses package-lock via npm ci; Builder FROM node:20-alpine but package.json engines require node>=22.19.0 | multi-stage good
- **Seq 94** `dashboard/public/manifest.json` — Stale purple theme + emoji icon vs current brand | theme_color #d946ef purple leftover; emoji robot data-URI icon not brand SVG
- **Seq 96** `dashboard/src/App.routes.test.jsx` — Useful regression for analytics redirect | Useful redirect test but does not exercise real App router | does not import real App — partial route mirror; Does not import App.jsx — tests stub routes only
- **Seq 101** `dashboard/src/components/Common/ErrorBoundary.jsx` — Silent network error passthrough may mask outages | logs errors only in development | ERR_NETWORK / Network Error silently returns children — can hide failures
- **Seq 106** `dashboard/src/components/Layout/Header.jsx` — Hardcoded sample notifications present false Live alerts | shows user email in UI (expected); hardcoded fake notifications not from API | botStatus prop unused (_botStatus); notifications are sample data misleading as Live | framer animations
- **Seq 109** `dashboard/src/components/Layout/Sidebar.jsx` — Missing tenantId defaults to linas unlocking ops surfaces | tenantId||linas default can wrongly expose ops surface | Live Chat/Activity Flow/APK gated to tenantId===linas client-side; admin sees all permitted items; Missing tenantId defaults to linas unlocking Live Chat/Activity Flow/APK ops surfaces | default tenantId linas if missing — could wrongly show ops surface | health poll 60s OK
- **Seq 114** `dashboard/src/components/LiveChat/MobileLiveChatThreadPane.jsx` — Unreachable status copy branch; media URL trust boundary | renders image_url/audio_url from API — SSRF/XSS depends on URL allowlisting server-side; accept=image/* client only | dead branch text currentStatus===human inside else of currentStatus===human (unreachable copy) | maps full history; no windowing
- **Seq 118** `dashboard/src/components/LiveChat/ModernAudioPlayer.jsx` — 8 Live Chat importers; widely used. Minor play-state desync on failed audio.play() | Client sends arbitrary audioUrl to GET /api/media/audio?url=…; SSRF mitigated server-side in modules/media_api.py (_fetch_with_ssrf_guard, tests/test_wave1_security.py). Player does not sanitize URL display in console.error. | handlePlayPause sets isPlaying via toggle before audio.play() resolves; failed play can leave UI out of sync until onError fires | Single <audio> per message; external proxy adds server round-trip per play; acceptable for chat scale
- **Seq 125** `dashboard/src/components/UserManagement/PermissionMatrix.jsx` — Imported by UserForm and RoleManager on active Settings users tab; double-toggle bubble risk | Active PermissionMatrix; double-toggle risk on card click | UI-only; enforcement depends on server accepting permissions on user CRUD | Card onClick and inner checkbox onChange both call handleToggle — click on toggle may double-fire (bubble); Card onClick and checkbox onChange may double-toggle on click bubble | 11 animated cards with staggered delay — negligible
- **Seq 147** `dashboard/src/constants/permissions.jsx` — Central RBAC map used by ProtectedRoute and permissions utils; tests assert live-chat + FAQ routes | FEATURE_METADATA exported with zero importers; TRAINING legacy naming (agent) | Client-side role templates only; server must enforce. training permission still on roles while FEATURES.TRAINING is legacy redirect. | ANALYTICS and DASHBOARD both map path /app; FEATURES.TRAINING path /training but PATH maps /training to contentManagers — intentional FAQ single-entry | FEATURE_METADATA unused export; ANALYTICS.path same as DASHBOARD (/app)
- **Seq 149** `dashboard/src/constants/productFeatures.js` — SAAS_NAV_ITEMS active on Dashboard; DISABLED_FRONTEND_ROUTES + isDisabledFrontendRoute have zero callers | Disabled routes listed but not enforced by this helper (dead) — App.jsx may still route separately | isDisabledFrontendRoute unused — disabled surface gating may be incomplete vs constants
- **Seq 157** `dashboard/src/contexts/OperatorStatusContext.jsx` — Active provider in App; silent fallback violates fail-loud preference | agent KEEP_AS_IS but silent no-op outside provider remains KEEP_FIX | useOperatorStatus silently falls back to no-op setter when outside provider — hidden fallback
- **Seq 158** `dashboard/src/contexts/PermissionsContext.jsx` — Core permissions context mounted in App | App wraps PermissionsProvider but usePermissions() has zero consumers; migrateUsers on mount is sole active behavior (agent) | UI-only; migrateUsers() localStorage migration on every mount | none | usePermissions unused; Sidebar/ProtectedRoute call utils/permissions directly | roles memo empty deps — OK static
- **Seq 165** `dashboard/src/hooks/useApiQA.js` — Still part of useApi; product surface disabled but API client retained | submitFeedback used by live chat; ~15 legacy QA/local-qa methods have zero page consumers (agent) | getQACategories returns hardcoded mock categories offline | Large dead QA CRUD surface still exported via useApi; getQACategories hardcoded offline fallback
- **Seq 166** `dashboard/src/hooks/useApiTesting.js` — Offline mock success:true replies for testText/image/voice/webhook; route disabled but code live in facade | test endpoints can drive bot with arbitrary phone — server must auth+entitle | Many ERR_NETWORK paths return success:true mock bot replies — can look like real AI when offline
- **Seq 174** `dashboard/src/index.jsx` — Application entrypoint | Dev console.error/unhandledrejection suppress ERR_NETWORK — masks backend-down failures (agent) | dev suppresses Network Error console noise and unhandledrejection ERR_NETWORK | DEV patches console.error and unhandledrejection to hide Network Error / ERR_NETWORK
- **Seq 183** `dashboard/src/pages/Dashboard.jsx` — Shows all SAAS_NAV_ITEMS regardless of user permissions | Shows all SAAS_NAV_ITEMS regardless of user permissions | agent: thin hub but tiles not permission-filtered | links not filtered by user permissions in this page — Sidebar/ProtectedRoute gate destinations | no permission filter on nav tiles
- **Seq 189** `dashboard/src/pages/LiveChatBotOverlay.jsx` — God-object prop dump; already <500 but needs prop narrowing | God-object unused destructuring/imports (eslint-disable); functional overlay in LiveChatThread | massive unused destructuring (eslint-disable) | eslint-disable no-unused-vars; 60+ unused controller fields and dead imports (FeedbackModal, ModernAudioPlayer, etc.) | duplicates sidebar list UI
- **Seq 190** `dashboard/src/pages/LiveChatDetails.jsx` — Dead Transfer/Priority buttons mislead operators | Transfer to Another Operator and Mark as Priority buttons are no-ops (no onClick handlers)
- **Seq 191** `dashboard/src/pages/LiveChatModals.jsx` — Active modals; prop dump pattern like siblings | Active modals; duplicate fragment wrappers + unused-import LOC-split debt | FAQ save-all-languages actions — server must authz | god-object destructure; duplicate fragment wrappers | duplicate nested fragments; god-object unused destructure
- **Seq 194** `dashboard/src/pages/LiveChatThreadHeader.jsx` — Active header; same full-controller prop pattern | Active header; unused-import / full-controller destructuring debt from LOC split | god-object destructure
- **Seq 196** `dashboard/src/pages/Login.jsx` — Dev connection help embeds personal absolute paths | Hardcodes personal laptop paths /Users/mahmoudalzougbhi/linas ai bot in connection error UI — wrong for other machines and leaks local layout

### Deploy / nginx (1)

- **Seq 305** `deploy/nginx-api-include.conf` — Active deploy snippet per README; drift vs full config on /oauth/ routes. | access_log off + crit-only error_log on webhook/data-deletion/integrations; owner-ai SSE has 300s timeout and proxy_buffering off. | Snippet lacks /oauth/ and /meta/deauthorize present in full nginx-linasaibot.conf—include-only installs may miss OAuth routes. | SSE location disables buffering—correct for streaming.

### Docs (stale / product) (2)

- **Seq 313** `docs/ANALYTICS_LOGIC.md` — Accurate event logic but references removed /analytics dashboard route. | Documents user_id masking ...XXXX for privacy. | Stale: dashboard Analytics sidebar route redirected to /app in App.jsx:141; doc line 113 outdated.
- **Seq 318** `docs/CLAUDE_MEMORY.md` — Useful but 495 lines with version-specific claims that may be outdated. | States v2.7.22 and deprecated conversation_log—partially stale vs CM cutover and current branch; use with caution.

### Handlers / Firestore (7)

- **Seq 456** `firestore.indexes.json` — rg: live_chat_index query paths in live_chat_service_*; doc drift on index #3 collection | docs/FIRESTORE_INDEXES.md item 3 mentions conversations collection_group human_takeover_active but JSON defines live_chat_index.human_takeover_active — doc/index mismatch | required for ordered/filtered live_chat_index queries at scale
- **Seq 457** `handlers/VERSION.py` — rg: only handlers/text_handlers.py imports VERSION; stale build notes | Stale: BUILD_ID NAME_COLLECTION_v1, LAST_MODIFIED 2025-01-24, CHANGES claims 5 modular files while tree has 20+ handler modules | print_version_info() runs on every text_handlers import (noisy logs)
- **Seq 462** `handlers/text_handlers_firestore.py` — rg: _delayed_processing_tasks imported by webhook dedupe, dashboard lab, social processor | misnamed file (re-exports many non-firestore symbols) — maintainability debt | in-memory task dict per worker
- **Seq 463** `handlers/text_handlers_message.py` — rg: 7+ importers; tests enforce LOC split | verbose DEBUG prints include user_id, phone, message preview — log PII risk | text_turn_epoch prevents duplicate sends; training mode delegation; MAX_TEXT_LINES guard | sentiment + optional Firestore sentiment update per message; per-user asyncio.Lock in greeting module
- **Seq 472** `handlers/text_handlers_respond_phase12.py` — rg: terminal phase; dead _pack block after halt return | unreachable _pack after return _PHASE_HALT (dead code) | analytics + optional training log per turn
- **Seq 482** `handlers/text_handlers_start.py` — rg: exported from text_handlers; webhook_process comments removed direct call | webhook start_command_whatsapp no longer calls start_command directly — possible dead export
- **Seq 484** `handlers/voice_handlers.py` — rg: webhook_handlers_voice + dashboard lab import handle_voice_message | uses synchronous conv_doc_ref.get() inside async handler (blocks event loop); skip_firestore_save prevents double-save | pydub transcode + Whisper API per voice message

### Mobile app (13)

- **Seq 536** `mobile/linas-ai/src/auth/tokenStore.ts` — Validate stored user JSON; prior KEEP_AS_IS thin | getUser JSON.parse without Zod — corrupt/unexpected SecureStore JSON can throw or yield untyped role data | unvalidated parse can crash auth hydration
- **Seq 542** `mobile/linas-ai/src/components/PrimaryButton.tsx` — Static colors break dark theme on widely used button | Uses static colors import instead of useTheme — dark mode inconsistent
- **Seq 543** `mobile/linas-ai/src/components/SideDrawer.tsx` — Theme + Dimensions issues on live NavDrawer | static colors; dead empty if(!open) block; Dimensions.get at module scope | SCREEN_W stale on rotation can mis-size drawer
- **Seq 544** `mobile/linas-ai/src/components/StatusChip.tsx` — Static theme colors on live badges | static colors — not theme-resolved
- **Seq 545** `mobile/linas-ai/src/components/TextField.tsx` — Static theme on primary form control | static colors — dark mode mismatch
- **Seq 549** `mobile/linas-ai/src/features/auth/RegisterScreen.tsx` — Weak password gate + non-i18n errors need fix | client allows password length >=6 — weak client-side minimum vs common policy | error strings hardcoded English ('Registration failed'/'Network error') bypass i18n; RegisterSchema only success/error
- **Seq 568** `mobile/linas-ai/src/features/chat/ChatScreen.tsx` — Dead isPlatformOwner prop + always-null workspaceLabel need cleanup/wiring | none elevated — guest drafts saved locally; auth gate on limit | isPlatformOwner declared in Props but not used; workspaceLabel always passed null to ChatHeader | 386 lines under 500; multiple hooks per turn — monitored by scroll/stream tests
- **Seq 627** `mobile/linas-ai/src/features/cm/cmMediaApi.ts` — Live ArticlesEditor caller; FormData part shape risks Expo 57 upload failures | auth via apiUpload | FormData appends RN {uri,name,type} Blob cast — Expo SDK 57 may reject (owner upload uses appendLocalFile instead)
- **Seq 710** `mobile/linas-ai/src/features/shared/SimpleResourceScreen.tsx` — Useful for resource routes but EN-hardcoded copy should use tr(). | Shows raw JSON only in __DEV__ | Hardcoded English error/empty strings (not i18n).
- **Seq 731** `mobile/linas-ai/src/i18n/locales/whatsappAr.ts` — Incomplete ar/fr translation for WhatsApp keys. | whatsappAr.ts and whatsappFr.ts still contain mostly English strings — incomplete localization.
- **Seq 733** `mobile/linas-ai/src/i18n/locales/whatsappFr.ts` — Incomplete ar/fr translation for WhatsApp keys. | whatsappAr.ts and whatsappFr.ts still contain mostly English strings — incomplete localization.
- **Seq 736** `mobile/linas-ai/src/theme/ThemeContext.tsx` — Fail-open useTheme conflicts with no-hidden-fallback product rule; should throw like useI18n. | useTheme() silently returns lightColors + no-op setMode when provider missing (hidden fail-open).
- **Seq 745** `mobile/linas-ai/tests/design_handoff.test.mjs` — Stale DRAWER_MODULES order assertion (expects cm in grid, omits smartFollowUp) conflicts with drawerModules.ts and navDrawerSmartFollowUp.test.mjs — will fail or was not updated. | Stale drawer order expectations vs drawerModules.ts

### API modules (24)

- **Seq 773** `modules/auth_api.py` — Working auth surface but linas default tenant coalescing needs Wave 3 style cleanup. | Public login/register etc via is_public_api. Login defaults tenantId to linas when missing. Session path without user_id closes IDOR; legacy /session/{user_id} self-only. | tenant_id or 'linas' default on login/forgot paths — multi-tenant footgun if stale users lack tenantId. | login retries with sleeps on backend unavailable
- **Seq 775** `modules/auth_users_api.py` — Functional but linas coalescing + in-memory filter deserve cleanup. | require_session + middleware userManagement permission. Cross-tenant create/update forbidden. Filters by session.tenant_id. Defaults tenantId or 'linas' when reading users. | linas default on missing tenantId; role 'owner' vs 'platform_owner' naming in seat filter. | get_all_users then filter in memory
- **Seq 781** `modules/content_files_api.py` — Legacy global file API; should be archived or tenant-scoped — not safe as SaaS surface. | No Depends; middleware contentManagers. No tenant_id — global storage (linas-era). migrate-legacy mutates files. | Not multi-tenant safe; superseded by CM for SaaS tenants.
- **Seq 785** `modules/dashboard_api_health.py` — Keep health endpoints; Monty-default readiness should align with Meta Cloud product. | Public health/ready; ready never echoes secrets; Monty key required when provider=montymobile in prod. | Default WHATSAPP_PROVIDER montymobile in ready check — legacy bias. | ready probes multiple deps
- **Seq 787** `modules/dashboard_api_lab_message.py` — Product-disabled but ~470 LOC of dead lab body should be removed/archived after owner GO — not KEEP_SPLIT (already under 500 and split). | Lab handlers call _refuse_disabled_lab_endpoint first. Middleware also disables prefixes. simulate-webhook additionally requires non-prod + ALLOW_DEBUG_SIMULATE_WEBHOOK. Dead code after refuse still contains provider switch logic (unreachable). | Large unreachable bodies after refuse — maintenance burden.
- **Seq 788** `modules/dashboard_api_lab_upload.py` — Disable or remove /api/stats remnant; uploads already refused. | Upload routes refuse disabled. /api/stats NOT in DISABLED_API_PREFIXES — still live for authenticated analytics permission (middleware maps /api/stats to analytics). | /api/stats returns in-memory lab stats including recent conversation snippets — low value, possible info leak to analytics-role users.
- **Seq 789** `modules/dashboard_api_lab_voice.py` — Same as other lab leftovers — delete unreachable bodies when GO. | Immediate _refuse_disabled_lab_endpoint; middleware disables /api/test-* | Dead bodies after refuse
- **Seq 792** `modules/event_handlers.py` — Must stop defaulting MontyMobile when product is Meta Cloud. | Still initializes MontyMobile as default WhatsApp provider on startup (legacy); error message mentions Qiscus. Continues on adapter failure. | scheduler starts on boot
- **Seq 793** `modules/event_handlers_monitor_jobs.py` — Approaching 500 LOC with dead continue-indent block; fix dead code / consider further split — not yet KEEP_SPLIT (>500 rule). | uses job locks; sends WhatsApp to real customers when enabled | Indent/unreachable block historically risk in preview path (lines ~88-99 under continue) — dead code after continue; monitor job is large (~474 LOC). | scans scheduled messages; Firestore writes per send
- **Seq 794** `modules/event_handlers_populate_jobs.py` — Not wired in current scheduler start — verify before DELETE_CANDIDATE. | Populate jobs not registered in event_handlers_scheduler.start_smart_messaging_scheduler — potentially orphaned job functions. | appointment API fetches
- **Seq 799** `modules/instructions_api.py` — Legacy global instructions file API; align with CM or archive. | middleware training permission; restore uses resolve_backup_filename path safety. | Global single style guide — not tenant-scoped (linas-era).
- **Seq 800** `modules/live_chat_api.py` — Core live chat API with leftover debug file logging and wildcard SSE CORS header. | Mutations use require_session + reject_social_operator_mutation. Reads rely on middleware liveChat. SSE sets Access-Control-Allow-Origin: *. mark-read/operator-status lack explicit require_session in handler (middleware still auth). | Leftover agent debug region writes JSONL to .cursor/debug-420609.log on get_conversation_details — must remove. | SSE long-lived connections; unified chats pagination
- **Seq 818** `modules/models.py` — Monty/dual-WA references — Cloud cutover pending
- **Seq 827** `modules/settings_api.py` — Monty/dual-WA references — Cloud cutover pending | GET /api/settings/integrations returns redacted configured/missing flags only (no secret values); lists Monty/Cloud env key names
- **Seq 828** `modules/smart_messaging_api.py` — Smart messaging still imports/uses Monty language/provider helpers (_monty_whatsapp_language_code / dual send paths) — Cloud cutover pending
- **Seq 830** `modules/smart_messaging_api_send_template.py` — Explicit MontyMobile template send implementation — Cloud cutover pending | no per-route Depends; /api/* gated by DashboardAuthMiddleware (smartMessaging permission). Sends via montymobile_template_service. | Docstring/route still MontyMobile-centric; language via _monty_whatsapp_language_code
- **Seq 831** `modules/smart_messaging_api_send_test.py` — Monty/dual-WA references — Cloud cutover pending | no per-route Depends; /api/* gated by DashboardAuthMiddleware session+RBAC
- **Seq 835** `modules/smart_messaging_api_templates.py` — Monty language helper still core to template APIs — Cloud cutover pending | no per-route Depends; /api/* gated by DashboardAuthMiddleware (smartMessaging) | _monty_whatsapp_language_code maps persisted language to Monty template language codes
- **Seq 839** `modules/webhook_handlers.py` — WhatsAppFactory montymobile path still wired at startup via event_handlers | webhook verify uses hmac.compare_digest on WHATSAPP_WEBHOOK_VERIFY_TOKEN; query token in request
- **Seq 840** `modules/webhook_handlers_dedupe.py` — Monty/dual-WA references — Cloud cutover pending
- **Seq 842** `modules/webhook_handlers_photo.py` — Monty/dual-WA references — Cloud cutover pending
- **Seq 843** `modules/webhook_handlers_process.py` — Monty/dual-WA references — Cloud cutover pending
- **Seq 844** `modules/webhook_handlers_voice.py` — Monty/dual-WA references — Cloud cutover pending
- **Seq 845** `modules/whatsapp_adapters.py` — Legacy send_whatsapp_message uses WHATSAPP_API_TOKEN Bearer; prints full response JSON; typing indicator simulated | Authorization Bearer WHATSAPP_API_TOKEN; logs response.json() to stdout (PII risk)

### Services (19)

- **Seq 945** `services/api_integrations_booking.py` — Uses os.getenv in create/body-part helpers but file does not import os — NameError on those code paths | Missing `import os` while calling os.getenv for LINASLASER_BODY_PARTS_ITEM_ID_KEY / CREATE_APPOINTMENT_LEGACY_BODY_PARTS / FORCE_BODY_PARTS_WITH_SESSIONS / APPOINTMENT_BODY_PART_IDS_ONLY / UPDATE_DATE_SET_STATUS_AVAILABLE
- **Seq 946** `services/api_integrations_catalog.py` — Uses os.getenv for body-parts/service-data paths without importing os | Missing `import os` while calling os.getenv for LINASLASER_GET_BODY_PARTS_PATH / LINASLASER_SERVICE_DATA_PATH
- **Seq 948** `services/api_integrations_edit.py` — Uses os.getenv for edit/paused paths without importing os | Missing `import os` while calling os.getenv for LINASLASER_APPOINTMENTS_EDIT_PATH / UPDATE_PAUSED_APPOINTMENT_PATH / UPDATE_PAUSED_DEFAULT_STATUS_AVAILABLE
- **Seq 980** `services/chat_response_runtime_tool_create_name.py` — Monty/dual-WA references — Cloud cutover pending
- **Seq 1161** `services/meta_messaging.py` — Active Meta messaging adapter; linas default tenant_id in dataclass should derive from binding only | HMAC signature verification on webhooks; page tokens from env/registry | MetaMessagingSettings defaults tenant_id=linas — multi-tenant risk if binding tenant omitted
- **Seq 1171** `services/mobile_refresh_token_service.py` — Mobile auth tokens should require explicit tenant_id | secrets/billing surface — server-side only; API authz required | refresh token payload defaults tenant_id to linas
- **Seq 1175** `services/montymobile_template_service.py` — Phase 0C W0C-D full re-read: active Monty template path with real importers; KEEP_FIX for legacy Monty retention + broad exception swallowing on send — migrate/retire when Cloud-only. | API key forced from MONTYMOBILE_API_KEY env (tracked JSON key stripped). Logs tenant/api_id but not raw key. Still legacy provider surface — only for Monty-configured tenants. | Broad except Exception on send path returns success:False (logged). Nested bare except around payload.to extraction and JSON error parse. Treats Monty success=true without messageId as failure (good).
- **Seq 1176** `services/montymobile_template_service_payload.py` — Phase 0C W0C-D full re-read: required companion mixin for Monty template sends; KEEP_FIX with parent Monty legacy path. | none on static review (no secrets; debug prints template ids/params — avoid enabling noisy DEBUG in prod logs with PII phones) | Language dict coerced to 'ar' default; body parameters_count padding with empty strings when named slots missing — can still produce Monty 'invalid body variables' if config wrong. Header image lookup soft-fails on message_preview_service import errors.
- **Seq 1203** `services/owner_alert_store.py` — Owner alert persistence; linas default on empty tenant | tenant path defaults to linas
- **Seq 1227** `services/owner_push_token_store.py` — Push token store; linas default on empty tenant | secrets/billing surface — server-side only; API authz required | tenant path defaults to linas
- **Seq 1270** `services/social_contact_routing.py` — Active social routing; linas fallback breaks multi-tenant isolation | defaults tenant_id to linas when missing in user_data
- **Seq 1271** `services/social_contact_routing_detect.py` — Phone routing detection; linas-centric defaults need tenant-scoped config | resolve_social_whatsapp_number defaults tenant_id=linas; env override only for linas
- **Seq 1273** `services/social_messaging_processor.py` — Meta social event processor; linas fallback on missing tenant | event tenant_id falls back to settings.tenant_id or linas
- **Seq 1274** `services/social_user_id.py` — Cross-channel user id helper; linas default risks id collision across tenants | scopes social user ids with linas default tenant
- **Seq 1290** `services/token_wallet_models.py` — Billing models active; empty tenant_id should not silently become linas in SaaS | linas default tenant reference; secrets/billing surface — server-side only; API authz required | normalize tenant defaults to linas when empty
- **Seq 1295** `services/user_service.py` — Active auth service; linas default tenant normalization needs fail-closed for new tenants | bcrypt hashing; query timeouts; tenant-scoped collection paths | _normalize_tenant_id defaults missing tenant to linas — SaaS isolation risk | blocking sleep; streaming iteration — watch memory on large sets
- **Seq 1302** `services/whatsapp_adapters/montymobile_adapter.py` — Phase 0C W0C-D full re-read: factory-selected when Monty configured; KEEP_FIX for silent except around cloud dual-bind guard + stub template send + broad swallow — harden/retire with Monty deprecation. | Holds api-key in instance headers. Intended fail-closed via cloud_blocks_monty_send(source_number) before text send — but bare `except Exception: pass` around that guard means import/runtime errors silently allow send (fail-open). | Broad except Exception on all send_* paths returns success:False. HTTP 200 non-JSON assumed success for text/image. send_audio_message falls back to text link. Adapter send_template_message is a stub (sends plain text 'Template: name') — real templates go through montymobile_template_service.
- **Seq 1303** `services/whatsapp_adapters/montymobile_adapter_parse.py` — Phase 0C W0C-D full re-read: required by montymobile_adapter; KEEP_FIX with Monty legacy adapter cluster. | none on static review (parser only; ignores own source_number echoes and status-only webhooks) | Broad except Exception returns None on parse failures (logged). Status-only Meta webhooks ignored. Uses message.from over contacts[].wa_id when they disagree. Room→phone mapping can fall back to room_id as-is.
- **Seq 1319** `services/whatsapp_cloud/legacy_isolation.py` — Phase 0C W0C-D full re-read: active callers (event_handlers, montymobile_adapter); KEEP_FIX — document/harden fail-open on DB scan failure vs advertised fail-closed. | Intended fail-closed on dual Monty+Cloud ownership of same number. Gap: cloud_bound_display_digits() returns empty set on DB/scan Exception (emits event) — dual-bind assert then sees no overlap (fail-open on scan failure). is_phone_number_id_cloud_bound similarly returns False on error. | Overlap compares full digits and last4 against active WhatsAppConnection rows. cloud_blocks_monty_send only blocks when sending as the Monty source that is also Cloud-bound — not arbitrary customer destinations. | cloud_bound_display_digits scans all active WhatsAppConnection rows (pilot-scale comment in source)

---

## Delete candidates — `DELETE_CANDIDATE` (all rows)

**Count: 46** — zero external importers after module-path recheck (or orphan cluster / orphan test). Do not delete until Mahmoud approves.

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
- **Seq 575** `mobile/linas-ai/src/features/chat/CreatePostTaskChips.tsx` — No importers after full module-path recheck; orphan | orphan component; static colors
- **Seq 576** `mobile/linas-ai/src/features/chat/CreativeDraftCard.tsx` — Zero importers; superseded/unwired | orphan; static colors; English hardcoding
- **Seq 577** `mobile/linas-ai/src/features/chat/GuestBanner.tsx` — No importers after module-path recheck; orphan candidate
- **Seq 579** `mobile/linas-ai/src/features/chat/HistoryDrawer.tsx` — No importers after module-path recheck; orphan candidate
- **Seq 592** `mobile/linas-ai/src/features/chat/createPostTasks.ts` — Only imported by orphan CreatePostTaskChips; intent fn unused | orphan catalog + unused intent detector
- **Seq 649** `mobile/linas-ai/src/features/control/ControlCenterDrawer.tsx` — rg finds zero production imports; only negative test mention; NavDrawer is the live drawer | Marked @deprecated Prefer NavDrawer; GROUP_LABELS_SAFE duplicates controlAreas GROUP_LABELS
- **Seq 687** `mobile/linas-ai/src/features/livechat/LiveChatComposer.tsx` — Zero importers; design_handoff forbids LiveChatComposer in thread; product is read-only | records audio / picks images | Dead UI: LiveChatThread explicitly read-only and does not mount composer
- **Seq 759** `mobile/live-chat-android/README.md` — Documents superseded WebView wrapper; Expo LiveChatScreen is product operator path. Confirm no staff still build this before delete.
- **Seq 760** `mobile/live-chat-android/app/build.gradle.kts` — Part of legacy WebView app cluster; Expo supersedes. | release minify disabled
- **Seq 761** `mobile/live-chat-android/app/proguard-rules.pro` — Cluster member of live-chat-android. | no hardening rules yet
- **Seq 762** `mobile/live-chat-android/app/src/main/AndroidManifest.xml` — Cleartext + backup flags on legacy wrapper; prefer delete with cluster. | android:usesCleartextTraffic=true; allowBackup=true; broad media permissions for WebView.
- **Seq 763** `mobile/live-chat-android/app/src/main/java/com/linaslaser/livechat/MainActivity.kt` — Superseded by Expo LiveChatScreen; WebView wrapper not primary product. | JS enabled; third-party cookies accepted; mixed content compatibility mode; SetJavaScriptEnabled suppressLint. | full WebView
- **Seq 764** `mobile/live-chat-android/app/src/main/res/layout/activity_main.xml` — Cluster member.
- **Seq 765** `mobile/live-chat-android/app/src/main/res/values/strings.xml` — Cluster member. | App branded Lina Live Chat (legacy naming).
- **Seq 766** `mobile/live-chat-android/build.gradle.kts` — Cluster member.
- **Seq 767** `mobile/live-chat-android/gradle.properties` — Cluster member; production URL in repo is OK for wrapper but project obsolete. | points at production domain in tracked file
- **Seq 768** `mobile/live-chat-android/settings.gradle.kts` — Cluster member.
- **Seq 865** `scripts/cm/inventory_snapshot.py` — No tracked callers
- **Seq 866** `scripts/cm/run_migration_dry.py` — No tracked callers
- **Seq 869** `scripts/debug_firestore_chats.py` — No tracked callers | uses Firestore credentials path (FIRESTORE_SERVICE_ACCOUNT_KEY_PATH / data/firebase_data.json)
- **Seq 871** `scripts/diagnose_outbound_dedupe.py` — No tracked callers
- **Seq 874** `scripts/migrate_phone_identity.py` — No tracked callers | uses Firestore credentials path (FIRESTORE_SERVICE_ACCOUNT_KEY_PATH / data/firebase_data.json)
- **Seq 877** `scripts/phase2_load_simulation.py` — No tracked callers
- **Seq 878** `scripts/plan_economics_simulation.py` — No tracked callers
- **Seq 930** `scripts/verify_agent_api_contracts.py` — No tracked callers
- **Seq 970** `services/bot_data_service.py` — Phase 0C: only self + PERSISTENT_STORAGE_REFACTOR.md mention; no runtime importers — DELETE_CANDIDATE
- **Seq 1090** `services/dynamic_model_selector.py` — Zero importers — orphan service with module-level singleton only
- **Seq 1092** `services/enhanced_message_handler.py` — Zero importers — orphan; production uses handlers/* + chat_response_runtime
- **Seq 1098** `services/faq_translation_service.py` — Zero importers — orphan; only cleanup_reports reference
- **Seq 1099** `services/gender_detection.py` — Only imported by orphan services/enhanced_message_handler.py — dead chain
- **Seq 1123** `services/live_monitoring.py` — Zero importers; duplicate of live_chat_service architecture; safe archive candidate after confirm no dynamic import | in-memory only; not wired to live_chat_service or SSE
- **Seq 1139** `services/message_queue_service.py` — No static importers; storage paths remain for data compat — remove code after confirming no cron references | orphaned; smart_messaging_queue.py is active queue path | full JSON load/save on each operation if ever invoked
- **Seq 1140** `services/message_sync_service.py` — Zero importers; only pairs with unused message_queue_service | orphaned companion to message_queue_service | would scan all appointments if invoked

---

## Archive candidates — `MOVE_TO_ARCHIVE`

**Count: 100**

| Area | Count | Examples |
|---|---:|---|
| `scripts` | 44 | `scripts/appointment_api_manual_probe.py`, `scripts/audit/line_count_gate.py`, `scripts/audit_meta_app_a_scopes.py` |
| `docs (other)` | 18 | `docs/CM_FULL_CORPUS_LEDGER.md`, `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md`, `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md` |
| `docs/cm_phase_evidence` | 11 | `docs/cm_phase_evidence/PHASE0.md`, `docs/cm_phase_evidence/PHASE1.md`, `docs/cm_phase_evidence/PHASE2.md` |
| `docs/evidence` | 9 | `docs/evidence/customer_reply_ai_v2/01_baseline_audit.md`, `docs/evidence/customer_reply_ai_v2/02_dod_evidence_report.md`, `docs/evidence/mobile_design_handoff/02_dod_evidence_report.md` |
| `.planning` | 7 | `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONCERNS.md`, `.planning/codebase/CONVENTIONS.md` |
| `docs/design` | 6 | `docs/design/MAHMOUD_MOBILE_PROMPT.md`, `docs/design/MAHMOUD_MOBILE_PROMPT_content_management.md`, `docs/design/MAHMOUD_MOBILE_PROMPT_guest_chat.md` |
| `data` | 4 | `data/analytics_events.jsonl`, `data/conversation_log.jsonl`, `data/qa_pairs.jsonl` |
| `dashboard` | 1 | `dashboard/README.md` |

<details><summary>Full MOVE_TO_ARCHIVE list (all paths)</summary>

- Seq 32: `.planning/codebase/ARCHITECTURE.md` — Dated 2026-01-19; diverges from current CI/CM/WA Cloud/mobile product
- Seq 33: `.planning/codebase/CONCERNS.md` — Stale concern list contradicts current repo state
- Seq 34: `.planning/codebase/CONVENTIONS.md` — Superseded by ruff/mypy and current practices
- Seq 35: `.planning/codebase/INTEGRATIONS.md` — Stale integration map vs Meta Cloud + social OAuth reality
- Seq 36: `.planning/codebase/STACK.md` — Dated stack without mobile-first stack
- Seq 37: `.planning/codebase/STRUCTURE.md` — Describes old tree and pages
- Seq 38: `.planning/codebase/TESTING.md` — Contradicts current automated test reality
- Seq 57: `dashboard/README.md` — Severely outdated README with wrong ports/domains/features
- Seq 282: `data/analytics_events.jsonl` — Runtime/historical event dump better archived out of main tree; service can use live path outside git
- Seq 284: `data/conversation_log.jsonl` — JSONL data file; refs: no external refs found
- Seq 292: `data/qa_pairs.jsonl` — JSONL data file; refs: no external refs found
- Seq 293: `data/reports_log.jsonl` — JSONL data file; refs: no external refs found
- Seq 319: `docs/CM_FULL_CORPUS_LEDGER.md` — Phase2/stale or superseded documentation naming/content | agent: Tied to active CM cutover workflow and migration code.
- Seq 321: `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_architecture.md` — Phase2/stale or superseded documentation naming/content
- Seq 322: `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_overview.md` — Phase2/stale or superseded documentation naming/content
- Seq 324: `docs/CONTENT_MANAGEMENT_AI_CONTROL_PLANE_PLAN_runtime.md` — Phase2/stale or superseded documentation naming/content
- Seq 330: `docs/LIVE_CHAT_FIX_SUMMARY.md` — Phase2/stale or superseded documentation naming/content
- Seq 342: `docs/META_VERIFIED_APP_CUTOVER_RUNBOOK.md` — Phase2/stale or superseded documentation naming/content
- Seq 343: `docs/PHASE2_FINAL_REPORT.md` — Phase2/stale or superseded documentation naming/content
- Seq 344: `docs/PHASE2_FIREBASE_MOBILE_AUTH_AUDIT.md` — Phase2/stale or superseded documentation naming/content
- Seq 345: `docs/PHASE2_IAP_EXTERNAL_CHECKLIST.md` — Phase2/stale or superseded documentation naming/content
- Seq 346: `docs/PHASE2_MOBILE_BETA_REPORT.md` — Phase2/stale or superseded documentation naming/content
- Seq 347: `docs/PHASE2_MOBILE_BETA_STATUS.md` — Phase2/stale or superseded documentation naming/content
- Seq 348: `docs/PHASE2_PRE_RELEASE_REPORT.md` — Phase2/stale or superseded documentation naming/content
- Seq 349: `docs/PHASE2_PRODUCTION_RECONCILE.md` — Phase2/stale or superseded documentation naming/content
- Seq 350: `docs/PHASE2_TESTFLIGHT_GATE.md` — Phase2/stale or superseded documentation naming/content
- Seq 351: `docs/PHASE2_TIKTOK_SNAP_CAPABILITY_AUDIT.md` — Phase2/stale or superseded documentation naming/content
- Seq 352: `docs/PHASE2_WAVE0_STATUS.md` — Phase2/stale or superseded documentation naming/content
- Seq 353: `docs/PHASE2_WEB_STORE_LINKS.md` — Phase2/stale or superseded documentation naming/content
- Seq 374: `docs/cm_phase_evidence/PHASE0.md` — Historical evidence capture; not runtime
- Seq 375: `docs/cm_phase_evidence/PHASE1.md` — Historical evidence capture; not runtime
- Seq 376: `docs/cm_phase_evidence/PHASE2.md` — Historical evidence capture; not runtime
- Seq 377: `docs/cm_phase_evidence/PHASE3.md` — Historical evidence capture; not runtime
- Seq 378: `docs/cm_phase_evidence/PHASE4.md` — Historical evidence capture; not runtime
- Seq 379: `docs/cm_phase_evidence/PHASE5.md` — Historical evidence capture; not runtime
- Seq 380: `docs/cm_phase_evidence/PHASE6.md` — Historical evidence capture; not runtime
- Seq 381: `docs/cm_phase_evidence/PHASE7.md` — Historical evidence capture; not runtime
- Seq 382: `docs/cm_phase_evidence/PHASE8.md` — Historical evidence capture; not runtime
- Seq 383: `docs/cm_phase_evidence/phase0_fixture_inventory.json` — Historical evidence capture; not runtime
- Seq 384: `docs/cm_phase_evidence/phase4_migration_conflict_report.json` — Historical evidence capture; not runtime
- Seq 386: `docs/design/MAHMOUD_MOBILE_PROMPT.md` — Design handoff/docs; product may have moved on
- Seq 387: `docs/design/MAHMOUD_MOBILE_PROMPT_content_management.md` — Design handoff/docs; product may have moved on
- Seq 389: `docs/design/MAHMOUD_MOBILE_PROMPT_guest_chat.md` — Design handoff/docs; product may have moved on
- Seq 390: `docs/design/MAHMOUD_MOBILE_PROMPT_live_chat.md` — Design handoff/docs; product may have moved on
- Seq 392: `docs/design/MAHMOUD_MOBILE_PROMPT_quality_and_verification.md` — Design handoff/docs; product may have moved on
- Seq 419: `docs/design/pdf_text/handoff.txt` — Design handoff/docs; product may have moved on
- Seq 420: `docs/evidence/customer_reply_ai_v2/01_baseline_audit.md` — Historical evidence capture; not runtime
- Seq 421: `docs/evidence/customer_reply_ai_v2/02_dod_evidence_report.md` — Historical evidence capture; not runtime
- Seq 423: `docs/evidence/mobile_design_handoff/02_dod_evidence_report.md` — Historical evidence capture; not runtime
- Seq 444: `docs/evidence/phase2_load_simulation.json` — Historical evidence capture; not runtime
- Seq 445: `docs/evidence/plan_economics_wave0.json` — Historical evidence capture; not runtime
- Seq 448: `docs/evidence/system_copilot_diagnosis_faq.json` — Historical evidence capture; not runtime
- Seq 449: `docs/evidence/system_copilot_v2/01_baseline_audit.md` — Historical evidence capture; not runtime
- Seq 450: `docs/evidence/system_copilot_v2/02_dod_evidence_report.md` — Historical evidence capture; not runtime
- Seq 451: `docs/evidence/system_copilot_v2/capability_manifest.json` — Historical evidence capture; not runtime
- Seq 455: `docs/whatsapp_cloud/WHATSAPP_CLOUD_COEXISTENCE.md` — Phase2/stale or superseded documentation naming/content
- Seq 856: `scripts/appointment_api_manual_probe.py` — Manual appointment API probe; no workflow or import callers
- Seq 857: `scripts/audit/line_count_gate.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 858: `scripts/audit_meta_app_a_scopes.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 859: `scripts/audit_meta_bindings_readonly.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 860: `scripts/backfill_live_chat_index.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 861: `scripts/check_copilot_v2_manifest.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 862: `scripts/check_message_flow.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 863: `scripts/check_provider_status.py` — Phase 0C: no workflow refs; restore MOVE_TO_ARCHIVE (ops/probe script)
- Seq 867: `scripts/cm_prepare_remove_linas_bridge.py` — Ops/dev utility; no GitHub workflow callers verified — archive rather than delete
- Seq 868: `scripts/cm_publish_tenant.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 870: `scripts/delete_all_conversations.py` — Phase 0C lead: MOVE_TO_ARCHIVE/protected-ops; official SEC finding retained (not KEEP_SECURITY_FIX disposition to avoid implying in-app route fix)
- Seq 872: `scripts/manage_meta_page_subscription.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 873: `scripts/meta_webhook_contract.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 875: `scripts/montymobile_manual_probe.py` — Monty outbound/inbound probe only; zero production imports
- Seq 881: `scripts/prod_apply_instagram_login_secrets.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 883: `scripts/prod_apply_meta_multi_app.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 887: `scripts/prod_apply_whatsapp_cloud_phase1_flags.sh` — Ops/dev utility; no GitHub workflow callers verified — archive rather than delete
- Seq 901: `scripts/prod_cm_publish_faq_only.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 902: `scripts/prod_cm_repair_linas_prices_publish.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 903: `scripts/prod_cm_rollback.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 904: `scripts/prod_cm_rollback_version.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 905: `scripts/prod_cm_runtime_proof.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 906: `scripts/prod_cm_set_linas_bridge_flag.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 907: `scripts/prod_cm_sot_audit.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 908: `scripts/prod_cm_verify_durable_bridge.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 909: `scripts/prod_cutover_meta_social.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 910: `scripts/prod_meta_comment_runtime_probe.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 911: `scripts/prod_meta_dm_live_watch.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 912: `scripts/prod_preflight_readonly.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 913: `scripts/prod_restore_meta_social_rollback.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 914: `scripts/prod_rollback_meta_social.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 915: `scripts/prod_set_meta_verify_token.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 916: `scripts/prod_snapshot_meta_social_rollback.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 917: `scripts/prod_upsert_model_routing_env.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 918: `scripts/prod_verify_canonical_social_ai.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 919: `scripts/prod_verify_webhook_challenge.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 920: `scripts/prod_whatsapp_cloud_migrate.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 921: `scripts/prod_whatsapp_cloud_phase1_ops.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 922: `scripts/provision_dashboard_admin.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 925: `scripts/run_queue_worker.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 926: `scripts/scan_mobile_bundle_secrets.mjs` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 927: `scripts/scan_tracked_secrets.sh` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 928: `scripts/seed_meta_app_a_registry.py` — Ops/probe script; Phase 0C re-read; archive candidate
- Seq 931: `scripts/wa_app_review_temp_bind.py` — App-review temp script; not production runtime

</details>

---

## Binary / asset review — `BINARY_ASSET_REVIEW`

**Count: 81**

| Prefix | Count |
|---|---:|
| `docs/evidence/mobile_design_handoff` | 20 |
| `dashboard/public/brand` | 17 |
| `docs/design/landing` | 12 |
| `mobile/linas-ai/docs` | 11 |
| `docs/design/pdf_pages` | 9 |
| `mobile/linas-ai/assets` | 8 |
| `docs/evidence/public-landing` | 2 |
| `docs/design (other)` | 1 |
| `mobile/releases` | 1 |

<details><summary>Full BINARY_ASSET_REVIEW list (all paths)</summary>

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

## Previously known security concerns (`KNOWN_SECURITY_CONCERNS.md`)

Each concern has **exactly one** status. Full evidence in `docs/audit/KNOWN_SECURITY_CONCERNS.md`.

| # | Concern | Status | Evidence (short) |
|---|---|---|---|
| 1 | Mobile login and refresh rate limiting | **ALREADY_FIXED** | `services/auth_rate_limits.py` `auth_rate_limit_rules` for `/api/auth/mobile/login` and `/api/auth/mobile/refresh` (IP + identifier buckets). Wired via `modules… |
| 2 | Trusted proxy / client-IP resolution | **ALREADY_FIXED** | `client_ip()` prefers `X-Real-IP` (nginx `$remote_addr`), does **not** trust leftmost `X-Forwarded-For`. `TRUSTED_PROXY_MODE=direct |
| 3 | Wallet admin-credit authorization | **ALREADY_FIXED** | `modules/wallet_api.py` `_admin_credit_allowed` + `assert_admin_credit_target_allowed` — cross-tenant only `platform_owner`; allowlisted tenant admins same-tena… |
| 4 | Production CORS | **ALREADY_FIXED** | `modules/core.py` `cors_allow_origins()` — production drops `http://linasaibot.com` / `http://www…`; keeps HTTPS + localhost. Commit `caacdfe`. |
| 5 | Tenant assertions on shared handlers | **CONFIRMED_FIX_REQUIRED** | Middleware gate **exists**: non-`linas` sessions blocked from legacy `/api/live-chat` etc. (`modules/api_security.py`). Remaining gap: many services still silen… |
| 6 | Role/permission elevation | **CONFIRMED_FIX_REQUIRED** | `dashboard/src/contexts/AuthContext.helpers.js` `buildUserData` defaults `role=admin` and `tenantId=linas`; `RoleManager` custom roles in `localStorage`; `Prote… |
| 7 | CSRF and constant-time secret comparison | **ALREADY_FIXED** | Cookie mutations require CSRF header+cookie; `hmac.compare_digest` in `modules/api_security.py`. Also webhook verify tokens use `compare_digest`. Commit `536555… |
| 8 | Filename/path sanitization | **ALREADY_FIXED** | `services/media_service.py` `sanitize_media_filename` + `resolve_media_file_path` (`relative_to` containment); `services/safe_path.py` for backup/restore. Cover… |
| 9 | Distributed production rate limiting | **CONFIRMED_FIX_REQUIRED** | `services/rate_limit_service.py` is **file-backed per-process** only (`_DATA_ROOT/auth/rate_limits`). No Redis/distributed limiter implemented in-tree. Multi-in… |

### Status counts

| Status | Count |
|---|---:|
| ALREADY_FIXED | 6 |
| CONFIRMED_FIX_REQUIRED | 3 |

### False positives

| Item | Status | Evidence |
|---|---|---|
| `services/cm/shadow_eval.py` “eval() present” | **FALSE_POSITIVE** | Only symbol is `run_shadow_eval`; no Python `eval(` builtin. |

### Blocked

None for the nine known concerns above.

---

## KEEP_SPLIT / files >500 LOC

- **KEEP_SPLIT disposition count:** **0** (zero).
- **Hand-written application/tracked product files >500 physical lines:** **0** (see `docs/audit/OVER_500_FILES.md`).
- Stale `docs/audit/FILES_OVER_500.csv` is a pre-split W00 snapshot — **not** current truth.
- Excluded from gate: `docs/audit/*` report artifacts, `data/*.jsonl` dumps, generated lockfiles, binaries.
- Characterization tests still needed for former god-file facades (LiveChat, chat_response_service, utils, live_chat_service, text_handlers_respond) — split debt, not LOC debt.

---

## Surface keeps (informational — not fix queues)

- `LANDING_KEEP`: 35
- `KEEP_MOBILE_API`: 15
- `KEEP_AS_IS`: 1145
- `GENERATED_SKIP`: 2

---

## Appendix A — Actionable path index (quick scan)

Paths that need owner decision before Phase 1 (security + performance + fix + delete):

**166 paths**

- `DELETE_CANDIDATE` · Seq 53 · `config/montymobile_templates.json`
- `DELETE_CANDIDATE` · Seq 100 · `dashboard/src/components/BotInstructionsTab.jsx`
- `DELETE_CANDIDATE` · Seq 103 · `dashboard/src/components/ContentFilesPanel.jsx`
- `DELETE_CANDIDATE` · Seq 104 · `dashboard/src/components/DynamicMessagesPanel.jsx`
- `DELETE_CANDIDATE` · Seq 119 · `dashboard/src/components/SystemPromptKnowledgeStylePanel.jsx`
- `DELETE_CANDIDATE` · Seq 120 · `dashboard/src/components/TrainingFileEditor.jsx`
- `DELETE_CANDIDATE` · Seq 121 · `dashboard/src/components/TrainingFileEditor.locSplit.test.js`
- `DELETE_CANDIDATE` · Seq 122 · `dashboard/src/components/TrainingFileEditor.meta.js`
- `DELETE_CANDIDATE` · Seq 123 · `dashboard/src/components/TrainingFileEditorBackups.jsx`
- `DELETE_CANDIDATE` · Seq 124 · `dashboard/src/components/TrainingFileEditorSearch.jsx`
- `DELETE_CANDIDATE` · Seq 131 · `dashboard/src/components/landing/LinasBotMascot.jsx`
- `DELETE_CANDIDATE` · Seq 146 · `dashboard/src/constants/linasBrand.js`
- `DELETE_CANDIDATE` · Seq 172 · `dashboard/src/hooks/usePermissions.jsx`
- `DELETE_CANDIDATE` · Seq 575 · `mobile/linas-ai/src/features/chat/CreatePostTaskChips.tsx`
- `DELETE_CANDIDATE` · Seq 576 · `mobile/linas-ai/src/features/chat/CreativeDraftCard.tsx`
- `DELETE_CANDIDATE` · Seq 577 · `mobile/linas-ai/src/features/chat/GuestBanner.tsx`
- `DELETE_CANDIDATE` · Seq 579 · `mobile/linas-ai/src/features/chat/HistoryDrawer.tsx`
- `DELETE_CANDIDATE` · Seq 592 · `mobile/linas-ai/src/features/chat/createPostTasks.ts`
- `DELETE_CANDIDATE` · Seq 649 · `mobile/linas-ai/src/features/control/ControlCenterDrawer.tsx`
- `DELETE_CANDIDATE` · Seq 687 · `mobile/linas-ai/src/features/livechat/LiveChatComposer.tsx`
- `DELETE_CANDIDATE` · Seq 759 · `mobile/live-chat-android/README.md`
- `DELETE_CANDIDATE` · Seq 760 · `mobile/live-chat-android/app/build.gradle.kts`
- `DELETE_CANDIDATE` · Seq 761 · `mobile/live-chat-android/app/proguard-rules.pro`
- `DELETE_CANDIDATE` · Seq 762 · `mobile/live-chat-android/app/src/main/AndroidManifest.xml`
- `DELETE_CANDIDATE` · Seq 763 · `mobile/live-chat-android/app/src/main/java/com/linaslaser/livechat/MainActivity.kt`
- `DELETE_CANDIDATE` · Seq 764 · `mobile/live-chat-android/app/src/main/res/layout/activity_main.xml`
- `DELETE_CANDIDATE` · Seq 765 · `mobile/live-chat-android/app/src/main/res/values/strings.xml`
- `DELETE_CANDIDATE` · Seq 766 · `mobile/live-chat-android/build.gradle.kts`
- `DELETE_CANDIDATE` · Seq 767 · `mobile/live-chat-android/gradle.properties`
- `DELETE_CANDIDATE` · Seq 768 · `mobile/live-chat-android/settings.gradle.kts`
- `DELETE_CANDIDATE` · Seq 865 · `scripts/cm/inventory_snapshot.py`
- `DELETE_CANDIDATE` · Seq 866 · `scripts/cm/run_migration_dry.py`
- `DELETE_CANDIDATE` · Seq 869 · `scripts/debug_firestore_chats.py`
- `DELETE_CANDIDATE` · Seq 871 · `scripts/diagnose_outbound_dedupe.py`
- `DELETE_CANDIDATE` · Seq 874 · `scripts/migrate_phone_identity.py`
- `DELETE_CANDIDATE` · Seq 877 · `scripts/phase2_load_simulation.py`
- `DELETE_CANDIDATE` · Seq 878 · `scripts/plan_economics_simulation.py`
- `DELETE_CANDIDATE` · Seq 930 · `scripts/verify_agent_api_contracts.py`
- `DELETE_CANDIDATE` · Seq 970 · `services/bot_data_service.py`
- `DELETE_CANDIDATE` · Seq 1090 · `services/dynamic_model_selector.py`
- `DELETE_CANDIDATE` · Seq 1092 · `services/enhanced_message_handler.py`
- `DELETE_CANDIDATE` · Seq 1098 · `services/faq_translation_service.py`
- `DELETE_CANDIDATE` · Seq 1099 · `services/gender_detection.py`
- `DELETE_CANDIDATE` · Seq 1123 · `services/live_monitoring.py`
- `DELETE_CANDIDATE` · Seq 1139 · `services/message_queue_service.py`
- `DELETE_CANDIDATE` · Seq 1140 · `services/message_sync_service.py`
- `KEEP_FIX` · Seq 2 · `.env.example`
- `KEEP_FIX` · Seq 10 · `.github/workflows/meta-app-a-scope-audit.yml`
- `KEEP_FIX` · Seq 12 · `.github/workflows/meta-comment-runtime-probe.yml`
- `KEEP_FIX` · Seq 22 · `.github/workflows/model-routing-policy-apply.yml`
- `KEEP_FIX` · Seq 29 · `.github/workflows/wa-cloud-webhook-readonly-probe.yml`
- `KEEP_FIX` · Seq 31 · `.gitignore`
- `KEEP_FIX` · Seq 40 · `README-LOCAL.md`
- `KEEP_FIX` · Seq 47 · `api_config.py`
- `KEEP_FIX` · Seq 50 · `backend/Dockerfile.simple`
- `KEEP_FIX` · Seq 51 · `backend/requirements.txt`
- `KEEP_FIX` · Seq 52 · `config.py`
- `KEEP_FIX` · Seq 56 · `dashboard/Dockerfile.prod`
- `KEEP_FIX` · Seq 94 · `dashboard/public/manifest.json`
- `KEEP_FIX` · Seq 96 · `dashboard/src/App.routes.test.jsx`
- `KEEP_FIX` · Seq 101 · `dashboard/src/components/Common/ErrorBoundary.jsx`
- `KEEP_FIX` · Seq 106 · `dashboard/src/components/Layout/Header.jsx`
- `KEEP_FIX` · Seq 109 · `dashboard/src/components/Layout/Sidebar.jsx`
- `KEEP_FIX` · Seq 114 · `dashboard/src/components/LiveChat/MobileLiveChatThreadPane.jsx`
- `KEEP_FIX` · Seq 118 · `dashboard/src/components/LiveChat/ModernAudioPlayer.jsx`
- `KEEP_FIX` · Seq 125 · `dashboard/src/components/UserManagement/PermissionMatrix.jsx`
- `KEEP_FIX` · Seq 147 · `dashboard/src/constants/permissions.jsx`
- `KEEP_FIX` · Seq 149 · `dashboard/src/constants/productFeatures.js`
- `KEEP_FIX` · Seq 157 · `dashboard/src/contexts/OperatorStatusContext.jsx`
- `KEEP_FIX` · Seq 158 · `dashboard/src/contexts/PermissionsContext.jsx`
- `KEEP_FIX` · Seq 165 · `dashboard/src/hooks/useApiQA.js`
- `KEEP_FIX` · Seq 166 · `dashboard/src/hooks/useApiTesting.js`
- `KEEP_FIX` · Seq 174 · `dashboard/src/index.jsx`
- `KEEP_FIX` · Seq 183 · `dashboard/src/pages/Dashboard.jsx`
- `KEEP_FIX` · Seq 189 · `dashboard/src/pages/LiveChatBotOverlay.jsx`
- `KEEP_FIX` · Seq 190 · `dashboard/src/pages/LiveChatDetails.jsx`
- `KEEP_FIX` · Seq 191 · `dashboard/src/pages/LiveChatModals.jsx`
- `KEEP_FIX` · Seq 194 · `dashboard/src/pages/LiveChatThreadHeader.jsx`
- `KEEP_FIX` · Seq 196 · `dashboard/src/pages/Login.jsx`
- `KEEP_FIX` · Seq 305 · `deploy/nginx-api-include.conf`
- `KEEP_FIX` · Seq 310 · `docker-compose.yml`
- `KEEP_FIX` · Seq 313 · `docs/ANALYTICS_LOGIC.md`
- `KEEP_FIX` · Seq 318 · `docs/CLAUDE_MEMORY.md`
- `KEEP_FIX` · Seq 456 · `firestore.indexes.json`
- `KEEP_FIX` · Seq 457 · `handlers/VERSION.py`
- `KEEP_FIX` · Seq 462 · `handlers/text_handlers_firestore.py`
- `KEEP_FIX` · Seq 463 · `handlers/text_handlers_message.py`
- `KEEP_FIX` · Seq 472 · `handlers/text_handlers_respond_phase12.py`
- `KEEP_FIX` · Seq 482 · `handlers/text_handlers_start.py`
- `KEEP_FIX` · Seq 484 · `handlers/voice_handlers.py`
- `KEEP_FIX` · Seq 536 · `mobile/linas-ai/src/auth/tokenStore.ts`
- `KEEP_FIX` · Seq 542 · `mobile/linas-ai/src/components/PrimaryButton.tsx`
- `KEEP_FIX` · Seq 543 · `mobile/linas-ai/src/components/SideDrawer.tsx`
- `KEEP_FIX` · Seq 544 · `mobile/linas-ai/src/components/StatusChip.tsx`
- `KEEP_FIX` · Seq 545 · `mobile/linas-ai/src/components/TextField.tsx`
- `KEEP_FIX` · Seq 549 · `mobile/linas-ai/src/features/auth/RegisterScreen.tsx`
- `KEEP_FIX` · Seq 568 · `mobile/linas-ai/src/features/chat/ChatScreen.tsx`
- `KEEP_FIX` · Seq 627 · `mobile/linas-ai/src/features/cm/cmMediaApi.ts`
- `KEEP_FIX` · Seq 710 · `mobile/linas-ai/src/features/shared/SimpleResourceScreen.tsx`
- `KEEP_FIX` · Seq 731 · `mobile/linas-ai/src/i18n/locales/whatsappAr.ts`
- `KEEP_FIX` · Seq 733 · `mobile/linas-ai/src/i18n/locales/whatsappFr.ts`
- `KEEP_FIX` · Seq 736 · `mobile/linas-ai/src/theme/ThemeContext.tsx`
- `KEEP_FIX` · Seq 745 · `mobile/linas-ai/tests/design_handoff.test.mjs`
- `KEEP_FIX` · Seq 773 · `modules/auth_api.py`
- `KEEP_FIX` · Seq 775 · `modules/auth_users_api.py`
- `KEEP_FIX` · Seq 781 · `modules/content_files_api.py`
- `KEEP_FIX` · Seq 785 · `modules/dashboard_api_health.py`
- `KEEP_FIX` · Seq 787 · `modules/dashboard_api_lab_message.py`
- `KEEP_FIX` · Seq 788 · `modules/dashboard_api_lab_upload.py`
- `KEEP_FIX` · Seq 789 · `modules/dashboard_api_lab_voice.py`
- `KEEP_FIX` · Seq 792 · `modules/event_handlers.py`
- `KEEP_FIX` · Seq 793 · `modules/event_handlers_monitor_jobs.py`
- `KEEP_FIX` · Seq 794 · `modules/event_handlers_populate_jobs.py`
- `KEEP_FIX` · Seq 799 · `modules/instructions_api.py`
- `KEEP_FIX` · Seq 800 · `modules/live_chat_api.py`
- `KEEP_FIX` · Seq 818 · `modules/models.py`
- `KEEP_FIX` · Seq 827 · `modules/settings_api.py`
- `KEEP_FIX` · Seq 828 · `modules/smart_messaging_api.py`
- `KEEP_FIX` · Seq 830 · `modules/smart_messaging_api_send_template.py`
- `KEEP_FIX` · Seq 831 · `modules/smart_messaging_api_send_test.py`
- `KEEP_FIX` · Seq 835 · `modules/smart_messaging_api_templates.py`
- `KEEP_FIX` · Seq 839 · `modules/webhook_handlers.py`
- `KEEP_FIX` · Seq 840 · `modules/webhook_handlers_dedupe.py`
- `KEEP_FIX` · Seq 842 · `modules/webhook_handlers_photo.py`
- `KEEP_FIX` · Seq 843 · `modules/webhook_handlers_process.py`
- `KEEP_FIX` · Seq 844 · `modules/webhook_handlers_voice.py`
- `KEEP_FIX` · Seq 845 · `modules/whatsapp_adapters.py`
- `KEEP_FIX` · Seq 945 · `services/api_integrations_booking.py`
- `KEEP_FIX` · Seq 946 · `services/api_integrations_catalog.py`
- `KEEP_FIX` · Seq 948 · `services/api_integrations_edit.py`
- `KEEP_FIX` · Seq 980 · `services/chat_response_runtime_tool_create_name.py`
- `KEEP_FIX` · Seq 1161 · `services/meta_messaging.py`
- `KEEP_FIX` · Seq 1171 · `services/mobile_refresh_token_service.py`
- `KEEP_FIX` · Seq 1175 · `services/montymobile_template_service.py`
- `KEEP_FIX` · Seq 1176 · `services/montymobile_template_service_payload.py`
- `KEEP_FIX` · Seq 1203 · `services/owner_alert_store.py`
- `KEEP_FIX` · Seq 1227 · `services/owner_push_token_store.py`
- `KEEP_FIX` · Seq 1270 · `services/social_contact_routing.py`
- `KEEP_FIX` · Seq 1271 · `services/social_contact_routing_detect.py`
- `KEEP_FIX` · Seq 1273 · `services/social_messaging_processor.py`
- `KEEP_FIX` · Seq 1274 · `services/social_user_id.py`
- `KEEP_FIX` · Seq 1290 · `services/token_wallet_models.py`
- `KEEP_FIX` · Seq 1295 · `services/user_service.py`
- `KEEP_FIX` · Seq 1302 · `services/whatsapp_adapters/montymobile_adapter.py`
- `KEEP_FIX` · Seq 1303 · `services/whatsapp_adapters/montymobile_adapter_parse.py`
- `KEEP_FIX` · Seq 1319 · `services/whatsapp_cloud/legacy_isolation.py`
- `KEEP_PERFORMANCE_FIX` · Seq 13 · `.github/workflows/meta-comment-webhooks-reconcile.yml`
- `KEEP_PERFORMANCE_FIX` · Seq 102 · `dashboard/src/components/Common/LoadingScreen.jsx`
- `KEEP_PERFORMANCE_FIX` · Seq 160 · `dashboard/src/hooks/useApi.jsx`
- `KEEP_SECURITY_FIX` · Seq 6 · `.github/workflows/dashboard-auth-secret-apply.yml`
- `KEEP_SECURITY_FIX` · Seq 7 · `.github/workflows/deploy.yml`
- `KEEP_SECURITY_FIX` · Seq 8 · `.github/workflows/instagram-login-secrets-apply.yml`
- `KEEP_SECURITY_FIX` · Seq 21 · `.github/workflows/meta-webhook-nginx-setup.yml`
- `KEEP_SECURITY_FIX` · Seq 23 · `.github/workflows/openai-api-key-apply.yml`
- `KEEP_SECURITY_FIX` · Seq 27 · `.github/workflows/subscription-exempt-probe.yml`
- `KEEP_SECURITY_FIX` · Seq 30 · `.github/workflows/whatsapp-cloud-phase1-apply.yml`
- `KEEP_SECURITY_FIX` · Seq 95 · `dashboard/src/App.jsx`
- `KEEP_SECURITY_FIX` · Seq 126 · `dashboard/src/components/UserManagement/RoleManager.jsx`
- `KEEP_SECURITY_FIX` · Seq 152 · `dashboard/src/contexts/AuthContext.helpers.js`
- `KEEP_SECURITY_FIX` · Seq 153 · `dashboard/src/contexts/AuthContext.jsx`
- `KEEP_SECURITY_FIX` · Seq 168 · `dashboard/src/hooks/useLiveChatMediaComposer.jsx`
- `KEEP_SECURITY_FIX` · Seq 192 · `dashboard/src/pages/LiveChatSidebar.jsx`
- `KEEP_SECURITY_FIX` · Seq 197 · `dashboard/src/pages/MobileLiveChat.jsx`
- `KEEP_SECURITY_FIX` · Seq 203 · `dashboard/src/pages/Settings.jsx`
- `KEEP_SECURITY_FIX` · Seq 535 · `mobile/linas-ai/src/auth/guestSession.ts`
- `KEEP_SECURITY_FIX` · Seq 801 · `modules/live_chat_api_debug.py`

---

## Appendix B — Cross-links

- Inventory SoT: `docs/audit/FILE_INVENTORY.csv`
- Official SEC register: `docs/audit/SECURITY_FINDINGS.md` (SEC-001 … SEC-070)
- Known concerns: `docs/audit/KNOWN_SECURITY_CONCERNS.md`
- Over-500 matrix: `docs/audit/OVER_500_FILES.md`
- Phase 0C reconciliation: `docs/audit/PHASE0C_RECONCILIATION.md`
- Phase 1 plan (do not execute yet): `docs/audit/PHASE1_REMEDIATION_PLAN.md`

---

_End of complete problems file. STOP — await Mahmoud Phase 1 approval._
