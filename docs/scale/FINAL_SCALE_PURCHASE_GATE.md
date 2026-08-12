# FINAL SCALE PURCHASE GATE — Linas AI

**Date:** 2026-08-12  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Status:** `BLOCKED_OWNER_ACTION — DIGITALOCEAN TEAM HOLD (billing/lock)`  
**Do NOT merge. Do NOT deploy new release. BOC OFF. Do NOT buy $15 single-node Valkey as final HA.**

Companion: [`HA_PURCHASE_EXECUTION.md`](./HA_PURCHASE_EXECUTION.md)

## Live reconciliation (2026-08-12 doctl)

| Item | Live account | Verdict |
|------|--------------|---------|
| Valkey 8 lon1 `db-s-1vcpu-2gb` + 1 standby (2 nodes) | Available; HA nodeNums `[1,2,3]`; **~$60/mo** | MATCH |
| Regional HTTP LB lon1 1 node | **~$12/mo** | MATCH |
| Second app ≥2 vCPU / 4 GiB lon1 | Prefer **`s-2vcpu-4gb` @ $24/mo** (not $32 Intel-120GB) | MATCH |
| Spaces | Local media path exists; **not required** for inbound HA correctness this wave | SKIP create |
| Create Valkey/LB/droplet | **403 team hold / account locked** | **BLOCKED** |

### HA new monthly (reconciled)

**`$96/mo`** = Valkey HA $60 + LB $12 + `s-2vcpu-4gb` $24 (+ $0 Spaces).  
Prior estimate `$104–$141` → accurate **`$96`** (or `$104` only if choosing `s-2vcpu-4gb-120gb-intel`).

## Recommendation

Proceed with **HA** (not LEAN) as soon as DO unlocks the team:

1. Managed Valkey `linas-redis-prod` Valkey 8 lon1 `db-s-1vcpu-2gb` × **2 nodes** (~$60)
2. Regional HTTP LB lon1 (~$12)
3. Second app `s-2vcpu-4gb` lon1 (~$24)
4. Trusted sources = Linas app nodes only (never SportBook Valkey)

## Why purchase is still required

Production `/api/ready` historically shows Redis configured but unreachable. Without dedicated Linas Valkey + LB + peer node, multi-instance rate-limit, queues, locks, and failover certification cannot run on real infra.

## Durability code (Phase B) — not blocked

Inbound Meta events now persist to durable ledger **before** ACK; Valkey queue is delivery, not sole authority; reconcile watchdog re-enqueues stuck events (`unexplained_missing_events=0` in unit proof).
