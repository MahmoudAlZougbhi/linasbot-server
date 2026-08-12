# FINAL_SECURITY_FINDINGS.md — SEC-001…SEC-070 closeout

**Agent:** C3 (SEC closeout) + FINAL FREEZE VERIFICATION reconcile  
**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**FINAL_CANDIDATE_SHA:** `1900bf59925c61e35e4defe41cdbcb557a719062`  
**Sources:** `docs/audit/SECURITY_FINDINGS.md` + current code (`rg`/read) + Phase 1 / post–Phase-1 remediation commits + freeze re-check.  
**Rule:** Exactly one disposition per SEC. Do not treat stale `Status: OPEN` text in `SECURITY_FINDINGS.md` as current truth without re-check.  
**Freeze note:** Dispositions unchanged. ACCEPTED MEDIUM (038/041/048) remain explicit — not cleared by pytest PASS. Full accepted table: `FINAL_FREEZE_VERIFICATION.md` §4.

### Allowed dispositions

| Disposition | Meaning |
|---|---|
| `FIXED` | Remediated in repo (code/workflow/archive). |
| `FALSE_POSITIVE` | Not a defect / defensive property misfiled as a finding. |
| `ACCEPTED_RISK_WITH_REASON` | Residual risk accepted (product/ops/monitor). |
| `LIVE_ACTIVATION_PENDING` | Fixed or ready in repo; needs live/owner activation. |
| `BLOCKED_EXTERNAL_DEPENDENCY` | Cannot close without external party/system. |

---

## Counts

| Disposition | Count |
|---|---:|
| FIXED | 34 |
| ACCEPTED_RISK_WITH_REASON | 32 |
| LIVE_ACTIVATION_PENDING | 4 |
| FALSE_POSITIVE | 0 |
| BLOCKED_EXTERNAL_DEPENDENCY | 0 |
| **TOTAL** | **70** |

---

## Dispositions (SEC-001 … SEC-070)

