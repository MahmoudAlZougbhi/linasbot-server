# Mobile scale notes (5k owners)

**Date:** 2026-08-12

## Risks on current clients

- Synchronized polling after reconnect can stampede a single API node.
- Live Chat SSE is process-local (`live_chat_sse_broadcaster`) — needs sticky sessions or Redis pubsub before multi-API.
- Dashboard/Requests list refresh must stay paginated with jittered backoff.

## Mitigations (server-side this phase)

- Graceful drain → readiness 503 so clients backoff instead of hammering a dying node.
- Rate-limit Redis path (once Valkey live) for auth/refresh.
- Scenario A synthetic passed locally at 100→5000 concurrent session-shaped work (not live droplet proof).

## Client follow-ups (preserve behavior; incremental)

- Jitter reconnect (already preferred in mobile networkError patterns).
- Bound reconnect loops on 503/drain.
- Prefer push/SSE over tight polling where product already supports it.
- Conditional refresh / ETag-style where present.

Do not invent a claim that production currently serves 5k owners.
