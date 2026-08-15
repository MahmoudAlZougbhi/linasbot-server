# Postgres cutover for RC (billing / auth tokens / meta registry)

Concise operator checklist. **No live prod flag flips or droplet changes from this doc alone** — run import/verify in a controlled window after Mahmoud approval.

Code defaults after this change (production-cutover-ready):

| Env | Default | Explicit override |
|-----|---------|-------------------|
| `LINAS_BILLING_BACKEND` | `postgres` | `file` (local/dev / emergency rollback) |
| `LINAS_AUTH_TOKEN_BACKEND` | `postgres` | `file` |
| `META_REGISTRY_BACKEND` | `postgres` | `file` or `dual` (migration helper only) |

Fail-closed: when backend is `postgres` and DB is unavailable, services raise (`BillingBackendError` / `MetaRegistryError`). There is **no** silent file SoT fallback.

## 1. Migrations

```bash
# Relevant additive heads (chain includes meta registry, billing/auth, credits/entitlements, apple)
alembic upgrade heads
```

Key revisions: `20260812_meta_app_registry`, `20260812_ha_billing_auth`, `20260812_credit_entitlements`, `20260812_apple_billing`.

## 2. Import file → Postgres

Existing scripts (do not duplicate):

```bash
# Wallets, Stripe/admin idempotency, mobile refresh, email tokens,
# credit_ledger balances/entries, entitlements + processed events
python scripts/ha/import_billing_auth_to_postgres.py
python scripts/ha/import_billing_auth_to_postgres.py --dry-run   # count only

# Meta registry: DO NOT import on the 2026-08-14 production state.
# Managed PG is non-empty/newer and NFS is stale. Use the dedicated HA runbook.
```

Current Meta procedure: `docs/scale/META_REGISTRY_POSTGRES_HA_CUTOVER.md`.
`import_meta_registry_to_postgres.py` is default-dry-run, requires digest CAS for
apply, and refuses a non-empty divergent target without a separate destructive
confirmation plus an exact encrypted four-table backup.

## 3. Verify parity

```bash
# Meta: use verify_meta_registry_postgres.py; never re-import stale NFS as parity.

# Billing/auth/credits/entitlements count re-import (idempotent) + optional parity probe
python scripts/ha/verify_billing_auth_parity.py
```

## 4. Cutover (code defaults already postgres)

After import+parity on the target DB:

1. Confirm `DATABASE_URL` / `LINAS_WHATSAPP_DATABASE_URL` points at Managed PG.
2. Set `META_REGISTRY_BACKEND=postgres` explicitly and identically on both nodes
   before NFS retirement. Do not switch the current production state to `dual`,
   because dual mode would mirror newer PG writes into a stale file path.
3. Follow the backup/readiness/failover gates in the dedicated Meta HA runbook.
4. Restart app processes so they pick up env (no BOC; no unapproved live flips).

## 5. Rollback

Set env **explicitly** (do not rely on old code defaults):

```bash
# Billing/auth emergency rollback follows their dedicated runbooks.
export LINAS_BILLING_BACKEND=file
export LINAS_AUTH_TOKEN_BACKEND=file

# Meta registry rollback is four-table PG snapshot restore only.
# Never enable/re-import the stale NFS file as authority.
```

Notes:

- Rollback to `file` reintroduces node-local SoT — treat as temporary.
- `dual` is migration helper only (PG primary + file mirror), not a long-term mode.
- Apple transaction / credit-grant **tables** are always Postgres regardless of billing flag.

## 6. Apple revoke outbox drain

```bash
# AuthKey path only (never prints PEM). Retries pending account-delete revokes.
python scripts/ha/process_apple_revoke_outbox.py
python scripts/ha/process_apple_revoke_outbox.py --limit 50
```

## 7. Residual NODE_LOCAL risks (harmless for READY)

After code defaults + successful cutover, critical financial/auth/registry SoT is Postgres. Residual node-local that may remain **NONE-critical** for READY:

- Caches, logs, rollback artifacts, temp files
- Guest/session leftovers not covered by auth-token backend
- Media/NFS paths unrelated to billing/auth/registry (separate HA track)
- Explicit `file`/`dual` env overrides if left set on a node
