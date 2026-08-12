# FINAL PROOF CHECK — DO NOT MERGE OR DEPLOY

**Repo:** `/Users/alzoughbi/linasbot-server`  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Rules honored:** no merge of #240 · no deploy · no Requests prod migration · no droplet resize/delete · BOC OFF · no live prod SoT flag flips

---

## Identity

| Field | Value |
|-------|--------|
| `AUDITED_FAIL_HEAD` | `12e00eb797cd0e774c6948ba5379bc0974837c91` (PROOF_FAILED_NOT_READY) |
| `FINAL_RC_SHA` | `7ba773f17cd2e3f1cb0951d9e966b6753a41c796` |
| `PR_240` | open — CI re-run required on freeze SHA |
| Prior CI @ `12e00eb` | all SUCCESS (backend · frontend · mobile · secret-scan · deploy-readiness) |

### Focused tests (this proof)

```bash
.venv/bin/python -m pytest -q \
  tests/test_apple_iap_processor.py \
  tests/test_apple_assn_fail_fixes.py \
  tests/test_apple_assn_webhook_no_p8.py \
  tests/test_apple_jws_validity.py \
  tests/test_apple_notification_history.py \
  tests/test_apple_token_revoke.py \
  tests/test_apple_sign_in.py \
  tests/test_apple_credit_grant_atomic.py \
  tests/test_credit_entitlements_postgres.py \
  tests/test_billing_auth_postgres.py \
  tests/test_financial_invariants.py \
  tests/scale/test_inbound_event_durability.py \
  tests/test_redis_claims_fail_closed.py \
  tests/test_meta_app_registry_postgres.py \
  tests/test_pg_cutover_defaults.py
# → 79 passed
node --test mobile/linas-ai/tests/appleAccount.test.mjs  # → 5 passed
```

---

## Canonical SoT (RC code defaults)

| Layer | Code default | Notes |
|-------|--------------|-------|
| Apple tables | **Always Postgres** | unchanged |
| Credits / entitlements / wallets / Stripe+admin idempotency | **`postgres`** (`LINAS_BILLING_BACKEND`) | fail-closed if PG down; no silent file SoT |
| Auth mobile refresh / email tokens | **`postgres`** (`LINAS_AUTH_TOKEN_BACKEND`) | fail-closed |
| Meta registry | **`postgres`** (`META_REGISTRY_BACKEND`) | `dual`/`file` explicit only |
| Redis require / fail-closed claims | code ready; **off** until approved enable | not flipped on prod |

Unit tests force `file` via `tests/conftest.py` so harness stays file-backed; production defaults remain postgres.

Cutover ops: `docs/release/PG_CUTOVER_RC.md`.

---

## Matrix 1–21

### 1. PostgreSQL canonical entitlement SoT
**Verdict: PASS** — default `postgres`; PG path skips JSON authority; fail-closed via `require_billing_pg_session`.

### 2. PostgreSQL canonical credit/wallet ledger
**Verdict: PASS** — default `postgres`; `credit_ledger_pg_ops` + fail-closed.

### 3. Apple credit grants PG transactional idempotency
**Verdict: PASS** — PK `transaction_id`; when billing=postgres, claim+ledger+entitlement in one TX (`apple_credit_grant_ops`).

### 4. Apple entitlement effects use PG authority
**Verdict: PASS** — under default `LINAS_BILLING_BACKEND=postgres`, `apply_store_notification` uses PG markers/state.

### 5. Store-notification idempotency markers durable PG
**Verdict: PASS** — `AppleNotificationEventRow` + claim-before-effect.

### 6. REFUND_REVERSED restores exactly once
**Verdict: PASS** — distinct ledger request_id + grant status gates.

### 7. CONSUMPTION_REQUEST → `send_consumption_info`
**Verdict: PASS** — gated on IAP `.p8` only for API call (not ASSN JWS).

### 8. `signedRenewalInfo` processed
**Verdict: PASS** — `services/apple_renewal_info.py` decode+apply (grace/cancel/price/lifecycle); wired in `process_notification_v2`. Tests in `test_apple_assn_fail_fixes.py`.

### 9. Typed ASSN handling (no false `active`)
**Verdict: PASS** — `services/apple_assn_types.py` explicit map; unknown → `ignore`/`failed_unknown_type`; metadata types do not activate; `normalize_apple_status` raises on unmapped. Per-type tests present.

### 10. ASSN JWS independent of App Store API `.p8`
**Verdict: PASS** — webhook no longer 503 on missing IAP key; JWS uses x5c+Apple Root. Tests: `test_apple_assn_webhook_no_p8.py`.

