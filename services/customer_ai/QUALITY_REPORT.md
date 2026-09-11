# Customer Brain — QUALITY REPORT (offline evidence)

**Branch:** `cleanup/ai-setup-runtime`  
**Generated from tip work after Phase 0–29 scaffolding**  
**Live spend:** false (deterministic offline suite)

## Suite size

- Offline case bank: **876** cases (target 800–1500)
- Categories covered: retrieval, grounding, hallucination, prices, hours, stock, booking, multilingual (en/ar/lb/arabizi/fr/mixed), multi-turn, injection, contradiction, abstain, multi-intent, noisy, products, FAQ, handoff, long_kb, duplicates

## Retrieval (lexical BM25 over fixture cards; dense/Voyage not in this offline pass)

| Metric | Value |
| --- | --- |
| cases | 65 |
| Recall@1 | 0.969 |
| Recall@3 | 0.969 |
| Recall@5 | 0.969 |
| Recall@10 | 0.969 |
| Precision@5 | 0.962 |
| Precision@10 | 0.962 |
| MRR | 0.969 |
| nDCG@5 | 0.969 |
| nDCG@10 | 0.969 |

## Grounding / hallucination traps (deterministic)

| Metric | Value |
| --- | --- |
| grounding cases | 149 |
| caught unsupported rate | 1.0 |
| missed unsupported | **0** |

## Multilingual pass rates (suite category checks)

| Lang | pass_rate |
| --- | --- |
| en | 0.937 |
| ar | 0.976 |
| arabizi | 0.976 |
| lb | 1.0 |
| fr | 1.0 |
| mixed | 1.0 |

## Latency (offline planner+BM25 only)

Suite case latency p50/p95/p99 ≈ 0.001 / 0.04 / 0.06 ms (micro-ops on fixtures).  
Dedicated bench (30 repeats): BM25 p95 ≈ 0.022 ms; planner+BM25 p95 ≈ 0.032 ms.

**NOT measured here (requires providers/DB):** embedding query, vector search, rerank, generation, verifier LLM, end-to-end turn.

## Cost

Offline suite cost = **$0** (no provider calls).  
Provider cost instrumentation exists via pending provider events; full p95 turn cost = **NOT DONE** without authorized live spend.

## Load simulation

50 tenants × 4 lexical requests, 8 workers: error_rate 0, p95 ≈ 0.032 ms.  
**Explicit:** does not exercise Voyage/OpenAI/DB pools. Do not extrapolate production capacity.

## Phase 22 gates (offline)

| Gate | Result |
| --- | --- |
| Recall@5 ≥ 0.95 | PASS |
| Recall@10 ≥ 0.98 | **FAIL** (0.969) |
| missed unsupported = 0 | PASS |
| case_count ≥ 800 | PASS |

**OFFLINE QUALITY GATES: FAIL** (honest — Recall@10 threshold not met on current lexical fixture set).

## Contextual Voyage (Phase 3)

**NOT DONE / KEEP BASELINE.** voyage-context-4 remains reserved. No shadow eval vs entity dense without live Voyage spend authorization in this task.

## Remaining production blockers

- Live pgvector write/query + pointer ready on prod DB
- Live Voyage + OpenAI turn metrics (latency/cost)
- Atomic candidate index switch proven on HA
- Dense+rerank metrics in offline/CI (needs embeddings fixture or recorded vectors)
- Full 300-tenant provider-backed load
- Customer enablement still OFF by policy for this workstream
