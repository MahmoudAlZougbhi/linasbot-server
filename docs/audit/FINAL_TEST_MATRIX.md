# FINAL_TEST_MATRIX — Phase R gates

**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**Agent:** Phase R gates (report-only; no product code edits; no push)  
**Overall gate:** **FAIL**

---

## 1. Backend — pytest

| Gate | Result | Counts / notes |
|------|--------|----------------|
| Full suite `.venv/bin/python -m pytest -q --tb=line` | **FAIL** | Collection interrupted: **3 errors** |
| Suite excluding broken Meta webhook imports | **FAIL** | **1133 passed**, **16 failed**, 2 warnings (~9.5s) |

### Collection errors (blocks clean full run)

Missing module `scripts.meta_webhook_contract` (source lives under `archive/scripts/meta_webhook_contract.py`; import path broken):

1. `tests/test_meta_token_validation.py`
2. `tests/test_meta_webhook_contract.py`
3. `tests/test_reconcile_meta_comment_webhooks.py`

`--co` report: **1149 tests collected, 3 errors** (exit 2).

### Failures after `--ignore` of the three collection-broken modules

| Test | Symptom (short) |
|------|-----------------|
| `tests/test_auth_migration.py::test_no_known_default_admin_password_in_user_service_source` | Assert expects `ensure_default_admin is disabled` string in user service source |
| `tests/test_live_chat_no_legacy_scan.py::test_unified_chats_empty_index_sets_rebuild_flag_without_legacy` | Mock `get_firestore_db` missing on `services.live_chat_service` |
| `tests/test_live_chat_no_legacy_scan.py::test_waiting_queue_empty_index_never_calls_source_scan` | Same |
| `tests/test_meta_connections_api.py::test_lina_app_b_activation_is_rejected_before_any_subscription` | `activate_meta_connection` missing on module |
| `tests/test_meta_connections_api.py::test_reconnect_atomically_replaces_provider_then_removes_old_subscription` | Same |
| `tests/test_meta_connections_api.py::test_reconnect_first_party_disconnected_binding` | `reconnect_meta_connection` missing |
| `tests/whatsapp_cloud/test_app_review_bind.py` (9 tests) | `debug_token` missing on `app_review_bind` (monkeypatch) |
| `tests/whatsapp_cloud/test_whatsapp_cloud_core.py::test_attempt_state_replay_and_expiry` | `NameError: UTC is not defined` in `services/whatsapp_cloud/repository.py` |

**Product code not patched** (prefer report failures). No test-env pin applied.

---

## 2. Dashboard (`dashboard/`)

| Gate | Result | Counts / notes |
|------|--------|----------------|
| `npm test -- --run` (vitest) | **PASS** | **30** files, **78** tests passed (~7.9s) |
| `npm run build` (vite) | **PASS** | Built in ~978ms |

---

## 3. Mobile (`mobile/linas-ai/`)

| Gate | Result | Counts / notes |
|------|--------|----------------|
| `npx tsc --noEmit -p .` | **FAIL** | Exit 2 — cannot find module `expo-web-browser` (`App.tsx`, `whatsappCloudConnect.ts`). Listed in `package.json` (`~57.0.2`) but **not installed** under `node_modules/`. |
| `npm test` / `node --test tests/*.test.mjs` | **FAIL** | **97** tests: **91 pass**, **6 fail** |

### Mobile test failures

1. `drawer module order matches binding product order`
2. `cold open is branded star splash then chat (no character mash / progress boot)`
3. `owner stream shows Thinking then live bubble in the same footer slot`
4. `proposal card exposes complete V2 actions beyond Review/Discard`
5. `voice STT wires transcript into composer draft (no auto-send)`
6. `i18n still exposes retry + messageFailed copy users see` (expects `/Tap to retry/` in `ChatStatusBanners`; source uses `tr('tapToRetry')`)

**Note:** `npm test` runs `typecheck` first, so the script fails before node tests when `tsc` fails; node tests were also run directly for counts above.

---

## 4. Residual scans (secret / PII / tenant patterns)

Scope: non-archive app paths (`modules/`, `services/`, `dashboard/src/`, `mobile/linas-ai/`, `utils/`, `workers/`, `config/`, `main.py`), excluding tests, docs, `node_modules`, `.venv`. Comment-stripped for `operator_001`. Tracked-file scan via `git grep` for secrets.

| Pattern | Residual count | Verdict note |
|---------|----------------|--------------|
| `operator_001` (non-comment, app code) | **0** | Mentions remain only in end-of-line comments / docs / tests (e.g. “no silent operator_001 default”). |
| `\bsilent\b` (app, non-test) | **17** | Almost all intentional policy language (“never silent fallback / publish”). |
| `"linas"` / `'linas'` string literals (app, non-test) | **29** | Hardcoded tenant id / exemptions / defaults remain (e.g. entitlements, wallet, Meta bind, CM constants). |
| `linas` word hits beyond string literals (app, non-test) | **372** | Mostly brand/product naming, env keys, comments-adjacent identifiers — high noise. |
| `silent` **or** `linas` combined (word + literals) | **418** | Aggregate of rows above. |
| `Access-Control-Allow-Origin` + `*` in app code | **0** | Live Chat SSE reflects allowlisted `Origin` (tests assert never `*`). Docs/audit still mention historical `*`. |
| `sk-live` / `BEGIN PRIVATE KEY` in tracked files | **0** | `git grep -nE 'sk-live\|BEGIN PRIVATE KEY'` clean. |

### Scan methodology notes

- Raw broad `rg` without comment-stripping / path filters over-counts (docs + comments).
- No trivial env pin required for scans.

---

## 5. Lead verdict summary

| Area | Pass/Fail |
|------|-----------|
| Pytest (full / effective) | **FAIL** (3 collection errors + 16 failures) |
| Dashboard test + build | **PASS** |
| Mobile tsc | **FAIL** (missing `expo-web-browser` install) |
| Mobile unit tests | **FAIL** (6/97) |
| Residual operator_001 / CORS\* / live private keys | **PASS** (0 residuals in scoped app / tracked secrets) |
| Residual `silent` / `"linas"` tenant hardcodes | **OPEN** (29 string literals; 17 `silent` policy hits) |

**Phase R gates: FAIL** — do not treat cleanup branch as green until pytest collection path for archived Meta webhook script is restored or tests retired, WhatsApp Cloud / Meta connection / live-chat legacy-scan failures are addressed, and mobile deps + flaky/outdated source assertions are fixed.
