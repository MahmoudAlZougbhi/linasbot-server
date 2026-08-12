# Phase 13 — Production preparation checklist (draft)

**Status:** DRAFT while Phases 2–12 complete. Do not merge until this is READY.  
**PR:** #240  
**Rule:** Merging `main` triggers Quality Gates then Production Deploy.

---

## 13.1 Release backup / rollback (prepare before merge)

| Item | Owner action / note |
|------|---------------------|
| Exact current production SHA | Record at cutover |
| Exact new release SHA | PR #240 merge commit |
| Database backup/snapshot | Postgres WA Cloud + Requests tables |
| Firestore backup/restore plan | Live Chat / users |
| Previous deploy artifact | systemd/unit path |
| Rollback command | `git revert` / redeploy previous SHA |
| Migration forward/rollback | `20260812_customer_requests` additive; downgrade drops new tables only |
| Meta connection snapshot | VERIFY_AND_PRESERVE — no disconnect/rebuild |
| Redis rollback | unset require flag / previous URL |
| nginx / systemd rollback | prior unit files |

Do not expose secrets in this doc or commits.

---

## 13.2 Redis

Inspect DigitalOcean first (owner/ops).

- If Redis **already exists**: configure `RATE_LIMIT_REDIS_URL` / `REDIS_URL`, TLS/auth, multi-worker test, outage fail-closed (see `docs/RATE_LIMIT_REDIS.md`). Production must **not** silently fall back to file/memory.
- If a **new paid Redis** must be purchased: stop with `BLOCKED_OWNER_ACTION` — exact product/region/size/cost/button for Mahmoud.

Optional durable queues: `LINAS_REQUIRE_REDIS` remains opt-in; do not enable without owner approval.

---

## 13.3 Requests migration + indexes

- Validate migration on production-like copy first
- Apply additive `20260812_customer_requests` only after backup
- Confirm single Alembic head
- No destructive rewrite

---

## 13.4 systemd / nginx / Meta

- systemd units match deploy workflow
- nginx webhook routes unchanged (VERIFY_AND_PRESERVE)
- Meta: validate tokens/webhooks without OTP if possible; if Meta OTP/owner confirmation required → `BLOCKED_OWNER_ACTION`

---

## 13.5 Merge gate

Only when checklist above is READY:

1. Merge PR #240 via normal protected method
2. Wait Quality Gates
3. Wait Production Deploy
4. Phase 15 live smoke

If critical smoke fails: documented rollback, fix, redeploy.
