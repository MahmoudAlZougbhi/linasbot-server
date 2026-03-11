# AI Smart Employee Bot – Implementation Plan

This document maps the **AI Smart Employee Architecture Plan** to the Lina's AI Bot codebase and provides a concrete implementation roadmap.

---

## Canonical State Structure

The conversation state should include these fields explicitly:

| Field | Type | Description |
|-------|------|-------------|
| `gender` | `"unknown" \| "male" \| "female"` | User's gender for service guidance |
| `awaiting_gender` | `bool` | Bot asked for gender; waiting for user answer |
| `awaiting_clarification` | `bool` | Bot asked for clarification; waiting for user answer |
| `awaiting_name` | `bool` | Bot asked for name; waiting for user answer |
| `original_question` | `str \| None` | Saved when flow interrupted by gender/clarification/name |
| `clarification_target` | `str \| None` | e.g. `"pricing_service"`, `"booking_details"` |
| `selected_service` | `str \| None` | Detected or user-specified service |
| `last_bot_question_type` | `str \| None` | `"gender"`, `"clarification"`, `"name"` |
| `human_handover_active` | `bool` | Conversation in human takeover; no normal support |

---

## Current State vs. Target Architecture

### State Management

| Plan State | Current Implementation | Location | Gap |
|------------|------------------------|----------|-----|
| `gender` | `config.user_gender` + `user_greeting_stage` | `config.py`, `text_handlers_respond.py` | ✅ Exists. Consolidate to single `gender` state. |
| `awaiting_gender` | Implicit (inferred from `greeting_stage` + `gender`) | — | ❌ Add explicit flag. Priority order depends on it. |
| `awaiting_clarification` | `pending_clarification_query` (truthy = awaiting) | `user_data` | ⚠️ Implicit. Add explicit `awaiting_clarification` flag. |
| `awaiting_name` | `awaiting_name_input` | `user_data` | ✅ Exists. |
| `original_question` | `initial_user_query_to_process` (gender) + `pending_clarification_query` (clarification) | `user_data` | ⚠️ Split. Unify as `original_question` + `what_interrupted`. |
| `human_handover_active` | `user_in_human_takeover_mode` + Firestore | `config.py`, Firestore | ✅ Exists. |
| `clarification_target` | None | — | ❌ Add. |
| `selected_service` | None | — | ❌ Add. |
| `last_bot_question_type` | None | — | ❌ Add. |

### Actions

| Plan Action | Current Implementation | Gap |
|-------------|------------------------|-----|
| `greeting` | Implicit in GPT response | ⚠️ No explicit routing. GPT decides. |
| `ask_gender` | `ask_gender`, `initial_greet_and_ask_gender` | ✅ Exists. |
| `ask_clarification` | Dynamic retrieval `ask_clarification` + GPT | ⚠️ Selector decides; no code-level router. |
| `answer_question` | `answer_question`, `provide_info`, etc. | ✅ Exists. |
| `human_handover` | `human_handover`, `human_handover_confirmed` | ✅ Exists. |
| `fallback` | `unknown_query` + generic error | ⚠️ No dedicated fallback action. |

---

## Priority Order (Plan §4)

**Target order:**
1. Human request → `human_handover`
2. `human_handover_active` → no normal support
3. `awaiting_gender` + user answered gender → save gender, continue `original_question`
4. `awaiting_clarification` + user answered → continue `original_question`
5. Greeting only → `greeting`
6. Gender required + unknown → `ask_gender`
7. Enough info → `answer_question`
8. Missing info → `ask_clarification`
9. Otherwise → `fallback`

**Current flow:** Human takeover and awaiting-name are checked early. Gender + clarification continuation exist but are scattered. **No explicit code-level router** that enforces this order before GPT.

---

## Implementation Roadmap

### Phase 1: State Consolidation

**Goal:** Introduce a single, explicit conversation state structure.

**Files:** `config.py`, `handlers/text_handlers_respond.py`, `handlers/text_handlers_message.py`

