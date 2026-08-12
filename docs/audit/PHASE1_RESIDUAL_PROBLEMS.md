# Phase 1 — Residual problems (owner file)

**Role:** SYNTHESIZER  
**Branch:** `chore/project-cleanup-reorg` (ahead of `origin/main` ~124 commits)  
**Generated:** 2026-08-12  
**Sources:** `PHASE1_REINSPECT_REPORT.md`, `ALL_PROBLEMS_FOUND.md` (top), `SECURITY_FINDINGS.md` (summary), `git log`/`git status`, plus synthesizer spot-check `rg`.

**Scope:** Remaining problems **after** Phase 1 Waves 0–13 (executable work largely applied; several waves PARTIAL). No application source was changed for this document.

---

## Spot-check regressions (synthesizer)

| Pattern | Result |
|---|---|
| `operator_001` in dashboard media / liveChatApi | **FIXED** — composer uses `user?.id` and refuses if missing |
| `operator_001` in `modules/models.py` | **STILL** — `FeedbackRequest` / `TakeoverRequest` defaults |
| `tenantId \|\| "linas"` / `\|\| 'linas'` in dashboard src | **FIXED** — Settings/Sidebar/Dashboard use strict `=== 'linas'` |
| `simulateWebhook` UI in `LiveChatSidebar` | **FIXED** — no rebuild/simulate/Test flow strings in sidebar |
| `simulateWebhook` in `useApiLiveChat.js` | **STILL** — hook still posts `/api/debug/simulate-webhook` (UI gated; API surface remains) |
| AuthContext fail-open / keep cached `auth_session` on error | **FIXED** — catch clears session + `setUser(null)`; 401/403 clear |
| `BotInstructionsTab` / `TrainingFileEditor*` / `usePermissions.jsx` | **FIXED** — files gone; no production imports |

---

## 1. STILL_BROKEN (must fix)

Clear code / product residuals that Phase 1 intended to close (or classic regressions still present). Safe to schedule as next GO waves without infra approval unless noted.

### Security / authz / attribution

| # | Item | Evidence | Suggested wave |
|---|---|---|---|
| S1 | `modules/models.py` defaults `operator_id="operator_001"` on `FeedbackRequest` / `TakeoverRequest` | Spot-check; clients can omit operator and get wrong attribution | Wave 12 (W12-A9) |
| S2 | `useApiLiveChat.js` still exports `simulateWebhook` + `rebuildLiveChatIndex` | UI removed; any future importer can call debug webhook | Wave 2 residual / Wave 12 |
| S3 | Live Chat SSE `Access-Control-Allow-Origin: *` in `modules/live_chat_api.py` | Reinspect OWNER_ASK; still `*` in source | Wave 12 (needs origin policy — see §3 if blocked) |

### Tenant fail-closed gaps (Known concern #5 remainder)

| # | Item | Evidence | Suggested wave |
|---|---|---|---|
| S4 | `handlers/photo_handlers.py` `tenant_id … or "linas"` | Spot-check; voice handler already fail-closed | Wave 3 / 4 residual |
| S5 | `modules/whatsapp_cloud_ops_api.py` `body.get("tenant_id") or "linas"` (×2) | Spot-check | Wave 12 |
| S6 | Broader silent `or "linas"` / env defaults still in services (examples: `ai_usage_limits.py`, `chat_response_runtime_prompt.py`, `tenant_mobile_dashboard/compose.py`, `auth_email_tokens.py`, wallet/entitlement env coalescing) | Spot-check; Wave 3 closed owned services + session load/revoke; SaaS isolation debt remains | Wave 3 follow-up / 12–13 |

### Mobile KEEP_FIX leftovers (Wave 11 PARTIAL)

| # | Item | Evidence | Suggested wave |
|---|---|---|---|
| S7 | `SideDrawer.tsx` — static `Dimensions.get('window')` at module load; colors from static theme import (not `useTheme`) | Reinspect; file still matches | W11-A3 |
| S8 | `PrimaryButton` (and related StatusChip/TextField plan) — static `colors.*` not theme provider | Spot-check PrimaryButton | W11-A2 |
| S9 | `ChatScreen.tsx` — still accepts `isPlatformOwner`; overlays pass `workspaceLabel={null}` debt | Spot-check | W11-A5 |
| S10 | `cmMediaApi.ts` FormData shape for Expo 57 | Plan residual; file still present | W11-A6 |
| S11 | WA locale / i18n packs (`whatsappAr` / `whatsappFr` / SimpleResourceScreen) | Reinspect residual | W11-A7 |

