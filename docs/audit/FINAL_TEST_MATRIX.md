# FINAL_TEST_MATRIX — FINAL FREEZE VERIFICATION

**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**FINAL_APPLICATION_CANDIDATE_SHA:** `72d1d439b589f4d111b0a4cc7cd61030ceaca677`  
**Overall gate:** **PASS** → **READY_FOR_OWNER_REVIEW**

Fresh re-run only (no reused PASS). Python: `.venv/bin/python`.

---

## 1. Backend — pytest

| Gate | Result | Counts / notes |
|------|--------|----------------|
| Full suite `.venv/bin/pytest -q` | **PASS** | **1213 passed**, 0 failed, 2 warnings |
| ruff modules/services/handlers/config/main | **PASS** | **0** findings |

---

## 2. Dashboard (`dashboard/`)

| Gate | Result | Counts / notes |
|------|--------|----------------|
| `npm test` (vitest) | **PASS** | **78 passed / 0 failed** (25 files) |
| `npm run build` | **PASS** | no operator Live Chat / `MobileLiveChat` chunks; `/mobile/live-chat` → `/#get-app` |
| `npm run lint` | **PASS** | 0 warnings (`--max-warnings 0`) |
| `npm run typecheck` | **PASS** | 0 TS errors |

---

## 3. Mobile (`mobile/linas-ai/`)

| Gate | Result | Counts / notes |
|------|--------|----------------|
| `npx tsc --noEmit` | **PASS** | via `npm test` |
| `node --test tests/*.test.mjs` | **PASS** | **97 passed**, 0 failed |
| `npm run lint:lines` | **PASS** | no file >400 in mobile src |
| `npm run secret-scan` | **PASS** | 223 files |
| `npx expo-doctor` | **PASS** | **20/20** |

---

## 4. Residual scans

| Pattern / gate | Result | Notes |
|---------|--------|-------|
| tracked-secret scan | **PASS** | |
| npm audit gate | **PASS** | 0 vulns |
| pip-audit / pip check | **PASS** | |
| app source >500 LOC | **PASS** | **0** |
| inventory parity | **PASS** | **1508** = `git ls-files` |
| PII print residual scan | **PASS** | `tests/test_log_pii_print_redaction.py` |
| obsolete operator SPA primary ship | **PASS** | all former operator paths → `/#get-app` |

---

## 5. Lead verdict summary

| Area | Pass/Fail |
|------|-----------|
| Pytest full | **PASS** (1213) |
| Dashboard vitest | **PASS** (78) |
| Dashboard build | **PASS** |
| Dashboard lint/typecheck | **PASS** |
| Mobile tsc + unit | **PASS** (97) |
| Expo-doctor | **PASS** (20/20) |
| Ruff | **PASS** (0) |
| Secrets / audits / LOC / inventory | **PASS** |

**Freeze gates: PASS** — see `FINAL_FREEZE_VERIFICATION.md`. Live activation A1–A7 still owner-only and **not** executed.
