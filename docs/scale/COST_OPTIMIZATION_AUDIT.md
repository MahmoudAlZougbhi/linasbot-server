# Cost Optimization + Original Node Necessity Audit — Linas AI

**Date:** 2026-08-12 (UTC)  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Constraint:** Audit + organizational project moves only. **No merge / app-release deploy.** **No droplet resize executed.** **No original-node delete.** **HA Valkey + Managed PG HA preserved.** **node01 local Postgres not deleted** (concurrent Managed PG cutover/soak).

---

## 1. Exact role of every Linas resource

| Resource | ID / address | Spec | Role (observed 2026-08-12) | Project |
|----------|--------------|------|----------------------------|---------|
| Original app node | droplet `510629908` · `139.59.167.62` / `10.106.0.3` · name `ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01` | `s-2vcpu-2gb-90gb-intel` · 2 vCPU / 2 GiB / 90 GiB | **LB backend** (`linasbot` `:8003` + nginx `:80/:443`). **NFS server** for `meta_registry` → node02. **Local PG 17 still running** on `10.106.0.3:5432` (rollback/soak; WA app DSN already points at Managed PG). Legacy `linas_ai_bot` uvicorn `:8000` still active. Certbot LE live for `linasaibot.com`. Daily localhost PG backup cron still present. | `linas ai bot` |
| Peer app node | droplet `591901417` · `167.99.89.243` / `10.106.0.4` · `linas-app-lon1-02` | `s-2vcpu-4gb` · 2 vCPU / 4 GiB / 80 GiB | **LB backend** only (app + nginx). **NFS client** mounts registry from node01. No local Postgres. No dedicated workers. | `linas ai bot` *(moved this audit)* |
| Regional HTTP LB | `linas-http-lb-lon1` `2535b8ff-…` · `157.245.31.104` | 1 node lon1 · HC `http://:8003/api/health` · TLS terminate → nginx `:80` | Public ingress for `linasaibot.com` / `www`. Health-based failover across both droplets. | `linas ai bot` *(moved)* |
| Managed Valkey | `linas-redis-prod` `c19219f0-…` | Valkey 8 · `db-s-1vcpu-2gb` × **2** (primary+standby) lon1 VPC | Shared Redis/Valkey for rate-limit URL, job-queue readiness, future durable claims. TLS/`rediss` private host `:25061`. | `linas ai bot` *(moved)* |
| Managed Postgres | `linas-postgres-prod` `17d6fb7e-…` | PG 17 · `db-s-1vcpu-2gb` × **2** lon1 VPC | **Live WA DSN target** on both nodes (`LINAS_WHATSAPP_DATABASE_URL` → private `:25060`, SSL). Cutover/soak in progress — **do not decommission node01 PG yet**. | `linas ai bot` *(moved)* |
| DNS domain | `linasaibot.com` | DO DNS | A `@` + `www` → LB `157.245.31.104` (TTL 60). Resend DKIM/SPF/DMARC/MX present. AAAA on `@` present. | `linas ai bot` |
| Volumes | — | — | **None** | — |
| Snapshots (Linas) | — | — | **None** observed for either droplet | — |
| Reserved IPs | — | — | **None** | — |
| DO Cloud Firewalls | — | — | **None** (DB trusted sources via DBaaS firewall + droplet UFW) | — |
| Spaces | — | — | **Not purchased** (media NFS already removed; legacy Create Post) | — |
| Dedicated worker droplets | — | — | **None** — workers not activated (`LINAS_REQUIRE_REDIS=false`; no `linasbot-worker@*` units) | — |

**Non-Linas (untouched):** SportBook / BOC droplets + `sportbook-*-prod` DBaaS in fra1/nyc3. **No SportBook/BOC project moves.**

### Live app wiring notes (both nodes)

- `LINAS_WHATSAPP_DATABASE_URL` → Managed PG private host (SSL flags present).
- `REDIS_URL` / `RATE_LIMIT_REDIS_URL` → Managed Valkey private host.
- `DATABASE_URL=postgres:5432` still present (compose-shaped leftover; not the WA authority).
- `META_REGISTRY_BACKEND` **not set** → live registry remains **file + NFS** on node01.
- Node-local `_DATA_ROOT` file state still present (auth/billing/tenants/logs/etc.) — not yet zero node-local SoT.

---

## 2. All resources moved into `linas ai bot`

Organizational assignment only (no recreate):

