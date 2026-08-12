# Linas AI Phase 2 — Final status

**Verdict:** `NOT LINAS AI APP PRODUCTION READY — EXTERNAL STORE/META/DEVICE GATES ONLY`

See also: `docs/PHASE2_PRODUCTION_RECONCILE.md`, `docs/PHASE2_PRE_RELEASE_REPORT.md`, `docs/PHASE2_IAP_EXTERNAL_CHECKLIST.md`.

## Production reconcile (live host, not branch assumptions)

| Item | Value |
|------|-------|
| Production SHA | `2b4dad24…` (PR #96) |
| `CM_DISABLE_LINAS_LEGACY_BRIDGE` | **true** |
| Published CM / `cm_runtime_pipeline` | **active** |
| Phase 2 Redis/workers/mobile on prod | **not yet** |

Never clear the durable bridge-disable flag.

## What this branch delivers

- Durable Redis queues + 4 systemd workers + deploy/readiness wiring (opt-in via `LINAS_REQUIRE_REDIS`)
- Credit reserve/capture/release with idempotency proofs
- Apple/Google IAP **code** paths (`purchase_ready=false` until sandbox)
- Meta capability matrix with truthful `live_verified` fields
- Expo mobile app (TS strict) + website pricing/features
- Expanded CI: backend/frontend/mobile/secret-scan/deploy-readiness + queue/credit tests

## External gates remaining

1. Apple / Google developer products + sandbox IAP verification  
2. Meta App Review / Advanced Access for comments & publish (`live_verified`)  
3. Mahmoud device sign-off with production Firebase + signed builds  
4. Explicit production activation: deploy branch + Redis URL + `LINAS_REQUIRE_REDIS=true` (reversible)

## Plan prices (unchanged)

Starter $24.99 · Growth $59 · Pro $109 · Max $250 — allowances from economics engine evidence under `docs/evidence/`.
