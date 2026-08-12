# HA residual writers under `/opt/linasbot_data` (A–D)

**Date:** 2026-08-12  
**Branch HEAD (at write):** discover via `git rev-parse HEAD`  
**Constraint:** classification only; no live NFS removal / flag flip.

| Class | Meaning |
|-------|---------|
| **A** | Still required local / ephemeral |
| **B** | Dual-read / migrate-ready (PG or Redis path in code; default file until cutover) |
| **C** | Dead / removable post-cutover |
| **D** | OWNER_ONLY / external / shared non-file |

## A — required local / ephemeral

- `logs/`, activity / debug traces
- `owner_*` proposals, alerts, attachments, usage drafts
- `creative_assets/`, `customer_response_traces/`, `faq_metrics/`
- `job_queue/` file backend (dev/local until `LINAS_REQUIRE_REDIS`)
- `auth/rate_limits/` (non-Redis rate limit file backend)
- `safety/`
- Scheduler claim files when Redis fail-closed is off

## B — migrate-ready (code present; prod flags still file)

| Path | Flag / notes |
|------|----------------|
| `meta_registry/` | `META_REGISTRY_BACKEND=file\|dual\|postgres` |
| `billing/wallets/` + wallet ledger | `LINAS_BILLING_BACKEND` |
| `billing/stripe_events/` | same |
| `billing/admin_credit_idempotency/` | same |
| `credit_ledger/` | **now PG-capable** via `LINAS_BILLING_BACKEND=postgres` |
| `entitlements/` (+ `processed_events/`) | **now PG-capable** via same flag |
| `auth/mobile_refresh/` | `LINAS_AUTH_TOKEN_BACKEND` |
| `auth/email_tokens/` | same |

Import: `scripts/ha/import_billing_auth_to_postgres.py`, `scripts/ha/import_meta_registry_to_postgres.py`.

## C — removable post-cutover

- Local `meta_registry/` after `postgres` + `remove_registry_nfs.sh`
- File copies of B after postgres flag + verify soak
- `meta_social_post_media/` (legacy; Create Post disabled; NFS already removed)

## D — OWNER_ONLY / external

- `/opt/linasbot/.env` (both nodes; mode 0600)
- Managed PG `linas-postgres-prod` / Valkey `linas-redis-prod`
- Firestore (users, live chat, session mirror)
- CM published content under tenant trees (product SoT; HA sticky/replicate separate)
- `smart_messaging/*`, `email/idempotency`, guest/owner chat caches — HA residuals (future migrate)
- `auth/sessions/` (FS primary + Firestore mirror)
- Apple `.p8` paths on deploy hosts (not in git)
- Resend dashboard residual **Onboarding** API key (cannot delete without another Full Access key)

## Post-deploy cutover sequence (do not execute now)

1. Deploy PR #240  
2. Import meta registry → `META_REGISTRY_BACKEND=dual` soak → `postgres` → `remove_registry_nfs.sh`  
3. Import billing/auth/credits/entitlements → `LINAS_BILLING_BACKEND=postgres` + `LINAS_AUTH_TOKEN_BACKEND=postgres`  
4. Owner gate: `LINAS_REQUIRE_REDIS` / `LINAS_FAIL_CLOSED_REDIS_CLAIMS`  
5. Requests migration **only** with separate owner GO  
6. Resize/replace compute per `docs/scale/RUNBOOK_RESIZE_REPLACE_NODE01_PREPARE.md`
