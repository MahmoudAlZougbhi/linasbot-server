# Customer Brain — CURRENT STATE

**Branch:** `cleanup/ai-setup-runtime`  
**Customer Brain:** permanent runtime (`CUSTOMER_BRAIN_ENABLED` removed)  
**Architecture class target:** Full Agentic AI Brain (E) — see QUALITY_REPORT for honest gate status  
**Lab UI only:** `LINAS_CUSTOMER_AI_LAB`  
**Tenant gate:** plan/channel only  
**Agent path:** `turn_pipeline` → `agent.loop.run_agentic_dm_path`  
**Budgets:** max_retrieval_rounds=3, max_agent_steps=6, max_tool_calls=8, verifier_repairs=1  
**Rollback:** `rollback/pre-brain-2026-09-11` → `0f23bcf1` (code redeploy only)

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
- Candidate build → `activate_pointer` atomic flip with rollback_version
- Queries filter by active `index_version`

## Memory

- Process store + optional Postgres (`customer_ai_memory_facts` / `customer_ai_memory_summaries`)
- Migration: `20260911_cust_ai_brain_e`

## Explicit unsupported

- Live booking availability tools (`get_availability`, `create_booking`) — no Customer Brain booking backend wired

## Do not claim

- Production deploy ready without live Voyage/OpenAI/pgvector gate PASS + channel smoke
