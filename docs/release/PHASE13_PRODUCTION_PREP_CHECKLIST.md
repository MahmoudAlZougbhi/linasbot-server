# Phase 13 — Production preparation checklist

**Status:** **BLOCKED_OWNER_ACTION** — prep report complete; owner must purchase Redis, approve migration apply, then approve merge.  
**PR:** #240  
**Report:** [`PHASE13_PRODUCTION_PREP_REPORT.md`](./PHASE13_PRODUCTION_PREP_REPORT.md)  
**Rule:** Merging `main` triggers Quality Gates then Production Deploy. **Do not merge** until the blocked list below is cleared by Mahmoud.

## BLOCKED_OWNER_ACTION (exact)

1. **Redis purchase:** No Linas-dedicated DO Valkey exists. Approve **Managed Valkey** `linas-redis-prod`, region **lon1**, size **`db-s-1vcpu-1gb`**, ~**$15/mo**. Do not reuse `sportbook-redis-prod` (fra1 / wrong product). After create: TLS/auth URL → `RATE_LIMIT_REDIS_URL` / `REDIS_URL`; multi-worker smoke; fail-closed. Do **not** activate live wiring without owner go-ahead after purchase.
2. **Meta VERIFY_AND_PRESERVE:** Live production **VERIFIED** (ready + preflight + scope audit + webhooks). No OTP required for those checks. Optional: fix GHA `META_PAGE_ACCESS_TOKEN` allowlist for CI Token Validate only — **do not** disconnect/rebuild live Meta.
3. **Migration apply approval:** Approve applying additive Alembic `20260812_customer_requests` on production Postgres **after backup**. Validated on ephemeral Postgres; **not applied** to prod.
4. **Merge approval:** Only after 1–3 and Phase 12 freeze green — then merge #240 (Quality Gates → Production Deploy).

---

## 13.1 Release backup / rollback (prepare before merge)

| Item | Owner action / note |
|------|---------------------|
| Exact current production SHA | `781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26` (recorded 2026-08-12) |
| Exact new release SHA | PR #240 merge commit |
| Database backup/snapshot | Postgres WA Cloud + Requests tables — see report §C |
| Firestore backup/restore plan | Live Chat / users — indexes owner-gated; dry-run OK |
| Previous deploy artifact | systemd `/etc/systemd/system/linasbot.service` |
| Rollback command | `git reset --hard 781a94ca3d50b02b6a8da1b0afeaeaa32e01bb26 && sudo bash /opt/linasbot/deploy.sh` |
| Migration forward/rollback | `20260812_customer_requests` additive; downgrade drops new tables only |
| Meta connection snapshot | VERIFY_AND_PRESERVE — live verified; no disconnect/rebuild |
| Redis rollback | unset require flag / previous URL |
| nginx / systemd rollback | prior unit files; no reload in Phase 13 prep |

Do not expose secrets in this doc or commits.

---

## 13.2 Redis

Inspected DigitalOcean: **no Linas Valkey**. Only `sportbook-redis-prod` (fra1). Prod has Redis URL configured but **unreachable**.

- Purchase gate: see BLOCKED list item 1 + full report.
- Optional durable queues: `LINAS_REQUIRE_REDIS` remains opt-in; do not enable without owner approval.

---

## 13.3 Requests migration + indexes

- Validated on production-like ephemeral Postgres (upgrade + downgrade)
- Apply additive `20260812_customer_requests` only after backup + owner approval
- Confirm single Alembic head
- No destructive rewrite

---

## 13.4 systemd / nginx / Meta

- systemd unit live + serving (read-only READY)
- nginx webhook routes functionally verified (VERIFY_AND_PRESERVE)
- Meta: live VERIFIED without OTP for completed checks

---

## 13.5 Merge gate

Only when checklist above is READY:

1. Merge PR #240 via normal protected method
2. Wait Quality Gates
3. Wait Production Deploy
4. Phase 15 live smoke

If critical smoke fails: documented rollback, fix, redeploy.
