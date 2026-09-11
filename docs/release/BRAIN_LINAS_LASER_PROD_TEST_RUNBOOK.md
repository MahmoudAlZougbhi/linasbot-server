# Customer Brain — Linas Laser production test runbook

**Branch tip:** `cleanup/ai-setup-runtime`  
**Rollback tag (pre-Brain main):** `rollback/pre-brain-2026-09-11` → `0f23bcf1d35886acec5dbf53eb1af2faf2734757`

## Critical fact

With this branch deployed, `CUSTOMER_BRAIN_ENABLED=false` returns `engine_removed` (old Luna/Terra engine is gone).  
**Instant AI restore = redeploy the rollback tag**, not only flipping the flag off.

## 0) Before deploy

- [ ] Confirm live prod SHA is recorded (should match rollback tag if prod was on `main` @ `0f23bcf1`).
- [ ] Confirm Voyager + OpenAI keys available on nodes (do not commit).
- [ ] Keep `MESSAGE_BILLING_CUTOVER=false` for this test window.
- [ ] Linas Laser: AI Setup sections published (or publish once after deploy).

## 1) Deploy branch (Brain still OFF)

- [ ] Merge/deploy `cleanup/ai-setup-runtime` to production.
- [ ] Leave `CUSTOMER_BRAIN_ENABLED=false` and `LINAS_CUSTOMER_AI_LAB=false` for first smoke.
- [ ] Smoke: app boots, Owner Portal loads, Meta webhooks still received.
- [ ] Run Alembic to expected head `20260910_req_web_chat` if not already applied.

## 2) Enable for Linas Laser live AI test

On production env only after step 1 smoke:

```text
CUSTOMER_BRAIN_ENABLED=true
LINAS_CUSTOMER_AI_LAB=true
OPENAI_API_KEY=...
VOYAGE_API_KEY=...
MESSAGE_BILLING_CUTOVER=false
```

- [ ] Owner Portal → **Message flow**: open a live turn and confirm stages (receive → plan → search → evidence → reply → cost).
- [ ] Owner Portal → Brain lab: turn on tenant `lab` (capture-only).
- [ ] Owner Portal → Costs: pending events appear for lab / Linas Laser tenant_id.
- [ ] Force reindex for Linas Laser after publish (Owner lab reindex or admin search API). Published Knowledge is chunked for search automatically on index.
- [ ] Live channel smoke on Linas Laser only: WA / IG / FB / TikTok / Web as connected.

## 3) If AI breaks during Meta testing — rollback

**Preferred (restore previous answering engine):**

1. Redeploy / checkout tag `rollback/pre-brain-2026-09-11` (`0f23bcf1`).
2. Restart app nodes.
3. Confirm inbound Meta/WA replies work on the previous engine.
4. Keep fixing on `cleanup/ai-setup-runtime` offline; re-attempt deploy later.

**Do not rely on** `CUSTOMER_BRAIN_ENABLED=false` alone to restore old AI on this branch.

## 4) After a good live window

- [ ] Leave cutover flags off until commercial readiness passes.
- [ ] Record known-good Brain deploy SHA for the next rollback point.
