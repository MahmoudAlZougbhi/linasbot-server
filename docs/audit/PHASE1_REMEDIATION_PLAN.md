# Phase 1 — Complete remediation plan (proposal only)

**Owner:** Mahmoud  
**Status:** PROPOSAL ONLY. **Do not implement until Mahmoud says `GO Wave N`.** He has **not** said GO.  
**Language:** Lebanese Arabic + English so the owner can scan either.  
**Sources (SoT):** `docs/audit/ALL_PROBLEMS_FOUND.md` (commit `589ead8`), `docs/audit/SECURITY_FINDINGS.md` (SEC-001…SEC-070), `docs/audit/KNOWN_SECURITY_CONCERNS.md`, `docs/audit/FILE_INVENTORY.csv`, `docs/audit/PHASE0C_RECONCILIATION.md`.  
**Supersedes:** prior Wave counts that said KEEP_SECURITY_FIX 15 / KEEP_FIX 59 / DELETE 23 / ARCHIVE 130 / “unmerged 801–1100 claims”. Those are **stale**.

---

## 0. How to read this (kif te2ra)

- **Wave** = batch of work. You say `GO Wave N` before anyone edits application source.
- **Agent** = one small Cursor agent with **exclusive file ownership**. No two concurrent agents touch the same file.
- **Cap** = max **5 agents at a time** (hard). Never launch all waves together.
- **Infra/CI/deploy/Docker/nginx/compose/prod env/DB/Redis/queues/PM2** = **OWNER-APPROVAL wave**. Agent stops and asks: *“I need to change server/infra/build config. Do you approve?”*
- **No hidden fallbacks.** If a fix would silently switch implementations, the agent **STOPS and asks you**.
- **No Meta cutover, no DB migration, no prod deploy, no new feature flags** unless you explicitly ask.
- **Audit/plan docs only until GO.** This file is not permission to edit app code.

### Inventory totals (Phase 0C — current truth)

| Disposition | Count | Plan treatment |
|---|---:|---|
| KEEP_SECURITY_FIX | **17** | Waves 2 + 6 (+ W2-A7 debug elevation) |
| KEEP_PERFORMANCE_FIX | **3** | Wave 7 |
| KEEP_FIX | **100** | Waves 3–5, 8, 10–13 (+ parked infra) |
| DELETE_CANDIDATE | **46** | Wave 1 |
| MOVE_TO_ARCHIVE | **100** | Wave 9 |
| BINARY_ASSET_REVIEW | **81** | Wave 9-B |
| KEEP_SPLIT | **0** | none |
| LANDING_KEEP / KEEP_MOBILE_API / KEEP_AS_IS / GENERATED_SKIP | 35+15+1145+2 | **no change** (except SEC rows noted as ASK) |
| **Inventory rows** | **1544** | — |

### Official SEC findings (SEC-001…SEC-070)

| Severity | Count | Primary waves |
|---|---:|---|
| CRITICAL | **2** | Wave 2 (SEC-010), Wave 9 harden/archive (SEC-017) |
| HIGH | **15** | Waves 2 + 6 |
| MEDIUM | **18** | Waves 2–6, 12–13 (mapped below) |
| LOW | **16** | Waves 1/5/6/9/14 (many KEEP_AS_IS → ASK only) |
| INFO | **19** | mostly KEEP_AS_IS — document / monitor, no drive-by edits |
| **TOTAL** | **70** | — |

### Known concerns (`KNOWN_SECURITY_CONCERNS.md`)

| # | Status | Wave |
|---|---|---|
| 1–4, 7–8 | ALREADY_FIXED | none |
| 5 Tenant assertions / linas defaults | CONFIRMED_FIX_REQUIRED | **Wave 3** |
| 6 Role/permission elevation | CONFIRMED_FIX_REQUIRED | **Wave 2** |
| 9 Distributed rate limiting (Redis) | CONFIRMED_FIX_REQUIRED | **Wave 13 parked — OWNER (Redis/infra)** |
| shadow_eval “eval()” | FALSE_POSITIVE | none |

### Recommended first GO

**Security first (recommended):**  
1. Treat **Wave 0 as DONE** (Phase 0C evidence — see §Wave 0).  
2. Answer open questions in §15 (at least tenant fail-closed + Transfer/Priority + OperatorStatus).  
3. **`GO Wave 2`** — closes CRITICAL SEC-010 + HIGH dashboard/mobile authz holes.  
4. Then **`GO Wave 6`** (OWNER APPROVAL for CI) and/or **`GO Wave 3`** (tenant fail-closed after A+C answer).

**Deletes first (optional):** `GO Wave 1` anytime after Wave 0 DONE — lowest product risk, disjoint from Wave 2 locks. Can run Wave 1 **after** Wave 2 starts only if file sets stay disjoint and concurrency ≤5.

**Do not** start Wave 2 live-chat debug patch (`W2-A7`) without Wave 0 DONE evidence (already present).  
**Do not** start Wave 9 move of `scripts/delete_all_conversations.py` without SEC-017 harden decision.

---

## 1. Hard rules for every agent

1. Investigate (`rg` + read) before any edit. Do not invent APIs, env vars, or flags.
2. If **any real caller** is found on a delete: **STOP**, reclassify, do not delete.
3. Files approaching **1000 LOC**: split **before** adding logic. Prefer **<500 LOC**.
4. One commit per agent. Message: `fix(waveN): <why>` or `chore(waveN): delete orphan <cluster>`. Update inventory disposition notes only for files that actually changed.
5. No `git push` unless Mahmoud asks.
6. No `--no-verify`, no force-push, no amend of others’ commits.
7. Shared lock files (never two agents at once, even across waves):

