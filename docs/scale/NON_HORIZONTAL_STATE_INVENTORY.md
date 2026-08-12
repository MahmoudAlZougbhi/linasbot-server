# Non-horizontal state inventory + fixes

**Date:** 2026-08-12  
**Updated after:** [Non-horizontal state scan](0f7b246e-9de9-46b9-9f94-11f9758101f7), [Queue worker architecture scan](1c061648-d6bc-4441-bb23-4c17d974bc06)

| Path / symbol | Class | Priority | Action |
|---------------|-------|----------|--------|
| `modules/webhook_handlers_dedupe.py` memory mid/bodyfp caches | MOVE_TO_REDIS | P0 | **Fixed:** Redis claim first via `services/scale/redis_claims.py` |
| `services/durable_event_claim.try_acquire_job_lock` | MOVE_TO_REDIS | P0 | **Fixed:** Redis claim preferred; file fallback for local/dev |
| `modules/event_handlers_scheduler.daily_refresh_messages_job` | SINGLETON_JOB_NEEDS_DISTRIBUTED_LOCK | P0 | **Fixed:** was unlocked; now uses `try_acquire_job_lock` |
| Dispatcher / monitor / follow-up scheduler jobs | SINGLETON_JOB_NEEDS_DISTRIBUTED_LOCK | P0 | **Fixed:** Redis-preferred job locks |
| `services/job_queue.py` file backend | REMOVE for prod scale | P0 | Redis path exists; activate with Valkey + `LINAS_REQUIRE_REDIS` |
| `services/rate_limit_service.py` | ALREADY_DISTRIBUTED (redis) | P0 | Needs reachable Linas Valkey |
| Meta IG/FB AI via `asyncio.create_task` (no Redis enqueue) | MOVE_TO_REDIS queue | P0 | **Fixed path:** durable ledger persist before ACK; Redis enqueue when `job_queue` production-ready; else local delivery of persisted record; reconcile watchdog |
| WA Cloud webhook awaits AI+send inline | MOVE_TO_REDIS queue | P0 | **Inbound durable in Postgres** (`whatsapp_webhook_events` + messages before AI); AI/outbound async split residual post-Valkey |
| Requests `process_pending_outbox` inline on API | MOVE_TO_REDIS / request worker | P0 | **Residual — post-Valkey wave** |
| `config.py` `user_*` conversation dicts | MOVE_TO_REDIS | P0 | **Residual** (combine buffer / takeover / booking FSM) |
| `handlers/text_handlers_*` delayed combine registries | MOVE_TO_REDIS | P0 | **Residual** |
| `services/whatsapp_adapters/outbound_text_dedupe.py` in-memory | MOVE_TO_REDIS / enable FS dedupe | P0 | **Residual** |
| Token wallet / credit ledger / entitlements JSON | MOVE_TO_POSTGRES | P0 | **Residual — needs owner schema approval** |
| Stripe / admin-credit file idempotency | MOVE_TO_POSTGRES / REDIS | P0 | **Residual** |
| Smart messaging file queue + in-memory dict | MOVE_TO_POSTGRES / Redis | P0 | **Residual** (locks only prevent double cron ticks) |
| Guest/session/mobile refresh/email token files | MOVE_TO_REDIS / POSTGRES | P0–P1 | **Residual** |
| `services/outbound_turn_idempotency.py` | ALREADY_DISTRIBUTED (Firestore) | — | Keep |
| Meta durable `try_claim_event` | ALREADY_DISTRIBUTED | — | Keep |
| Requests Postgres outbox / WA pause | ALREADY_DISTRIBUTED | — | Keep |
| `services/live_chat_sse_broadcaster.py` | MOVE_TO_REDIS pubsub | P1 | Sticky LB or Redis pubsub |
| `services/meta_social_media_store.py` local disk | MOVE_TO_OBJECT_STORAGE | P1 | Spaces if multi-node media |
| Live Chat / retrieval TTL caches | SAFE_LOCAL_CACHE | — | OK |

## Horizontal scale code added (this phase)

- `services/scale/*` — queue protocol, Redis adapter, conversation lock, distributed lock, provider limiter, shutdown, readiness, redis claims, metrics  
- Worker drain + conversation lock + provider gate  
- `/api/scale/metrics`, `/api/scale/ready`  
- Load harness A–E  

## Next wave (after Valkey purchase — do not invent silent fallbacks)

1. Wire Meta/WA ingress → durable `high_priority` enqueue (no GPT in webhook).  
2. AI + outbound worker handlers.  
3. Requests outbox worker.  
4. Redis-backed `config.user_*` / combine / outbound dedupe.  
5. Owner-approved Postgres for wallets/entitlements/sessions.
