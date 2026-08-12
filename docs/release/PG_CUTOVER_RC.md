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

# Meta registry JSON → PG (verifies fingerprint; exits non-zero on mismatch)
python scripts/ha/import_meta_registry_to_postgres.py
python scripts/ha/import_meta_registry_to_postgres.py --store /path/to/registry.json
```

## 3. Verify parity

```bash
# Re-run imports (idempotent) + fingerprint check for meta
python scripts/ha/import_meta_registry_to_postgres.py

# Billing/auth/credits/entitlements count re-import (idempotent) + optional parity probe
python scripts/ha/verify_billing_auth_parity.py
```

## 4. Cutover (code defaults already postgres)

After import+parity on the target DB:

1. Confirm `DATABASE_URL` / `LINAS_WHATSAPP_DATABASE_URL` points at Managed PG.
2. **Do not** set `LINAS_BILLING_BACKEND` / `LINAS_AUTH_TOKEN_BACKEND` / `META_REGISTRY_BACKEND` unless overriding — unset means postgres.
3. Optional soak: `META_REGISTRY_BACKEND=dual` only during migration, then `postgres`.
4. Restart app processes so they pick up env (no BOC; no unapproved live flips).

## 5. Rollback

Set env **explicitly** (do not rely on old code defaults):

```bash
# Emergency file SoT (local node / NFS — divergent risk; short window only)
export LINAS_BILLING_BACKEND=file
export LINAS_AUTH_TOKEN_BACKEND=file
export META_REGISTRY_BACKEND=file   # or dual if PG still writable and you need mirror

# Restart processes. Re-import from file if PG was partially written during failed cutover.
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
