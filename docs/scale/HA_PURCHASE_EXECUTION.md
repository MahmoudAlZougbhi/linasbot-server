# HA PURCHASE EXECUTION — Linas AI

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Path:** HA (not LEAN $15 single-node Valkey)

## Phase A — Live DO price reconciliation (account evidence)

Source: `doctl account get`, `doctl databases options slugs --engine valkey`, `doctl compute size list`, `doctl compute droplet get 510629908`, create probe.

| Resource | Slug / plan | Nodes | Account price | Approved target | Match? |
|----------|-------------|-------|---------------|-----------------|--------|
| Valkey 8 lon1 HA | `db-s-1vcpu-2gb` | **2** (primary+standby) | **~$60/mo** ($30×2) | ~$60 | **YES** |
| Regional HTTP LB lon1 | `size-unit=1` | 1 | **~$12/mo** | ~$12 | **YES** |
| App peer ≥2 vCPU / 4 GiB | **`s-2vcpu-4gb`** | 1 | **$24/mo** | ~$24 (warn if ~$32) | **YES** (cheapest) |
| Alt Intel 4 GiB | `s-2vcpu-4gb-intel` | 1 | $28/mo | — | skip (costlier) |
| Alt Intel 120GB | `s-2vcpu-4gb-120gb-intel` | 1 | **$32/mo** | — | skip |
| Existing Linas node | `s-2vcpu-2gb-90gb-intel` | 1 | **$24/mo** (existing) | keep | YES |
| Spaces | — | — | **not created** | only if required | see below |

### Spaces decision

**Proof:** `services/meta_social_media_store.py` writes under `LINASBOT_DATA_ROOT/meta_social_post_media` (local droplet disk). Inbound webhook durability does **not** depend on that path (Firestore/Postgres + inbound ledger).  
**Decision:** Do **not** create Spaces for this HA launch. Residual P1: multi-node social-post media GETs can diverge until Spaces or sticky media node is added later.

### Accurate HA new-monthly (when purchase unblocked)

| Item | Monthly |
|------|---------|
| Valkey HA `db-s-1vcpu-2gb` ×2 | **$60** |
| Regional LB 1 node | **$12** |
| Second app `s-2vcpu-4gb` | **$24** |
| Spaces | **$0** |
| **NEW total** | **`$96/mo`** |

Prior band `$104–$141` reconciled to **`$96`** with cheapest suitable 4 GiB peer (`s-2vcpu-4gb`). If owner insists on Intel/larger disk peer matching premium SKUs, use `$28` or `$32` droplet → **`$100`** or **`$104`**.

Existing Linas droplet ($24) + new $96 → **Linas infra ≈ $120/mo** (excluding SportBook/BOC).

## BLOCKED_OWNER_ACTION — cannot purchase

```
doctl account status: locked
status_message: team locked due to lack of payment or improper use
POST /v2/databases → 403 "team is currently on a hold"
```

Prices/topology **match** approved HA targets. Purchase/create of Valkey, LB, and second droplet is **blocked by DigitalOcean team hold**, not by price mismatch.

**Owner action:** Clear DO billing/hold (support ticket), unlock team, then re-run create commands in this doc. Do **not** buy `db-s-1vcpu-1gb` ($15 single-node) as final HA.

### Create commands (after unlock only)

```bash
# Valkey HA — never SportBook; never $15 single-node as final HA
doctl databases create linas-redis-prod \
  --engine valkey --region lon1 --size db-s-1vcpu-2gb \
  --num-nodes 2 --version 8

# Second app peer (cheapest ≥2vCPU/4GiB)
doctl compute droplet create linas-app-lon1-02 \
  --region lon1 --size s-2vcpu-4gb --image ubuntu-24-04-x64 \
  --vpc-uuid d0e11d67-3fba-4966-b2db-6a471307df85 \
  --enable-private-networking

# Regional HTTP LB (attach Linas droplets only after both healthy)
doctl compute load-balancer create \
  --name linas-http-lb-lon1 --region lon1 --size-unit 1 \
  --forwarding-rules entry_protocol:http,entry_port:80,target_protocol:http,target_port:80 \
  --health-check protocol:http,port:8000,path:/api/ready,check_interval_seconds:10,response_timeout_seconds:5,healthy_threshold:3,unhealthy_threshold:3 \
  --droplet-ids 510629908,<NEW_DROPLET_ID> \
  --vpc-uuid d0e11d67-3fba-4966-b2db-6a471307df85
```

Trusted sources on Valkey: Linas app droplet IPs/tags only. BOC stays OFF. Do not merge PR #240. Do not deploy new app release from this wave.

## Phase B — Durability (in-repo; done without purchase)

Authoritative inbound ledger + Meta ingress persist-before-ACK + reconcile watchdog. See ledger + tests `tests/scale/test_inbound_event_durability.py`.