**Changes:**
1. Add `user_conversation_state` dict (or extend `user_data_whatsapp`) with:
   - `gender`: `"unknown" | "male" | "female"`
   - `awaiting_gender`: `bool` — explicit flag; priority order uses "awaiting_gender + user answered gender"
   - `awaiting_clarification`: `bool`
   - `awaiting_name`: `bool` (alias for `awaiting_name_input`)
   - `original_question`: `str | None`
   - `clarification_target`: `str | None` (e.g. `"pricing_service"`, `"booking_details"`)
   - `selected_service`: `str | None`
   - `last_bot_question_type`: `str | None` (`"gender"`, `"clarification"`, `"name"`)
   - `human_handover_active`: `bool`

2. Migrate existing flags:
   - `initial_user_query_to_process` → `original_question` (when interrupted by gender)
   - `pending_clarification_query` → `original_question` (when interrupted by clarification)
   - Set `last_bot_question_type` when sending gender/clarification/name questions

---

### Phase 2: Code-Level Router

**Goal:** Implement a simple router that returns one of the 6 actions **before** GPT, using state + message.

**New file:** `services/conversation_router.py`

**Logic (pseudo):**
```python
def route(user_id, message, state) -> str:
    # 1. Human request (meaning-based, not keyword-only)
    if is_human_request(message):
        return "human_handover"
    # 2. Human takeover active
    if state.get("human_handover_active"):
        return None  # handled elsewhere
    # 3. Awaiting gender + user answered gender
    if state.get("awaiting_gender") and is_gender_answer(message):
        return "answer_question"  # with original_question
    # 4. Awaiting clarification + user provided detail
    if state.get("awaiting_clarification") and has_clarification_content(message):
        return "answer_question"  # resume_original_question (see note below)
    # 5. Greeting only (no service/pricing/booking)
    # IMPORTANT: Apply only when NO active pending state (awaiting_gender, awaiting_clarification, awaiting_name).
    # Example: bot asks "أي خدمة؟", user replies "هلا، ليزر شعر" — must NOT route to greeting; must treat as clarification answer.
    if not any([state.get("awaiting_gender"), state.get("awaiting_clarification"), state.get("awaiting_name")]) and is_greeting_only(message):
        return "greeting"
    # 6. Gender required + unknown
    if needs_gender_for_service(message) and state.get("gender") == "unknown":
        return "ask_gender"
    # 7. Enough info
    if has_enough_info(message, state):
        return "answer_question"
    # 8. Missing info
    if needs_clarification(message):
        return "ask_clarification"
    # 9. Fallback
    return "fallback"
```

**Integration:** Call router at start of `_process_and_respond`. For actions `greeting`, `ask_gender`, `ask_clarification`, `fallback`—handle in code when possible; for `answer_question` and `human_handover`, pass through to existing logic with structured context.

**answer_question – two conceptual subtypes:**

The router returns a single action `answer_question`, but the system must distinguish:

- **answer_new_question**: User asks a fresh question; answer the latest message.
- **resume_original_question**: Router returned `answer_question` because `awaiting_gender` or `awaiting_clarification` was active and the user answered. In this case, **the system must answer `original_question`, not the latest user message.**

> **Critical:** When `answer_question` is returned while `awaiting_gender` or `awaiting_clarification` was active, the system MUST answer `original_question`. A developer must NOT mistakenly apply `answer_question` to the latest message only — that would lose context and produce wrong replies.

---

### Phase 3: Structured Operational Context (Plan §10)

**Goal:** Build a structured context block instead of raw history alone.

**Files:** `services/chat_response_service.py`, `utils/utils.py` (`get_system_instruction`)

**Changes:**
1. Add `operational_context` block to system prompt:
   ```
   Conversation State:
   - gender: female
   - awaiting_gender: false
   - awaiting_clarification: false
   - original_question: "شو الأسعار عندكن؟"
   - selected_service: "laser hair removal"
   - last_bot_question_type: "clarification"

   Current User Message: "ليزر شعر"

   Task: The user previously asked about prices. The bot asked which service.
   The user has now answered with the service. Answer the original question
   about prices for laser hair removal. Do not ask for clarification again.
   ```

2. Pass `operational_context` from `_process_and_respond` into `get_bot_chat_response`, and append it to the system instruction.

