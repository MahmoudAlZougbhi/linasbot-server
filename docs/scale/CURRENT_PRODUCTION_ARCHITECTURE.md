# Current Production Architecture — Linas AI

**Date:** 2026-08-12  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240)  
**Rule:** Read-only inventory for scale phase. No purchase / merge / deploy in this doc.

## Evidence classes

| Class | Meaning |
|-------|---------|
| OBSERVED_AT_RUNTIME | Live probe / doctl / `/api/ready` |
| DECLARED_IN_CODE | Repo systemd, main, services |
| INFERRED | DNS + droplet match / docs |
| UNKNOWN_NOT_ACCESSIBLE | Needs prod SSH or secret not available locally |

---

## 1. Live inventory (OBSERVED)

### Compute

| Resource | Value | Class |
|----------|-------|-------|
| DNS `linasaibot.com` | `139.59.167.62` | OBSERVED |
| Droplet | `ubuntu-s-2vcpu-2gb-90gb-intel-lon1-01` ID `510629908` | OBSERVED |
| Region | **lon1** | OBSERVED |
| Size | **2 vCPU / 2 GiB RAM / 90 GiB disk** | OBSERVED |
| Status | active | OBSERVED |
| Load balancers | **none** in this DO account | OBSERVED |
| Other droplets | SportBook / Boc / staging in **fra1/nyc3** — not Linas app | OBSERVED |

### Managed databases (this DO account)

| Name | Engine | Region | Size | Nodes | Linas use? |
|------|--------|--------|------|-------|------------|
| `sportbook-redis-prod` | Valkey 8 | **fra1** | `db-s-1vcpu-1gb` | 1 | **NO** — SportBook; wrong product/region |
| `sportbook-postgres-prod` | Postgres 18 | fra1 | `db-s-1vcpu-2gb` | 1 | **NO** |

**No dedicated Linas Managed Valkey or Managed Postgres exists today.**

### Live readiness (`GET https://linasaibot.com/api/ready`) — OBSERVED 2026-08-12

| Check | Result |
|-------|--------|
| overall `ok` | `true` |
| Meta social messaging | ok / App A active |
| Firestore | ok |
| `data_root_writable` | ok |
| job_queue.backend | `redis` |
| redis_configured | `true` |
| redis_reachable | **`false`** (`ConnectionError`) |
| redis_required | `false` |
| production_ready (queue) | `false` |
| WhatsApp inbound AI | enabled=false (product invariant) |

Interpretation: a Redis URL is set in prod env, but the endpoint is **unreachable**. Rate-limit / durable queue must not be treated as live shared state until a reachable Linas Valkey exists.

### Postgres (WhatsApp / Requests)

| Item | Status | Class |
|------|--------|-------|
| Engine URL env | `LINAS_WHATSAPP_DATABASE_URL` / `DATABASE_URL` | DECLARED |
| Pool defaults | `pool_size=5`, `max_overflow=10` per process (`db/session.py`) | DECLARED |
| Host provider/size | Not exposed via public ready; likely droplet-local or external PG | UNKNOWN / prior audit INFERRED |
| HA / standby | **None observed** for Linas | OBSERVED (no Linas managed PG) |

### Object storage / media

| Item | Status | Class |
|------|--------|-------|
| DigitalOcean Spaces | No Linas Spaces inventory via doctl spaces keys alone; CM/meta media uses `_DATA_ROOT` paths | DECLARED |
| `services/meta_social_media_store.py` | Local disk under `_DATA_ROOT/meta_social_post_media` | DECLARED |

### Firestore

Used for live chat, webhook/AI turn claims, social state (DECLARED + ready ok).

---

## 2. Process topology (DECLARED)

```mermaid
flowchart TB
  Internet([Internet / Meta / Mobile]) --> DNS[linasaibot.com DNS]
  DNS --> Droplet[Single lon1 droplet<br/>2vCPU / 2GB]
  Droplet --> Nginx[nginx TLS terminate]
  Nginx --> API[systemd linasbot<br/>uvicorn / FastAPI main.py]
  API --> FS[(Firestore)]
  API --> LocalDisk[(local _DATA_ROOT<br/>files / media / caches)]
  API --> PG[(Postgres WA/Requests<br/>if configured)]
  API -.->|REDIS_URL set but unreachable| RedisX[Broken Redis endpoint]
  WorkerTpl[linasbot-worker@.service<br/>optional queues] -.-> RedisX
  API --> OpenAI[OpenAI API]
  API --> Meta[Meta Graph API]
```

