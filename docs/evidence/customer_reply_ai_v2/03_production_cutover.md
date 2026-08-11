# Customer Reply AI V2 — Production Cutover Evidence

**Branch:** `feat/customer-reply-v2-production`  
**Base:** `origin/main` @ `28ea5fa`  
**Verdict:** **CODE COMPLETE for V2 as sole IG/FB customer generative engine** (deploy/live Meta verification tracked separately)

## Architecture (production)

```
DM: webhook → gates → run_customer_reply_v2_dm
  → customer facts + rolling 3h window
  → restricted/handoff (server) → FAQ fast path
  → Retrieval Luna (gpt-5.6-luna, max 2 rounds, published CM tools)
  → Answer Tera (gpt-5.6-terra, reasoning_effort=medium, full AI Basics+Style+Languages)
  → validate → one Tera Medium repair → safe failure (never Classic)

Comment: shared Comment Context Builder (IG+FB Graph)
  → caption/parent/thread/media_status + bounded visual inputs
  → same Retrieval Luna + Answer Tera + one repair
```

## Model routing

| Stage | Model | Effort |
|-------|-------|--------|
| Retrieval | `gpt-5.6-luna` | `none` |
| Final answer + repair | `gpt-5.6-terra` | `medium` |

Fail closed on misconfiguration. No silent substitute. No Classic generative fallback.

## Removed

- `CUSTOMER_REPLY_AI_V2` / `CUSTOMER_REPLY_AI_V2_LIVE` shadow switches
- Classic `generate_answer_with_usage` from live IG/FB DM + comment CM handlers
- Answer-path Luna / retrieval-path Terra (roles were inverted vs policy)

## Preserved

- Owner Copilot V2
- Guest AI routing
- Binding / App A / plan / comment asset switches / published CM / restricted / handoff / idempotency
- WhatsApp inbound AI disabled; App B comments unsupported

## Honest blockers for full production DoD

1. Production deploy of merged SHA
2. Controlled live IG/FB DM + comment verification on Meta assets
3. Telemetry confirmation in prod logs (Luna retrieval + Tera medium)
4. TestFlight after healthy prod
