# Customer Brain — QUALITY REPORT

**Branch:** `cleanup/ai-setup-runtime`  
**Live artifact:** `services/customer_ai/evals/artifacts/live_lab_latest.json`  
**Offline suite:** PASS (`ok: true`)

## Live lab gates (authoritative for runtime)

| Gate | Status | Detail |
|---|---|---|
| CODE | PASS | brain permanent |
| INDEX | PASS | contextual active |
| VOYAGE | PASS | live key used (value never printed) |
| OPENAI | BLOCKED | `OPENAI_API_KEY` missing locally — BLOCKED_BY_SECRET |
| PGVECTOR | PASS | docker lab Postgres + extension |
| CONTEXTUAL_MODEL | PASS | `voyage-context-4`, dims 1024, chunks 5, version `ctx:lab_ctx_v1` |
| RETRIEVAL_EVAL | PASS | Recall@10 **1.0**, MRR 1.0, nDCG@10 1.0 |
| MULTILINGUAL | PASS | ar / en / fr / arabizi / mixed |
| GROUNDING | NOT_RUN | needs OpenAI generator+critic |
| TOOLS | PASS | registry + branch prices 60/75 + booking unsupported |
| MEMORY | PASS | write → reconnect → read + tenant isolation |
| MULTIMODAL | BLOCKED | extractors/providers not live |
| ATOMIC_SWITCH | PASS | SQL candidate copy → activate → query → rollback |
| LOAD | PASS | n=6, error_rate 0 |
| LATENCY | PASS | retrieval p50≈5.3s p95≈16s (provider-backed hybrid; not LLM E2E) |
| COST | BLOCKED | needs OpenAI turns |
| CHANNEL_SMOKE | BLOCKED | no sandbox channel credentials |
| BILLING | NOT_RUN | needs OpenAI turns |
| SECURITY | PASS | other-tenant empty index + memory isolation |
| PGVECTOR_BENCH | PASS | HNSW / index scan in EXPLAIN ANALYZE |
| RERANK | PASS | `rerank-2.5` |
| RELATIONS | PASS | branch-scoped price via tools |

BLOCKED ≠ PASS.

## Bugs found and fixed during live validation

1. **`probe_pgvector` always false** — raw SQL string under SQLAlchemy 2; fixed with `text()`. Blocked all pgvector writes.
2. **Index pointer PK collision** — `id=tenant:family` ignored `space_id`; fixed stable `sha1(space)` suffix.
3. **`rollback_pointer` memory-only** — now persists SQL rollback.
4. **Arabic label dropout** — catalog cards kept EN title only; all label langs now indexed.
5. **`get_price` ignored `price_entries` / branch** — branch-scoped amounts now resolve (Antelias 60 vs Verdun 75).
6. **Missing HNSW** — added `ix_customer_ai_search_embedding_hnsw` (+ migration).

## Offline retrieval (unchanged suite)

| Metric | Value |
|---|---|
| Recall@10 | 1.0 |
| MRR | 1.0 |
| Grounding unsupported misses | 0 |

## Verdict

| Question | Answer |
|---|---|
| Production ready? | **NO** |
| Level | **D = Full Agentic RAG** (live Voyage+pgvector+memory+tools proven) |
| Level E? | **NO** — OpenAI agent/critic/cost + channel smoke still BLOCKED/NOT_RUN |

Multimodal is an optional product capability here: missing extractors block MULTIMODAL gate but do not alone redefine D↔E if agent+index+memory+tools are live. OpenAI absence **does** block E.
