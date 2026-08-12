# Distributed rate limiting (Redis)

Shared rate limiting for auth and sensitive routes lives in
`services/rate_limit_service.py`, wired through `services/auth_rate_limits.py`
(`check_rate_limit` / `auth_rate_limit_rules`) and direct `hit()` callers
(e.g. guest AI).

## Backends

| `RATE_LIMIT_BACKEND` | Behavior |
| --- | --- |
| `redis` | Sliding window via Redis sorted sets (shared across workers/instances) |
| `file` | Per-process JSON files under data root (legacy / non-prod default) |
| `memory` | In-process dict only (dev/test) |

**Selection rules**

- If `RATE_LIMIT_BACKEND` is set to `redis` / `file` / `memory`, that value is used.
- If unset and `ENVIRONMENT` / `ENV` / `APP_ENV` is `prod` or `production` → **`redis`**.
- If unset and non-production → **`file`** (previous behavior).

Production **never** silently falls back from Redis to file/memory when Redis is
required but unavailable.

## Redis URL

Resolved in order:

1. `RATE_LIMIT_REDIS_URL`
2. `REDIS_URL`
3. `LINAS_REDIS_URL`

Optional: `RATE_LIMIT_KEY_PREFIX` (default `linas:rl`),
`RATE_LIMIT_UNAVAILABLE_RETRY_AFTER` (default `60`).

## Unavailable Redis (fail-closed)

When the active backend is Redis and the client/URL is missing or Redis errors:

- The miss is **logged** at error level (`rate_limit fail-closed: ...`).
- `hit()` returns `(False, retry_after)` and sets `last_deny_reason = "backend_unavailable"`.
- `check_rate_limit` maps that to **HTTP 503** with `Retry-After` (not a silent allow, and not a silent file backend).
- Direct `hit()` callers (guest AI) also deny the request (typically as 429 via their own handler).

## API surface

```python
from services.rate_limit_service import rate_limit_service

allowed, retry_after = rate_limit_service.hit(
    "login:1.2.3.4",
    limit=10,
    window_seconds=300,
)
# allowed: bool
# retry_after: seconds until a slot may free (0 when allowed)
```

Covered routes (via existing rule wiring): login / refresh / reset / verify /
resend / register / forgot / change-password / guest-ai / sensitive mutation
prefixes.

## Production Redis status

**This repository change does not provision, deploy, or activate production Redis.**
Operators must set `RATE_LIMIT_BACKEND=redis` (or rely on production default) and a
reachable Redis URL in the live environment before multi-worker rate limits are
effective in prod. Until then, production with Redis unset/down will **fail closed**
on rate-limited routes (503 / deny), not fall back to file-only.
