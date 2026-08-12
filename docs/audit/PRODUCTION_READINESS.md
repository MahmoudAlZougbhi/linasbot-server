# Production Readiness — Owner Verdict

**Role:** PRODUCTION READINESS LEAD  
**Repo:** `/Users/alzoughbi/linasbot-server`  
**Branch:** `chore/project-cleanup-reorg` (ahead of `origin/main` by ~125 commits; **not pushed**)  
**HEAD at write:** see `git rev-parse HEAD`  
**Date:** 2026-08-12  
**Ambition bar:** multi-tenant SaaS, up to ~100k concurrent users  

**Method:** Read Phase 1 residual / reinspect / SEC / known concerns; code-verified with `rg` + file reads; parallel scopes A–F (security, tenant/backend, dashboard, mobile, infra/CI, tests). Application source **not** changed for this verdict. Docs only.

---

## القرار / Verdict

# **NO-GO**

| العربية | English |
|---|---|
| **القرار النهائي: NO-GO** — المشروع **غير جاهز** لإنتاج SaaS متعدد المستأجرين بطموح ~100 ألف مستخدم متزامن. | **Final verdict: NO-GO** — not ready for multi-tenant SaaS production at the ~100k concurrent bar. |
| إصلاحات Phase 1 أغلقت معظم ثغرات الصلاحيات الحرجة على لوحة التحكم (fail-closed للـ role/tenant، بوابة liveChat، رفع صلاحيات debug). | Phase 1 closed most critical dashboard authz holes (role/tenant fail-closed, liveChat route gate, debug elevation). |
| لكن عزل المستأجرين ما زال ضعيفاً (افتراضات `linas` صامتة على مسارات ساخنة)، والحد من المعدل ملفّي لكل عملية، وMonty ما زال المزود الافتراضي، وديون البنية غير معتمدة. | But tenant isolation is still weak (silent `linas` defaults on hot paths), rate limits are file/per-process, Monty remains default provider, and infra debt is unapproved. |
| إطلاق مقيّد لمستأجر `linas` فقط يمكن إعادة تقييمه لاحقاً كـ **GO WITH BLOCKERS** إذا قبل محمود قائمة P0 صراحةً وحدد النطاق. | A constrained **linas-only** soft launch could later be re-scored **GO WITH BLOCKERS** if Mahmoud explicitly accepts the P0 list and scopes production. |

**Why this is not GO WITH BLOCKERS:** Verdict criteria treat “no confidence multi-tenant isolation (widespread `linas` defaults on hot paths)” as an automatic **NO-GO** for the stated SaaS ambition. Core authz is improved, but isolation + scale posture fail the bar.

---

## Why (concrete)

