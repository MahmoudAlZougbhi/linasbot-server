# Phase 0C — Previously known security concerns (reconciliation)

Each concern has **exactly one** status.

| # | Concern | Status | Evidence |
|---|---|---|---|
| 1 | Mobile login and refresh rate limiting | **ALREADY_FIXED** | `services/auth_rate_limits.py` `auth_rate_limit_rules` for `/api/auth/mobile/login` and `/api/auth/mobile/refresh` (IP + identifier buckets). Wired via `modules/api_security.py` → `check_rate_limit`. Tests: `tests/test_wave1_security.py` (mobile login/refresh rule assertions). Commit `778ab86`. |
| 2 | Trusted proxy / client-IP resolution | **ALREADY_FIXED** | `client_ip()` prefers `X-Real-IP` (nginx `$remote_addr`), does **not** trust leftmost `X-Forwarded-For`. `TRUSTED_PROXY_MODE=direct|x-real-ip`. Commit `778ab86`. |
| 3 | Wallet admin-credit authorization | **ALREADY_FIXED** | `modules/wallet_api.py` `_admin_credit_allowed` + `assert_admin_credit_target_allowed` — cross-tenant only `platform_owner`; allowlisted tenant admins same-tenant. Tests: `tests/test_saas_auth_token_wallet.py::test_admin_credit_cross_tenant_platform_owner_only`. Commit `caacdfe`. |
| 4 | Production CORS | **ALREADY_FIXED** | `modules/core.py` `cors_allow_origins()` — production drops `http://linasaibot.com` / `http://www…`; keeps HTTPS + localhost. Commit `caacdfe`. |
| 5 | Tenant assertions on shared handlers | **CONFIRMED_FIX_REQUIRED** | Middleware gate **exists**: non-`linas` sessions blocked from legacy `/api/live-chat` etc. (`modules/api_security.py`). Remaining gap: many services still silently default `tenant_id` to `linas` (e.g. `services/user_service.py`, `meta_messaging.py`, `social_contact_routing.py`, wallet models) — SaaS isolation debt. Inventory `KEEP_FIX` rows track defaults. |
| 6 | Role/permission elevation | **CONFIRMED_FIX_REQUIRED** | `dashboard/src/contexts/AuthContext.helpers.js` `buildUserData` defaults `role=admin` and `tenantId=linas`; `RoleManager` custom roles in `localStorage`; `ProtectedRoute` admin bypass; `App.jsx` `/mobile/live-chat` missing `requiredPermission=liveChat`. Dispositions `KEEP_SECURITY_FIX` on seq 95/126/152/197. |
| 7 | CSRF and constant-time secret comparison | **ALREADY_FIXED** | Cookie mutations require CSRF header+cookie; `hmac.compare_digest` in `modules/api_security.py`. Also webhook verify tokens use `compare_digest`. Commit `5365550`. Wave1 CSRF tests present (env fixture errors noted in BASELINE_TESTS_BUILDS — test existence still evidence of intent). |
| 8 | Filename/path sanitization | **ALREADY_FIXED** | `services/media_service.py` `sanitize_media_filename` + `resolve_media_file_path` (`relative_to` containment); `services/safe_path.py` for backup/restore. Covered by wave1 SSRF/path tests. |
| 9 | Distributed production rate limiting | **CONFIRMED_FIX_REQUIRED** | `services/rate_limit_service.py` is **file-backed per-process** only (`_DATA_ROOT/auth/rate_limits`). No Redis/distributed limiter implemented in-tree. Multi-instance deploy can under-enforce limits. `docs/audit/RESIDUAL_STATUS.md` notes Redis workers optional/unset. |

## False positives recorded this phase

| Item | Status | Evidence |
|---|---|---|
| `services/cm/shadow_eval.py` “eval() present” | **FALSE_POSITIVE** | Only symbol is `run_shadow_eval`; no Python `eval(` builtin. Lab/golden offline evaluator; must not be on live webhook path (documented in module docstring). |

## Blocked

None for the nine known concerns above.