| ID | Disposition | One-line evidence |
|---|---|---|
| SEC-001 | FIXED | Typed `CONFIRM=APPLY_DASHBOARD_AUTH_SECRET` (`a9b7cb8`, `.github/workflows/dashboard-auth-secret-apply.yml`) |
| SEC-002 | FIXED | `appleboy/ssh-action@v1.2.0` + `chmod 700` data backup (`3863a6d`, `deploy.yml`); emergency still confirmation-gated |
| SEC-003 | FIXED | Typed `CONFIRM=APPLY_INSTAGRAM_LOGIN_SECRETS` (`a9b7cb8`) |
| SEC-004 | FIXED | Typed `CONFIRM=APPLY_META_WEBHOOK_NGINX_SETUP` (`a9b7cb8`) |
| SEC-005 | FIXED | Typed `CONFIRM=APPLY_OPENAI_API_KEY` (`a9b7cb8`) |
| SEC-006 | FIXED | Probe redacts display-name dump; aggregates + fail-closed import (`d46fbec`) |
| SEC-007 | FIXED | Removed `git reset --hard` from `whatsapp-cloud-phase1-apply.yml` (`02055ae`) |
| SEC-008 | FIXED | `App.jsx` `/mobile/live-chat` `requiredPermission="liveChat"` (`69c82d9`) |
| SEC-009 | FIXED | RoleManager/UserForm/UserList system roles only; no assignable localStorage custom roles (`bd769ae`, `e2746ad`) |
| SEC-010 | FIXED | Auth helpers fail-closed: missing role/tenantId → `null` (`578499e`, `AuthContext.helpers.js`) |
| SEC-011 | FIXED | AuthContext clears `auth_session` on 401/403/errors; no admin cache restore (`578499e`) |
| SEC-012 | FIXED | Media composer uses `user?.id`; models require `operator_id` (no `operator_001`) (`758f786`, `4cf5676`) |
| SEC-013 | FIXED | Rebuild/simulate UI removed from `LiveChatSidebar` (`cb5498c`) |
| SEC-014 | FIXED | Same liveChat route gate as SEC-008 (`69c82d9`, `App.jsx`) |
| SEC-015 | FIXED | Settings uses strict `tenantId === 'linas'` (`ee5c983`) |
| SEC-016 | FIXED | debug-firestore / status / rebuild require admin\|platform_owner (`2c5fdf8`, `4cf5676`) |
| SEC-017 | FIXED | Hardened dry-run default + archived CLI (`3e22e82`, `88f0d81` → `archive/scripts/delete_all_conversations.py`) |
| SEC-018 | ACCEPTED_RISK_WITH_REASON | CM content-audit workflow: SSH + masked phones; Actions actors can read CM structure summaries — accepted with existing mitigations |
| SEC-019 | ACCEPTED_RISK_WITH_REASON | CM production cutover: high-impact but confirmation + concurrency — accept ops model |
| SEC-020 | ACCEPTED_RISK_WITH_REASON | Meta login-config apply: GH environment + empty-secret fail — accept |
| SEC-021 | ACCEPTED_RISK_WITH_REASON | Meta multi-app secrets apply: large secret surface over SSH — accept with env protection |
| SEC-022 | ACCEPTED_RISK_WITH_REASON | Meta social atomic cutover: confirmation + environment + rollback key — accept |
| SEC-023 | ACCEPTED_RISK_WITH_REASON | Meta rollback snapshot: encrypted archive without typed confirm — accepted lower-risk ops |
| SEC-024 | ACCEPTED_RISK_WITH_REASON | WA App Review migrate: availability/token guards + flock — accept |
| SEC-025 | LIVE_ACTIVATION_PENDING | Booking `DEFAULT_*_ID` fail-closed in prod (`a924227`); founder welcome copy + in-memory multi-instance still need live env / scale posture |
| SEC-026 | LIVE_ACTIVATION_PENDING | `montymobile_templates.json` deleted; Cloud-only factory (`70e2105`); live Meta cutover/secrets still pending |
| SEC-027 | FIXED | Auth test gap closed — App now requires `liveChat` (was documenting SEC-008 omit) |
| SEC-028 | FIXED | ProtectedRoute + Sidebar: admin no longer bypasses `requiredPermission` / permissionKey (`4cf5676`) |
| SEC-029 | FIXED | Header fake Live notifications removed (`f9a8686`) |
| SEC-030 | FIXED | Sidebar missing tenant ≠ linas; admin permission bypass removed (`45400c5`, `4cf5676`) |
| SEC-031 | FIXED | `SystemPromptKnowledgeStylePanel` deleted (Wave 1 orphan cluster) |
| SEC-032 | FIXED | `TrainingFileEditor` cluster deleted (`3c3bf72`) |
| SEC-033 | ACCEPTED_RISK_WITH_REASON | UserManagement client permission gate; server `/users` authz must remain — accept client UX |
| SEC-034 | ACCEPTED_RISK_WITH_REASON | GuestChatPanel localStorage guest session — landing product; server rate-limits |
| SEC-035 | ACCEPTED_RISK_WITH_REASON | CSRF token in localStorage — accept vs httpOnly redesign |
| SEC-036 | FIXED | simulate/rebuild UI removed; `useApiLiveChat` no longer exports simulate/rebuild; APIs elevated (`cb5498c`, hook return cleaned) |
| SEC-037 | FIXED | Testing Lab offline no longer returns fake `success:true` for sends/provider switch (`71aec92`, `8a2eeae`) |
| SEC-038 | ACCEPTED_RISK_WITH_REASON | ActivityFlow full JSON PII for entitled operators — intentional observability |
| SEC-039 | FIXED | Dashboard SAAS nav filtered by permissions + linas ops gate (`fe6634a`, `e2746ad`) |
| SEC-040 | FIXED | LiveChat route permission covered by ProtectedRoute / liveChat gates (SEC-008/014) |
| SEC-041 | ACCEPTED_RISK_WITH_REASON | FAQ save-all-languages UI; server must authz — accept client surface |
| SEC-042 | ACCEPTED_RISK_WITH_REASON | Thread renders server media URLs; attribution fixed upstream (SEC-012) — accept URL trust model |
| SEC-043 | ACCEPTED_RISK_WITH_REASON | ResetPassword token in URL — standard email-link pattern; server enforces |
| SEC-044 | LIVE_ACTIVATION_PENDING | Nginx privacy/OAuth/`deauthorize` synced in repo (`a924227`); live nginx reload/deploy pending |
| SEC-045 | ACCEPTED_RISK_WITH_REASON | `nginx-privacy-log.conf` excludes `$request_uri`/`$args` — intentional hardening (already in tree) |
| SEC-046 | LIVE_ACTIVATION_PENDING | Unit documents non-root `linasbot` user (`a924227`); live host still `User=root` until provisioned |
| SEC-047 | FIXED | Phone/message-preview DEBUG prints removed (`2eb7214`, `test_text_handlers_message_sec047.py`) |
| SEC-048 | ACCEPTED_RISK_WITH_REASON | Unauthorized human_handover coerce after cooldown — product rule; Wave 14 accept |
| SEC-049 | ACCEPTED_RISK_WITH_REASON | `main.py` `access_log=False` + APK auth — defensive; monitor |
| SEC-050 | ACCEPTED_RISK_WITH_REASON | Guest AI `FORBIDDEN_GUEST_TOOLS` denylist — by design; monitor |
| SEC-051 | ACCEPTED_RISK_WITH_REASON | Meta App Registry OAuth secrets surface — server-side; authz required |
| SEC-052 | ACCEPTED_RISK_WITH_REASON | Instagram Login OAuth secrets surface — server-side; authz required |
| SEC-053 | ACCEPTED_RISK_WITH_REASON | Instagram Login tokens — server-side; authz required |
| SEC-054 | FIXED | Meta webhook HMAC `compare_digest`; settings `tenant_id` default empty (no silent linas) (`dd2af66`) |
| SEC-055 | ACCEPTED_RISK_WITH_REASON | Meta OAuth AES-GCM + state TTL — defensive; monitor |
| SEC-056 | ACCEPTED_RISK_WITH_REASON | Meta OAuth Graph secrets — server-side; authz required |
| SEC-057 | ACCEPTED_RISK_WITH_REASON | Meta OAuth return secrets — server-side; authz required |
| SEC-058 | FIXED | Mobile refresh tokens require tenant (`db7d826`) |
| SEC-059 | FIXED | Owner push token store requires tenant (`9eb034a`) |
| SEC-060 | ACCEPTED_RISK_WITH_REASON | `sensitive_request_logging` redaction — must stay installed; monitor |
| SEC-061 | ACCEPTED_RISK_WITH_REASON | Store IAP billing surface — server-side; authz required |
| SEC-062 | ACCEPTED_RISK_WITH_REASON | Stripe checkout billing surface — server-side; authz required |
| SEC-063 | ACCEPTED_RISK_WITH_REASON | Token metering billing surface — server-side; authz required |
| SEC-064 | ACCEPTED_RISK_WITH_REASON | Token package catalog — server-side; authz required |
| SEC-065 | FIXED | Wallet tenant normalize fail-closed; unlimited list is explicit product config (`c5bc159`) |
| SEC-066 | ACCEPTED_RISK_WITH_REASON | Wallet `InsufficientTokenBalance` fail-closed + RLock — defensive; monitor |
| SEC-067 | FIXED | `user_service` requires tenant (`ae10d12`) |
| SEC-068 | ACCEPTED_RISK_WITH_REASON | Wallet spend analytics — server-side; authz required |
| SEC-069 | ACCEPTED_RISK_WITH_REASON | WhatsApp Cloud crypto helpers — server-side; authz required |
| SEC-070 | FIXED | Guest session IDs use `crypto.getRandomValues` (`da217c0`, `guestSession.ts`) |