### Archive / cleanup leftovers

| # | Item | Evidence | Suggested wave |
|---|---|---|---|
| S12 | **82** `MOVE_TO_ARCHIVE` paths still at original location (18 moved) | Inventory vs disk: 44 scripts, 33 docs, 4 `data/*.jsonl`, 1 `dashboard/README.md` | Wave 9 batches |
| S13 | Wave 12 lab / stats remnants (`dashboard_api_lab_*`, unreachable lab bodies, `/api/stats` authz) | Plan W12-A4; modules still present | Wave 12 |

**STILL_BROKEN count (owner scan):** **13** line items above (S1–S13). Several S6 paths are a *family* of tenant-default sites, not one file.

---

## 2. PARKED_OWNER / infra

Do **not** implement without Mahmoud explicit approval (“I need to change server/infra/build config. Do you approve?”).

| # | Item | Why parked |
|---|---|---|
| P1 | Redis / distributed rate limit (`services/rate_limit_service.py`) — Known concern **#9** | File-backed per-process only; needs Redis/shared store |
| P2 | `config.py` defaults / welcome copy / `DEFAULT_*_ID` / in-memory multi-instance (SEC-025) | Global lock + product identity |
| P3 | Docker / nginx / compose / `firestore.indexes.json` **deploy** | Infra deploy surface |
| P4 | `deploy/nginx-api-include.conf` missing `/oauth/` + `/meta/deauthorize` vs full conf | Nginx |
| P5 | `backend/Dockerfile.simple`, `dashboard/Dockerfile.prod`, dual `requirements.txt` | Build/runtime drift |
| P6 | `.gitignore` PHP leftovers + jsonl untrack | Repo hygiene / may drop tracked dumps |
| P7 | GHA KEEP_FIX soft probes (meta-app-a-scope-audit, meta-comment-runtime-probe, model-routing-policy-apply, wa-cloud-webhook-readonly-probe) | CI behavior / stale branches |
| P8 | `useApi.jsx` instantiates all API sub-hooks on App mount | Wave 7 **parked** performance; larger hook split |
| P9 | `config/montymobile_templates.json` — **KEEP** (Wave 1 STOP) | Live Monty callers; SEC-026 residual until Monty cutover |
| P10 | systemd root + EnvironmentFile (SEC-046) | Infra unit hardening |

---

## 3. BLOCKED (owner answer required before code)

| # | Item | Ask |
|---|---|---|
| B1 | SSE CORS exact origin policy for live_chat_api | Which origins replace `*`? |
| B2 | `content_files_api` / `instructions_api` SaaS scope | Archive vs tenant-scope (not safe multi-tenant as-is) |
| B3 | `legacy_isolation.cloud_bound_display_digits` returns `set()` on DB error (fail-open empty) | Fail-**closed** may block Monty sends — approve behavior change? |
| B4 | SEC-017 `scripts/delete_all_conversations.py` | Harden+archive vs archive-only; **never ran** in Phase 1 |
| B5 | APK in git / `data/*.jsonl` / BINARY_ASSET_REVIEW (**81** still on disk) | Keep vs LFS vs untrack vs archive |
| B6 | SEC-028 ProtectedRoute `role===admin` bypass | KEEP_AS_IS documented vs require permissions for admin too (Wave 14) |
| B7 | Wave 14 KEEP_AS_IS security decisions (SEC-018…024 Meta workflows, GuestChat CSRF/localStorage, ActivityFlow PII JSON, ResetPassword token-in-URL, human_handover coerce, etc.) | Accept vs change — no drive-by edits |

---

## 4. FIXED_CONFIRMED (brief count only)

High-confidence closes from Phase 1 + reinspect second pass (spot-check aligned):