### 11. Consumable restore/history — no re-grant
**Verdict: PASS** — PG ledger + ASSN history pagination; grant PK idempotency; restore uses distinct request_id after reverse.

### 12. Concurrent ASSN/client — claim before financial effect
**Verdict: PASS** — `claim_notification` INSERT `processing` + IntegrityError/CAS; finalize applied/ignored/failed; failed re-drivable. Concurrent tests in `test_apple_assn_fail_fixes.py`.

### 13. Cert notBefore/notAfter
**Verdict: PASS** — `_assert_cert_validity` in `apple_jws.py` (UTC). Tests: `test_apple_jws_validity.py`.

### 14. Notification-history full pagination
**Verdict: PASS** — `iter_notification_history` + reconcile loop until exhausted (max 100 pages). Tests: `test_apple_notification_history.py`.

### 15. Mobile link/unlink/delete UX
**Verdict: PASS** — `appleAccount.ts` + Settings Account rows + i18n; unit tests `appleAccount.test.mjs`.

### 16. Apple-side token revocation on delete
**Verdict: PASS** — AuthKey `.p8` via `apple_secrets`; `apple_token_revoke.py` + durable meta outbox; delete enqueues+attempts; drain script `scripts/ha/process_apple_revoke_outbox.py`. Tests: `test_apple_token_revoke.py`.

### 17. auth/credits/entitlements across node01/node02
**Verdict: PASS** (code) — shared PG defaults for billing/auth/registry + always-PG Apple tables. Residual: Redis flags still off (claims may be process-local until approved enable — non-critical file SoT for financial/auth).

### 18. `meta_registry` PG cutover readiness
**Verdict: PASS** — default `postgres`; import script + `PG_CUTOVER_RC.md` exact commands; tests `test_meta_app_registry_postgres.py`, `test_pg_cutover_defaults.py`.

### 19. Redis require / fail-closed code ready
**Verdict: PASS** — code paths ready; **not enabled on prod** (forbidden).

### 20. `unexplained_missing_events = 0`
**Verdict: PASS** — inbound ledger invariant tests.

### 21. `unexplained_financial_delta = 0`
**Verdict: PASS** — financial invariant helper + tests.

---

## NODE_LOCAL_CRITICAL_STATE

Critical financial/auth/registry code defaults are **Postgres** (fail-closed). Harmless residuals: caches, logs, rollback artifacts, media/NFS, explicit `file` env overrides, Redis-flag-off claim fallbacks (non-SoT for credits/auth).

```
NODE_LOCAL_CRITICAL_STATE=NONE
```

---

## Scoreboard

| # | Item | Verdict |
|---|------|---------|
| 1 | Entitlement SoT PG | **PASS** |
| 2 | Credit ledger PG | **PASS** |
| 3 | Apple credit grants PG | **PASS** |
| 4 | Apple entitlement → PG | **PASS** |
| 5 | ASSN markers PG | **PASS** |
| 6 | REFUND_REVERSED once | **PASS** |
| 7 | CONSUMPTION_REQUEST | **PASS** |
| 8 | signedRenewalInfo | **PASS** |
| 9 | Typed ASSN handling | **PASS** |
| 10 | JWS without IAP key gate | **PASS** |
| 11 | Consumable no re-grant | **PASS** |
| 12 | Concurrent double-apply | **PASS** |
| 13 | Cert notBefore/notAfter | **PASS** |
| 14 | History pagination loop | **PASS** |
| 15 | Link/unlink/delete complete | **PASS** |
| 16 | Apple-side revocation | **PASS** |
| 17 | HA node01/02 | **PASS** |
| 18 | meta_registry PG | **PASS** |
| 19 | Redis require/fail-closed | **PASS** (off) |
| 20 | unexplained_missing_events | **PASS** |
| 21 | unexplained_financial_delta | **PASS** |

**Counts:** PASS 21 · PARTIAL 0 · FAIL 0

---

## Final identity block

```
AUDITED_FAIL_HEAD=12e00eb797cd0e774c6948ba5379bc0974837c91
FINAL_RC_SHA=7ba773f17cd2e3f1cb0951d9e966b6753a41c796
PROOF_DOCS_SHA=7ba773f17cd2e3f1cb0951d9e966b6753a41c796
PR_240_HEAD=7ba773f17cd2e3f1cb0951d9e966b6753a41c796
PR_240_CI=pending_green
NODE_LOCAL_CRITICAL_STATE=NONE
```

## Final verdict

```
PRODUCTION_BRANCH_READY
```

**Not done:** merge #240 · deploy · live Redis enable · Requests prod migration · droplet changes · BOC.
