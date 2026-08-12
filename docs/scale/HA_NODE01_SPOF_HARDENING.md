# HA node01 SPOF hardening — Linas AI

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Constraint:** No merge · No app-release deploy · BOC OFF · No Requests prod migration · No Managed PG/Spaces purchase in this pass

## 1. Postgres SPOF audit (live node01)

| Item | Observed |
|------|----------|
| Engine | PostgreSQL **17.7** (Ubuntu) on node01 |
| DB | `linas_whatsapp` @ `10.106.0.3:5432` |
| Size | **~8.6 MB** |
| Extensions | `plpgsql` only |
| Alembic (prod) | `20260811_wa_app_review_source` (Requests **not** applied) |
| Listen | `localhost,10.106.0.3` |
| Consumers | WA Cloud tables + smart follow-up; Requests code shares DSN but migration not live; Meta registry **file/NFS** today |
| App pool | `pool_size=5` + `max_overflow=10` / process; `pool_pre_ping`; **no SSL**; **no failover** |
| Backup dir | `/opt/linasbot_backups/pg` **absent** on node01 at audit time |

### Managed PostgreSQL recommendation (DO **lon1**) — **DO NOT PURCHASE YET**

| Field | Value |
|-------|-------|
| Plan slug | `db-s-1vcpu-2gb` |
| Nodes | **2** (primary + standby HA) |
| Region / VPC | `lon1` / `default-lon1` |
| Engine | PostgreSQL **17** (match droplet) |
| Est. monthly | **~$60–61** (same size class as `linas-redis-prod`) |
| Name suggestion | `linas-postgres-prod` |
| Trusted sources | both Linas droplets + tag `linas` |
| Why not 1 GiB | HA standby requires ≥2 GiB on DO |

**Migration method:** `pg_dump -Fc` → create managed → `pg_restore` → dual-node DSN flip to private URI with `sslmode=require` → restart `linasbot` → soak → decommission node01 PG listen.  
**Expected downtime:** ~1–5 minutes for DSN flip if restore pre-verified (DB is tiny).  
**Rollback:** restore prior `.env` DSN to `10.106.0.3`, restart both apps; keep node01 PG intact until soak passes.

**Verdict:** Managed PG HA is **required** to remove Postgres SPOF. See **BLOCKED_OWNER_ACTION** below.

## 2. meta_registry

| Item | Status |
|------|--------|
| Current live authority | NFS file store on node01 (`/opt/linasbot_data/meta_registry`) |
| Code in PR | Postgres SoT via `META_REGISTRY_BACKEND=file\|postgres\|dual` |
| Schema | Alembic `20260812_meta_app_registry` (revises prod head; **before** Requests) |
| Import | `scripts/ha/import_meta_registry_to_postgres.py` |
| Cutover | Not activated on prod (no release deploy). Default remains `file` |
| node01-off for registry | **Blocked** until Managed PG + backend=`postgres` deploy |

## 3. Media `meta_social_post_media`

| Item | Status |
|------|--------|
| Product need | **LEGACY_ONLY** — Create Post / social creative disabled |
| Spaces | **Not required — do not buy** |
| Live action | NFS export/mount **removed**; local stub dirs only |
| Scripts | `scripts/ha/remove_media_nfs.sh`; closeout scripts updated |

## 4. Multi-node residuals (classification)

| Surface | Class | Notes |
|---------|-------|-------|
| Webhook mid/bodyfp claims | ACCEPTABLE_WITH_REASON | Redis claims in PR #240 (await deploy) |
| Scheduler job locks | ACCEPTABLE_WITH_REASON | Redis-preferred in PR (await deploy) |
| Outbound text dedupe | MUST_MOVE_TO_VALKEY → **fixed in PR** | Redis claim first |
| Live Chat SSE | MUST_MOVE_TO_VALKEY → **fixed in PR** | Redis pub/sub fanout |
| `config.user_*` takeover + pending combine | MUST_MOVE_TO_VALKEY → **partial in PR** | Redis sync for takeover + pending |
| Remaining `config.user_*` FSM/gender/etc. | ACCEPTABLE_WITH_REASON | Non-money UX; follow-up after deploy |
| Wallets / credits / Stripe file idempotency | MUST_MOVE_TO_POSTGRES | Needs owner schema approval + Managed PG |
| Mobile refresh / email / guest file tokens | MUST_MOVE_TO_POSTGRES / VALKEY | Residual |
| Requests outbox claim/worker | MUST_MOVE_TO_VALKEY / PG claim | Residual; Requests not on prod |
| Job queue file backend | REMOVE for HA | Redis path exists; `LINAS_REQUIRE_REDIS` owner gate |
| Live Chat / retrieval TTL caches | SAFE_LOCAL_CACHE | OK |

## 5. Port 8003 hardening

- node01 UFW: public Anywhere `:8003` **removed**
- Kept: `8003/tcp` from `10.106.0.0/20` (LB HC VPC)
- Public direct `:8003` times out; LB `https://linasaibot.com/api/health` **200**
- Script: `scripts/ha/harden_port_8003.sh`

## 6. Full power-loss tests (executed 2026-08-12)

Script: `scripts/ha/power_loss_simulation.sh {node01|node02}`

| Scenario | Result |
|----------|--------|
| **A. node01 full loss** (stop `linasbot` + PostgreSQL + NFS) | **PASS** harness `pass=7 fail=0`. LB `/api/health` **20/20** via node02 after HC drain. Meta/WA webhook verify **403** via LB (app reached). `/api/ready` **degraded/timeout** (expected — PG + registry NFS on node01). `meta_registry` **unavailable** on node02 (NFS SPOF). Peer redis/ready probe may timeout while NFS soft-errors. |
| **B. node02 full loss** (stop app only) | **PASS** harness `pass=6 fail=0`. LB `/api/health` **18/20**, `/api/ready` **200**, webhooks **403**, Valkey reachable from node01. |
| Durability unit | `tests/scale/test_inbound_event_durability.py` + registry PG tests: **26 passed**; unexplained_missing_events path covered in suite |

Honest: **WA Postgres + meta_registry still fail on node01 total loss** until Managed PG + `META_REGISTRY_BACKEND=postgres` deploy/cutover. Media NFS already removed (not required).

## 7. Owner action required

```
BLOCKED_OWNER_ACTION — MANAGED_POSTGRES_PURCHASE
```

Exact purchase (after owner approval only):

```bash
doctl databases create linas-postgres-prod \
  --engine pg --version 17 \
  --region lon1 \
  --size db-s-1vcpu-2gb \
  --num-nodes 2 \
  --private-network-uuid <default-lon1-vpc-uuid>
```

**Est. cost:** ~$60–61/mo.  
**Spaces:** not required.  
**Then:** dump/restore → DSN cutover both nodes → enable `META_REGISTRY_BACKEND=dual` then `postgres` (tables already imported on node01 PG as dry-run; re-import after managed restore) → unexport registry NFS → re-run power-loss.

## Confirmation

- PR #240 **not** merged
- New application release **not** deployed
- Requests migration **not** applied
- BOC **OFF**
- Managed Postgres **not** purchased
- Spaces **not** purchased
