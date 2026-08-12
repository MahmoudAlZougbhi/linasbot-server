# Customer Reply AI V2 — Baseline Audit

**Branch:** `feat/system-copilot-v2`  
**Baseline SHA (pre Customer Reply V2 commits):** `85dc62dd73d572ade8e1463e2be93b6de7d6fe41`  
**Scope:** Linas AI only · IG/FB DMs + comments · Published CM only

## Call graph (pre-V2)

```
Meta webhook → dedupe → tenant binding
  → handlers/text_handlers_respond._handle_published_cm_runtime
       → services/cm/runtime_pipeline.prepare_response
            restricted → handoff regex → FAQ → interpreter → semantic top-2 knowledge/care packet
       → services/cm/answer_generation (single gpt-5.6-luna call)
       → finalize_response → Meta send → TRACE
Comments: services/meta_comment_replies (same CM prepare; no media context)
```

## Findings

| Area | Baseline |
|------|----------|
| Model | Single Answer Luna `gpt-5.6-luna`; no Retrieval Luna |
| History | CM path unused history; legacy 12h window |
| Top-2 | Semantic knowledge/care `top_k=2` authoritative after FAQ miss |
| Facts | Display name yes; explicit name correction / gender persistence weak on social CM path |
| Media | Comment media_id present; not sent to model |
| Flags | No `CUSTOMER_REPLY_AI_V2*` |
| App A/B | Comments App A only; App B `app_b_not_supported` |
| WhatsApp inbound AI | Disabled (`whatsapp_inbound_ai_disabled`) |
| Published/Draft | Runtime loads published only via `load_published_content` |

## Owner Copilot V2 preserved

Customer V2 is an **additional** package (`services/customer_reply_v2/`) beside `services/owner_copilot_v2/`. No Owner/Guest architecture restart.
