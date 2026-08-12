# FINAL SCALE PURCHASE GATE — Linas AI

**Date:** 2026-08-12  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Status:** `BLOCKED_OWNER_ACTION — DIGITALOCEAN SCALE RESOURCES`  
**Do NOT purchase until owner approves. Do NOT merge. Do NOT deploy.**

## Recommendation

Owner wants **HA that matters** and **low initial cost**, with scale-by-replicas later.

| Option | Valkey | Compute | LB | New monthly | When |
|--------|--------|---------|----|-------------|------|
| **LEAN** | `db-s-1vcpu-1gb` ×1 lon1 **$15** | keep 1 droplet | none | **~$15** | Lowest cost; **no Valkey HA** (1GB cannot add standby) |
| **HA (recommended for HA goal)** | `db-s-1vcpu-2gb` ×**2** lon1 **$60** | 2× app droplets + LB | $12 + ~$64 | **~$136–$141** | Survives one app node + Valkey primary loss |

**Master recommendation:** Approve **HA Valkey + Regional LB + second app droplet** when ready for true HA.  
If owner must minimize spend **this week**, approve **LEAN Valkey $15** only as an interim shared-state enabler — architecture already HA-ready in code — then upgrade Valkey to OPTION HA before calling the platform HA.

**Do not buy the prior “$15 only” as a final HA answer.** It cannot be multi-node.

---

## Purchase table

| Resource | Existing/New | Region | Size | Nodes | HA | Monthly Cost | Required Now? |
|----------|--------------|--------|------|-------|----|--------------|---------------|
| Valkey LEAN `linas-redis-prod` | **New** | lon1 | `db-s-1vcpu-1gb` | 1 | No | **$15** | Yes for shared RL/queues (if choosing LEAN) |
| Valkey HA `linas-redis-prod` | **New** | lon1 | `db-s-1vcpu-2gb` | **2** | **Yes** | **$60** | Yes if choosing HA |
| Regional HTTP LB | New | lon1 | 1 node | 1 | Yes | **$12** | Required for HA multi-droplet |
| App droplet #1 | Existing | lon1 | `s-2vcpu-2gb-90gb-intel` (~$24) | 1 | No alone | existing | Keep |
| App droplet #2 | New (HA) | lon1 | `s-2vcpu-4gb` (~$32) prefer | 1 | Yes w/ #1 | **~$32** | HA path |
| Workers | Colocate initially | lon1 | — | — | — | $0 | Yes (systemd) |
| Postgres | Existing Linas | — | — | — | No | existing | Resize later per DB plan |
| Spaces | New if needed | lon1 | starter | — | — | ~$5 | Only if multi-node media |
| SportBook Valkey | Existing | fra1 | 1GB | 1 | No | — | **Never reuse** |

### Totals

- **LEAN_LAUNCH_MONTHLY (new):** **~$15** (Valkey L)  
- **HA_LAUNCH_MONTHLY (new):** **~$104–$141** depending on droplet sizes + Spaces  

---

## Exact owner action (HA path)

1. DigitalOcean → **Databases** → **Create** → Engine **Valkey 8**  
2. Region **London (lon1)**  
3. Plan **1 vCPU / 2 GiB** (`db-s-1vcpu-2gb`)  
4. Standby nodes: **1** (total nodes **2**) → ~**$60/mo**  
5. Name: `linas-redis-prod`  
6. Create Regional Load Balancer lon1 (~**$12/mo**) targeting Linas droplets  
7. Create/resize second app droplet as needed  
8. Trusted sources: firewall Valkey to Linas droplets only  
9. Return TLS URL to wire `REDIS_URL` / `RATE_LIMIT_REDIS_URL` (owner secret step) — **no live activate without separate go-ahead**

CLI sketch (after approval only):

```bash
doctl databases create linas-redis-prod --engine valkey --region lon1 --size db-s-1vcpu-2gb --num-nodes 2 --version 8
```

## Exact owner action (LEAN interim)

```bash
doctl databases create linas-redis-prod --engine valkey --region lon1 --size db-s-1vcpu-1gb --num-nodes 1 --version 8
```

Cost **~$15/mo**. Not HA.

---

## Why purchase is required

Production `/api/ready` shows `redis_configured=true` but `redis_reachable=false`. Without a dedicated reachable Linas Valkey, distributed rate-limit, durable queues, conversation locks, and multi-instance webhook claims cannot be activated safely. SportBook Valkey must not be reused.