| Lock file | Why |
|---|---|
| `dashboard/src/App.jsx` | Routes + permissions |
| `dashboard/src/contexts/AuthContext.jsx` | Session fail-open |
| `dashboard/src/contexts/AuthContext.helpers.js` | admin/linas defaults (SEC-010) |
| `dashboard/src/contexts/AuthContext.users.js` | Coupled with AuthContext |
| `config.py` | Global identity/defaults |
| `main.py` | App wiring |
| `.github/workflows/deploy.yml` | Prod deploy |
| `dashboard/src/utils/permissions.jsx` | Custom roles storage |
| `dashboard/src/components/Layout/Sidebar.jsx` | Tenant gating |
| `services/user_service.py` | Tenant normalize |
| `modules/live_chat_api.py` | Imports debug module; SSE CORS |

8. If blocked: write `STOP: <reason>` in the PR/commit body and ping Mahmoud. Do not improvise.

---

## 2. Concurrency + grand totals

| Wave | Agent slots | Concurrent max | Gate |
|---|---:|---:|---|
| 0 Verify (Phase 0C) | **0** (DONE) | — | Evidence in `PHASE0C_RECONCILIATION.md`; optional residual W0-R1 only |
| 1 Safe deletes | **14** | 5 | `GO Wave 1` |
| 2 App security (CRITICAL/HIGH) | **8** | 4 (locks) | `GO Wave 2` |
| 3 Tenant fail-closed | **7** | 4 | `GO Wave 3` + fail-closed **A+C** answer |
| 4 Handler correctness | **6** | 5 | `GO Wave 4` |
| 5 Dashboard product KEEP_FIX | **10** + parked | 4 | `GO Wave 5` after Wave 2; answers for A3/A8/A9 |
| 6 GitHub Actions security | **4** | 2 | **OWNER APPROVAL** then `GO Wave 6` |
| 7 Performance | **2** + 1 parked | 2 | `GO Wave 7` |
| 8 Monty/legacy harden | **4** | 2 | `GO Wave 8` — A1 docs first; no silent cutover |
| 9 Archive 100 + binaries 81 | **8** batches + binary ASK | **1–2** | `GO Wave 9` + APK/jsonl decisions |
| 10 Docs / root KEEP_FIX | **5** + infra parked | 2 | `GO Wave 10` + which parked files approved |
| 11 Mobile KEEP_FIX | **8** | 4 | `GO Wave 11` |
| 12 API modules KEEP_FIX | **10** | 4 | `GO Wave 12` after Wave 2/3 where coupled |
| 13 Remaining services + known#9 | **5** + Redis parked | 3 | `GO Wave 13`; Redis = OWNER |
| 14 SEC residual ASK / KEEP_AS_IS | **0 code** (decision log) | — | Owner answers only |

**Grand total agent-slots (executable):** **14+8+7+6+10+4+2+4+8+5+8+10+5 ≈ 91**  
(+ ~10–15 owner-approval / parked infra slots if you approve those files)  
**Never all at once.** Typical session: one wave, ≤5 concurrent, merge, Mahmoud tests, then next GO.

**Definition of done (every wave):**
- Each agent: scoped tests green, no extra files touched, commit exists, Mahmoud test steps listed.
- Wave lead: `git status` clean of foreign files; lock files unchanged by non-owners.
- Mahmoud tests on device/browser as listed. Capture-based validation after he says “done”.

---

## Wave 0 — Verify-first — **DONE (Phase 0C)**

**Goal / الهدف:** Confirm live-chat debug authz and destructive CLI risk **before** coding.

**Status:** **DONE** in Phase 0C. Do **not** re-run full verify agents unless Mahmoud wants a residual re-confirm.

### Evidence (do not re-invent)

| Claim | Disposition / finding | Evidence path |
|---|---|---|
| Seq **801** `modules/live_chat_api_debug.py` | Elevated to **KEEP_SECURITY_FIX** (HIGH) — auth+`liveChat` required, but **insufficient elevation** for debug-firestore / rebuild-index | `docs/audit/PHASE0C_RECONCILIATION.md` §3; `ALL_PROBLEMS_FOUND.md` KEEP_SECURITY_FIX; **SEC-016** |
| Seq **870** `scripts/delete_all_conversations.py` | **MOVE_TO_ARCHIVE** / protected-ops; official **SEC-017 CRITICAL** retained (shell + Firebase creds + `--confirm` only) | `PHASE0C_RECONCILIATION.md` §4; SECURITY_FINDINGS SEC-017 |

### Residual only (optional) — W0-R1

**Owns:** create/update `docs/audit/WAVE0_VERIFY.md` pointing at the two evidence sections above (no app edits).  
**Gate:** not required before Wave 2. Use only if Mahmoud wants a one-page pointer.  
**Commit:** `docs(audit): Wave 0 residual pointer to Phase 0C evidence`

### Wave 0 out of scope

Patching debug routes (→ **W2-A7**), archiving/hardening delete script (→ **W9** + SEC-017 decision), any app code.

---

## Wave 1 — Safe deletes (`DELETE_CANDIDATE` = 46)

**Goal / الهدف:** Delete proven orphans only. Each agent owns a **cluster**. If `rg` finds a real caller (including `import()`, `React.lazy`, expo-router, tests, scripts, **runtime** docs): **STOP and reclassify**.

**Mandatory `rg` per agent:**
```
rg -n -g '!docs/audit/**' -g '!node_modules/**' \
  '<basename without ext>' '<ModuleName>' \
  -g '*.py' -g '*.js' -g '*.jsx' -g '*.ts' -g '*.tsx' -g '*.json' -g '*.yml' -g '*.md'
```
Also search: `lazy(`, `import(`, expo-router under `mobile/linas-ai/src/app/`.

