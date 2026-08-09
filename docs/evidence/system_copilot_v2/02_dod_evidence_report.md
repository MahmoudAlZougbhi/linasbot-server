# System Copilot V2 — Definition of Done & Evidence Report

**Branch:** `feat/system-copilot-v2`  
**Base:** `origin/main` @ `d36c841` (PR #104)  
**Verdict:** **SYSTEM COPILOT V2 IMPLEMENTED (pending prod approval)**  
**STOP:** No production merge/deploy/Meta mutation/App Review in this task.

## §22 / §32 checklist

| Requirement | Status | Evidence |
|-------------|--------|----------|
| One Sol owner brain (`LINAS_OWNER_MODEL=gpt-5.6-sol`) | Done | `services/owner_copilot_v2/flags.py`, `brain.py`, `provider.py` |
| Structured tool calling (not regex-primary finals) | Done | `tool_schemas.py` + Sol tool loop; regex only creative refuse / confirm tokens |
| No `_summarize()` as final UI under V2 | Done | V2 path streams Sol text; legacy `_summarize` only when `OWNER_COPILOT_V2=false` |
| Guest Luna + no 50-word ceiling + 10 Q | Done | `guest_ai_service.py`, `guest_chat_limits.py`, tests |
| Creative cancelled / unreachable | Done | `creative_policy.py`, control drawer, App routes, registry `unavailable` |
| Live Chat read-only | Done | `LiveChatThread.tsx` (composer/takeover removed) |
| Streaming SSE protocol | Done | `POST .../messages/stream`, `stream_protocol.py`, mobile XHR SSE consumer |
| Choices (max 3) | Done | `choices.py`, `ChoiceChips.tsx`, choice API |
| Attachments + price-list vision contract | Done | `attachments.py`, `vision_import.py`; fixture path for CI; live multimodal needs API key |
| Diagnosis read-only / App A | Done | `diagnosis_health.py` (`meta_mutations=false`, `app=A`) |
| Flags / kill switches / shadow writes | Done | `OWNER_COPILOT_V2`, `OWNER_COPILOT_WRITES=false`, `OWNER_COPILOT_META_ACTIONS=false` |
| Capability manifest + CI freshness | Done | `capability_manifest.json`, `scripts/check_copilot_v2_manifest.py` |
| Isolation Guest/Owner/Customer | Preserved | Separate services; no shared memory |
| File size discipline (~400 lines) | Done | line-limit check on V2 + mobile src |

## Automated tests (Python 3.11)

```
python3.11 -m pytest \
  tests/test_owner_copilot_v2.py \
  tests/test_owner_ai_create_post_chat.py \
  tests/test_system_copilot.py \
  tests/test_guest_ai_api.py \
  tests/test_system_copilot_phase2b.py -q
→ 43 passed
```

Manifest: `python3.11 scripts/check_copilot_v2_manifest.py` → OK

## Honest blockers / gaps (not faked)

1. **Live OpenAI streaming/vision smoke** — no `OPENAI_API_KEY` in this agent environment; provider multimodal proof deferred to Mahmoud staging with redacted logs.
2. **Mobile recordings/screenshots (§32 items 1–12)** — require device/simulator run after `npm install` (new `expo-image-picker`, `expo-document-picker`) + rebuild; not captured here.
3. **CM UX deep simplify cherry-pick from PR #105** — not merged; V2 branch is source of truth for chat/setup; CM screens largely unchanged beyond drawer/nav cleanup.
4. **Shadow mode default** — `OWNER_COPILOT_WRITES=false` until Mahmoud enables writes on staging.
5. **Production deploy** — explicitly stopped pending approval.

## Flags for staging enablement (after approval)

```
OWNER_COPILOT_V2=true
OWNER_COPILOT_WRITES=false          # keep until write soak
OWNER_COPILOT_META_ACTIONS=false   # keep permanently for V2 diagnosis
LINAS_OWNER_MODEL=gpt-5.6-sol
LINAS_GUEST_MODEL=gpt-5.6-luna
# optional: LINAS_OWNER_VISION_MODE=multimodal
```

## What was not changed

- SportBook / BOC
- Live Meta disconnect/reconnect/token/webhook
- Destructive deletion of creative historical data (dormant code remains)
- Production env / deploy scripts

## Ask Mahmoud

1. Review this draft PR.
2. Staging soak with writes still off, then enable `OWNER_COPILOT_WRITES` for internal tenants.
3. Capture §32 recordings on device.
4. Explicit approval before production merge/deploy.