| URN | Action |
|-----|--------|
| `do:droplet:510629908` | already in project |
| `do:domain:linasaibot.com` | already in project |
| `do:droplet:591901417` | **assigned this audit** (was wrongly under default `BOC`) |
| `do:loadbalancer:2535b8ff-b89c-442b-b5bf-91eae51ed3f6` | **assigned** |
| `do:dbaas:c19219f0-4179-4c0e-aff4-6ff708b3408a` | **assigned** |
| `do:dbaas:17d6fb7e-30d7-442a-a716-5c5344639659` | **assigned** |

Verified: all six Linas URNs now list under project `70160077-6e21-4fc7-9c81-45e6b60d8919` (`linas ai bot`).

---

## 3. Current app node sizes

| Node | Size slug | vCPU | RAM | Disk | ~$/mo (doctl) |
|------|-----------|------|-----|------|----------------|
| node01 `510629908` | `s-2vcpu-2gb-90gb-intel` | 2 | 2 GiB | 90 GiB | **$24** |
| node02 `591901417` | `s-2vcpu-4gb` | 2 | 4 GiB | 80 GiB | **$24** |

---

## 4. Measured RAM / CPU per node

**Sample window:** 2026-08-12 ~18:43–18:46 UTC (after concurrent restart churn; LB `/api/health` **200** again).

| Metric | node01 (2 GiB) | node02 (4 GiB) |
|--------|----------------|----------------|
| Mem total | 1.92 GiB | 3.82 GiB |
| Mem used (total−available) | ~692–726 MiB (~35%) | ~651–683 MiB (~17%) |
| Mem available | ~1.25–1.28 GiB | ~3.2 GiB |
| Load average | ~0.02–0.05 | ~0.06–0.39 |
| `linasbot` RSS (steady) | ~158–162 MiB | ~158–160 MiB |
| `linasbot` MemoryPeak (systemd) | ~116–139 MiB (restarts) | ~118 MiB |
| nginx RSS sum | ~34 MiB | ~29 MiB |
| Local Postgres RSS sum | ~76 MiB (**node01 only**) | 0 |
| Legacy `:8000` uvicorn RSS | ~84 MiB (**node01 only**) | 0 |
| Dedicated workers | none | none |
| Open TCP (ss) | ~45 | ~44 |
| CPU nproc | 2 | 2 |

**Interpretation:** At zero/near-zero production traffic, a clean app node (python + nginx + OS, **without** local PG / legacy uvicorn / NFS server) sits well under **~700 MiB** working set. node01’s extra ~160 MiB is local PG + legacy process + NFS stack.

**Failover headroom:** One remaining 2 GiB node already runs the live app stack with **~1.2+ GiB available** while also hosting PG+NFS+legacy. A clean 2 GiB peer failover target is therefore safe for **current launch traffic**.

---

## 5. Smallest safe app node size today

| Candidate | Verdict | Why |
|-----------|---------|-----|
| `s-1vcpu-1gb` ($6) | **REJECT** | Working set already approaches 650–700+ MiB; no peer-failover headroom; 1 vCPU weak for API+schedulers. |
| `s-1vcpu-2gb` ($12) | **REJECT for HA app** | RAM OK for idle, but single vCPU is a bottleneck if peer dies and all LB traffic + schedulers land on one node. |
| `s-2vcpu-2gb` ($18) | **RECOMMENDED target** | Matches measured need + failover headroom; symmetrical with node01 class. |
| `s-2vcpu-2gb-90gb-intel` ($24) | **ACCEPTABLE keep** | node01 already on this; keep if 90 GiB disk / Intel SKU desired; not required for RAM. |
| `s-2vcpu-4gb` ($24) | **OVERSIZED now** | node02 measured ~17% RAM used; no workers; no local PG. |

**Smallest safe size today:** **`s-2vcpu-2gb` (2 vCPU / 2 GiB)** for each app replica, assuming clean app-only role (or current node01 role with local PG still present — already proven on 2 GiB).

**Do not resize until:** snapshot/backup + peer healthy behind LB + Managed PG soak complete enough that brief node drain is safe + rollback plan below. **This audit did not resize.**

---

## 6. Can the 4GB node be reduced?

**Yes — recommended after soak, not during concurrent PG cutover.**

- Resize **node02 only first**: `s-2vcpu-4gb` → `s-2vcpu-2gb` (save **~$6/mo**).
- Keep disk size unchanged unless DO requires otherwise.
- Rollback: resize back to `s-2vcpu-4gb` (or restore snapshot) while node01 serves LB.

**Power-off resize note:** DO CPU/RAM resize typically power-cycles the droplet. Drain via LB (stop `linasbot` or remove from LB), resize, smoke, rejoin.