**Agent count:** 14. Concurrent max 5. All file sets disjoint.  
**SEC note:** deleting `config/montymobile_templates.json` closes **SEC-026** (LOW — committed Monty ids/phone). Deleting orphan Training/SystemPrompt panels closes **SEC-031/032** (unreachable).

### W1-A1 — TrainingFileEditor cluster (5)

**Owns:** `TrainingFileEditor.jsx`, `.meta.js`, `Backups.jsx`, `Search.jsx`, `.locSplit.test.js` under `dashboard/src/components/`.  
**Tests:** vitest ContentManagers / App.routes after delete.  
**Commit:** `chore(wave1): remove orphan TrainingFileEditor cluster`  
**Owner test:** FAQ/content managers load; no missing-module console errors.

### W1-A2 — Dashboard panel orphans (4)

**Owns:** `BotInstructionsTab.jsx`, `ContentFilesPanel.jsx`, `DynamicMessagesPanel.jsx`, `SystemPromptKnowledgeStylePanel.jsx`.  
**Commit:** `chore(wave1): remove orphan dashboard instruction/content panels`

### W1-A3 — Landing mascot + brand constant (2)

**Owns:** `dashboard/src/components/landing/LinasBotMascot.jsx`, `dashboard/src/constants/linasBrand.js`.  
**Tests:** `publicLanding.test.jsx`. Do not touch `LANDING_KEEP` brand PNGs.

### W1-A4 — orphan usePermissions hook (1)

**Owns:** `dashboard/src/hooks/usePermissions.jsx` only.  
**Does not own:** `PermissionsContext.jsx`, `utils/permissions.jsx` (lock).

### W1-A5 — Mobile GuestBanner + HistoryDrawer (2)

**Owns:** `GuestBanner.tsx`, `HistoryDrawer.tsx` under `mobile/linas-ai/src/features/chat/`.  
**STOP** if expo-router / ChatScreen imports them.

### W1-A6 — Mobile create-post orphans (3)

**Owns:** `CreatePostTaskChips.tsx`, `CreativeDraftCard.tsx`, `createPostTasks.ts`.  
**Commit:** `chore(wave1): remove unused mobile create-post orphan cluster`

### W1-A7 — ControlCenterDrawer (1)

**Owns:** `mobile/linas-ai/src/features/control/ControlCenterDrawer.tsx`.  
**Confirm:** NavDrawer is live path; only negative test mentions → delete.

### W1-A8 — LiveChatComposer (1)

**Owns:** `mobile/linas-ai/src/features/livechat/LiveChatComposer.tsx`.  
**Confirm:** LiveChatThread is read-only product path.

### W1-A9 — legacy `mobile/live-chat-android` cluster (10)

**Owns entire tree:** README, gradle files, Manifest, MainActivity.kt, layouts, strings, properties, settings.  
**Ask Mahmoud before GO if any staff still build the APK.** Product path is Expo LiveChatScreen.  
**Commit:** `chore(wave1): remove superseded live-chat-android WebView app`

### W1-A10 — Monty templates JSON only (1)

**Owns:** `config/montymobile_templates.json` (SEC-026).  
**Does not own:** `scripts/montymobile_manual_probe.py` (now **MOVE_TO_ARCHIVE** → Wave 9).  
**STOP** if any KEEP_FIX Monty service loads this path.

### W1-A11 — orphan scripts batch (8)

**Owns:**  
`scripts/cm/inventory_snapshot.py`, `scripts/cm/run_migration_dry.py`, `scripts/debug_firestore_chats.py`, `scripts/diagnose_outbound_dedupe.py`, `scripts/migrate_phone_identity.py`, `scripts/phase2_load_simulation.py`, `scripts/plan_economics_simulation.py`, `scripts/verify_agent_api_contracts.py`.  
**Does:** `rg` workflows + imports; delete only if zero callers. **Do not run** against Firestore.

### W1-A12 — dead services batch A (5)

**Owns:** `bot_data_service.py`, `dynamic_model_selector.py`, `enhanced_message_handler.py`, `faq_translation_service.py`, `gender_detection.py`.  
**Read-only:** `main.py` (do not edit). Confirm no includes.

### W1-A13 — live_monitoring.py (1)

**Owns:** `services/live_monitoring.py`. Confirm not wired to live_chat_service / SSE.

### W1-A14 — message_queue + message_sync (2)

**Owns:** `services/message_queue_service.py`, `services/message_sync_service.py`.  
Confirm active path is `smart_messaging_queue.py`. Cron/systemd refs → STOP. Do not delete `scripts/run_queue_worker.py` here (archive Wave 9).

### Wave 1 out of scope

Archive moves, binaries, Monty adapters, any KEEP_* file.

### Wave 1 owner test (after all 14 merge)

Dashboard login + landing + content managers + live chat list; mobile guest chat; `pytest tests/test_endpoint_auth_matrix.py -q`.

---

## Wave 2 — App security (CRITICAL + HIGH client/server authz)

**Goal / الهدف:** Fail **closed**. Close privilege/tenant spoof and live-chat elevation holes.  
**Maps:** Known concern **#6**; SEC-010 CRITICAL; SEC-008/009/011/012/013/014/015/016/070 HIGH (+ SEC-028 ASK).  
**Depends on:** Wave 0 DONE (satisfied).  
**Agent count:** 8. Concurrent max **4**.  
**Coupling:** A1 owns App+MobileLiveChat together. A2 owns both AuthContext files together.

### W2-A1 — liveChat route permission (SEC-008, SEC-014, SEC-027)

