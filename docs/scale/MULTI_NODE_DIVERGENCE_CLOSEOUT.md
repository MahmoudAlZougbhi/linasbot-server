# Multi-node divergence closeout — Linas AI HA

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Constraint:** No merge · No app-release deploy · BOC OFF · No Requests migration

## Audit (before)

| Surface | node01 (`139.59.167.62` / `10.106.0.3`) | node02 (`167.99.89.243` / `10.106.0.4`) |
|---------|----------------------------------------|----------------------------------------|
| `meta_registry` | Local `/opt/linasbot_data/meta_registry` (4 bindings) | Local copy (same bytes then; would diverge on write) |
| `meta_social_post_media` | Missing (no active files) | Missing |
| `LINAS_WHATSAPP_DATABASE_URL` | `127.0.0.1:5432` (Postgres listening) | `127.0.0.1:5432` (**nothing listening**) |
| Valkey | Shared `linas-redis-prod` private `rediss` | Same |
| LB sticky | `none` | `none` |

## Closures (current prod code + shared infra; no release deploy)

### 1. meta_registry — shared FS authority

- NFSv4 export on node01: `/opt/linasbot_data/meta_registry` → node02 only (`10.106.0.4`)
- node02 mounts same path (`fstab` persistent, `_netdev,nofail`)
- Both app processes use existing file registry + `fcntl` against one authoritative tree
- Scripts: `scripts/ha/close_divergence_node01.sh`, `close_divergence_node02.sh`

### 2. social media / runtime media — **REMOVED** (Spaces not required)

- Create Post / social creative is product-disabled; `meta_social_post_media` is legacy-only
- NFS export/mount for media **removed** (local stub dirs only)
- **Do not buy Spaces** for this path
- See `HA_NODE01_SPOF_HARDENING.md`

### 3. WhatsApp Postgres — identical reachable DSN

- Postgres on node01 listens on `localhost,10.106.0.3`
- `pg_hba` + UFW allow `linas_whatsapp` from `10.106.0.4/32`
- **Both nodes:** `LINAS_WHATSAPP_DATABASE_URL` host = `10.106.0.3` (identical DSN)
- node02 `psql` SELECT against shared DB = PASS
- Managed Linas Postgres **not** purchased (residual SPOF if entire node01 dies)

### 4–5. Independent serve + no sticky

- Each node `:8003` serves `/api/health`, `/api/ready`, Meta + WA webhook verify (403 on bad token)
- LB `sticky_sessions.type=none`
- App-only failover: node01 down → LB 20/20 via node02; node02 down → LB 20/20 via node01
- Fixed node01 UFW so LB HC on `:8003` reaches node01 (was blocking sole-node failover)

## Verify results (`scripts/ha/verify_multi_node_closeout.sh`)

**SUMMARY pass=31 fail=0**

| Test | Result |
|------|--------|
| Independent node API/webhook paths | PASS |
| Redis/shared-state + identical WA DSN | PASS |
| Media NFS cross-node | PASS |
| LB Meta/WA read-only smoke | PASS (403 challenge = app reached) |
| node01 app down → traffic via node02 | PASS (20/20) |
| node02 app down → traffic via node01 | PASS (20/20) |
| `tests/scale/test_inbound_event_durability.py` | PASS · unexplained_missing_events = 0 |

## Remaining risks

1. **node01 full outage SPOF** — WA Postgres + registry NFS still on node01. Media NFS removed. Managed PG required — see `HA_NODE01_SPOF_HARDENING.md` (`BLOCKED_OWNER_ACTION — MANAGED_POSTGRES_PURCHASE`).
2. **NFS `fcntl` under dual writers** — registry still file/NFS until `META_REGISTRY_BACKEND=postgres` after Managed PG + deploy.
3. **PR #240 not deployed** — Redis claims / SSE pubsub / outbound dedupe / registry PG backend await deliberate merge+deploy.
4. **Other residuals** — wallets/auth file stores (see `NON_HORIZONTAL_STATE_INVENTORY.md`).
5. **Port `:8003`** — hardened to VPC `10.106.0.0/20` only on node01 (public Anywhere removed; LB HC verified).

## Confirmation

- PR #240 **not** merged
- New application release **not** deployed
- Requests migration **not** applied
- BOC **OFF**
