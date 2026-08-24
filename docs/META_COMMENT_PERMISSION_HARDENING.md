# Meta comment permission hardening (PR)

Production-safe fail-closed path for Instagram/Facebook **public comment AI replies**.
This change does **not** claim to fix Meta Advanced Access or missing comment webhook/API delivery.

## Problem

`comments_enforcement_decision(..., granted_scopes=None)` allowed replies whenever CM + per-asset toggles were ON, even when Postgres had no trusted permission verification tied to the active token.

## Solution

1. **Postgres-backed verification on `meta_asset_bindings`**
   - `comment_permission_status`: `verified_granted` | `verified_missing` | `unknown`
   - `comment_permission_verified_at`, `comment_permission_source`
   - `comment_permission_credential_id`, `comment_permission_token_fingerprint` (SHA-256 prefix; never logs tokens)

2. **Official runtime source**
   - Active binding + sealed credential in the registry (Postgres SoT)
   - Callers no longer pass optional `granted_scopes`

3. **Fail-closed runtime**
   - `unknown` without a token-bound verification record → no AI reply (`comment_permissions_could_not_be_verified`)
   - Does **not** disconnect, unsubscribe webhooks, or force Comments toggle OFF
   - UI shows blocker via `channel_capability_state`

4. **Last-known-good**
   - Reconcile job uses Meta `debug_token`
   - Transient Meta/HTTP errors keep `verified_granted` for the **same** token fingerprint

5. **Token rotation**
   - New credential/fingerprint invalidates old verification → `unknown` until re-verified

6. **Readiness scopes**
   - Instagram Login: `instagram_business_manage_comments`
   - Facebook Login (Page-linked IG / Facebook Page): `instagram_manage_comments` / Page comment scopes via `required_comment_scopes_for_binding()`

7. **Tenant `linas`**
   - Still uses Standard Access App Review policy (`comments_policy_allows`)
   - No bypass for unknown permission verification

## Migration

### Alembic

Revision: `20260826_meta_comment_perm` (after `20260825_tenant_runtime_cfg`)

Adds five nullable-safe columns with defaults (`unknown` / empty / `0`).

### Data backfill (runtime, not destructive)

On OAuth reconnect and on comment sync/reconcile ticks:

- `bootstrap_unknown_comment_permissions()` / `persist_comment_permission_from_credential()` derive state from **stored credential scopes** in Postgres (`source=migration_stored_scopes` or `oauth_stored_scopes`).
- Active `@linaslaser`-style bindings with comment scopes in the sealed credential become `verified_granted` without manual SQL.

### Deploy order (requires approval)

1. Apply Alembic migration on managed Postgres (node01/node02 share the same DB):
   `alembic upgrade 20260826_meta_comment_perm`
2. **Before any node receives the new build on the load balancer**, run backfill once:
   `python scripts/backfill_meta_comment_permission_verification.py`
   Optional dry-run first: `--dry-run`
3. Deploy the same clean SHA to **both** node01 and node02; verify identical revision:
   `alembic current` → `20260826_meta_comment_perm`
4. Verify `/api/mobile/integrations` comments state for Facebook still shows granted scopes.
5. Confirm DM paths unchanged (Facebook DM + Instagram DM regression on device).

**Do not deploy to production without explicit approval.**

### Why backfill before LB

The migration adds columns defaulting to `unknown`. Old code ignores them. New code reads them.
Running backfill **after migration, before LB traffic hits new code** keeps working Facebook
Comments on `verified_granted` instead of briefly appearing as unknown.

## Rollback

1. Roll back application to previous release (enforcement reverts to legacy `granted_scopes=None` allow path).
2. Optional: `alembic downgrade 20260825_tenant_runtime_cfg` drops the five columns.
   - Verification state is lost; re-upgrade re-defaults to `unknown` until OAuth/reconcile repopulates.
3. No credential/token data is modified by this migration.

## Impact

| Area | Changed? |
|------|----------|
| AI comment reply enforcement | Yes — fail-closed on unknown |
| Comments toggle / Connect / disconnect | No |
| Meta webhook subscriptions | No |
| Facebook DM / Instagram DM | No |
| Meta delivering comment webhooks/API data | No (external / Advanced Access) |

## Tests added

`tests/test_meta_comment_permission_verification.py` covers granted/missing/unknown/LKG/token rotation/scope names/toggle blocker/shared enforcement.

## Files touched (core)

- `alembic/versions/20260826_meta_comment_permission_verification.py`
- `db/models/meta_registry.py`
- `services/meta_comment_permission_verification.py`
- `services/meta_app_registry_common.py`, `services/meta_app_registry_bindings.py`, `services/meta_app_registry_pg_store.py`
- `services/cm/actions.py`
- `services/channel_capability_state.py`
- `services/meta_comment_replies.py`, `services/meta_social_comment_sync.py`, `services/meta_social_comment_sync_jobs.py`
- `modules/meta_connections_api.py`, `modules/meta_connections_api_lifecycle.py`
