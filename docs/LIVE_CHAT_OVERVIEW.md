# Live Chat Overview (Backend)

Single-page map of the live chat backend so you can jump to the right spot quickly without hunting across files. The real-time channel stays SSE-only; initial data comes from APIs / Firestore.

## Core runtime code
- `services/live_chat_service.py` — canonical conversation logic, index sync/backfill helpers, inbox/waiting-queue, metrics, takeover/release/send/end, FAQ context.
- `services/live_chat_contracts.py` — normalization helpers (conversation/message shape, canonical `conversation_state`, timestamps, unread counts, dedupe).
- `services/live_chat_sse_broadcaster.py` — SSE hub with heartbeat, queue backpressure, and optional initial payload (realtime-only, not the primary data source).
- `modules/live_chat_api.py` — FastAPI endpoints for inbox/unified-chats, active, waiting, details/history, actions (takeover/release/send/edit/end), metrics, FAQ context, debug Firestore, rebuild index.
- `routes/live_chat_routes.py` — wiring for live chat routes (framework binding/shims).

## Supporting scripts / tooling
- `scripts/backfill_live_chat_index.py` — safe manual rebuild/backfill of `live_chat_index` (supports dry-run, limits, optional state backfill; never overwrites valid `conversation_state`).
- API debug endpoint: `POST /api/live-chat/rebuild-index` (calls `rebuild_index_from_firestore`).

## Data + storage touchpoints
- Firestore: `artifacts/{APP_ID}/users/{user_id}/conversations/*` is source of truth; `artifacts/{APP_ID}/live_chat_index` is the projection/inbox.
- `conversation_state` is derived canonically; backfill only fills missing values, never downgrades existing ones.

## Behavior guardrails
- SSE is realtime-only (not for initial dashboard data).
- Index rebuild/backfill: safe, non-destructive; fills missing states only; logs written/repaired/skipped counts.
- Heartbeats and queue dropping prevent slow clients from blocking SSE.

## Related docs (already in repo)
- `docs/LIVE_CHAT_API_CONTRACT.md` — baseline API contract.
- `docs/LIVE_CHAT_REALTIME.md` — SSE behavior.
- `docs/LIVE_CHAT_REFACTOR_ROLLOUT.md` — rollout notes.
- `docs/LIVE_CHAT_PERFORMANCE_FIXES.md`, `docs/LIVE_CHAT_FAQ_CORRECTION_WORKFLOW.md`, `docs/LIVE_CHAT_IDENTITY_VERIFICATION.md` — workflows/perf/identity specifics.

## Quick navigation (common tasks)
- Rebuild index safely: `python -m scripts.backfill_live_chat_index --dry-run` then run without `--dry-run` if it looks good.
- Inspect realtime channel: `services/live_chat_sse_broadcaster.py`.
- Update API behavior: `modules/live_chat_api.py` (keep SSE for realtime; APIs for initial data).
- Adjust canonical state/normalization: `services/live_chat_contracts.py` and `_normalize_conversation_state` in `services/live_chat_service.py`.
