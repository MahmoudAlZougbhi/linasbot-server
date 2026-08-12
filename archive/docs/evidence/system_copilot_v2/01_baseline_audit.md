# System Copilot V2 — Baseline Audit (pre-edit)

**Branch:** `feat/system-copilot-v2`  
**Audit time:** 2026-08-10  
**origin/main SHA:** `d36c8410ec80633121a18923086f80d4fdb6e27f` (Merge PR #104 — gpt-5.6 models)  
**Working tree SHA at audit start:** same as origin/main  
**Deployed SHA:** not verified from this workstation (no live prod SSH in this task). Treat repo main ≠ proven deployed until ops confirms.

## Call graph (Owner)

```
mobile ChatScreen / useChatSession
  → POST /api/owner-ai/conversations/{id}/messages  (modules/owner_ai_api.py)
  → owner_chat_store.append_message
  → run_owner_turn (services/owner_ai_orchestrator.py)
       ├─ pack_owner_turn_context (owner_ai_context.py) — fixed 8×600 chars
       ├─ regex _INTENT_PATTERNS (primary semantic router — forbidden for V2 finals)
       ├─ route_owner_turn (owner_ai_model_router.py) — splits owner_help (luna) / CM (sol) / creative
       ├─ help/unmatched → generate_owner_conversational_reply (luna, max_tokens=360)
       └─ else → dispatch_tool → _summarize() as final UI reply  ← V2 forbids this
```

## Call graph (Guest)

```
useGuestChatSession → guest API → compose_guest_reply (guest_ai_service.py)
  DEFAULT_GUEST_MODEL=gpt-4o-mini (env LINAS_GUEST_MODEL)
  GUEST_MAX_WORDS=50, GUEST_MAX_QUESTIONS=10
  No tools; knowledge via retrieve_capabilities
```

## Call graph (Customer)

```
Meta webhook → chat_response_service / CM runtime
  High-volume path: LINAS_CUSTOMER_HV_MODEL default gpt-5.6-luna
  Must stay isolated from owner chat history/tools
```

## Effective models (repo defaults; secrets redacted)

| Surface | Env key | Default on main |
|---------|---------|-----------------|
| Owner help | `LINAS_OWNER_HELP_MODEL` | `gpt-5.6-luna` |
| Owner CM | `LINAS_OWNER_CM_MODEL` | `gpt-5.6-sol` |
| Creative | `LINAS_CREATIVE_MODEL` | `gpt-5.6-sol` |
| Customer HV | `LINAS_CUSTOMER_HV_MODEL` | `gpt-5.6-luna` |
| Guest | `LINAS_GUEST_MODEL` | `gpt-4o-mini` |
| Unified owner (V2 target) | `LINAS_OWNER_MODEL` | **missing** |

Production overrides for `LINAS_*_MODEL` were not readable from this environment.

## Prompts / routing / caps

- Owner system prompt: `services/owner_ai_context.py` `SYSTEM_PROMPT`
- Guest system prompt: `services/guest_ai_service.py` `build_guest_system_prompt` (sales-oriented)
- Regex intents: `services/owner_ai_orchestrator.py` `_INTENT_PATTERNS`
- Final UI templates: `_summarize()` in orchestrator (hardcoded strings)
- Owner conversational cap: `max_tokens=360`
- Guest cap: `max_tokens=320`
- Context: `MAX_RECENT_MESSAGES=8`, `MAX_MESSAGE_CHARS=600`
- Silent model downgrade risk: guest default `gpt-4o-mini`; no per-turn mini fallback on owner help path (raises `OwnerAIModelError`)

## Creative paths (to disable)

- Tools: `create_creative_draft`, `schedule_creative_draft` (`owner_ai_tools_creative.py`)
- Registry: `creative_studio`, `scheduled_posts` (`system_knowledge_registry.py`)
- Mobile: `controlAreas` `create`/`scheduled`, `CreatePostTaskChips`, `CreativeDraftCard`, `ComposerPlusSheet` create_post, ChatScreen create-post mode
- Dashboard Creative Studio screen: `mobile/linas-ai/src/features/creative/CreativeStudioScreen.tsx`

## Canonical CM store

- `services/cm/` (draft/live revisions, publish, sections) — keep as SoT
- Owner CM patches: propose → approve via `owner_ai_cm_approval.py`
- No duplicate setup store discovered for V2; first-run must write same CM draft

## Meta / App A

- App A remains only Meta app for Linas AI social; multi-app registry tests exist under `tests/test_meta_*`
- V2 diagnosis must be **read-only**; no live disconnect/reconnect/token reset/webhook mutation in this branch

## Automated test baseline (Python 3.11)

```
python3.11 -m pytest tests/test_system_copilot.py tests/test_guest_ai_api.py -q
→ 17 passed
```

Related: `tests/test_system_copilot_phase2b.py`, `tests/test_owner_ai_create_post_chat.py`

## Gaps vs V2 product (binding)

1. Split brain (luna help + sol CM + regex + `_summarize`) — not one Sol planner/writer  
2. No true SSE/streaming owner protocol  
3. No in-chat choices protocol  
4. No multimodal attachments / price-list vision import  
5. Creative still active  
6. Live Chat still has composer + takeover  
7. Guest 50-word ceiling + mini default + salesy tone  
8. Memory fixed 8×600, not token-aware  
9. Capability registry keyword-only; creative still listed  
10. No `OWNER_COPILOT_V2` / write / Meta kill switches  

## Isolation status

Guest / Owner / Customer paths are separate modules today; V2 must keep that isolation while upgrading Owner+Guest.
