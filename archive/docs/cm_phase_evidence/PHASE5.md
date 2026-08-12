# Phase 5 — Semantic index + interpreter (shadow only)

## Objective
Build the retrieval + intent-extraction building blocks needed by the runtime pipeline, and
prove they can be evaluated offline (shadow) with zero live-traffic or outbound-send side
effects.

## Implementation
- `services/cm/embeddings.py` — `embed_texts()` supports a deterministic, dependency-free
  `CM_EMBEDDING_PROVIDER=hash` provider (for tests/dev) and the default OpenAI-compatible
  provider. `embedding_pin()` always returns the provider/model/version/dimensions so every
  index/version manifest can prove which embedding produced it.
- `services/cm/semantic_index.py` — `build_index()` embeds FAQ + Knowledge + Care content for
  one content version into a tenant-scoped, on-disk vector index; `search()` does cosine top-k,
  optionally filtered by `kind`/`language`.
- `services/cm/query_interpreter.py` — `interpret_query_deterministic()` extracts booking/human
  intent, restricted topics, service, and branch via regex/lexicon matching with no AI call;
  `interpret_query()` adds an optional, explicitly-flagged (`CM_INTERPRETER_LLM=true`) LLM
  enrichment pass — deterministic-only is the default and is always skippable.
- `services/cm/shadow_eval.py` — `run_shadow_eval()` runs FAQ + interpreter + semantic search
  over an explicit, caller-provided question list only (Lab/golden/replay) — it takes no
  webhook/user-message input and never calls a send function.

## Acceptance
- Hash embeddings are fully deterministic (same text → same vector, no network).
- Semantic index and shadow eval are tenant-scoped; never write outside
  `{LINASBOT_DATA_ROOT}/tenants/{tenant}/cm/indexes/`.
- `interpret_query_deterministic()` alone is sufficient for booking/human/restricted detection
  (LLM enrichment is additive, off by default, and errors never break the deterministic result).
- Shadow eval never sends a message and never mutates customer conversation history.

## Tests
`pytest tests/test_cm_semantic_shadow.py`

## Notes
This phase intentionally does not touch the live webhook/response path — that wiring is Phase 6.

## Gate re-verification (autonomous)
- Full pytest 322 passed (legacy defaults)
- mypy: Success 181 files
- frontend lint/typecheck/test/build: passed
