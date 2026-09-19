# Products — Save / Publish / Query / DM image

Runtime is a tool executor around Terra. Terra authors customer text from EVIDENCE only.

## Save (owner CRUD)

- Luna writes search chunks at save (`ai_search_*` metadata).
- `image_index` stores sha256 / pHash / histogram per product image.
- Incremental Voyage upsert (`reindex.py`) updates **that product’s** vectors. Full tenant rebuild is publish-time / fallback only.

## Publish

- `index_job.index_published_tenant` compiles published CM cards **plus** customer-facing products (write path may load the catalog).
- Voyage embeddings land in pgvector (`customer_ai_search_documents`) with mandatory `tenant_id` filter. Serving uses the existing HNSW/IVF index.
- Expected ops: publish-time compile is the expensive path; do not load a million rows on a customer turn. Incremental CRUD upsert is the live catalog path.

## Query (customer turn)

- Embed the **question only** → hybrid pgvector top-K → hydrate product rows **by id**.
- Tools: `search_products(query)` (vector/hybrid), `get_product(id)` (exact fields). No list-all tool.
- Stale products pointer blocks product answers with an actionable `product_index_stale` reason until upsert/rebuild succeeds.

## DM product photo

1. High-confidence fingerprint match → product evidence cards injected; Terra writes the reply.
2. Else GPT vision `describe_stills` → text → same RAG. Never invent a product.
3. Voyage multimodal image search is `LINAS_PRODUCT_MULTIMODAL_SEARCH` (default OFF).