**Owns:** `dashboard/src/App.jsx`, `dashboard/src/pages/MobileLiveChat.jsx`; may edit tests `MobileLiveChat.auth.test.jsx`, `MobileLiveChat.test.js`.  
**Does:** Add `requiredPermission` for liveChat on `/mobile/live-chat` `ProtectedRoute` — same constant as `/live-chat`. Do not invent a permission key.  
**Tests:** vitest MobileLiveChat auth + ProtectedRoute + permissions.  
**Commit:** `fix(wave2): require liveChat permission on mobile live-chat route`  
**Owner test:** user without liveChat → URL redirect; with permission → works.

### W2-A2 — Auth defaults + fail-open (SEC-010 CRITICAL, SEC-011)

**Owns:** `AuthContext.helpers.js`, `AuthContext.jsx` + AuthContext tests.  
**Does:**
1. `buildUserData`: **never** default `role=admin` or `tenantId=linas`. Missing → incomplete session / logout (fail closed). Do not default `emailVerified=true` if that unlocks surface.
2. Session errors: do **not** keep privileged `auth_session` on 401/403. Clear and send to login.
3. **Ask if unanswered:** network timeout only — show “can’t reach server” with **no** privileged UI vs force re-login. **Forbidden:** restore cached admin session.
4. Remove debug `console.log` of auth payloads.  
**Commit:** `fix(wave2): fail closed on missing role/tenant and session errors`  
**Owner test:** real linas admin still works (tenant from **server**). Missing tenant mock → no ops tabs.

### W2-A3 — RoleManager localStorage custom roles (SEC-009)

**Owns:** `dashboard/src/components/UserManagement/RoleManager.jsx`.  
**Lock nearby:** `utils/permissions.jsx` — do not edit; if required → STOP.  
**Does:** Stop assigning client-only custom `roleId` to server users; hide/disable custom-role persistence. Keep system roles. Do not invent server-backed custom roles.  
**Ask:** hide now vs later server roles? **Default:** hide/disable client-only.  
**Commit:** `fix(wave2): stop client-only custom roles from being assigned`

### W2-A4 — operator_001 (SEC-012)

**Owns:** `dashboard/src/hooks/useLiveChatMediaComposer.jsx`.  
**Does:** Use authenticated operator id. **No** fallback to `operator_001`. If no id on user → STOP and ask.  
**Commit:** `fix(wave2): send live-chat media as authenticated operator`

### W2-A5 — simulateWebhook / rebuild UI (SEC-013, SEC-036)

**Owns:** `dashboard/src/pages/LiveChatSidebar.jsx`.  
**Does not own:** `useApiLiveChat.js`.  
**Does:** Remove/hide Rebuild index + Test flow from operator sidebar. Prefer remove UI. Server routes gated in W2-A7.  
**Commit:** `fix(wave2): hide live-chat debug webhook and rebuild-index from operators`

### W2-A6 — Settings tenantId default (SEC-015)

**Owns:** `dashboard/src/pages/Settings.jsx` (+ integrations test).  
**Does:** `user?.tenantId === "linas"` only — missing tenantId unlocks **nothing**.  
**Commit:** `fix(wave2): do not treat missing tenantId as linas in Settings`

### W2-A7 — live_chat_api_debug elevation (SEC-016 HIGH)

**Owns:** `modules/live_chat_api_debug.py`.  
**Read-only / sequential if needed:** `modules/live_chat_api.py` (lock).  
**Does:** Require **admin/ops elevation** beyond bare `liveChat` for `debug-firestore` and `rebuild-index` (reuse existing permission/role helpers — do not invent). Fail 401/403. Prefer delete endpoints if Mahmoud chooses delete over gate — **ASK**.  
**Tests:** extend `tests/test_endpoint_auth_matrix.py` + live_chat / wave1 security tests.  
**Commit:** `fix(wave2): require elevated auth on live-chat debug and rebuild-index`

### W2-A8 — mobile guest session entropy (SEC-070)

**Owns:** `mobile/linas-ai/src/auth/guestSession.ts`.  
**Does:** Use `crypto.getRandomValues` (or Expo-safe crypto) — **not** `Math.random` into Uint8Array. Optionally call `clearGuestSessionId` after login/register if callers exist without inventing new auth flow.  
**Commit:** `fix(wave2): use CSPRNG for mobile guest session ids`  
**Owner test:** guest chat still starts; ids change across sessions.

### SEC-028 ASK (ProtectedRoute admin bypass)

**File:** `dashboard/src/components/Auth/ProtectedRoute.jsx` (KEEP_AS_IS).  
**Not an auto agent.** Mahmoud: keep admin bypass (document) **or** schedule a Wave 2 follow-on to require explicit permissions even for admin. Default until answered: **leave** (client-only; server must enforce).

### Wave 2 out of scope

Backend tenant defaults (Wave 3), Sidebar (Wave 5), CI (Wave 6), CSRF redesign.

---

## Wave 3 — Tenant default `linas` fail-closed (backend)

**Goal / الهدف:** Missing tenant **never** becomes `linas`.  
**Maps:** Known concern **#5**; SEC-025 (config noted separately), SEC-065/067 medium surfaces, social/meta tenant defaults.

### Question for Mahmoud (blocking)

When `tenant_id` is missing:

| Option | Behavior |
|---|---|
| **A (recommended)** | **403** / raise — refuse to guess |
| B | **400** bad request |
| **C (recommended with A)** | Tenant from **auth/binding only**; ignore body tenant; still 403 if auth has no tenant |

**Recommendation:** **A + C.** Founder tenant `linas` works only when session/binding **says** linas. Never default.

**Agent count:** 7. Concurrent max 4. Only W3-A1 owns `user_service.py` (lock).

Shared pattern:
1. Find `or "linas"` / `tenant_id="linas"` / `_normalize_tenant_id` in **owned files only**.
2. Empty → dedicated error (reuse existing exception if present). No silent linas.
3. Caller outside owned file needing signature change → **STOP**.
4. Extend existing tests.

