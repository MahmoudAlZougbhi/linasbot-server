# HA node01 SPOF hardening — Linas AI

> Historical 2026-08-12 evidence. The Meta registry authority/counts and cutover
> sequence below are superseded by the read-only 2026-08-14 inventory and
> `docs/scale/META_REGISTRY_POSTGRES_HA_CUTOVER.md`. Never import the now-stale
> NFS file over the newer Managed Postgres registry.

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Constraint:** No merge · No app-release deploy · BOC OFF · No Requests prod migration

## 1. Managed PostgreSQL HA — **LIVE**

| Field | Value |
|------|-------|
| Name / ID | `linas-postgres-prod` / `17d6fb7e-30d7-442a-a716-5c5344639659` |
| Engine | PostgreSQL **17** (managed 17.10) |
| Region / VPC | `lon1` / `default-lon1` (`d0e11d67-…`) |
| Size / nodes | `db-s-1vcpu-2gb` × **2** (primary + standby) |
| Est. monthly | **~$60–61** (same size class as `linas-redis-prod`) |
| Network | Private only; trusted sources = droplets `510629908`, `591901417` + tag `linas` |
| App DB | `linas_whatsapp` (not SportBook/BOC) |
| TLS | `sslmode=require` from **both** app nodes (proved) |
| Standby | `pg_stat_replication`: `linas-postgres-prod-2` streaming (async) + `pghoard` |
| Forced failover | **Not executed** (safe path: standby streaming proved; DO auto-failover) |

### Migration executed

1. Verified `pg_dump -Fc` on node01 → `/opt/linasbot_backups/pg/` (+ sha256 + meta).
2. `pg_restore` into managed; **exact row-count parity** (19 tables); extensions=`plpgsql`; indexes=68; constraints=214.
3. Alembic on managed advanced to `20260812_ha_billing_auth` (billing/auth tables additive). **Requests migration not applied.**
4. Both nodes `LINAS_WHATSAPP_DATABASE_URL` → private managed URI with `sslmode=require` (no localhost / `10.106.0.3`).
5. Env backups under `/opt/linasbot_backups/env/`. **node01 local PG left intact for rollback** (`alembic=20260812_meta_app_registry`).

Scripts: `scripts/ha/managed_pg_*.sh`, `_managed_pg_common.sh`.

## 2. meta_registry

| Item | Status |
|------|--------|
| File/NFS live authority | Still NFS on node01 (`META_REGISTRY_BACKEND` default `file` — **no release deploy**) |
| Managed PG rows | `meta_asset_bindings=4`, `meta_binding_credentials=4` |
| Dual-read file↔PG | **PASS** (binding_id / tenant_id / asset_id / credential links) |
| Cutover to `postgres` | **Blocked on PR #240 deploy** then `dual` → `postgres` → `remove_registry_nfs.sh` |

## 3. Media `meta_social_post_media`

LEGACY_ONLY — NFS removed earlier; **Spaces not required**.

## 4. Correctness-critical multi-node state (code in PR)

| Surface | Status |
|---------|--------|
| Wallets / Stripe / admin-credit idempotency | **PG path in PR** via `LINAS_BILLING_BACKEND=file\|postgres` (default file). Tables + import done on managed. Live apps still file until deploy+flag. |
| Mobile refresh / email auth tokens | **PG path in PR** via `LINAS_AUTH_TOKEN_BACKEND=file\|postgres`. Imported (12 mobile / 4 email). |
| Credit ledger / entitlements | Still file (documented residual in `billing_backend.py`) |
| Requests outbox claim | **SKIP LOCKED + processing** in PR; Requests **not** on prod |
| Webhook / outbound / job locks / takeover | Redis-first; **`LINAS_FAIL_CLOSED_REDIS_CLAIMS`** (and/or `LINAS_REQUIRE_REDIS`) fail-closed — prepared, **not enabled** on prod |
| Valkey | HA locks/RL/queues remain on `linas-redis-prod` |

## 5. Port 8003 hardening

- node01 + node02: public `:8003` **blocked**; VPC `10.106.0.0/20` only for HC.
- LB `https://linasaibot.com/api/health` **200**.

## 6. Full power-loss tests (post Managed PG)

| Scenario | Result |
|----------|--------|
| **A. node01 full loss** (stop app + local PG + NFS) | **PASS** `pass=8 fail=0`. LB health **20/20**. **Managed PG reachable from node02**. Registry NFS residual documented. |
| **B. node02 full loss** | **PASS** `pass=6 fail=0`. LB health **20/20**, ready **200**, webhooks **403**, Valkey OK. |
| Unit durability / registry / billing / claims | **63 passed** (scale + billing + redis fail-closed + outbox + wallet auth) |

## 7. Confirmation

- PR #240 **not** merged
- New application release **not** deployed (DSN/env cutover + restarts only)
- Requests migration **not** applied
- BOC **OFF**
- Managed Postgres **purchased and cut over**
- Spaces **not** purchased
- node01 PG **not destroyed** (rollback available)