---

## Related (not numbered SEC, activation only)

| Item | Repo status | Live |
|---|---|---|
| Redis distributed rate limit (`rate_limit_service.py`) | FIXED in repo (`3762c43`) — prod defaults Redis, fail-closed | LIVE_ACTIVATION_PENDING — provision Redis URL |
| Firestore indexes (`firestore.indexes.json`) | Repo SoT + deploy checklist docs | LIVE_ACTIVATION_PENDING — owner `firebase deploy --only firestore:indexes` |
| SSE CORS allowlist | FIXED (`db9fbdf`) | Deploy app to activate |
| Content-files / instructions APIs | Disabled 410 (`648bc02`) | Deploy app to activate |

See `docs/audit/FINAL_EXTERNAL_ACTIVATION_CHECKLIST.md`.

---

## Method notes

- Phase 1 reinspect / residual / production-readiness docs still say OPEN/PARKED for several items; **post–Phase-1 commits** closed SEC-017, SEC-028, Redis-in-repo, Monty templates delete, nginx include sync, systemd docs, etc.
- Dead destructures of `simulateWebhook` in LiveChat page hooks are hygiene (undefined bindings); security close is UI+export+elevation.
- Zero `FALSE_POSITIVE` / `BLOCKED_EXTERNAL_DEPENDENCY` in this closeout pass.