| Agent | Owns | Commit theme |
|---|---|---|
| W3-A1 | `services/user_service.py` | fail closed missing tenant |
| W3-A2 | `services/token_wallet_models.py` | wallet tenant normalize |
| W3-A3 | `services/mobile_refresh_token_service.py` | refresh requires tenant |
| W3-A4 | `owner_alert_store.py`, `owner_push_token_store.py` | owner stores |
| W3-A5 | `social_contact_routing.py`, `social_contact_routing_detect.py` | routing |
| W3-A6 | `social_messaging_processor.py`, `social_user_id.py` | processor + ids |
| W3-A7 | `services/meta_messaging.py` | binding-only tenant |

**Also schedule in Wave 12 (same rule, different files):** `modules/auth_api.py`, `modules/auth_users_api.py` linas coalescing on login/read — do **not** start those until Wave 3 pattern is approved (same A+C).

**Out of scope:** `config.py` (Wave 10 parked), Sidebar/Settings (Waves 2/5), DB migrations.

**Owner test:** linas admin with explicit tenant OK; empty tenant cannot read/write linas data (live chat / wallet / social).

---

## Wave 4 — Handler correctness (KEEP_FIX handlers)

**Agent count:** 6. Concurrent max 5.  
**Maps:** SEC-047 (PII logs); related handler debt.

| Agent | Owns | Does |
|---|---|---|
| W4-A1 | `handlers/text_handlers_message.py` | Redact/remove DEBUG phone/preview (SEC-047); reuse sensitive logging helper read-only |
| W4-A2 | `handlers/voice_handlers.py` | Async Firestore get — no event-loop block; no invented threadpool fallback |
| W4-A3 | `handlers/text_handlers_start.py` | Remove dead `start_command` if proven; barrel change → STOP |
| W4-A4 | `handlers/VERSION.py` | Stop print on import |
| W4-A5 | `handlers/text_handlers_respond_phase12.py` | Delete unreachable `_pack` after halt |
| W4-A6 | `handlers/text_handlers_firestore.py` | Docstring only — no `git mv` |

**SEC-048** (`text_handlers_respond_phase6.py` human_handover coerce) is KEEP_AS_IS — **ASK** before changing (Wave 14). Do not silently alter handover policy.

**Owner test:** one text + one voice message; logs without phone/preview; voice saves once.

---

## Wave 5 — Dashboard product KEEP_FIX

**After Wave 2.** Agent count: 10 executable + parked. Concurrent max 4.

| Agent | Owns | Does |
|---|---|---|
| W5-A1 | `PermissionMatrix.jsx` | Stop double-toggle bubble |
| W5-A2 | `Dashboard.jsx` | Filter SAAS_NAV_ITEMS by existing permission helper (SEC-039) |
| W5-A3 | `LiveChatDetails.jsx` | **ASK:** hide vs implement Transfer/Priority — **default hide** (no fake API) |
| W5-A4 | `Login.jsx` | Remove personal `/Users/mahmoud…` paths |
| W5-A5 | `ErrorBoundary.jsx` | Do not swallow network errors |
| W5-A6 | `Header.jsx` | Remove fake Live notifications (SEC-029) |
| W5-A7 | `Sidebar.jsx` (lock) | Missing tenantId ≠ linas (SEC-030) |
| W5-A8 | `OperatorStatusContext.jsx` | **ASK:** throw outside provider (recommended — no silent no-op) |
| W5-A9 | `useApiQA.js`, `useApiTesting.js` | **ASK:** remove mock `success:true` (hidden fallbacks — SEC-037 related) |
| W5-A10 | `PermissionsContext.jsx`, `productFeatures.js`, `permissions.jsx` | Remove unused exports only; App.jsx needed → STOP sequential |

### Parked in Wave 5 (OWNER / later)

| Item | File |
|---|---|
| Node 20 vs engines 22 | `dashboard/Dockerfile.prod` |
| God-object unused props | LiveChatBotOverlay / Modals / ThreadHeader |
| Dead copy / media URL trust | MobileLiveChatThreadPane (server SSRF already guarded) |
| Audio play-state | ModernAudioPlayer |
| Stub App.routes test | App.routes.test.jsx |
| PWA purple/emoji | manifest.json |
| index.jsx DEV network suppress | `dashboard/src/index.jsx` — ASK (masks outages) |

**Owner test:** permission matrix, hub tiles, login error copy, header, sidebar tenant, error boundary with API down.

---

## Wave 6 — GitHub Actions security (OWNER APPROVAL)

**STOP.** Ask: *“I need to change server/infra/build config. Do you approve?”*  
**Maps:** SEC-001…SEC-007 HIGH/MEDIUM; related KEEP_SECURITY_FIX workflows.

**Agent count:** 4. Concurrent max **2**. `deploy.yml` lock.

| Agent | Owns | Does |
|---|---|---|
| W6-A1 | dashboard-auth-secret-apply, instagram-login-secrets-apply, meta-webhook-nginx-setup, openai-api-key-apply | Typed confirmation like siblings (SEC-001/003/004/005) |
| W6-A2 | `deploy.yml` (lock) | Pin ssh-action to sibling `v1.2.0`; restrict `data/` backup perms (SEC-002); keep emergency gate |
| W6-A3 | `subscription-exempt-probe.yml` | Redact logs; bound Firestore stream; fail closed on import failure (SEC-006) |
| W6-A4 | `whatsapp-cloud-phase1-apply.yml` | Stop `git reset --hard` side effect (SEC-007) — ASK if reset intentional |

**Out of scope:** Running workflows against production; Meta cutover KEEP_AS_IS workflows (SEC-018…024 — ASK only in Wave 14).