---

### Phase 4: Selector Input for Follow-ups (Plan §11)

**Goal:** When user is answering a clarification, send full context to selector, not just the last message.

**File:** `services/dynamic_retrieval_service.py`, `handlers/text_handlers_respond.py`

**Changes:**
1. When `awaiting_clarification` and user replies, build selector input:
   ```
   Original user question: شو الأسعار عندكن؟
   Bot clarification: لأي خدمة بدك الأسعار؟
   User follow-up answer: ليزر شعر
   ```
2. Pass this combined string to `retrieve_and_merge()` instead of only `user_input_to_process`.

---

### Phase 5: System Prompt Structure (Plan §9)

**Goal:** Enforce order: Style Guide → Core KB → State → Original Question → Last Bot Question → Retrieved Context → Task.

**File:** `utils/utils.py` (`get_system_instruction`)

**Current order:** Gender instruction → KB + Style → Price → Custom context → Q&A → Appointment rules → Human handover.

**Target order:**
1. Style Guide
2. Core Knowledge Base
3. Current conversation state (operational_context)
4. Original question (if any)
5. Last bot question type
6. Retrieved context (additive)
7. Current task instruction

**Changes:** Refactor `get_system_instruction` to accept `operational_context`, `original_question`, `last_bot_question_type` and build the prompt in this order. Ensure retrieved content is **additive**, never replacing Style Guide or Core KB.

---

### Phase 6: Hard Rules for AI (Plan §12)

**Goal:** Add short, direct rules to system instruction.

**File:** `utils/utils.py` (`get_system_instruction`), `data/style_guide.txt`

**Add to system prompt:**
1. Treat the conversation as continuous, not as isolated messages.
2. If the bot previously asked for clarification and the user now provides the missing detail, answer the original question immediately.
3. Do not ask for clarification again if enough information is now available.
4. If the message is only a greeting, respond with a warm greeting.
5. If gender is required for service guidance and still unknown, ask for gender before continuing.
6. If the user provides the requested gender, continue with the original request immediately.
7. Do not invent facts outside the provided knowledge.
8. Use the Style Guide and Core Knowledge Base as the main foundation. Retrieved context is additional support only.
9. Stay on task. Do not loop or restart unnecessarily.
10. If the user asks for a human, transfer immediately.

Keep these concise; avoid duplicating with existing style guide content.

---

### Phase 7: Greeting Rule (Plan §5)

**Goal:** For greeting-only messages, reply with a warm greeting; do not force gender or clarification.

**Implementation:**
- Router returns `greeting` only when `is_greeting_only(message)` **and** there is no active pending state (`awaiting_gender`, `awaiting_clarification`, `awaiting_name`).
- **Greeting-only detection should apply only when there is no active pending state.** If the user replies to a clarification or gender question with a greeting + content (e.g. "هلا، ليزر شعر" after "أي خدمة؟"), do NOT route to greeting — treat as clarification/gender answer first.
- Use a short, natural greeting template (e.g. "Marhaba, ana Marwa... kif fini se3dik el yom?").
- Do **not** call GPT for pure greetings if a template suffices; or call GPT with a minimal prompt that says "respond with a warm greeting only."

---

### Phase 8: Gender Rule (Plan §6)

**Goal:** Ask for gender only when needed for service guidance. After user answers, continue `original_question` immediately.

**Current:** `initial_user_query_to_process` is used; flow exists but is intertwined with `greeting_stage`.

**Changes:**
- When router returns `ask_gender`, set `original_question` = current message, `awaiting_gender` = True, `last_bot_question_type` = `"gender"`.
- When user answers gender, router returns `answer_question` (resume_original_question); clear `awaiting_gender`, then pass `original_question` to GPT as the main query — **not** the latest message.
- Remove redundant gender ask on simple greetings.

---

### Phase 9: Clarification Rule (Plan §7)

**Goal:** Ask clarification only when necessary. Save `original_question`, set `awaiting_clarification`. When user replies with the detail, answer immediately.

**Current:** Dynamic retrieval returns `ask_clarification`; `pending_clarification_query` is set. Flow exists but `original_question` is not unified.

