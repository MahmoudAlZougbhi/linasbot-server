# Customer Brain — CURRENT STATE

**Branch:** `cleanup/ai-setup-runtime`  
**Customer Brain:** permanent runtime (`CUSTOMER_BRAIN_ENABLED` removed)  
**Architecture class target:** Full Agentic AI Brain (E)  
**Honest live class:** still **D** until OpenAI-backed agent turns + channel smoke pass (see QUALITY_REPORT)  
**Lab UI only:** `LINAS_CUSTOMER_AI_LAB`  
**Tenant gate:** plan/channel only  
**Agent path:** `turn_pipeline` → `agent.loop.run_agentic_dm_path`  
**Budgets:** max_retrieval_rounds=3, max_agent_steps=6, max_tool_calls=8, verifier_repairs=1  
**Rollback:** `rollback/pre-brain-2026-09-11` → `0f23bcf1` (code redeploy only)

## Live lab (non-production)

Runner: `python -m services.customer_ai.evals.live_lab_runner`  
Artifact: `services/customer_ai/evals/artifacts/live_lab_latest.json`  
Requires: `VOYAGE_API_KEY`, `DATABASE_URL` / `LINAS_WHATSAPP_DATABASE_URL` with pgvector, Redis optional.

Proven live in lab (see QUALITY_REPORT for gate table):
- voyage-context-4 contextual index → pgvector → activate
- durable PG memory (write → reconnect → read)
- hybrid retrieval Recall@10 = 1.0 on lab corpus
- rerank-2.5, branch-scoped `get_price`, atomic pointer switch + SQL rollback
- HNSW used in EXPLAIN ANALYZE

Blocked / not run (external):
- `OPENAI_API_KEY` absent locally → agent/critic/cost/billing E2E
- channel sandbox credentials → CHANNEL_SMOKE
- multimodal extractors → MULTIMODAL

## Runtime flow

```
Inbound → gates → history(50) + durable memory/summary
→ normalize + rewrite → plan
→ fast/full path
→ multi-round retrieve (entity + voyage-context-4 knowledge) + authority resolve
→ dynamic bounded tools
→ structured facts + evidence + receipts
→ generate → deterministic grounding + critic → repair → send
```

## Indexing

- Entity index: `voyage-4-large` (services/products/hours/branches)
- Contextual knowledge index: `voyage-context-4` via `/contextualizedembeddings`
- Candidate build → `activate_pointer` atomic flip with rollback_version (SQL-backed rollback)
- Queries filter by active `index_version`
- HNSW index: `ix_customer_ai_search_embedding_hnsw`

## Memory

- Process store + Postgres (`customer_ai_memory_facts` / `customer_ai_memory_summaries`)
- Migration: `20260911_cust_ai_brain_e` (+ HNSW / active-version indexes)

## Explicit unsupported

- Live booking availability tools (`get_availability`, `create_booking`) — no Customer Brain booking backend wired

## Do not claim

- Production ready / level **E** without OpenAI live agent + available channel smokes + billing proof