**Owner test:** YAML review / non-prod dry-run only. Do not rotate real keys as a test.

---

## Wave 7 — Performance (`KEEP_PERFORMANCE_FIX` = 3)

| Agent | Owns | Does |
|---|---|---|
| W7-A1 | `LoadingScreen.jsx` | Lighten framer; fix stale feature copy |
| W7-A2 | `useApi.jsx` | Avoid instantiating all sub-hooks if Rules-of-Hooks safe; else STOP for App.jsx sequential |
| W7-A3 parked | `meta-comment-webhooks-reconcile.yml` | Lean deps — **OWNER APPROVAL** |

---

## Wave 8 — Monty / legacy KEEP_FIX (no silent cutover)

**Do not** remove Monty. Isolation stays until Mahmoud approves cutover.

| Agent | Owns | Does |
|---|---|---|
| W8-A1 (first, docs) | `docs/audit/MONTY_REMAINING_CALLERS.md` (new) | Full caller inventory — no deletes |
| W8-A2 | `montymobile_template_service.py` + `_payload.py` | Stop broad swallow; no Cloud fallback |
| W8-A3 | `montymobile_adapter.py` + `_parse.py` | Same; fix fail-open around dual-bind guard |
| W8-A4 | `.env.example` | Clarify Meta Cloud product intent vs Monty legacy keys (**keep keys**) |

**Related KEEP_FIX deferred to Wave 12/13 (document in A1):** event_handlers Monty default, smart_messaging_* Monty helpers, webhook_handlers_*, models/settings Monty refs, `legacy_isolation.py` fail-open on DB scan, `modules/whatsapp_adapters.py` response JSON logging.

---

## Wave 9 — Archive (`MOVE_TO_ARCHIVE` = 100) + binaries (81)

**Concurrent max: 1–2.** `git mv` only.  
Repo has **no** `archive/` yet — **first batch creates `archive/`** (or owner-named path). Update references in same commit. `rg` `.github/workflows` before moving any `scripts/prod_*.sh`.

| Agent | Owns | Notes |
|---|---|---|
| W9-A1 | `.planning/codebase/*` (7) | git mv |
| W9-A2 | `docs/cm_phase_evidence/*` (11) | git mv |
| W9-A3 | listed `docs/evidence/*` non-screenshot (9) | git mv |
| W9-A4 | design MAHMOUD_MOBILE_PROMPT* + pdf_text | git mv |
| W9-A5 | PHASE2_*/CM plans/LIVE_CHAT_FIX/META runbook/whatsapp coexistence/CM ledger | **Ask** before META runbook |
| W9-A6a/b/c | `scripts/` archive list (~44) in 3 chunks | workflow `rg` first |
| W9-A7 | `dashboard/README.md` | git mv |
| W9-A8 | `data/*.jsonl` (4) | **OWNER** — PII; untrack vs archive vs gitignore |

### SEC-017 CRITICAL — `scripts/delete_all_conversations.py`

Before or as part of W9-A6 chunk that would move it:
1. **ASK Mahmoud:** archive only **vs** harden (typed phrase + dry-run default + louder banner) **then** archive.  
2. **Never run** against production as a test.  
3. Do not leave a discoverable unsigned bomb in `scripts/` without banner if you keep it temporarily.

### Binaries (W9-B*) — owner decisions

| Bucket | Count | Action |
|---|---:|---|
| `dashboard/public/brand/*` | 17 | **KEEP** |
| `mobile/linas-ai/assets/*` | 8 | **KEEP** |
| design/evidence screenshots, mockups, pdf_pages, landing zip/PDF | ~55 | Archive OK (`git mv`) |
| `mobile/releases/linas-live-chat-android.apk` | 1 | **ASK:** keep / LFS / remove |

---

## Wave 10 — Docs / root KEEP_FIX + parked infra

### Executable

| Agent | Owns | Does |
|---|---|---|
| W10-A1 | `docs/ANALYTICS_LOGIC.md` | Stale `/analytics` → `/app` |
| W10-A2 | `docs/CLAUDE_MEMORY.md` | Stale banner only — no 495-line rewrite |
| W10-A3 | `docs/FIRESTORE_INDEXES.md` (+ read-only JSON) | Doc match `live_chat_index` — **do not deploy index JSON** |
| W10-A4 | `README-LOCAL.md` | Align with `.env.example` |
| W10-A5 | `api_config.py` | Fix misleading path comment only — no merge into `config.py` |

### Parked — OWNER APPROVAL

| File | Issue |
|---|---|
| `deploy/nginx-api-include.conf` | Missing `/oauth/` + `/meta/deauthorize` vs full conf |
| `docker-compose.yml` | Stale tradershubs API URL |
| `backend/Dockerfile.simple` | Port 8000 vs 8003; `--reload` |
| `backend/requirements.txt` | Dual SoT drift |
| `dashboard/Dockerfile.prod` | Node 20 vs engines ≥22 |
| `firestore.indexes.json` | Index **deploy** |
| `config.py` (lock) | Welcome Marwa/Lina copy; DEFAULT_*_ID=1; in-memory multi-instance (SEC-025) |
| `.gitignore` | PHP leftovers + jsonl untrack |
| GHA KEEP_FIX: meta-app-a-scope-audit, meta-comment-runtime-probe, model-routing-policy-apply, wa-cloud-webhook-readonly-probe | Stale branches / soft exit 0 |

---

## Wave 11 — Mobile KEEP_FIX (13 paths → 8 agents)

