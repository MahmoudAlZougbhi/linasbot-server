# Products — Save / Publish / Query / DM image

Runtime is a tool executor around Terra. Terra authors customer text from EVIDENCE only.

## Save (owner CRUD)

- Luna writes search chunks at save (`ai_search_*` metadata).
- `image_index` stores sha256 / pHash / histogram plus a **64-d pHash bit vector**.
- Incremental Voyage upsert (`reindex.py`) updates **that product’s** text vectors. Image ANN upserts in the same fingerprint transaction.

## Publish

- `index_job.index_published_tenant` compiles published CM cards **plus** customer-facing products (write path may load the catalog).
- Voyage embeddings land in pgvector (`customer_ai_search_documents`) with mandatory `tenant_id` filter.
- Expected ops: publish-time compile is the expensive path; do not load a million rows on a customer turn.

## Query (customer turn)

- Embed the **question only** → hybrid pgvector top-K → hydrate product rows **by id**.
- Tools: `search_products(query)` (vector/hybrid), `get_product(id)` (exact fields). No list-all tool.
- Stale products pointer blocks product answers with an actionable `product_index_stale` reason until upsert/rebuild succeeds.

## DM product photo

1. Exact **sha256** equality (indexed) → confidence 1.0.
2. Else tenant-scoped **pHash ANN** (`phash_embedding <=> query LIMIT ≤24`) then re-rank with `combined_image_similarity` to top-K ≤8. Postgres uses pgvector HNSW. Missing ANN rows (legacy fingerprints) wait for batched `backfill_missing_ann` — not a customer-turn scan.
3. High-confidence hits become product evidence cards; Terra writes the reply. No auto-send.
4. Else GPT vision `describe_stills` → text RAG. Never invent a product.
5. Voyage multimodal image search stays `LINAS_PRODUCT_MULTIMODAL_SEARCH` default OFF.
6. Every ANN SQL filter is `tenant_id = :tenant_id`. Not cross-tenant. Not a 4000-row prefix LIKE scan.

## AI-first executor

Terra decides which product matters and whether to offer/send media. The runtime only:

- `search_products` / `get_product` — hybrid top-K then hydrate **by id** (never `list_all_for_tenant` on a customer turn)
- `check_setup_resources` / `send_resource` — explicit ids/kinds; no silent auto-send
- inbound ANN/sha256 — candidate product ids as EVIDENCE only
