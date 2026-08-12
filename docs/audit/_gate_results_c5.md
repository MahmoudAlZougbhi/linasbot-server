# Gate results — C5 (test gates)

Branch: `chore/project-cleanup-reorg`  
Agent: remediation C5  
Date: 2026-08-12

## Pytest focused suites

Command: `.venv/bin/python -m pytest` (13 files)

| Suite | Result |
|-------|--------|
| tests/test_wave1_security.py | pass |
| tests/test_endpoint_auth_matrix.py | pass (after test fix) |
| tests/test_saas_auth_token_wallet.py | pass |
| tests/test_tenant_user_isolation.py | pass |
| tests/test_tenant_fail_closed_a2.py | pass |
| tests/test_rate_limit_service.py | pass |
| tests/test_live_chat_sse_cors.py | pass |
| tests/test_legacy_isolation_fail_closed.py | pass |
| tests/test_models_operator_id.py | pass |
| tests/test_whatsapp_factory_cloud_only.py | pass |
| tests/test_product_modules_disabled.py | pass |
| tests/test_delete_all_conversations_guards.py | pass |
| tests/test_social_contact_routing_tenant_fail_closed.py | pass |

**Totals:** **132 passed**, **0 failed**

### Initial failure (fixed in test only)

- `tests/test_endpoint_auth_matrix.py::TestDebugAndSimulationEndpoints::test_simulate_webhook_disabled_in_production_like_env`
- Expected `403` + `PRODUCT_MODULE_DISABLED`; got `503` because `ENVIRONMENT=production` selects Redis rate-limit backend and fail-closes when Redis URL is unset.
- **Diagnosis:** stale test vs intentional fail-closed rate-limit remediation (already covered by `test_rate_limit_service.py`). Not a product bug.
- **Fix:** pin `RATE_LIMIT_BACKEND=memory` + `rate_limit_service.reconfigure(backend="memory")` for this case so the assertion stays on product-module disable.

## Dashboard vitest

Command: `cd dashboard && npm test -- --run` (`node_modules` present)

| Scope | Result |
|-------|--------|
| Full suite | **3 files failed / 23 passed**; **4 tests failed / 62 passed** |
| Auth / ProtectedRoute focused | **5 files / 19 tests passed** |

Auth-focused files run green:
- `src/components/Auth/ProtectedRoute.test.jsx`
- `src/contexts/AuthContext.test.jsx`
- `src/contexts/AuthContext.locSplit.test.jsx`
- `src/utils/authFetch.test.jsx`
- `src/MobileLiveChat.auth.test.jsx`

### Vitest failures (not fixed by C5 — report for lead)

Sidebar nav assertions cannot find expected links (`AI Setup`, `Download Live Chat APK`):

1. `src/components/Layout/Sidebar.downloads.test.jsx` — `shows Live Chat APK for admin`
2. `src/components/Layout/Sidebar.faqSingleEntry.test.jsx` — `shows AI Setup and no Bot Training / Legacy FAQ nav writers`
3. `src/components/Layout/Sidebar.productSurface.test.jsx` — both cases (`linas` restore + non-linas hide)

Likely product-surface / nav labeling drift vs tests; out of C5 Auth gate scope. No application source edited for these.

## Application source

No app/product source changes. Test-only patch in `tests/test_endpoint_auth_matrix.py`.

## Blockers

- Pytest C5 gates: **none**
- Dashboard Auth/ProtectedRoute: **none**
- Dashboard full vitest: **Sidebar product-surface tests failing** (4) — escalate to lead / UI remediation agent
