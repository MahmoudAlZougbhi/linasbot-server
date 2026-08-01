# Audit Closure Ledger

Baseline: `main` @ `709c296`. Branch: `fix/audit-closure-waves`.
Closure commit baseline for this cleanup: `bc1308d`.

## Explicit exclusions (unchanged)

| ID | Status |
|---|---|
| V2-AI-001 dual FAQ/content SoT | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |
| Dead FAQ top-three knowledge-store redesign | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |
| conversation_log training architecture redesign | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |

## Final gate evidence (local, pre-push cleanup)

| Gate | Command | Result |
|---|---|---|
| Format | `ruff format --check` services modules utils handlers storage config.py main.py tests scripts | exit 0 (160 files) |
| Ruff | `ruff check` same scope | exit 0 |
| Mypy | `mypy --config-file mypy.ini` services modules utils handlers storage config.py main.py scripts | exit 0 — **0 errors / 148 files** |
| Pytest | `pytest tests/ -q` | **210 passed**, 0 failed, 0 skipped |
| Import | `import main` | exit 0 (`import_ok True`) |
| pip-audit | `pip-audit -r requirements.txt --strict` | No known vulnerabilities |
| Secret scan | pattern scan (`sk-proj-…`, `EAA…`, `admin123`) | PASS |
| Auth matrix | `tests/test_endpoint_auth_matrix.py` (+ auth migration / live-chat / admin provision) | **35 passed** in focused run; full suite 210 |
| Social/Meta/WhatsApp | `pytest -k 'social or meta or whatsapp…'` | **56 passed**, 154 deselected |
| FE test | `npm test` (Vitest) | 18 files / **42 passed** |
| FE lint | `npm run lint` (`eslint . --max-warnings 0`) | **0 errors / 0 warnings** |
| FE typecheck | `npm run typecheck` (`tsc -p jsconfig.json --noEmit`, checkJs strict) | exit 0 — **0 errors**, ~74 `src` files |
| FE build | `npm run build` (Vite) | exit 0 |
| Route/browser smoke | `App.routes.test.jsx` + Vitest suite | covered in 42 FE tests |
| npm audit gate | `node scripts/npm_audit_gate.mjs` | pass — see exception below |
| Quality Gates workflow | `.github/workflows/quality-gates.yml` | includes mandatory FE `typecheck`; deploy waits on Quality Gates success |
| Bandit | `bandit -q -r services modules utils -lll` | exit 0 (no new high+ blockers beyond existing baseline scan) |

## Endpoint AuthN/AuthZ (final)

| Metric | Count |
|---:|
| Total `/api/*` routes | **137** |
| Public | **3** |
| Protected | **134** |

Public only: `GET /api/health`, `GET /api/ready`, `POST /api/auth/login`.

- `POST /api/auth/logout` — **protected** (session + CSRF).
- `POST /api/auth/bootstrap-admin` — **removed**; offline `scripts/provision_dashboard_admin.py` only.

## Wave finding status

All in-scope Wave 1–5 findings from prior audits are **CLOSED AND VERIFIED** with the evidence above and wave tests (`test_wave1_security`, `test_wave2_social_routing`, `test_wave3_metrics`, `test_wave4_reliability`, `test_endpoint_auth_matrix`, `test_live_chat_no_legacy_scan`, `test_auth_migration`, `test_admin_provisioning`).

Only remaining open items are the three **USER-EXCLUDED** knowledge-architecture rows.

### Pre-push cleanup (this commit)

1. **Python typing:** Removed `# type: ignore` in `services/durable_event_claim.py` by capturing `SERVER_TIMESTAMP` / `db` in the import try-scope (no `cast(Any)`, no ignore). Replaced OpenAI `cast(Any, …)` call sites with `ChatCompletionMessageParam` / `ChatCompletionToolParam` / `ResponseFormatJSONObject`. Social processor calls `handle_message(...)` with explicit kwargs. Active scope has **zero** `# type: ignore` and **zero** `cast(Any, …)`.
2. **Frontend lint:** `eslint . --max-warnings 0` → 0/0 (unused imports, entities, hook deps, dead handlers cleaned without rule disables).
3. **Frontend typecheck:** Added `dashboard/jsconfig.json` (checkJs + strict), `npm run typecheck`, domain JSDoc/`src/types/domain.d.ts`, `src/utils/apiValidate.js` validators. Wired into Quality Gates as a mandatory step. No `@ts-ignore` / `@ts-nocheck` / problem-file excludes.
4. **Local env:** `.venv-*/` and `.venv-py311/` in `.gitignore`.
5. **npm advisory exception:** Limited to **GHSA-qwww-vcr4-c8h2** on `react-router` / `react-router-dom` **7.18.2**, Declarative non-RSC (`App.jsx` BrowserRouter proof), package.json pin check; auto-invalidates if version/mode changes. Not a general high bypass.

### npm production audit counts (final)

```
{"info":0,"low":0,"moderate":0,"high":2,"critical":0,"total":2}
```

Both highs are the documented GHSA-qwww false-positive on patched Declarative `7.18.2`.

### Typing notes

- `mypy.ini`: `disallow_untyped_defs=True`, `follow_imports=silent`, `ignore_missing_imports=True` (third-party packages without stubs only; documented in `mypy.ini`)
- No first-party `# type: ignore`, no `ignore_errors`, no per-file mypy ignore lists
- FE: `checkJs` + `strict` + `noImplicitAny` + `strictNullChecks` + `noUncheckedIndexedAccess`; `maxNodeModuleJsDepth: 0` / `skipLibCheck` for third-party only

## External actions (not performed)

Push; merge; deploy; secret rotation; production backfill; Meta config change; customer message send.

## Safety

No merge, push, deployment, secret rotation, production backfill, Meta change, or customer send in this cleanup work.
Knowledge architecture exclusions remain untouched.
Preserved untracked: `scripts/debug_resume_probe.py`. Separate `fix/pause-resume-guardrail` worktree untouched.
