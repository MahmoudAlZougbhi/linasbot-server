# Retrieval V2 Phase 0/1 — foundations only

## Boundary

- New code lives under `services/retrieval_v2/` and `services/retrieval_index/`.
- **Not wired** into `customer_reply_v2`, Owner Copilot, CM publish, Comments, or Requests.
- Flags default **OFF**:
  - `RETRIEVAL_V2_ENABLED=false`
  - `RETRIEVAL_V2_SHADOW=false`

## What this phase provides

- `SearchDocument` schema + deterministic point IDs
- `EmbeddingProvider` / `SearchStore` contracts
- `GeminiEmbeddingProvider` (`gemini-embedding-2`, default dims **3072**, query/doc prompt prefixes — no `task_type`)
- `QdrantSearchStore` (Cosine dense vectors, mandatory `tenant_id` filter)
- Index pipeline skeleton: document → embed → upsert

## Env vars (no secrets in repo)

```
RETRIEVAL_V2_ENABLED=false
RETRIEVAL_V2_SHADOW=false
GEMINI_API_KEY=
GEMINI_EMBEDDING_MODEL=gemini-embedding-2
GEMINI_EMBEDDING_DIMENSIONS=3072
GEMINI_EMBEDDING_TIMEOUT_SECONDS=30
GEMINI_EMBEDDING_MAX_BATCH=32
QDRANT_URL=
QDRANT_API_KEY=
QDRANT_COLLECTION=tenant_business_v2
QDRANT_TIMEOUT_SECONDS=10
```

## Tests

```bash
python3 -m pytest tests/retrieval_v2 -q
```

Unit tests use FakeEmbeddingProvider + Qdrant `:memory:` — no live Gemini/Qdrant required.

Optional live smoke (not CI): set `GEMINI_API_KEY` + `QDRANT_URL`, write a one-off script — not included as required CI.

## Intentionally NOT connected yet

- BM25 / Cohere / ColBERT
- Query rewriting / translation
- File parsers / OCR
- CM publish hooks
- Customer live retrieval cutover
- Owner smart ingestion
- Credits for embeddings
