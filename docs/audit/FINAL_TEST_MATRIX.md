# FINAL_TEST_MATRIX — FINAL FREEZE VERIFICATION

**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**FINAL_CANDIDATE_SHA:** `1900bf59925c61e35e4defe41cdbcb557a719062`  
**Overall gate:** **FAIL** → **NOT_READY**

Fresh re-run only (no reused PASS). Python: `.venv/bin/python`.

---

## 1. Backend — pytest

| Gate | Result | Counts / notes |
|------|--------|----------------|
| Full suite `.venv/bin/python -m pytest -q --tb=line` | **PASS** | **1195 passed**, 0 failed, 2 warnings (~12.0s) |
| Auth/security focused | **PASS** | 13 passed |
| Migration validation (no mutation) | **PASS** | 15 passed |
| mypy scoped (`modules/auth_api.py`, `services/token_metering.py`) | **PASS** | 0 issues |
| ruff modules/services/handlers/config/main | **FAIL** | 186 findings |

---

## 2. Dashboard (`dashboard/`)

| Gate | Result | Counts / notes |
|------|--------|----------------|
| `npm test` (vitest) | **FAIL** | **4 failed / 74 passed** (78); `ProtectedRoute.test.jsx` ×3, `permissions.test.js` ×1 |
| Landing/auth/route subset | **PASS** | 16 passed |
| `npm run build` | **PASS** | `dashboard/build/` (~672ms); `MobileLiveChat-*.js` present for `/mobile/live-chat` only; operator paths redirect in `App.jsx` |
| `npm run lint` | **FAIL** | 91 warnings, max-warnings 0 |
| `npm run typecheck` | **FAIL** | 139 TS errors |

**Failure note:** `getDefaultPath` now returns `/` (landing-only) after `5f1d1ea`; tests still expect `/app`.

---

## 3. Mobile (`mobile/linas-ai/`)

| Gate | Result | Counts / notes |
|------|--------|----------------|
| `npx tsc --noEmit` | **PASS** | via `npm test` |
| `node --test tests/*.test.mjs` | **PASS** | **97 passed**, 0 failed |
| `npm run lint:lines` | **PASS** | no file >400 in mobile src |
| `npm run secret-scan` | **PASS** | 223 files |
| `npx expo-doctor` | **FAIL** | missing peers; 4 patch mismatches |

---

## 4. Residual scans

| Pattern / gate | Result | Notes |
|---------|--------|-------|
| tracked-secret scan | **PASS** | |
| npm audit gate | **PASS** | 0 vulns |
| pip-audit / pip check | **PASS** | |
| `operator_001` app code | **PASS** | comments/tests only |
| CORS `*` | **PASS** | |
| live private key / sk-live | **PASS** | |
| app source >500 LOC | **PASS** | **0** |
| workflow YAML | **PASS** | 28 OK |
| inventory parity | **PASS** | 1539 = `git ls-files` |
| unsafe `"linas"` defaults | **ACCEPTED** | explicit env/product defaults |
| obsolete operator SPA primary ship | **PASS** | redirects to `/#get-app`; mobile live-chat chunk only |

---

## 5. Lead verdict summary

| Area | Pass/Fail |
|------|-----------|
| Pytest full | **PASS** (1195) |
| Dashboard vitest | **FAIL** (4) |
| Dashboard build | **PASS** |
| Dashboard lint/typecheck | **FAIL** |
| Mobile tsc + unit | **PASS** (97) |
| Expo-doctor | **FAIL** |
| Ruff | **FAIL** |
| Secrets / audits / LOC / inventory | **PASS** |

**Freeze gates: FAIL** — see `FINAL_FREEZE_VERIFICATION.md`. Live activation A1–A7 still owner-only and **not** executed.
