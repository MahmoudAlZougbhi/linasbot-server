# Pre-deployment environment checklist (redacted)

Do **not** paste secret values into tickets, chat, commits, or logs. Mark each item configured / verified only.

## Required security (production fail-closed)

| Variable | Purpose | Production rule |
|----------|---------|-----------------|
| `DASHBOARD_AUTH_SECRET` | Session cookie HMAC signing | Must be set; long random; **never** generate per-process restart |
| `ENVIRONMENT` / `ENV` | `production` / `prod` | Enables fail-closed auth + readiness checks |
| `MONTYMOBILE_API_KEY` | WhatsApp outbound via MontyMobile | Required when provider is montymobile |
| `OPENAI_API_KEY` | LLM | Required; readiness checks presence only |

## First admin (empty DB)

No public HTTP bootstrap. Use offline CLI only:

`python scripts/provision_dashboard_admin.py --email … --prompt-password`

Optional: `PROVISION_ADMIN_PASSWORD` env (never argv, never tracked files).

No known/default passwords. Existing dashboard users keep hashes; `passwordEpoch` invalidates old sessions after password change.

## Session / CSRF / cookies

| Variable | Notes |
|----------|-------|
| `DASHBOARD_SESSION_TTL_SECONDS` | Default 12h |
| `DASHBOARD_COOKIE_SECURE` | Production should be true (or inferred) |
| `DASHBOARD_COOKIE_SAMESITE` | `lax` default; `none` requires Secure (WebView) |

## Meta / WhatsApp webhooks (names only)

| Variable / config | Notes |
|-------------------|-------|
| Meta App webhook verify token + app secret | Signature verification must remain enabled |
| WhatsApp / MontyMobile webhook auth | Inbound path authenticated as implemented |
| WhatsApp inbound AI | **Must remain disabled** (product contract) |

## Readiness

After deploy: `GET /api/ready` must return `ok: true` with boolean checks only (no secret values).  
`GET /api/health` is liveness only.

## Explicit non-goals

- Do not rotate production secrets in this closure work without a separate owner-approved rotation plan.
- Do not run Live Chat index backfill against production without approval (`scripts/backfill_live_chat_index.py`).
