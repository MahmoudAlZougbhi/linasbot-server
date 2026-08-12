# Customer Reply AI V2 — Definition of Done & Evidence Report

**Branch:** `feat/system-copilot-v2` (same PR #106 as System Copilot / Owner V2)  
**Verdict:** **CUSTOMER REPLY AI V2 IMPLEMENTED (pending prod approval)**  
**STOP:** No production merge/deploy. No Meta disconnect/token/webhook/Page/App Review mutations. No synthetic replies to real customers.

## Architecture (after)

```
DM: webhook → dedupe → tenant → customer facts → rolling 3h window
  → restricted/handoff (server) → Published FAQ fast path
  → Retrieval Luna (gpt-5.6-luna, max 2 rounds, typed read-only tools)
  → Answer Luna (gpt-5.6-luna, full AI Basics+Style + evidence, no tools)
  → validate → (shadow: keep classic CM reply) or (live: send V2 reply) → TRACE

Comment: separate context (caption/parent/media cache); no DM window mix
```

## Flags (shadow-first)

| Flag | Default | Role |
|------|---------|------|
| `CUSTOMER_REPLY_AI_V2` | `false` | Master switch |
| `CUSTOMER_REPLY_AI_V2_LIVE` | `false` | When false with V2 on: shadow plan; classic reply still sent |
| `CUSTOMER_SEMANTIC_RETRIEVAL_ENABLED` | on when V2 on | Hierarchical Retrieval Luna |
| `CUSTOMER_MEDIA_CONTEXT_ENABLED` | `false` | Comment image/carousel/video cache |
| `LINAS_CUSTOMER_MODEL` | `gpt-5.6-luna` | Both roles; no mini fallback |
| `MAX_CUSTOMER_RETRIEVAL_ROUNDS` | `2` | Server-enforced |
| `CUSTOMER_DM_CONTEXT_WINDOW_HOURS` | `3` | Rolling time window |

## Files changed (purpose)

| Path | Purpose |
|------|---------|
| `services/customer_reply_v2/*` | New V2 package (flags, manifest, window, facts, tools, Retrieval/Answer Luna, orchestrator, comment runtime, media, policy, observability) |
| `handlers/text_handlers_respond.py` | Wire V2 into published CM DM path (shadow/live) |
| `services/meta_comment_replies.py` | Wire V2 comment path |
| `.env.example` | Document new flags |
| `tests/test_customer_reply_ai_v2.py` | Fixture coverage |
| `docs/evidence/customer_reply_ai_v2/*` | Audit + DoD |

## Proof checklist (§21–24)

| Requirement | Evidence |
|-------------|----------|
| Separate Retrieval + Answer Luna calls/roles | `retrieval_luna.py` / `answer_luna.py`; tests assert both request `gpt-5.6-luna` |
| Full AI Basics/Style only on Answer | Manifest marks fixed; Answer messages include bodies; Retrieval manifest has no bodies |
| Max 2 rounds; 3rd refused server-side | `dispatch_retrieval_tool` + tests |
| No authoritative fixed top-2 | `authoritative_selector=retrieval_luna` in metadata |
| Rolling 3h window; >20 msgs; no 600 truncate | `test_rolling_three_hour_window_boundaries` |
| Name correction / gender explicit / language | `customer_facts.py` tests |
| FAQ context-dependent skip | `قديش هيدا؟` → miss |
| Comment toggle off / video cache / no DM mix | comment tests |
| Tenant isolation / path rejection / stale rev | retrieval tool tests |
| App B unreachable / WA inbound off | source invariants test |
| Published only | `load_published_content` / draft IDs rejected |
| Validation failure not sent | repair + safe fallback test |

## Automated tests

```
python3.11 -m pytest tests/test_customer_reply_ai_v2.py -q
→ 13 passed

python3.11 -m pytest tests/test_customer_reply_ai_v2.py \
  tests/test_cm_runtime_pipeline.py tests/test_cm_handler_integration.py \
  tests/test_meta_comment_replies.py -q
→ 39 passed
```

## Schema / migrations

No DB schema migration. Persistent customer facts + media cache stored under  
`{LINASBOT_DATA_ROOT}/tenants/{tenant}/customer_reply_v2/`.

## Rollback

1. Set `CUSTOMER_REPLY_AI_V2=false` (instant revert to classic published CM pipeline).  
2. Or keep V2 on with `CUSTOMER_REPLY_AI_V2_LIVE=false` (shadow only).  
3. Owner Copilot V2 flags unchanged.

## Honest blockers

1. **Live OpenAI smoke** — no `OPENAI_API_KEY` in this agent environment; Retrieval/Answer live tool-call smoke deferred to staging with redacted logs.  
2. **Live Meta media frame extraction** — cache API + fixtures shipped; production Graph media download/frame extract not enabled (requires Mahmoud approval + `CUSTOMER_MEDIA_CONTEXT_ENABLED`).  
3. **Production deploy / LIVE send** — explicitly stopped; defaults keep classic customer-visible replies.  
4. **Shadow dual-compare metrics dashboard** — structured safe traces emitted; ops dashboard wiring not in this change.

## What was not changed

- SportBook / BOC  
- Owner Copilot V2 architecture  
- Live Meta tokens/webhooks/Page subscriptions/App Review  
- WhatsApp inbound AI (remains disabled)  
- Creative providers / Live Chat takeover send tools  

## Ask Mahmoud

1. Review Customer Reply V2 commits on PR #106.  
2. Staging: `CUSTOMER_REPLY_AI_V2=true` + `CUSTOMER_REPLY_AI_V2_LIVE=false` shadow soak.  
3. Internal test assets only before `CUSTOMER_REPLY_AI_V2_LIVE=true`.  
4. Explicit approval before production merge/deploy.