| Agent | Owns | Does |
|---|---|---|
| W11-A1 | `tokenStore.ts` | Validate stored user JSON (Zod/schema already used elsewhere — reuse) |
| W11-A2 | PrimaryButton, StatusChip, TextField | Theme via `useTheme` — static colors → theme |
| W11-A3 | `SideDrawer.tsx` | Theme + rotation-safe dimensions |
| W11-A4 | `RegisterScreen.tsx` | Stronger client password gate + i18n errors (align server policy — do not invent weaker) |
| W11-A5 | `ChatScreen.tsx` | Remove dead `isPlatformOwner` / null workspaceLabel debt |
| W11-A6 | `cmMediaApi.ts` | FormData shape safe for Expo 57 (match owner upload helper) |
| W11-A7 | `SimpleResourceScreen.tsx` + `whatsappAr.ts` + `whatsappFr.ts` | i18n / complete WA locale strings |
| W11-A8 | `ThemeContext.tsx` + `design_handoff.test.mjs` | **Throw** if `useTheme` outside provider (no fail-open); fix stale drawer order test |

**Owner test:** dark mode controls; register; guest→login; CM media upload; drawer tests green.

---

## Wave 12 — API modules KEEP_FIX (24 paths → 10 agents)

Apply Wave 3 fail-closed rule where tenant coalescing appears. No Monty→Cloud silent switch.

| Agent | Owns | Does |
|---|---|---|
| W12-A1 | `auth_api.py`, `auth_users_api.py` | Remove linas default coalescing (after Wave 3 GO + A+C) |
| W12-A2 | `live_chat_api.py` (lock) | Remove `.cursor/debug-*.log` writes; tighten SSE `ACAOrigin: *` — ASK exact CORS policy |
| W12-A3 | `content_files_api.py`, `instructions_api.py` | **ASK:** archive vs tenant-scope — not safe SaaS as-is; no silent keep |
| W12-A4 | lab_message / lab_upload / lab_voice | Delete unreachable bodies after refuse; `/api/stats` remnant — disable or authz-tighten |
| W12-A5 | `dashboard_api_health.py` | Align ready-check provider bias with Meta Cloud product (no silent Monty cutover) |
| W12-A6 | `event_handlers.py`, `event_handlers_monitor_jobs.py`, `event_handlers_populate_jobs.py` | Dead code / verify populate orphan; Monty default → document+ASK |
| W12-A7 | smart_messaging_api + send_template + send_test + templates | Monty helpers — harden/document only until cutover GO |
| W12-A8 | webhook_handlers + dedupe/photo/process/voice | Same — no silent provider switch |
| W12-A9 | `modules/models.py`, `modules/settings_api.py` | Dual-WA docs/flags clarity |
| W12-A10 | `modules/whatsapp_adapters.py` | Stop printing full response JSON (PII); no new fallback |

---

## Wave 13 — Remaining services KEEP_FIX + known concern #9

| Agent | Owns | Does |
|---|---|---|
| W13-A1 | `api_integrations_booking.py` | Add missing `import os` (NameError) — tiny correctness |
| W13-A2 | `api_integrations_catalog.py` | Same |
| W13-A3 | `api_integrations_edit.py` | Same |
| W13-A4 | `chat_response_runtime_tool_create_name.py` | Monty refs — document/ASK with Wave 8 inventory |
| W13-A5 | `services/whatsapp_cloud/legacy_isolation.py` | Fail-**closed** on DB scan failure (today fail-open empty set) — **ASK** before behavior change (can block Monty sends) |

### Parked — OWNER (Redis / infra)

| Item | File | Notes |
|---|---|---|
| Known concern **#9** distributed rate limit | `services/rate_limit_service.py` | Needs Redis/shared store — **do not implement without Mahmoud infra approval** |

---

## Wave 14 — SEC residual / KEEP_AS_IS decisions (no code until answered)

Owner decision log only. Agents do not start from this wave without explicit per-item GO.

| ID | Topic | Disposition | Ask |
|---|---|---|---|
| SEC-028 | ProtectedRoute `role===admin` bypass | KEEP_AS_IS | Keep documented vs require permissions for admin too |
| SEC-018…024 | High-impact Meta/CM workflows | KEEP_AS_IS | Confirmation/env already partly mitigated — any extra gates? |
| SEC-034 | GuestChatPanel localStorage session | LANDING_KEEP | Accept vs harden |
| SEC-035 | CSRF in localStorage | KEEP_AS_IS | Accept vs httpOnly redesign (large) |
| SEC-038 | ActivityFlow full JSON PII | KEEP_AS_IS | Accept observability vs redact |
| SEC-043 | ResetPassword token in URL | KEEP_AS_IS | Accept email-link pattern |
| SEC-046 | systemd root + EnvironmentFile | KEEP_AS_IS | Harden unit user/perms? (**infra**) |
| SEC-048 | unauthorized human_handover coerce | KEEP_AS_IS | Product rule change? |
| SEC-049…069 INFO | billing/oauth/logging surfaces | KEEP_AS_IS | Monitor — server authz must remain |
| SEC-033 | UserManagement client-only check | KEEP_AS_IS | Confirm `/users` server enforce |
| Binary APK / jsonl / META runbook | Wave 9 | — | keep vs archive vs LFS |

---

## 3. Coverage map — every bucket + SEC severity

| Bucket | Count | Waves |
|---|---:|---|
| KEEP_SECURITY_FIX | **17** | 2 (App/mobile/debug 10 files) + 6 (CI 7 files) |
| SEC CRITICAL | **2** | SEC-010 → W2-A2; SEC-017 → W9 + harden ASK |
| SEC HIGH | **15** | W2 + W6 (+ SEC-028 ASK W14) |
| SEC MEDIUM | **18** | W2–6, W12–13, W14 |
| SEC LOW/INFO | **32** | W1 deletes where applicable; else W14 / KEEP_AS_IS |
| Known concerns FIX_REQUIRED | **3** | #5→W3, #6→W2, #9→W13 parked |
| KEEP_PERFORMANCE_FIX | **3** | 7 |
| DELETE_CANDIDATE | **46** | 1 |
| KEEP_FIX | **100** | 3,4,5,8,10,11,12,13 (+ parked) |
| MOVE_TO_ARCHIVE | **100** | 9 |
| BINARY_ASSET_REVIEW | **81** | 9-B |
| KEEP_AS_IS / LANDING / MOBILE_API / GENERATED | 1197 | no drive-by change |

