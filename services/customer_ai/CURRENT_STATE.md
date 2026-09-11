# Customer Brain — CURRENT STATE

**Branch:** `cleanup/ai-setup-runtime`
**Customer Brain:** permanent runtime (CUSTOMER_BRAIN_ENABLED removed)
**Lab UI only:** `LINAS_CUSTOMER_AI_LAB` (Owner Lab page / capture API)
**Tenant gate:** plan/channel only — experimental allowlist removed
**Agent path:** `turn_pipeline` → `agent.loop.run_agentic_dm_path`
**Budgets:** max_retrieval_rounds=3, max_agent_steps=6, max_tool_calls=8, verifier_repairs=1
**Rollback:** `rollback/pre-brain-2026-09-11` → `0f23bcf1` (code redeploy only)

---

# Customer Brain — CURRENT STATE (pre Phase 0→29 upgrade)

**Branch:** `cleanup/ai-setup-runtime`  
**Tip at audit start:** `5218b8eb778b20c481abd4f1d3463b00f3e9289d`  
**PR:** #648  
**Rollback (unchanged):** `rollback/pre-brain-2026-09-11` → `0f23bcf1`  
**Date:** 2026-09-11

## Hard constraints (this workstream)

- No production deploy / no merge to `main`.
- Do not enable Brain for real customers in this task.
- `MESSAGE_BILLING_CUTOVER` stays false.
- Flag-off does **not** restore Luna/Terra (`engine_removed` / emergency fail-closed).
- Do not invent readiness; mark gaps NOT DONE when blocked.

## Pipeline map (actual)

| Stage | Location | Maturity |
| --- | --- | --- |
| Brain OFF / emergency | `brain_off.py`, `flags.py` | Done — fail-closed, no Luna |
| Tenant gate | `tenant_gate.py` | Done — allowlist/`linas` or lab only (`testing_ready` does not unlock) |
| Runtime entry | `runtime.py` | Done |
| Gates | `gates.py` | Medium |
| Planner | `planner/heuristic.py`, `planner/openai_plan.py` | Medium — multi-intent thin |
| Exact FAQ | `faq_exact.py`, `faq_turn.py` | Medium |
| Semantic FAQ | `faq_semantic.py` | Medium — ambiguity → clarify |
| Lexical | `retrieve/lexical.py` | BM25 Okapi present; no field weights / Arabic norm |
| Dense | `retrieve/hybrid.py` + Voyage entity space | Medium — entity only; voyage-context-4 reserved |
| RRF | `hybrid.py` `_rrf` | Present, untuned |
| Rerank | `retrieve/rerank.py` | Present; ON by default; weak contract/timeout |
| Expand/evidence | `retrieve/expand.py`, `cards.py` | Medium |
| Generate + repair | `generate/reply.py`, `compose/blocks.py` | Medium — 1 repair |
| Grounding | `grounding/facts.py`, `extract.py` | Regex/pattern level — **not claim-level** |
| Coverage | `coverage.py` | Delivery quality checks present |
| Visual | `visual.py` | Disabled + localized clarify |
| Templates | `templates.py` | Partial localization |
| Index/store | `search/store.py`, `index_job.py`, `force_reindex.py` | Pointer + fail-closed; atomic candidate switch incomplete |
| Publish index | `services/cm/publish.py` `brain_index_status` | Visible best-effort |
| Message flow | `stage_timeline.py`, `turn_inspector.py` | Human stages; missing IR/verifier detail |
| Evals | `evals/golden_pack_linas.py`, `runner.py` | **Thin** (~tens of cases, not 800–1500) |
| Readiness CLI | — | Missing |
| Shadow mode | — | Missing |
| Claim verifier | — | Missing |
| Contradiction | — | Missing |
| Source authority | — | Missing |
| Latency/cost/load harness | stubs only | Missing real reports |

## Prior gaps 1–21 (presence check)

| # | Status at tip |
| --- | --- |
| 1–4 P0 cutover/handler/gates/readiness | Present |
| 5–7 grounding/repair/BM25 | Present (surface-level grounding) |
| 8 voyage-context-4 | Reserved / not wired (correct until measured) |
| 9–12 provenance/coverage/visual/i18n | Present (partial i18n) |
| 13 eval suite | Golden pack only — **insufficient** |
| 14–15 lab/FAQ | Present |
| 16–21 dead paths/naming/staleness/docs | Present |

## Baseline verdict before upgrade work

- **Product RAG:** medium — real BM25+dense+RRF+rerank+repair+surface grounding.
- **Production-grade measurable RAG:** **NO** — missing large eval bank, IR metrics artifacts, claim verification, contradiction/authority, freshness versioning completeness, latency/cost/load evidence, shadow mode, readiness CLI.

## Upgrade plan order

1. Eval framework + IR metrics + case bank (≥800 deterministic) + baseline artifact  
2. Claim-level verification + contradiction + authority hooks  
3. Retrieval hardening only when measured (Arabic norm, diversity, field BM25)  
4. Observability/readiness/reindex safety/shadow/lab feedback  
5. Latency/cost/load harnesses (safe offline)  
6. Final re-audit table + honest PASS/FAIL gates  

Do not claim FULL CUSTOMER PRODUCTION READY in this workstream.
