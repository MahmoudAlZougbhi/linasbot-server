# Multi-node divergence closeout — Linas AI HA

> Historical 2026-08-12 evidence. Meta authority/cutover statements are
> superseded by `docs/scale/META_REGISTRY_POSTGRES_HA_CUTOVER.md`; current PG is
> newer and the NFS file must not be imported or enabled as authority.

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Constraint:** No merge · No app-release deploy · BOC OFF · No Requests migration

## Audit (before)

| Surface | node01 (`139.59.167.62` / `10.106.0.3`) | node02 (`167.99.89.243` / `10.106.0.4`) |
|---------|----------------------------------------|----------------------------------------|
| `meta_registry` | Local then NFS export | NFS mount |
| WhatsApp Postgres | Local listen SPOF | Pointed at `10.106.0.3` |
| Valkey | Shared managed | Shared managed |

## Closures (current)

### 1. meta_registry

- Still NFS file authority on live (`META_REGISTRY_BACKEND=file`).
- Managed PG holds matching rows (dual-read **PASS**).
- Switch to `postgres` + NFS removal **after** PR #240 deploy (`scripts/ha/remove_registry_nfs.sh`).

### 2. social media — REMOVED (Spaces not required)

### 3. WhatsApp Postgres — **Managed HA**

- Both nodes: identical private managed DSN + `sslmode=require`.
- Cluster: `linas-postgres-prod` (2 nodes).
- node01 local PG **kept** for rollback (not destroyed).

### 4–5. Independent serve + no sticky + `:8003` VPC-only

- LB sticky `none`; public `:8003` blocked on **both** nodes.
- App failover: node01 or node02 down → LB health via peer.

## Power-loss (post Managed PG)

| Test | Result |
|------|--------|
| node01 full loss | PASS — Managed PG OK from node02; registry NFS residual |
| node02 full loss | PASS |
| `verify_multi_node_closeout` (prior) | pass=31 fail=0 |

## Remaining risks

1. **Registry NFS** until PR deploy + `META_REGISTRY_BACKEND=postgres`.
2. **Billing/auth PG backends** in PR not live-enabled (flags default `file`).
3. **Credit ledger / entitlements** still file.
4. **`LINAS_REQUIRE_REDIS` / fail-closed claims** not enabled on prod.
5. Requests not on prod.

## Confirmation

- PR #240 **not** merged · no app-release deploy · Requests **not** applied · BOC **OFF**
