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

There is no isolated DigitalOcean staging cluster in this repository. Do not send the 1,900/min mix to live Meta/TikTok/WhatsApp customers or `www.linasaibot.com`.

CI persist smoke (SQLite, no workers):

`python scripts/loadtest/run_omnichannel_cert.py --ci-smoke`

Isolated local stack (Docker Postgres `:55432` + Redis `:56379`, loopback HTTP ingress, stub AI/provider in the cert worker process only):

```
LINAS_OMNI_CERT_STAGING=1 python scripts/loadtest/omnichannel_live_cert.py --compressed
LINAS_OMNI_CERT_STAGING=1 python scripts/loadtest/omnichannel_live_cert.py --hour --burst --keep-stack
LINAS_OMNI_CERT_STAGING=1 python scripts/loadtest/omnichannel_live_cert.py --soak-segment-seconds 3600 --keep-stack
```

Guards: `LINAS_OMNI_CERT_STAGING=1`, loopback/allowlisted hosts, `omni-cert-` tenant prefix, rate/duration/OpenAI cost caps, reject `www.linasaibot.com` and production provider hostnames.

Conversation order wait (`JobNotReady`) soft-requeues and must not consume DLQ attempts. The cert mix uses unique conversation keys for 90% of events so 1,900/min is not serialized onto 40 keys; 10% share a small pool to exercise ordering.

24-hour soak must be checkpointed segments writing `artifacts/omnichannel-cert/` (gitignored). `LINAS_OMNI_CERT_STAGING=1 python scripts/loadtest/omnichannel_cert_soak.py --segments 24 --segment-seconds 3600 --start-at 0`. Do not run a 24-hour GitHub Actions job without an explicit cost approval.

## Provider capacity (official docs, retrieved 2026-08-26)

Source: [Graph API rate limiting](https://developers.facebook.com/docs/graph-api/overview/rate-limiting/)

- Instagram Messaging Send API (text): 300 calls/second per IG professional account
- Instagram private replies to posts/reels: **750 calls/hour** per IG professional account
- Facebook Page private replies to IG posts/reels: 750 calls/hour per Page
- Instagram Live comment private replies: 100 calls/second

Requested cert mix includes 200 Instagram comments/minute = 12,000/hour inbound. Official private-reply quota is 750/hour (~12.5/min). That backlog is not fixable by adding API nodes. Do not claim a 60-second comment SLA against that quota.

TikTok Display API publishes 600 requests/minute per listed read endpoint ([TikTok API v2 rate limit](https://developers.tiktok.com/doc/tiktok-api-v2-rate-limit?enter_method=left_navigation)). Business comment-reply QPS is account/app specific; honor `429` / `Retry-After` / `X-TT-logid`. Content Posting is 6 requests/minute per user token and is a different product.

OpenAI volume at 1,900 replies/minute must use the cert stub. Real OpenAI calibration is a separate low-volume run and needs an authorized budget before exceeding $5 estimated cost (`MAX_ESTIMATED_OPENAI_USD`).