**Changes:**
- When sending clarification: set `original_question`, `awaiting_clarification` = True, `clarification_target` if useful.
- When user replies: if router detects clarification answer, set `awaiting_clarification` = False, `selected_service` if relevant, then answer `original_question`.
- Ensure we never ask the same clarification again once the user has answered.

---

### Phase 10: Human Handover Priority (Plan §13)

**Goal:** Human request = top priority. Transfer immediately; do not answer or clarify first.

**Current:** GPT detects human intent. Sentiment/takeover checks exist in `text_handlers_message`.

**Changes:**
- Add **code-level** human-request detection (simple heuristics + optional lightweight LLM) before GPT.
- If detected, route to `human_handover` immediately, skip normal flow.
- Ensure no other logic (gender, clarification) runs when human is requested.

---

### Phase 11: Fallback Rule (Plan §14)

**Goal:** When intent is unclear, reply with a short, natural clarification request.

**Example:** "أكيد، فيك توضحلي أكتر شو الخدمة أو الموضوع اللي بدك تستفسر عنه؟"

**Implementation:**
- When router returns `fallback`, use a localized fallback template.
- Optionally allow GPT to generate a short clarification with strict instructions (no invention, no long answers).

---

### Phase 12: Debugging / Logging (Plan §18)

**Goal:** Log orchestration data for every request.

**Add logging for:**
- Normalized user input
- State before/after update
- Detected action
- Selector input/output
- Final system prompt (or hash/summary)
- Retrieved knowledge titles
- Final AI raw response
- Final displayed message

**Location:** `handlers/text_handlers_respond.py`, `services/conversation_router.py`, `services/dynamic_retrieval_service.py`, `services/chat_response_service.py`

---

## File Change Summary

| File | Changes |
|------|---------|
| `config.py` | Add `user_conversation_state` or document state schema. |
| `handlers/text_handlers_respond.py` | Integrate router; use unified state; build operational context; pass to GPT. |
| `handlers/text_handlers_message.py` | Ensure state is initialized; early human-request check. |
| `services/conversation_router.py` | **New.** Router logic. |
| `services/dynamic_retrieval_service.py` | Accept combined selector input for follow-ups. |
| `services/chat_response_service.py` | Accept `operational_context`, `original_question`, `last_bot_question_type`; append to system prompt. |
| `utils/utils.py` | Refactor `get_system_instruction` for new structure; add hard rules. |
| `data/style_guide.txt` | Optional: trim redundant rules that move to code. |

---

## What to Avoid (Plan §19)

- Do **not** depend on too many exact keywords for routing.
- Do **not** create too many states beyond the 5 main + 3 optional.
- Do **not** let selector content replace Style Guide or Core KB.
- Do **not** lose `original_question` after gender or clarification.
- Do **not** ask clarification again after the user has answered.
- Do **not** treat every message as a new conversation.
- Do **not** force gender on greeting-only messages.
- Do **not** let the AI handle all routing/business logic alone.

---

## Recommended Implementation Order

1. **Phase 1** (State) – Foundation.
2. **Phase 2** (Router) – Core flow control.
3. **Phase 10** (Human handover priority) – Critical UX.
4. **Phase 3** (Operational context) – Better GPT behavior.
5. **Phase 4** (Selector input) – Better retrieval.
6. **Phase 5** (Prompt structure) – Align with plan.
7. **Phase 6** (Hard rules) – Reinforce behavior.
8. **Phases 7, 8, 9** (Greeting, Gender, Clarification) – Refine rules.
9. **Phase 11** (Fallback) – Edge cases.
10. **Phase 12** (Logging) – Observability.

---

## Success Criteria

- Bot greets naturally without forcing gender on "marhaba".
- When user asks "شو الأسعار؟", bot asks which service; when user says "ليزر شعر", bot answers prices for laser hair.
- When user asks about a service and gender is unknown, bot asks gender first, then answers the original question.
- When user asks for a human, transfer is immediate.
- No loops, no repeated clarification, no treating follow-ups as new requests.
- Code manages state, routing, and flow; AI handles natural understanding and wording.
