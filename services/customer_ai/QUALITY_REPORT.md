# Customer Brain — QUALITY REPORT

**Branch tip baseline for this report:** post-E implementation on `cleanup/ai-setup-runtime`  
**Offline suite:** PASS (`ok: true`)

## Retrieval (offline lexical + normalize)

| Metric | Value |
|---|---|
| Cases | 65 |
| Recall@1 | 1.0 |
| Recall@3 | 1.0 |
| Recall@5 | 1.0 |
| Recall@10 | **1.0** (≥0.98 PASS) |
| MRR | 1.0 |
| nDCG@10 | 1.0 |
| Precision@10 | 0.992 |

Grounding: `missed_unsupported_eq_0` PASS. Case bank ≥800 PASS.

## Contextual Voyage

- Model: `voyage-context-4`
- Endpoint: `/contextualizedembeddings`
- Dimensions: 1024
- Cutover: candidate version `ctx:{revision}` → `activate_pointer` (rollback_version preserved)
- Active entity space remains `voyage-4-large`

Live provider latency/cost: **NOT_RUN / BLOCKED without secrets in this environment**.

## Production gates (honest)

| Gate | Status |
|---|---|
| CODE | PASS |
| CONTEXTUAL_MODEL wired | PASS |
| RETRIEVAL_EVAL offline | PASS |
| GROUNDING offline | PASS |
| TOOLS registry | PASS |
| MEMORY durable API | PASS (PG requires migration apply) |
| MULTIMODAL ingest API | PASS (extractors may FAIL visibly without libs/providers) |
| ATOMIC_SWITCH | PASS (pointer+version filter) |
| VOYAGE live | BLOCKED without key runtime proof here |
| OPENAI live | BLOCKED without key runtime proof here |
| PGVECTOR live | depends on env |
| LOAD / LATENCY / COST / CHANNEL_SMOKE | NOT_RUN |

## Verdict

Offline + code architecture moved past D.  
**Do not claim production E ready** until live Voyage/OpenAI/pgvector + channel smoke PASS.
