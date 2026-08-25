# Omnichannel reliability

Logical flow for every channel:

`Webhook/HTTP → authenticate → durable inbound ledger → queue → AI generate → persist canonical reply → provider outbox → distributed limiter → send → reconcile`

Physical HA workers stay `high_priority`, `interactive`, `background`, `expensive`.

| Logical class | Physical worker |
| --- | --- |
| dm_urgent, outbound_dm, outbound_whatsapp, web_chat | high_priority |
| comments, outbound_comment, outbound_tiktok, reconcile_dlq, polling | background |
| owner_interactive | interactive |
| creative | expensive |

PostgreSQL is source of truth. Redis/Valkey is queues, leases, and rate limits only.

Alembic head: `20260826_omnichannel_rel`.

## Gates that stay fail-closed

- TikTok DMs: pending TikTok Business Messaging permission. Code may enqueue; send is gated.
- WhatsApp public onboarding: pending Meta Advanced Access. `PUBLIC_AVAILABILITY` stays off.

## Honest load certification

`scripts/loadtest/run_omnichannel_cert.py --ci-smoke` proves durable persist, idempotency, queue split, and 429 classification with mocked providers.

Full 60-minute baseline, 10-minute 2× burst, node/worker kill, and 24-hour soak must run on isolated staging. Do not send the 1,900/min mix to live Meta/TikTok/WhatsApp customers.
