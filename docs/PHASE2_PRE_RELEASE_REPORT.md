# Linas AI Phase 2 — Pre-release report

**Verdict:** `NOT LINAS AI APP PRODUCTION READY — EXTERNAL STORE/META/DEVICE GATES ONLY`

**Feature branch HEAD:** `f6f3eee239abe2d41ca35c365dcbd4903482a7a0`  
**PR:** https://github.com/MahmoudAlZougbhi/linasbot-server/pull/97  
**CI:** Quality Gates green (backend, frontend, mobile, secret-scan, deploy-readiness)

## 1) Reconciled production CM / bridge state

| Item | Value |
|------|-------|
| Production SHA (live deploy, PR #96) | `2b4dad24acb72da4efba7b61023c413faaaac53c` |
| `CM_DISABLE_LINAS_LEGACY_BRIDGE` | **true** (durable; preserved by deploy) |
| Linas published CM | **yes** (`linas_has_published_cm` / `tenant_uses_cm_runtime`) |
| Uses `cm_runtime_pipeline` | **yes** |
| Legacy bridge | **disabled** — never re-enable; emergency only `CM_EMERGENCY_FORCE_LEGACY=true` |
| Phase 2 Redis/mobile/workers on prod | **not activated** until this branch is deployed + `REDIS_URL` + `LINAS_REQUIRE_REDIS=true` |
| Phase 2-specific flags still disabled on prod | `REDIS_URL` unset / `LINAS_REQUIRE_REDIS` unset / IAP secrets unset / Meta comments+publish `live_verified=false` |

Earlier Phase 2 “flags not flipped” wording referred to **feature-branch code not deployed**, not live CM cutover.

## 2) Infra delivered in this branch

- Redis-backed durable queues (`REDIS_URL` / `LINAS_REDIS_URL`), four queues:
  - `high_priority` — customer/social
  - `interactive` — owner async
  - `background` — scheduled publishing
  - `expensive` — creative image/video
- Workers: `scripts/run_queue_worker.py` + `deploy/systemd/linasbot-worker@.service`
- Deploy: API + workers, preserve durable CM flags, fail if workers/readiness fail when durable queues activated
- Queue health: `/api/queue/health`, `/api/queue/ready`; `/api/ready` includes `job_queue` check
- Credit-safe async: reserve → enqueue (idempotent) → capture / DLQ release (idempotent)
- IAP endpoints + config status (`purchase_ready=false` until sandbox)
- Meta capability matrix with `supported_in_code` / `permission_present` / `app_review_advanced_access` / `webhook_active` / `live_verified`

## 3) Explicitly not done (external / Mahmoud gates)

- App Store / Play publish
- Real Apple/Google IAP secrets & sandbox purchase proof
- Force-enable Meta comments/publishing (`live_verified=false`)
- Final production activation of `LINAS_REQUIRE_REDIS` without Mahmoud go-ahead
- Physical-device signed E2E with production Firebase credentials on this Mac

## 4) Remaining blockers (under our control → cleared in code)

Code/infra blockers addressed on the feature branch. Remaining activation blockers are external/store/meta/device as listed above.
