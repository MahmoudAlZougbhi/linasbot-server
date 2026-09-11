# Customer Brain — Linas Laser production test runbook

**Branch tip:** `cleanup/ai-setup-runtime`  
**Rollback tag (pre-Brain main):** `rollback/pre-brain-2026-09-11` → `0f23bcf1d35886acec5dbf53eb1af2faf2734757`

## Critical fact

With this branch deployed, `CUSTOMER_BRAIN_ENABLED=false` returns `engine_removed` (old Luna/Terra engine is gone).  
**Instant AI restore = redeploy the rollback tag**, not only flipping the flag off.  
`EMERGENCY_LEGACY_REPLY_ENABLED` (default **false**) does **not** restore Luna/Terra — it fails closed with `emergency_legacy_unavailable`.

**Not customer-ready.** Do not claim production customer readiness until the gates below pass.

## Flag matrix (deploy gate)

| `CUSTOMER_BRAIN_ENABLED` | `EMERGENCY_LEGACY_REPLY_ENABLED` | Customer outcome | Luna/Terra? |
| --- | --- | --- | --- |
| `false` | `false` (default) | `engine_removed`, no reply | No |
| `false` | `true` | `emergency_legacy_unavailable`, no reply | No |
| `true` | any | Brain runtime (subject to tenant + index gates) | No |

Helper: `services.customer_ai.flags.assert_safe_brain_cutover()` →
`brain_on/off`, `emergency_legacy` (always false by default), `rollback_required_when_brain_off=true`.

## 0) Before deploy

- [ ] Confirm live prod SHA is recorded (should match rollback tag if prod was on `main` @ `0f23bcf1`).
- [ ] **Secrets (GitHub Actions — already set for the Linas live window; do not paste keys):**
  - `OPENAI_API_KEY` / `VOYAGE_API_KEY` present
  - `CUSTOMER_BRAIN_ENABLED=true`
  - `LINAS_CUSTOMER_AI_LAB=true`
  - `CUSTOMER_BRAIN_TENANT_ALLOWLIST=linas`
  - `EMERGENCY_LEGACY_REPLY_ENABLED=false`
  - `MESSAGE_BILLING_CUTOVER=false` (commerce stays off)
  - After merge/deploy, sync the same flag values onto both prod nodes (`scripts/prod_apply_customer_brain_flags.sh` via the HA two-node env path). GitHub Secrets alone do not rewrite `/opt/linasbot/.env`.
- [ ] Keep `EMERGENCY_LEGACY_REPLY_ENABLED=false`.
- [ ] Linas Laser: AI Setup sections published (or publish once after deploy).
- [ ] Run `assert_safe_brain_cutover()` mentally: Brain off ⇒ rollback tag required for AI.

## 1) Deploy branch (Brain still OFF)

- [ ] Merge/deploy `cleanup/ai-setup-runtime` to production.
- [ ] Leave `CUSTOMER_BRAIN_ENABLED=false` and `LINAS_CUSTOMER_AI_LAB=false` for first smoke.
- [ ] Smoke: app boots, Owner Portal loads, Meta webhooks still received.
- [ ] Run Alembic to expected head `20260910_req_web_chat` if not already applied.
- [ ] Confirm `CREATE EXTENSION vector` / customer AI search migration (`20260910_cust_ai_search`) applied where pgvector is available.

## 2) Index readiness checklist (before Brain ON)

- [ ] Alembic head includes customer AI search tables + pointers.
- [ ] pgvector extension present on the WhatsApp/Postgres DB used by hybrid search.
- [ ] `VOYAGE_API_KEY` set on app nodes.
- [ ] Force-reindex Linas Laser after publish (Owner lab reindex / admin search API). Publish returns `brain_index_status`; if `ready=false`, retry force-reindex — index failure is best-effort and retryable, not silent success.
- [ ] Confirm tenant index pointer `ready=true` for Linas Laser (`tenant_id=linas` by default).
- [ ] Product catalog edits mark products stale; product questions fail closed with `product_index_stale` until reindex.
- [ ] Visual path stays honest: multimodal disabled / resource-by-id only — no fake photo reading UX.
- [ ] Missing Voyage / extension / pointer ⇒ Brain fail-closed with `provider_not_configured` or `index_not_ready` (no silent lexical “success”).