| Bucket | Approx count / note |
|---|---|
| Wave 2 dashboard/mobile security (Auth fail-closed, helpers no admin/linas default, liveChat route permission, debug elevation, RoleManager system roles, Settings/Sidebar/Dashboard tenant gate, media operator from auth, sidebar debug UI removed, guestSession CSPRNG) | **~12** critical/high client+debug items closed |
| Wave 6 GHA (typed confirmation, probe harden, ssh pin, backup perms, no `reset --hard`) | **7** workflow KEEP_SECURITY_FIX paths addressed |
| Wave 1 deletes | **45/46** DELETE_CANDIDATE gone (only Monty templates kept) |
| Wave 3–5 / 7–8 / second-pass | Session load/revoke fail-closed; voice tenant refuse; Monty isolation fail-closed + media path; LoadingScreen; Register min 12 + Theme throw; hub tenant gate; adapters log redact; etc. |
| Orphan cluster spot-check | TrainingFileEditor / BotInstructionsTab / usePermissions **deleted** |
| Vitest (lead) | AuthContext + Settings + MobileLiveChat.auth + ProtectedRoute — **16 passed** |

Inventory CSV / `SECURITY_FINDINGS.md` may still list many of these as OPEN disposition text — treat **this residual file + reinspect report** as post-Phase-1 truth for “is it fixed in code?”, and refresh SEC status in a later audit pass.

---

## 5. Recommended next GO wave / agent split

**Recommended order (security + isolation first, then cleanup):**

### GO Wave A — Tenant + operator defaults (cap ≤5 agents)

| Agent | Owns (exclusive) | Does |
|---|---|---|
| A1 | `modules/models.py` | Remove `operator_001` defaults; require explicit `operator_id` |
| A2 | `handlers/photo_handlers.py` | Fail-closed tenant (mirror voice) |
| A3 | `modules/whatsapp_cloud_ops_api.py` | Fail-closed tenant on ops body |
| A4 | `dashboard/src/hooks/useApiLiveChat.js` | Drop or elevate-gate `simulateWebhook` / rebuild exports |
| A5 | Highest-risk remaining `or "linas"` service sites (from S6 list Mahmoud picks) | Fail-closed; **no** silent linas |

### GO Wave B — Mobile Wave 11 finish (cap ≤4)

| Agent | Owns | Does |
|---|---|---|
| B1 | PrimaryButton / StatusChip / TextField | `useTheme` |
| B2 | `SideDrawer.tsx` | Theme + rotation-safe dimensions |
| B3 | `ChatScreen.tsx` (+ overlays if needed) | Remove dead platform-owner / null label debt |
| B4 | `cmMediaApi.ts` + locale packs | Expo 57 FormData + i18n strings |

### GO Wave C — Archive batch 2 (Wave 9 continuation)

| Agent | Owns | Does |
|---|---|---|
| C1–C3 | Disjoint script/doc path batches from the **82** remaining MOVE list | Move only; STOP on live callers |
| — | `scripts/delete_all_conversations.py` | **Hold** until B4 answer |

### GO Wave D — after owner answers (B1–B3)

| Agent | Owns | Does |
|---|---|---|
| D1 | `live_chat_api.py` (lock) | SSE CORS per B1 |
| D2 | content_files / instructions APIs | Per B2 |
| D3 | `legacy_isolation.py` | Per B3 |

### Later / parked

- Redis rate limit (P1) — only with infra GO  
- Docker/nginx/compose/config.py (P2–P5) — infra GO  
- Binary/APK/jsonl (B5) — owner policy  
- Wave 14 SEC KEEP_AS_IS log (B6–B7) — decisions only  

**Do not push** until Mahmoud asks. Prefer `GO Wave A` then `GO Wave B` in parallel only if file sets stay disjoint and concurrency ≤5.

---

## Mahmoud one-page summary

| Group | Count |
|---|---:|
| STILL_BROKEN line items | **13** (+ S6 multi-file tenant-default family) |
| PARKED_OWNER / infra | **10** |
| BLOCKED (need answer) | **7** |
| FIXED_CONFIRMED | Large Phase 1 close-out (Wave 1–8 core + reinspect second pass); inventory SEC rows may lag |
| Next GO | **Wave A** (tenant/operator) → **Wave B** (mobile finish) → answers unlock D; archive C anytime with caller STOP |

**Not changed by this doc:** application source, infra, deploy, Redis, Meta cutover.
