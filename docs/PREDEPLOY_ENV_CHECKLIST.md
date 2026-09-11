# Pre-deployment environment checklist (redacted)

Do **not** paste secret values into tickets, chat, commits, or logs. Mark each item configured / verified only.

## Required security (production fail-closed)

| Variable | Purpose | Production rule |
|----------|---------|-----------------|
| `DASHBOARD_AUTH_SECRET` | Session cookie HMAC signing | Must be set; long random; **never** generate per-process restart |
| `ENVIRONMENT` / `ENV` | `production` / `prod` | Enables fail-closed auth + readiness checks |
| `WHATSAPP_API_TOKEN` | WhatsApp Cloud outbound | Required for Meta Cloud template/session send |
| `OPENAI_API_KEY` | LLM | Required; readiness checks presence only |
| `VOYAGE_API_KEY` | Customer Brain embed/rerank | Required before enabling Customer Brain semantic search; never reuse the OpenAI key |
| `MESSAGE_BILLING_ENABLED` | Message ledger gate | Default off. Keep credit gates until cutover is approved |
| `MESSAGE_BILLING_CUTOVER` | Public/checkout message offer | Default off. Do not sell unmapped message prices |
| `FREE_PLAN_ENFORCEMENT_ENABLED` | Free slot/content caps | Default off until section-2 Free values exist |
| `LINAS_CUSTOMER_AI_LAB` | Isolated Brain lab API | Default off. Capture-only; lab / lab_* tenants only |

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
| WhatsApp Cloud webhook auth | Inbound path authenticated as implemented |
| WhatsApp inbound AI | **Must remain disabled** (product contract) |

## Readiness

After deploy: `GET /api/ready` must return `ok: true` with boolean checks only (no secret values).  
`GET /api/health` is liveness only.

BOC / LinasLaser Agent booking (`LINASLASER_BOC_BOOKING_ENABLED`) defaults **off**. When off, readiness must not require BOC token or booking IDs (`checks.boc_booking`). See `docs/requests/BOC_FUTURE_INTEGRATION.md`. Do not enable BOC in production without owner approval.

## Explicit non-goals

- Do not rotate production secrets in this closure work without a separate owner-approved rotation plan.
- Do not run Live Chat index backfill against production without approval (`scripts/backfill_live_chat_index.py`).