## 3) Tenant / activation gates

Before real-customer Brain:

- [ ] `CUSTOMER_BRAIN_TENANT_ALLOWLIST` set, **or** default allowlist includes `linas`.
- [ ] Lab tenants (`lab` / `lab_*`) only when `LINAS_CUSTOMER_AI_LAB=true`.
- [ ] Non-allowlist non-lab tenants are **always** fail-closed (`brain_gates_incomplete` / `not_allowlisted`). `activation_readiness.testing_ready` is import-only and must **not** unlock other customers.

## 4) Enable for Linas Laser live AI test

On production env only after steps 1–3. **Flip flags via GitHub Secrets → approved prod env apply** (or node `.env` apply scripts). Never invent/paste OpenAI or Voyage key material — secrets already exist in the repo.

| Flag / secret | Action after smoke |
| --- | --- |
| `CUSTOMER_BRAIN_ENABLED` | set GitHub secret / prod env → `true` |
| `LINAS_CUSTOMER_AI_LAB` | set GitHub secret / prod env → `true` (create secret if missing) |
| `CUSTOMER_BRAIN_TENANT_ALLOWLIST` | optional; code default includes `linas` |
| `EMERGENCY_LEGACY_REPLY_ENABLED` | leave unset/`false` |
| `OPENAI_API_KEY` | **already in GitHub Secrets** — sync to nodes if needed; do not re-enter |
| `VOYAGE_API_KEY` | **already in GitHub Secrets** — sync to nodes if needed; do not re-enter |
| `MESSAGE_BILLING_CUTOVER` | leave `false` for this window |

Then:

- [ ] Publish Linas Laser CM + force-reindex (Knowledge is chunked for search on index).
- [ ] Owner Portal → **Message flow**: stages receive → plan → search → evidence → reply → cost.
- [ ] Owner Portal → Brain lab: tenant `lab` + verification exercises (no live billing).
- [ ] Owner Portal → Costs: pending provider events for lab / Linas Laser.
- [ ] Live channel smoke on Linas Laser only: WA / IG / FB / TikTok / Web as connected.
- [ ] Empty Brain stops must **not** show fake validation-failed success (`ai_called` stays false; pipeline `brain_no_reply` vs `ai_generated`).

### Gates (must pass before any customer-ready claim)

- [ ] Live pgvector write/query on provisioned DB
- [ ] Voyage + OpenAI live turns with measured cost
- [ ] Publish → index `brain_index_status.ready=true` (or documented force-reindex recovery)
- [ ] Product stale fail-closed verified after a catalog edit
- [ ] Channel plan gates + settle/outbox smoke on connected channels
- [ ] Rollback drill: tag `rollback/pre-brain-2026-09-11` restores prior engine

## 5) If AI breaks during Meta testing — rollback

**Preferred (restore previous answering engine):**

1. Redeploy / checkout tag `rollback/pre-brain-2026-09-11` (`0f23bcf1`).
2. Restart app nodes.
3. Confirm inbound Meta/WA replies work on the previous engine.
4. Keep fixing on `cleanup/ai-setup-runtime` offline; re-attempt deploy later.

**Do not rely on** `CUSTOMER_BRAIN_ENABLED=false` alone to restore old AI on this branch.  
**Do not rely on** `EMERGENCY_LEGACY_REPLY_ENABLED=true` — it is fail-closed, not an answering engine.

## 6) After a good live window

- [ ] Leave cutover flags off until commercial readiness gates pass.
- [ ] Record known-good Brain deploy SHA for the next rollback point.
- [ ] Do **not** market or enable for all customers until gates above are green.