| Unit | Role |
|------|------|
| `main.py` + FastAPI | API + webhook ingress + much AI/outbound **in-process** |
| `deploy/systemd/linasbot-worker@.service` | Optional Redis queue workers (`high_priority` / `interactive` / `background` / `expensive`) |
| Startup schedulers (`modules/event_handlers.py`) | Smart messaging + Instagram login lifecycle on **API process** |

---

## 3. Request paths (high level)

| Path | Today | Scale risk |
|------|-------|------------|
| Mobile / dashboard API | Stateless-ish FastAPI on one node | Single node CPU/RAM SPOF |
| Meta IG/FB webhooks | Signature → dedupe (memory+Firestore) → processing often **inline** | Horizontal dedupe gaps; latency under burst |
| WhatsApp Cloud | Postgres SoT when enabled | Pool budget if multi-replica |
| AI replies | Often same request path / process; Firestore `ai_turn_claims` | Ordering / duplicate under multi-worker |
| Outbound Meta | In-process + some queue hooks | Provider 429 → need backpressure |
| Requests feature | Postgres outbox pattern (code) | Needs worker separation at scale |
| Live Chat SSE | Process-local broadcaster | Sticky/session affinity or shared pubsub required |
| Rate limit | Redis preferred in prod; file/memory non-prod | Unreachable Redis → fail-closed only when required |

---

## 4. Single points of failure (current)

| SPOF | Impact if lost |
|------|----------------|
| Single lon1 droplet | Full outage (API + webhooks + colocated work) |
| No load balancer | Cannot multi-droplet without DNS cutover |
| Unreachable Redis | No shared rate-limit / durable queue / distributed locks |
| Local `_DATA_ROOT` media & file state | Not shareable across nodes |
| Process-local webhook dedupe / SSE / smart_messaging dicts | Breaks or duplicates under ≥2 API processes |
| Startup schedulers on every API replica | Duplicate cron work without distributed lock |
| Single Firestore project config | Soft SPOF (managed, but no multi-region app strategy) |
| Postgres (non-HA Linas) | Data plane SPOF if on single instance |
| Provider APIs (Meta / OpenAI) | External capacity ceiling (must queue, not crash) |

---

## 5. Capacity verdict (honest)

| Target | Verdict | Why |
|--------|---------|-----|
| ~5,000 concurrent **owner/mobile** users | **FAIL on current topology** | 2 vCPU / 2GB single node; no LB; Redis down; SSE/poll storm risk |
| ~100,000 active customer conversations (queued safely) | **FAIL on current topology** | No reachable durable queue; webhook/AI largely coupled; no measured worker pool |
| Scale by adding compute without rewrite | **NOT READY** until process-local authoritative state removed + queue/workers/readiness/shutdown shipped |

Do **not** claim “supports 100k” until synthetic scenarios A–E pass on a defined topology.

---

## 6. Key evidence paths

- `main.py`, `modules/dashboard_api_health.py`
- `deploy/systemd/linasbot-worker@.service`
- `services/job_queue.py`, `services/queues/*`
- `services/rate_limit_service.py`
- `db/session.py`
- `modules/webhook_handlers_dedupe.py`
- `services/outbound_turn_idempotency.py`
- `services/meta_social_media_store.py`
- `docs/release/PHASE13_PRODUCTION_PREP_REPORT.md`

---

## 7. Scale phase direction (preview)

Target logical services (colocate cheaply at launch, split later):

1. **API** — stateless mobile/dashboard  
2. **Webhook ingress** — validate, claim, enqueue, 200 fast  
3. **AI workers** — ordered per conversation  
4. **Outbound workers** — Meta/WA send + provider limits  
5. **Request/notification workers** — outbox / push  

Shared: Managed Valkey (Linas-dedicated lon1), Postgres with documented pool budget, optional Spaces for media, regional LB for HA topology.