1. **Multi-tenant isolation incomplete** — middleware blocks non-`linas` from legacy `/api/live-chat` etc. (`modules/api_security.py`), but ~22+ silent `or "linas"` / env-coalesce sites remain in handlers/services/modules (photo, cloud-ops bind, wallet/AI metering, entitlements). Missing tenant still collapses into `linas` on hot paths.
2. **Scale / concurrency** — `services/rate_limit_service.py` is **file-backed + in-process only** (Known concern #9). Not safe for multi-worker / multi-instance ~100k.
3. **Attribution / ops footguns** — `modules/models.py` still defaults `operator_id="operator_001"`; `scripts/delete_all_conversations.py` still in tree (shell + Firebase creds → full wipe); SSE `Access-Control-Allow-Origin: *` in `modules/live_chat_api.py`.
4. **Provider / cutover** — WhatsApp factory default remains `montymobile`; `config/montymobile_templates.json` still wired (api_key empty; IDs/phone committed — SEC-026 residual).
5. **Infra not owner-approved for change** — Docker Node 20 vs `engines >=22.19`, `nginx-api-include.conf` missing `/oauth/` + `/meta/deauthorize`, Firestore indexes not in GHA deploy, dual `requirements.txt` drift. Deploy without Mahmoud verification is unsafe.

**What is in good shape (do not re-litigate as OPEN criticals):** Auth helpers fail-closed; AuthContext clears session on error/401/403; `/mobile/live-chat` has `requiredPermission="liveChat"`; live-chat debug-firestore + rebuild require admin/platform_owner; dashboard tenant tabs use strict `=== 'linas'`; media composer uses `user?.id`; GHA secret-apply typed CONFIRM; deploy ssh-action `@v1.2.0` + backup `chmod 700`; guestSession CSPRNG; Quality Gates gate normal deploy.

---

## P0 blockers (must fix or explicitly accept before any SaaS / multi-tenant prod claim)

| # | Item | Path(s) | Notes |
|---|---|---|---|
| P0-1 | Photo handler silent tenant → `linas` | `handlers/photo_handlers.py` | Voice already fail-closed; photo still defaults |
| P0-2 | WhatsApp Cloud ops body tenant → `linas` | `modules/whatsapp_cloud_ops_api.py` (~376, ~406) | Bind/unbind silent default |
| P0-3 | Wallet / AI metering / usage collapse to `linas` | `services/token_wallet_service.py`, `ai_usage_limits.py`, `chat_response_runtime_prompt.py`, `wallet_spend_analytics.py`, related env coalescing | Cross-tenant charge / quota risk |
| P0-4 | `operator_001` API model defaults | `modules/models.py` (`FeedbackRequest`, `TakeoverRequest`) | Wrong attribution if client omits |
| P0-5 | SSE CORS `*` | `modules/live_chat_api.py` | Needs owner origin policy (BLOCKED B1) |
| P0-6 | `GET /api/live-chat/status` not elevated | `modules/live_chat_api_debug.py` | Any `liveChat` role; dumps shared index/users counts for `linas-ai-bot-backend` |
| P0-7 | Distributed rate limit (or hard single-instance accept) | `services/rate_limit_service.py` | Infra approval required for Redis |
| P0-8 | Legacy isolation fail-open on DB error | `services/whatsapp_cloud/legacy_isolation.py` (`cloud_bound_display_digits` → `set()`) | May allow Monty when Cloud bind scan fails |
| P0-9 | Destructive CLI still present | `scripts/delete_all_conversations.py` | Harden+archive or archive-only (OWNER_ASK B4) |
| P0-10 | Live nginx + Firestore indexes verified | `deploy/nginx-*.conf`, `firestore.indexes.json` | Confirm prod has OAuth/deauthorize; indexes deployed |

**P0 count: 10**

---

## P1 should-fix soon

| # | Item | Path(s) |
|---|---|---|
| P1-1 | Drop or elevate-gate `simulateWebhook` / `rebuildLiveChatIndex` exports | `dashboard/src/hooks/useApiLiveChat.js` (+ destructure sprawl in LiveChat hooks) |
| P1-2 | ProtectedRoute admin bypass of `requiredPermission` | `dashboard/src/components/Auth/ProtectedRoute.jsx` (SEC-028 — accept or change) |
| P1-3 | RoleManager / custom roles localStorage residual | `dashboard/src/components/UserManagement/RoleManager.jsx`, permissions utils |
| P1-4 | Auth email token / CM gates / compose tenant coalesce | `services/auth_email_tokens.py`, `services/cm/capability_gates.py`, `services/tenant_mobile_dashboard/compose.py` |
| P1-5 | content_files / instructions shared global storage | `modules/content_files_api.py`, `modules/instructions_api.py` (OWNER_ASK B2) |
| P1-6 | Docker Node engines mismatch | `dashboard/Dockerfile.prod` / `dashboard/Dockerfile` = Node 20 vs `engines >=22.19` |
| P1-7 | Sync or delete stale `backend/requirements.txt` | vs root `requirements.txt` |
| P1-8 | Align `nginx-api-include.conf` with full OAuth/deauthorize | `deploy/nginx-api-include.conf` |
| P1-9 | Mobile theme tokens + CM FormData Expo 57 | `PrimaryButton.tsx`, `StatusChip.tsx`, `TextField.tsx`, `cmMediaApi.ts` |
| P1-10 | WA AR/FR locale packs still English stubs | `whatsappAr.ts`, `whatsappFr.ts` |
| P1-11 | Probe CI still logs tenant/role aggregates | `.github/workflows/subscription-exempt-probe.yml` |
| P1-12 | Expand tests for remaining linas-default sites + `/status` elevation | `tests/`, vitest App.routes wiring |

**P1 count: 12**

---

## P2 debt / parked owner

| # | Item | Why parked |
|---|---|---|
| P2-1 | `config.py` defaults / welcome / in-memory multi-instance (SEC-025) | Infra / product identity |
| P2-2 | Docker/compose/systemd root hardening | Infra approval |
| P2-3 | Redis workers / shared store | Infra approval |
| P2-4 | Monty templates KEEP until cutover (SEC-026) | Live callers |
| P2-5 | Remaining ~82 MOVE_TO_ARCHIVE paths | Cleanup batches |
| P2-6 | BINARY_ASSET_REVIEW / APK / jsonl policy | Owner policy |
| P2-7 | Wave 14 KEEP_AS_IS Meta/GuestChat/CSRF/PII decisions | Accept vs change |
| P2-8 | `useApi.jsx` instantiates all API hooks on mount | Perf parked |
| P2-9 | Mobile `SideDrawer` static Dimensions; `ChatScreen` workspaceLabel null debt | UX |
| P2-10 | Soft GHA probes / stale branches | CI hygiene |

---

## Security posture summary

| Area | Status |
|---|---|
| Dashboard auth fail-closed (role+tenant) | **FIXED** — `AuthContext.helpers.js`, `AuthContext.jsx` |
| Privilege spoof via missing fields (SEC-010) | **FIXED in code** (inventory SEC status text may lag) |
| liveChat route permission (SEC-008/014) | **FIXED** — `App.jsx` |
| Debug dump/rebuild elevation (SEC-016) | **FIXED** for debug+rebuild; **`/status` residual** |
| Media operator attribution (SEC-012) | **FIXED** client-side; **models defaults residual** |
| GHA secret-apply confirmation (SEC-001..005) | **FIXED** typed CONFIRM |
| Deploy ssh pin + backup perms (SEC-002) | **FIXED** |
| Tracked live secrets (PEM / sk-proj / AIza) | **No live secrets found** in quick scan |
| CSRF / compare_digest / path sanitization | Prior ALREADY_FIXED (known concerns 7–8) |
| Multi-tenant data plane | **NOT ready** — linas defaults + shared content archives |
| Destructive ops script (SEC-017) | **Still present** — not HTTP-public; shell footgun |

Overall: **hardened single-tenant ops security**, **not** SaaS isolation / scale security.

---

## Multi-tenant SaaS readiness

**NOT READY.**

- Non-`linas` tenants are fail-closed off most legacy APIs (gate, not isolation).
- Silent `linas` defaults remain on photo, cloud-ops, wallet, AI limits, entitlements, compose.
- Live chat / SSE / content_files / instructions are shared linas-shaped stores.
- Middleware allowlist for App-B (auth, CM, meta connections, billing, mobile, …) is deliberate product split — full SaaS live-chat is not delivered.

---

## Mobile readiness

| Bar | Verdict |
|---|---|
| TestFlight / chat-auth pilot | **READY with residuals** (CSPRNG guest, Zod tokenStore, Theme throw, Register min 12) |
| Full multi-tenant SaaS mobile | **NOT READY** (theme static colors, WA locale stubs, CM FormData, single API origin) |

---

## Dashboard readiness

**WITH BLOCKERS** for SaaS; **usable for linas ops** after accepting residuals.

- FIXED: Auth fail-closed, Settings/Sidebar/Dashboard strict tenant, LiveChatSidebar debug UI removed, media operator from auth, liveChat permission on mobile route.
- Residual: hook still exports simulate/rebuild; admin ProtectedRoute bypass; custom-role localStorage odor; `useApi` mount cost.

---

## Infra / deploy readiness

**WITH BLOCKERS — do not deploy without Mahmoud approval.**

- GHA confirmation + Quality Gates → deploy path: **code-ready**.
- Must verify live: nginx full conf (OAuth/deauthorize), Firestore indexes applied.
- Parked: Docker Node mismatch, dual requirements, Redis, compose vs SSH `/opt/linasbot`, Monty templates IDs.
- Branch **not pushed**; deploying this branch would require explicit push + owner GO.

---

## Test / CI confidence

**MEDIUM.**

- Quality Gates: pytest + vitest + lint + secret-scan + deploy-readiness gate PRs and normal prod deploy.
- Strong suites: AuthContext fail-closed, ProtectedRoute/liveChat, wallet admin-credit, live-chat debug elevation matrix, tenant user isolation.
- Gaps: remaining linas-default sites untested; Redis limiter untested; SEC-028 policy untested; BASELINE docs stale vs CI.
- Local pitfall: system Python may lack sqlalchemy — use project venv / CI path.

---

## Exact Mahmoud checklist before any production deploy

1. **Decide scope:** SaaS multi-tenant (stay **NO-GO** until P0 closed) vs **linas-only** soft launch (possible later **GO WITH BLOCKERS** only after explicit accept of remaining P0s).
2. **Do not push / deploy** this branch until you approve.
3. If considering linas-only soft launch, **accept or fix each P0** in writing (especially P0-5 CORS origins, P0-7 rate-limit/single-instance, P0-9 delete script, P0-10 nginx+indexes).
4. Run **Quality Gates green** on the commit you intend to ship; prefer merge-to-`main` path, not ad-hoc feature-branch SSH.
5. Focused pytest (venv): `test_endpoint_auth_matrix.py`, `test_wave1_security.py`, `test_saas_auth_token_wallet.py`, `test_tenant_user_isolation.py`, `test_social_contact_routing_tenant_fail_closed.py`.
6. Focused vitest: AuthContext*, ProtectedRoute, MobileLiveChat.auth, Settings.integrations.
7. Optional: Prod Preflight Readonly workflow.
8. Confirm **live nginx** serves `/oauth/` and `/meta/deauthorize`.
9. Confirm **Firestore indexes** from `firestore.indexes.json` are live.
10. Confirm **Monty vs Cloud** cutover posture (Monty still default — accept or cut over).
11. Confirm **Redis / single-instance** policy for rate limits under expected load.
12. Post-deploy: `GET /api/ready` → ok; smoke login + liveChat permission deny + debug 403 for operator.
13. Never run `scripts/delete_all_conversations.py` against prod without a separate typed ops runbook (prefer archive first).

---

## Code-verify matrix (lead spot-check)

| Check | Result |
|---|---|
| Auth fail-closed role+tenant | **PASS** |
| `/mobile/live-chat` `requiredPermission` | **PASS** |
| debug-firestore / rebuild elevation | **PASS** |
| `/api/live-chat/status` elevation | **FAIL** (liveChat only) |
| `operator_001` leftovers | **FAIL** (`modules/models.py` only in app code) |
| tenant / `or "linas"` hot paths | **FAIL** (handlers 1, services ~10 files, modules 2+) |
| GHA confirmation gates | **PASS** |
| rate_limit_service Redis | **FAIL** (file-backed) |
| SSE CORS `*` | **FAIL** |
| `delete_all_conversations.py` | **PRESENT** |
| montymobile wired | **YES** (default provider) |
| Dockerfile engines mismatch | **YES** (Node 20 vs ≥22.19) |
| nginx-api-include oauth/deauthorize | **MISSING** in include snippet |
| Tracked live secrets | **None found** (Monty api_key empty) |

---

## Next for Mahmoud

**القرار النهائي: NO-GO**

**What to do next:** Fix list (Wave A tenant/operator defaults + P0 table), **not** approve deploy. After P0 closure (or written accept + linas-only scope), request a fresh readiness pass before any production deploy.

Do **not** push. Do **not** deploy. Do **not** change infra without explicit approval.

---

## Sources

- `docs/audit/PHASE1_RESIDUAL_PROBLEMS.md`
- `docs/audit/PHASE1_REINSPECT_REPORT.md`
- `docs/audit/SECURITY_FINDINGS.md` (critical/high — status text may lag code)
- `docs/audit/ALL_PROBLEMS_FOUND.md` (top)
- `docs/audit/KNOWN_SECURITY_CONCERNS.md`
- Code spot-checks + scopes A–F (2026-08-12)