---

## 7. Is original node `139.59.167.62` still required?

### Classification (now)

**`D. STILL_REQUIRED_FOR_SPECIFIC_REASON`**

Hard dependencies that still pin identity to node01 / `10.106.0.3`:

| Dependency | Status |
|------------|--------|
| `meta_registry` NFS export | **ACTIVE** — node02 mounts `10.106.0.3:/opt/linasbot_data/meta_registry` |
| Local PostgreSQL 17 | **ACTIVE** on `10.106.0.3:5432` (~8.9 MB `linas_whatsapp`, ~19 public tables) — keep until Managed PG soak + explicit decommission |
| Local file SoT under `/opt/linasbot_data` | auth/billing/tenants/smart_messaging/logs/etc. still node-local |
| Secrets | `/opt/linasbot/.env` runtime SoT on hosts |
| Legacy `linas_ai_bot.service` `:8000` | still running (pre-cleanup residue) |
| Certbot LE + nginx direct TLS | still on node01 (LB has its own cert; direct HTTPS still useful for ops) |
| Backup cron | `/etc/cron.d/linas-whatsapp-pg-backup` still dumps **localhost** PG (stale vs Managed DSN — update after soak) |
| LB member | still required as one of two healthy backends |

### Classification (after migrations complete)

Preferred path:

1. **`B. REPLACE_WITH_SMALLER_CLEAN_APP_NODE`** — provision a clean `s-2vcpu-2gb` app-only replica (no local PG, no NFS server, no legacy `:8000`, no 11-day cruft / dual code trees).
2. Then **`C. SAFE_TO_REMOVE_AFTER_REPLACEMENT`** of droplet `510629908` **only when** every checklist item below is green.

**Not `A. KEEP_AS_APP_NODE` forever** — the droplet is a legacy SPOF host (NFS + local PG + dual systemd apps), not a clean horizontal replica.

### Removal checklist (must all pass — do **not** delete yet)

- [ ] Managed PG soak passed; apps on both nodes use managed DSN only
- [ ] node01 PG listen decommissioned **after** owner approval (keep dumps)
- [ ] `META_REGISTRY_BACKEND=postgres` (or dual→postgres) live; NFS export/mount removed
- [ ] Billing/auth/token file stores migrated or explicitly accepted residual
- [ ] Legacy `linas_ai_bot.service` disabled/removed
- [ ] Replacement app droplet healthy in LB; failover proven; `unexplained_missing_events=0`
- [ ] DNS remains on LB (already true)
- [ ] Snapshots retained for rollback window

---

## 8. Smallest safe HA launch topology

```text
DNS linasaibot.com → Regional LB ($12)
                 ├─ App A  s-2vcpu-2gb  (API + colocated workers later)
                 └─ App B  s-2vcpu-2gb  (API + colocated workers later)
Shared: Valkey HA db-s-1vcpu-2gb ×2 ($60)
Shared: Postgres HA db-s-1vcpu-2gb ×2 ($60)
Spaces: $0 (not required)
BOC: OFF
Dedicated worker droplets: $0 now
```

**Invariants kept:** LB + 2 app nodes + Valkey primary/standby + Postgres primary/standby + no important node-local SoT (target) + durability features not stripped for cost.

---

## 9. Current vs optimized monthly cost

Prices from `doctl compute size list` + established DO managed DB list pricing (HA = 2 × node price for `db-s-1vcpu-2gb`).

| Line item | Current | Optimized launch |
|-----------|---------|------------------|
| node01 | $24 (`s-2vcpu-2gb-90gb-intel`) | $18–$24 (`s-2vcpu-2gb` or keep intel) |
| node02 | $24 (`s-2vcpu-4gb`) | $18 (`s-2vcpu-2gb`) |
| LB | $12 | $12 |
| Valkey HA ×2 | ~$60 | ~$60 (**keep**) |
| Postgres HA ×2 | ~$60 | ~$60 (**keep**) |
| Spaces / workers / volumes | $0 | $0 |
| **Total** | **~$180/mo** | **~$168/mo** (both at $18) or **~$174/mo** (keep node01 intel $24 + node02 $18) |

**Savings available without weakening HA:** ~**$6–$12/mo** by rightsizing app RAM (4 GiB → 2 GiB) and optionally dropping the 90 GiB Intel SKU when a clean replacement node is built.

**Do not** cut Valkey/PG to `db-s-1vcpu-1gb` — HA standby **not supported** on 1 GiB plans.