### KEEP_SECURITY_FIX path → agent (17/17)

| Seq | Path | Agent |
|---:|---|---|
| 6 | `.github/workflows/dashboard-auth-secret-apply.yml` | W6-A1 |
| 7 | `.github/workflows/deploy.yml` | W6-A2 |
| 8 | `.github/workflows/instagram-login-secrets-apply.yml` | W6-A1 |
| 21 | `.github/workflows/meta-webhook-nginx-setup.yml` | W6-A1 |
| 23 | `.github/workflows/openai-api-key-apply.yml` | W6-A1 |
| 27 | `.github/workflows/subscription-exempt-probe.yml` | W6-A3 |
| 30 | `.github/workflows/whatsapp-cloud-phase1-apply.yml` | W6-A4 |
| 95 | `dashboard/src/App.jsx` | W2-A1 |
| 126 | `RoleManager.jsx` | W2-A3 |
| 152 | `AuthContext.helpers.js` | W2-A2 |
| 153 | `AuthContext.jsx` | W2-A2 |
| 168 | `useLiveChatMediaComposer.jsx` | W2-A4 |
| 192 | `LiveChatSidebar.jsx` | W2-A5 |
| 197 | `MobileLiveChat.jsx` | W2-A1 |
| 203 | `Settings.jsx` | W2-A6 |
| 535 | `guestSession.ts` | W2-A8 |
| 801 | `live_chat_api_debug.py` | W2-A7 |

---

## 4. What we will NOT do

- Start Phase 1 coding without `GO Wave N`
- Meta verified-app **cutover**
- Production **deploy**
- **DB / Firestore index migrate** (doc drift = comments only)
- New **feature flags** unless asked
- Hidden **fallbacks** / silent Monty↔Cloud switch
- Delete **app icons** or brand PNGs
- Run `delete_all_conversations.py` against any database
- One mega-agent “fix everything”
- Exceed **5** concurrent agents
- Touch lock files from two agents at once

---

## 5. Merge / commit / rollback (all waves)

1. Branch `phase1/wN-aK-<slug>` from current integration base Mahmoud names.
2. **One commit per agent.**
3. Parent merges to `phase1/wave-N` after tests. Mahmoud says when to merge to main.
4. Rollback = `git revert <sha>`. No force-push to main.
5. Collision → stop wave; ownership means this should not happen.

---

## 6. GO gates (copy-paste)

Mahmoud, reply with one of:

- `Wave 0 DONE` acknowledged (default — Phase 0C evidence)
- `GO Wave 1` — safe deletes (46)
- `GO Wave 2` — **recommended first coding wave** (security)
- `GO Wave 3` + fail-closed **A/B/C** (recommend **A+C**)
- `GO Wave 4`
- `GO Wave 5` + Transfer/Priority **hide|implement**; OperatorStatus **throw|keep**; QA mocks **remove|keep**
- `GO Wave 6` + *“I approve CI/infra workflow changes”*
- `GO Wave 7`
- `GO Wave 8`
- `GO Wave 9` + APK decision + jsonl decision + SEC-017 harden|archive-only
- `GO Wave 10` + which parked infra files approved
- `GO Wave 11`
- `GO Wave 12` (+ content_files/instructions archive vs scope)
- `GO Wave 13` (+ legacy_isolation fail-closed yes/no; Redis rate-limit later)
- `GO Wave 14 answers: …` (SEC residual table)

Optional: `GO Wave 1 agents A1-A5 only` for a smaller first delete slice.

---

## 7. After each merged agent — report to Mahmoud

- Exact files changed  
- Root cause  
- What was fixed / **not** changed  
- Rebuild required? (dashboard npm / mobile Expo / none)  
- Tests run  
- Exact device/browser test steps  

Then Mahmoud tests. After **done**, parent inspects capture/logs before the next wave GO.

---

## 15. Open questions for Mahmoud (blocking / ordering)

Answer these to unlock waves cleanly:

1. **First GO:** Wave **2** (security) or Wave **1** (deletes)? Recommendation: **Wave 2**.
2. **Tenant missing (Wave 3):** confirm **A+C** (403 + auth-only tenant)?
3. **Transfer / Priority buttons:** hide or implement (needs real API — do not invent)?
4. **OperatorStatus outside provider:** throw (recommended) or keep no-op?
5. **QA/Testing hooks mock success:** remove (recommended) or keep?
6. **live_chat_api_debug:** elevate to admin/ops **or** delete endpoints?
7. **ProtectedRoute admin bypass (SEC-028):** keep or tighten?
8. **SEC-017 delete_all_conversations:** harden then archive, or archive-only?
9. **Session network timeout (W2-A2):** show offline UI vs force logout?
10. **Custom roles:** hide client-only now, or later server roles?
11. **Delete live-chat-android (W1-A9):** confirm no staff still builds it?
12. **APK in git / data jsonl / META runbook / Redis rate-limit:** keep, archive, LFS, or later infra project?
13. **SSE CORS `*` on live_chat_api:** what exact origin policy?
14. **legacy_isolation fail-closed on DB error:** approve behavior change (may block Monty sends)?
15. **content_files_api / instructions_api:** archive vs tenant-scope project?

---

_End of complete Phase 1 plan. STOP — await Mahmoud `GO Wave N`._
