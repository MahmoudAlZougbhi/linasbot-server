# Audit Closure Ledger

Baseline: `main` @ `709c296`. Branch: `fix/audit-closure-waves` (from `588e436`).

## Explicit exclusions (unchanged)

| ID | Status |
|---|---|
| V2-AI-001 dual FAQ/content SoT | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |
| Dead FAQ top-three knowledge-store redesign | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |
| conversation_log training architecture redesign | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |

## Final gate evidence (local, pre-push)

| Gate | Command | Result |
|---|---|---|
| Format | `ruff format --check` services modules utils handlers storage config.py main.py tests scripts | exit 0 (160 files) |
| Ruff | `ruff check` same scope | exit 0 |
| Mypy | `mypy --config-file mypy.ini` services modules utils handlers storage config.py main.py scripts | exit 0 — **0 errors / 148 files** |
| Pytest | `pytest tests/ -q` | **210 passed**, 0 failed, 0 skipped |
| Import | import `modules.core.app` | exit 0 |
| pip-audit | `pip-audit -r requirements.txt --strict` | 0 known |
| Secret scan | pattern scan | PASS |
| FE test | `npm test` | 18 files / **42 passed** |
| FE lint | `npm run lint` | 0 errors |
| FE build | `npm run build` | exit 0 |
| npm audit gate | `node scripts/npm_audit_gate.mjs` | pass (GHSA-qwww documented external false-positive on patched 7.18.2) |

## Endpoint AuthN/AuthZ (final)

| Metric | Count |
|---:|
| Total `/api/*` routes | **137** |
| Public | **3** |
| Protected | **134** |

Public only: `GET /api/health`, `GET /api/ready`, `POST /api/auth/login`.

- `POST /api/auth/logout` — **protected** (session + CSRF).
- `POST /api/auth/bootstrap-admin` — **removed**; offline `scripts/provision_dashboard_admin.py` only.

## Wave finding status (46 normalized → closed or excluded)

All in-scope Wave 1–5 findings from prior audits are **CLOSED AND VERIFIED** with the evidence above and wave tests (`test_wave1_security`, `test_wave2_social_routing`, `test_wave3_metrics`, `test_wave4_reliability`, `test_endpoint_auth_matrix`, `test_live_chat_no_legacy_scan`, `test_auth_migration`, `test_admin_provisioning`).

Only remaining open items are the three **USER-EXCLUDED** knowledge-architecture rows.

### Auth provisioning (final design)

- Service: `services/admin_provisioning_service.py`
- CLI: `scripts/provision_dashboard_admin.py` (`--prompt-password` or `PROVISION_ADMIN_PASSWORD`)
- Refuses known/default passwords; refuses non-empty user DB; idempotent `already_provisioned`; audit line without password
- Docs: `docs/DEPLOY_AUTH_MIGRATION_CHECKLIST.md`, `docs/PREDEPLOY_ENV_CHECKLIST.md`

### Typing notes

- `mypy.ini`: `disallow_untyped_defs=True`, `follow_imports=silent`, `ignore_missing_imports=True` (third-party packages without stubs; not per-module ignores)
- One pre-existing `# type: ignore` at `services/durable_event_claim.py` (present at `588e436`)
- No `ignore_errors`, no per-file mypy ignore lists

## External actions (not performed)

Push for hosted CI; set production secrets; optional Live Chat backfill with approval; Meta config confirmation out-of-band.

## Safety

No merge, push, deployment, secret rotation, production backfill, Meta change, or customer send in this closure work.
