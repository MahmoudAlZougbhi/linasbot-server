# Non-horizontal state inventory + fixes

**Date:** 2026-08-12

| Path / symbol | Class | Priority | Action |
|---------------|-------|----------|--------|
| `modules/webhook_handlers_dedupe.py` memory mid/bodyfp caches | MOVE_TO_REDIS | P0 | **Fixed:** Redis claim first via `services/scale/redis_claims.py`; memory remains same-process assist |
| `services/durable_event_claim.try_acquire_job_lock` | MOVE_TO_REDIS | P0 | **Fixed:** Redis claim preferred; file fallback for local/dev |
| `services/job_queue.py` file backend | REMOVE for prod scale | P0 | Redis path exists; require `LINAS_REQUIRE_REDIS` at activation (no silent prod fallback invention) |
| `services/rate_limit_service.py` | ALREADY_DISTRIBUTED (redis) | P0 | Keep fail-closed; needs reachable Valkey |
| `services/queues/redis_backend.py` | ALREADY_DISTRIBUTED | — | Reused via `DurableQueue` protocol |
| `services/outbound_turn_idempotency.py` | ALREADY_DISTRIBUTED (Firestore) | — | Keep |
| `services/live_chat_sse_broadcaster.py` | MOVE_TO_REDIS (pubsub) later | P1 | Sticky LB or Redis pubsub before multi-API live chat |
| `services/smart_messaging*.py` scheduled_messages dict | MOVE_TO_REDIS/POSTGRES | P1 | Scheduler already job-locked; deepen persistence next |
| `services/meta_social_media_store.py` local disk | MOVE_TO_OBJECT_STORAGE | P1 | Spaces purchase if multi-node media required |
| `services/mobile_refresh_token_service.py` file-backed | MOVE_TO_REDIS/POSTGRES | P1 | Multi-API auth |
| `services/auth_email_tokens.py` file-backed | MOVE_TO_REDIS/POSTGRES | P2 | |
| `services/smart_retrieval_service._TITLES_CACHE` | SAFE_LOCAL_CACHE | — | TTL cache |
| `services/live_chat_service` caches | SAFE_LOCAL_CACHE | — | TTL; not authoritative |
| Startup schedulers `event_handlers` | SINGLETON_JOB_NEEDS_DISTRIBUTED_LOCK | P0 | **Fixed** via Redis job locks |

## Horizontal scale code added

- `services/scale/*` — queue protocol, Redis adapter, conversation lock, distributed lock, provider limiter, shutdown, readiness roles, redis claims, metrics  
- Worker drain + conversation lock + provider gate in `services/queues/worker_runtime.py`  
- `/api/scale/metrics`, `/api/scale/ready`  
- Load harness `scripts/loadtest/run_scale_scenarios.py` scenarios A–E
