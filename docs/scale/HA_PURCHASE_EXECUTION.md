# HA PURCHASE EXECUTION — Linas AI

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Status:** `HA_INFRA_WIRED_AND_LOAD_CERTIFIED` (app release **not** merged/deployed)

## Resources created (live)

| Resource | ID / name | Spec | Monthly |
|----------|-----------|------|---------|
| Managed Valkey | `linas-redis-prod` `c19219f0-4179-4c0e-aff4-6ff708b3408a` | Valkey 8, lon1, `db-s-1vcpu-2gb` × **2** (primary+standby), TLS/`rediss`, VPC `default-lon1` | **$60** |
| Regional HTTP LB | `linas-http-lb-lon1` `2535b8ff-…` IP `157.245.31.104` | 1 node lon1; TLS terminate (DO LE cert `linasaibot-lb-cert`); → nginx `:80`; HC `http://:8003/api/health` | **$12** |
| App peer | `linas-app-lon1-02` `591901417` `167.99.89.243` / `10.106.0.4` | `s-2vcpu-4gb` lon1 | **$24** |
| Spaces | — | not created | **$0** |
| **NEW monthly** | | | **`$96`** |

Existing node `510629908` (`139.59.167.62`, `s-2vcpu-2gb-90gb-intel`) kept. Linas total ≈ **$120/mo** (+ SportBook/BOC unchanged).

**Trusted sources (Valkey):** droplet `510629908`, droplet `591901417`, tag `linas` only. **Never** SportBook (`sportbook-redis-prod` fra1 untouched).

**DNS:** `linasaibot.com` + `www` A → `157.245.31.104` (TTL 60).

## Wiring (current prod `main` @ `781a94c` — not PR #240)

- Both nodes: private `REDIS_URL` / `RATE_LIMIT_REDIS_URL` = Valkey `rediss://…` (TLS+auth); `LINAS_REQUIRE_REDIS=false`; `RATE_LIMIT_BACKEND=redis` set for forward-compat.
- Live `/api/ready`: `redis_reachable=true`, `production_ready=true`, Meta App A active on both.
- Nginx HTTP server accepts DO LB traffic when `X-Forwarded-Proto=https` (serves API/SPA); direct HTTP still redirects to HTTPS.
- Workers / durable queues **not** activated (`LINAS_REQUIRE_REDIS` remains false). **BOC OFF.** No Requests migration. PR #240 **not** merged / **not** deployed.

### Env note for operators

Private URI from: `doctl databases connection c19219f0-4179-4c0e-aff4-6ff708b3408a --private`.  
Do **not** commit passwords. Current prod rate-limit **code** on disk is still file-backed (`main`); Redis shared RL lands with PR #240 deploy. Fail-closed Redis RL applies after that release.

## HA / failover proof

| Test | Result |
|------|--------|
| Valkey TLS auth PING/SET/GET | PASS |
| Replication | `role=master`, `connected_slaves=1`; standby read OK (`master_link=up`) |
| Shared counter / idempotency / locks (real Valkey) | PASS (see real-infra cert) |
| LB both nodes | PASS |
| Stop node01; wait HC; LB `/api/health` | **20/20** via node02 |
| Restore node01 | PASS |
| Graceful SIGTERM on current `main` | Process dies → nginx 502 until restart (drain/503 is PR #240 code) |

Forced managed-primary Valkey kill not executed (DO auto-failover); standby replication proven.

## Durability proof

- In-repo ledger + reconcile: `tests/scale/test_inbound_event_durability.py` → `unexplained_missing_events=0`
- Real-infra cert includes that suite: **PASS**, unexplained **0**

## Load cert (real Valkey + LB + both nodes; mocked providers in harness)

Artifact: `docs/scale/LOAD_TEST_RESULTS_REAL_INFRA.json` — **`all_passed=true`**, `unexplained_missing_events=0`.

| Scenario | Result |
|----------|--------|
| 5k owners set | PASS |
| 20k burst idempotency (dupes) | PASS (18001 accepted / 1999 dupes) |
| OOO conversation locks (1000 conv) | PASS |
| Worker crash retry/DLQ | PASS |
| Durable ledger reconcile | PASS |
| LB `/api/health` ×200 @16 workers | PASS (p95 ~783ms) |
| LB `/api/ready` ×30 sequential | PASS |

Harness: `scripts/loadtest/run_real_infra_cert.py` (run on a Linas droplet; Valkey trusted sources block public clients).

## Multi-node divergence closeout (2026-08-12)

See `MULTI_NODE_DIVERGENCE_CLOSEOUT.md`. Closed on **current prod** (no PR #240 deploy):

| Item | Closure |
|------|---------|
| `meta_registry` | NFSv4 shared from node01 → node02 (`/opt/linasbot_data/meta_registry`) |
| social media files | NFSv4 shared `meta_social_post_media` (Spaces not purchased; not required) |
| WhatsApp Postgres | Identical DSN host `10.106.0.3` on both nodes; private listen + UFW/pg_hba |
| Independent paths | Both nodes serve health/ready/Meta/WA verify; LB sticky=`none` |
| Failover retest | node01 app down 20/20 via node02; node02 app down 20/20 via node01 |
| Durability | `unexplained_missing_events=0` (pytest) |

Scripts: `scripts/ha/close_divergence_node0{1,2}.sh`, `verify_multi_node_closeout.sh`.

## Remaining bottlenecks / residuals

1. **PR #240 not deployed** — Redis shared rate-limit, SIGTERM drain/503, inbound ledger in live webhook path await release.
2. **`LINAS_REQUIRE_REDIS=false`** — durable queue workers not on; job_queue Redis is reachable for readiness only.
3. **node01 full-outage SPOF** — WA Postgres + NFS still hosted on node01 (app failover proven; managed PG still OWNER gate).
4. **`/api/ready` heavy** under concurrency (Meta checks); LB HC uses `/api/health`.
5. **2vCPU nodes** — API concurrency headroom limited; scale out before 5k live owners.

## Ready for Requests migration + prod deploy of PR #240?

**Not yet.** Infra HA + Valkey + LB + multi-node shared registry/media/WA DSN are ready. Next OWNER gates: merge/deploy PR #240 deliberately, enable workers only with explicit `LINAS_REQUIRE_REDIS` approval, then Requests migration. Do **not** buy $15 single-node Valkey as final HA.
