# HA PURCHASE EXECUTION — Linas AI

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Status:** `HA_MANAGED_PG_CUTOVER_COMPLETE` (app release **not** merged/deployed)

## Resources created (live)

| Resource | ID / name | Spec | Monthly |
|----------|-----------|------|---------|
| Managed Valkey | `linas-redis-prod` `c19219f0-4179-4c0e-aff4-6ff708b3408a` | Valkey 8, lon1, `db-s-1vcpu-2gb` × **2**, TLS/`rediss`, VPC `default-lon1` | **$60** |
| Managed PostgreSQL | `linas-postgres-prod` `17d6fb7e-30d7-442a-a716-5c5344639659` | PG 17, lon1, `db-s-1vcpu-2gb` × **2**, private VPC, TLS | **~$60–61** |
| Regional HTTP LB | `linas-http-lb-lon1` `2535b8ff-…` IP `157.245.31.104` | TLS terminate → nginx `:80`; HC `http://:8003/api/health` | **$12** |
| App peer | `linas-app-lon1-02` `591901417` `167.99.89.243` / `10.106.0.4` | `s-2vcpu-4gb` lon1 | **$24** |
| Spaces | — | not created | **$0** |
| **NEW monthly (Valkey+LB+node02+PG)** | | | **~$156–157** |

Existing node `510629908` kept. SportBook/BOC databases **untouched**.

**Trusted sources (Valkey + Postgres):** droplet `510629908`, droplet `591901417`, tag `linas` only.

**DNS:** `linasaibot.com` + `www` A → `157.245.31.104`.

## Postgres cutover (2026-08-12)

- Dump/restore verified; both nodes private DSN + `sslmode=require`.
- Managed alembic head: `20260812_ha_billing_auth` (Requests **not** applied).
- node01 local PG retained for rollback.
- Scripts: `scripts/ha/managed_pg_*.sh`.

## Wiring notes

- Valkey: private `REDIS_URL` / `RATE_LIMIT_REDIS_URL`; `LINAS_REQUIRE_REDIS=false` (workers off).
- Postgres: private `LINAS_WHATSAPP_DATABASE_URL` with TLS on **both** nodes.
- `LINAS_BILLING_BACKEND` / `LINAS_AUTH_TOKEN_BACKEND` / `META_REGISTRY_BACKEND` remain **file** on live until PR #240 deploy + explicit flag flip.
- `LINAS_FAIL_CLOSED_REDIS_CLAIMS` prepared in PR; **not** enabled on prod.
- **BOC OFF.** No Requests migration. PR #240 **not** merged / **not** deployed.

## HA / failover proof

| Test | Result |
|------|--------|
| Valkey TLS + standby | PASS (prior) |
| Managed PG TLS from both nodes | PASS |
| Managed PG row parity vs node01 dump | PASS |
| Standby streaming (`linas-postgres-prod-2`) | PASS |
| Forced managed primary kill | **Skipped** (safe — standby proven; DO auto-failover) |
| Pool reconnect storm (30× SELECT) | PASS |
| LB both nodes | PASS |
| node01 full loss | PASS `pass=8 fail=0` — Managed PG OK from node02; registry NFS residual |
| node02 full loss | PASS `pass=6 fail=0` |

## Remaining before merge/deploy

1. Merge/deploy PR #240 deliberately.
2. Enable `META_REGISTRY_BACKEND=dual` → soak → `postgres` → unexport registry NFS.
3. Enable `LINAS_BILLING_BACKEND=postgres` + `LINAS_AUTH_TOKEN_BACKEND=postgres` after import verify.
4. Owner gate for `LINAS_REQUIRE_REDIS` / `LINAS_FAIL_CLOSED_REDIS_CLAIMS`.
5. Then Requests migration (separate approval).

## Confirmation

- PR #240 **not** merged · no app-release deploy · Requests **not** migrated · BOC **OFF** · Spaces **not** purchased
