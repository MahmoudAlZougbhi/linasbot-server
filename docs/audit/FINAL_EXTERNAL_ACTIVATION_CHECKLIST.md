# FINAL_EXTERNAL_ACTIVATION_CHECKLIST.md

**Purpose:** Live / owner activation items only (repo may already be FIXED).  
**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**Status:** Skeleton — incomplete; expand as ops runbooks land.  
**Companion:** `docs/audit/FINAL_SECURITY_FINDINGS.md`

Do **not** treat these as “still broken in code” without checking the FINAL SEC dispositions.

---

## Live activation items

| # | Item | Related SEC / note | Repo evidence | Owner action (live) | Done? |
|---|---|---|---|---|---|
| A1 | Meta WhatsApp Cloud cutover | SEC-026 | `70e2105` Cloud-only factory; `montymobile_templates.json` deleted; `config/whatsapp_cloud_templates.json` | Rotate/set live `WHATSAPP_*` secrets; confirm Graph send; retire Monty env | ☐ |
| A2 | Provision production Redis for rate limits | Known concern #9 (not numbered SEC); `rate_limit_service.py` | `3762c43` Redis backend + prod fail-closed | Set `RATE_LIMIT_REDIS_URL` / `REDIS_URL`; smoke multi-worker limits | ☐ |
| A3 | Deploy nginx conf (OAuth + deauthorize + privacy logs) | SEC-044 (+ privacy SEC-045 already in tree) | `a924227` `deploy/nginx-api-include.conf` synced | Reload live nginx from repo conf; verify `/oauth/` + `/meta/deauthorize` | ☐ |
| A4 | Firestore composite indexes | (infra; readiness P0-10) | `firestore.indexes.json` + `docs/FIRESTORE_INDEXES_DEPLOY.md` | Owner-approved `firebase deploy --only firestore:indexes` | ☐ |
| A5 | systemd non-root service user | SEC-046 | Unit comments + `EnvironmentFile` perms notes (`a924227`) | Create `linasbot` user; chown `.env`; set `User=`/`Group=`; restart units | ☐ |
| A6 | SEC-025 live env / scale posture | SEC-025 | Booking `DEFAULT_*_ID` fail-closed in prod (`a924227`) | Set booking env IDs; decide single-instance vs shared store for in-memory state | ☐ |
| A7 | Deploy app build that includes security fixes | SEC-016/028/010 family, SSE CORS, content-files 410, etc. | Multiple fix commits on branch | Merge/deploy approved SHA; smoke authz + `/api/ready` | ☐ |

---

## Explicitly out of scope here

- Code remediations already dispositioned **FIXED** in `FINAL_SECURITY_FINDINGS.md`
- **ACCEPTED_RISK_WITH_REASON** Meta/CM workflows (SEC-018…024) — ops process, not a missing deploy artifact
- Archive-only destructive CLI (SEC-017) — do not activate against prod

---

## Smoke after activation (draft)

1. `GET /api/ready` ok with Cloud WhatsApp env  
2. Rate-limit hits shared across ≥2 workers (Redis)  
3. `/oauth/meta/callback` + `/meta/deauthorize` reach app (not 404 at nginx)  
4. Live Chat queries no missing-index errors  
5. Worker process not running as root on new hosts  
6. Operator without elevation → live-chat debug/rebuild/status **403**

---

## Notes

- Branch must not be pushed/deployed until Mahmoud approves.  
- Expand each row with exact host paths, secret names, and rollback steps before production GO.