---

## 10. Future scale triggers + exact scale procedure

### Triggers (operational — prefer resize/add, not redesign)

| Signal | Threshold (start) | Action |
|--------|-------------------|--------|
| API CPU | >70% sustained 10m on a node | resize vCPU or add API replica |
| API RAM | available <20% or OOM risk | resize RAM or add replica |
| p95 latency (LB/API) | >500ms sustained (ex-provider) | add API replica / reduce in-process work |
| Active connections / FD | climbing with errors | add replicas; check pool sizes |
| Queue depth / oldest age | depth high or age >60s | raise worker concurrency or add worker processes/nodes |
| DB pool utilization | near `pool_size+max_overflow` | raise carefully or add read capacity later |
| Valkey memory / evictions | mem >70% or evictions >0 | resize Valkey plan (**keep ≥2 nodes**) |
| Provider limits (Meta/OpenAI) | 429 storms | queue + backoff — **do not** replica-storm |

### Exact future scale procedure

1. **Compute:** LB drain one node → snapshot → resize **or** clone new `s-2vcpu-2gb+` → install app + `.env` → HC green → add to LB → smoke (auth, Meta/WA webhook verify, email, Redis PING, PG, manual chat) → durability check `unexplained_missing_events=0` → repeat peer.
2. **Workers:** enable `linasbot-worker@*` on app nodes first with strict concurrency; only buy worker-only droplets when colocated CPU/RAM measured insufficient. Growth: 2 → 4 → 10 → 50 via systemd/pool config.
3. **Valkey / PG:** resize plan or add nodes **without** dropping to single-node topology.
4. **Never** remove durable event persistence, Valkey coordination, PG financial/auth authority, idempotency, conversation ordering, reconciliation/watchdog, graceful shutdown, or tenant isolation to save money.

### Safe resize / replacement test plan (when owner approves)

1. Snapshot both droplets (or at least the node being changed).
2. Confirm peer `linasbot` healthy + LB has ≥1 healthy member.
3. Stop/drain target node; resize one-at-a-time; do not change disk unnecessarily.
4. Full smoke: LB health/ready, auth, Meta/WA webhook, Requests (when enabled), email, Redis, PostgreSQL, manual chat.
5. Fail traffic onto the resized node; confirm HC.
6. Require `unexplained_missing_events=0`.
7. Only then repeat for peer / original-node replacement.

**Status this pass:** measured + plan documented; **resize not executed** (concurrent Managed PG work + avoid risk).

---

## Section 10 return summary (checklist)

| Return field | Value |
|--------------|-------|
| Exact role of every Linas resource | See §1 |
| Resources in `linas ai bot` | All 6 Linas URNs assigned (§2) |
| Current app node sizes | node01 2vCPU/2GB; node02 2vCPU/4GB (§3) |
| Measured RAM/CPU | §4 — ~650–730 MiB used; load ≈0 |
| Smallest safe app size today | **`s-2vcpu-2gb`** |
| Can 4GB be reduced? | **Yes** (after soak), to 2GB |
| Is `139.59.167.62` still required? | **Yes now** — NFS registry + local PG rollback + file SoT + legacy service |
| Keep / replace / remove | **`STILL_REQUIRED_FOR_SPECIFIC_REASON` → later `REPLACE_WITH_SMALLER_CLEAN_APP_NODE` → `SAFE_TO_REMOVE_AFTER_REPLACEMENT`** |
| Smallest safe HA launch topology | 2× `s-2vcpu-2gb` + LB + Valkey HA + PG HA (§8) |
| Current monthly cost | **~$180** |
| Optimized monthly cost | **~$168–$174** |
| Future scale triggers | §10 table |
| Exact future scale procedure | §10 procedure |

---

## Actions taken / not taken

| Done | Not done (by design) |
|------|----------------------|
| Full DO inventory | Droplet resize |
| Project assignment into `linas ai bot` | Original node delete |
| Live RAM/CPU measurement both nodes | Valkey/PG downgrade |
| Forensic original-node classification | Dedicated worker purchase |
| Cost topology recommendation | PR merge / app deploy |
| Coordinated: **did not delete node01 PG** | Spaces purchase |

**Concurrent note:** During this audit, Managed PG cutover activity and repeated `linasbot` restarts were observed on node01; node02 briefly hit NFS `registry.lock` I/O errors while node01 NFS/app flapped. LB recovered to **200**. Treat PG soak + registry NFS as **active migration surface** — cost rightsizing waits until that surface is quiet.
