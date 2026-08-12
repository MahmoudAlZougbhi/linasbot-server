# Phase 6 — Answer packet + validator + runtime

## Objective
Implement the canonical published-mode runtime order (plan §12) end-to-end — from a user
message to a validated, grounded reply — with an honest failure path and no silent fallback to
the legacy pipeline when `CM_RUNTIME_MODE=published`.

## Implementation
Exact pipeline order (`services/cm/runtime_pipeline.py::prepare_response`):
load published version → restricted → handoff (only if not restricted) → exact FAQ →
semantic FAQ (hit ⇒ stop, skip interpreter/generative) → Query Interpreter (FAQ-miss only) →
structured facts (`services/cm/structured_resolver.py`) → bounded semantic chunks → answer
packet (`services/cm/answer_packet.py`) → **caller runs the large-AI pipeline** → validate
(`services/cm/response_validator.py`) → at most one constrained regeneration → re-validate →
honest failure (`answer_validation_failed` dynamic message).

- `services/cm/structured_resolver.py` — deterministic (regex/lookup) resolution of restricted
  topics, handoff contact, service/price/branch facts from the *published* version only.
- `services/cm/answer_packet.py` — assembles `AnswerPacket` (identity, style, facts, chunks,
  locked platform rules, `source_ids`) — the only context passed to the large-AI step.
- `services/cm/response_validator.py` — deterministic claim checks (no AI call): restricted
  service offered, price mismatch/unsupported price claim, WhatsApp number mismatch, response
  language mismatch. Returns a stable, ordered list of failed rule IDs.
- `services/cm/runtime_pipeline.py::finalize_response` — validate → optional single
  `regenerate_fn` callback → re-validate → on failure, emits a PII-safe event (tenant, content
  version, index version, failed rule IDs — never message text) and returns the
  `answer_validation_failed` dynamic message.
- `services/cm/answer_generation.py` — minimal "large AI" caller: turns an `AnswerPacket` into
  one OpenAI chat completion. Deliberately **not** `get_bot_chat_response` (booking/CRM/tool
  orchestration is out of scope for the CM content-answer runtime in this phase).
- `services/dynamic_messages_service.py` — added `answer_validation_failed` for ar/en/fr/franco.
- `handlers/text_handlers_respond.py::_handle_published_cm_runtime` — the ONLY integration
  point: gated behind `cm_runtime_mode() == "published"` (default `"legacy"`, i.e. a no-op by
  default). Inserted after the human-takeover and out-of-clinic guardrail checks, before the
  router/booking flow, so session-safety behavior is unaffected. When active, it fully replaces
  the legacy flow for that message; a missing/invalid published pointer returns the honest
  `answer_validation_failed` message rather than falling back to legacy FAQ/GPT.

## Acceptance
- FAQ hit (exact or ≥0.90 semantic) returns immediately — the Query Interpreter and large-AI
  call are never invoked.
- Restricted + booking intent together never returns a WhatsApp number (restricted always wins).
- Validator blocks fabricated/mismatched prices, WhatsApp numbers, restricted-service offers,
  and response-language mismatches.
- A validation failure that survives one regeneration attempt returns the versioned
  `answer_validation_failed` message, never the raw invalid text.
- No published pointer ⇒ honest failure message, never a silent legacy fallback.

## Tests
```
pytest tests/test_cm_runtime_pipeline.py tests/test_cm_validator.py tests/test_cm_handler_integration.py
```

## Notes
`PublishedPointer.index_version_id` was relaxed to `str | None` (a version can exist with
content but no semantic index yet, e.g. immediately after a content-only migration) — this is a
schema-only change with no other call sites depending on it being required.

## Gate re-verification (autonomous)
- Full pytest 322 passed (legacy defaults)
- mypy: Success 181 files
- frontend lint/typecheck/test/build: passed
