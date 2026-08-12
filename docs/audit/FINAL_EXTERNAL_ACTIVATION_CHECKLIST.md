# FINAL_EXTERNAL_ACTIVATION_CHECKLIST.md

**Purpose:** Live / owner activation items only (repo may already be FIXED).  
**Branch:** `chore/project-cleanup-reorg`  
**Date:** 2026-08-12  
**FINAL_CANDIDATE_SHA:** `1900bf59925c61e35e4defe41cdbcb557a719062`  
**Freeze verdict:** **NOT_READY** (code gates) — activation still blocked regardless.  
**Companion:** `docs/audit/FINAL_SECURITY_FINDINGS.md` · `FINAL_FREEZE_VERIFICATION.md`

Do **not** treat these as “still broken in code” without checking FINAL SEC dispositions.  
**Do not execute** any row during freeze verification.

---

## Recommended activation order (dependency)

| Order | ID | Why this order |
|---|---|---|
| 1 | **A6** | Booking env IDs / scale posture before serving booking traffic |
| 2 | **A2** | Redis for distributed rate limits before multi-worker |
| 3 | **A4** | Firestore indexes before Live Chat query load |
| 4 | **A5** | Non-root systemd user before/with service restart |
| 5 | **A3** | nginx OAuth/deauthorize/privacy before Meta reliance |
| 6 | **A1** | Meta WhatsApp Cloud live secrets cutover |
| 7 | **A7** | Deploy app build + rollback plan last; smoke |

---

## Live activation items

| # | Item | Related SEC / note | Repo evidence | Owner action (live) | Mandatory before deploy of candidate? | Done? |
|---|---|---|---|---|---|---|
| A1 | Meta WhatsApp Cloud cutover | SEC-026 | Cloud-only factory; Monty templates deleted | Rotate/set live `WHATSAPP_*`; confirm Graph send; retire Monty env | **Yes** if WA Cloud prod | ☐ |
| A2 | Provision production Redis | rate_limit_service Redis backend | Prod fail-closed without Redis | Set `RATE_LIMIT_REDIS_URL` / `REDIS_URL`; smoke multi-worker | **Yes** multi-worker | ☐ |
| A3 | Deploy nginx conf | SEC-044 (+ SEC-045) | `deploy/nginx-api-include.conf` synced | Reload live nginx; verify `/oauth/` + `/meta/deauthorize` | **Yes** for Meta OAuth/deauth | ☐ |
| A4 | Firestore composite indexes | infra P0 | `firestore.indexes.json` | Owner-approved `firebase deploy --only firestore:indexes` | **Yes** for Live Chat at scale | ☐ |
| A5 | systemd non-root user | SEC-046 | Unit comments; still `User=root` in unit | Create `linasbot`; chown; set User/Group; restart | Strongly recommended | ☐ |
| A6 | Booking env / scale | SEC-025 | `DEFAULT_*_ID` fail-closed in prod | Set booking env IDs; single- vs multi-instance store | **Yes** if booking on | ☐ |
| A7 | Deploy app + rollback | security fix family | Branch commits incl. `5f1d1ea` | Deploy approved SHA only after gates green; smoke authz + `/api/ready` | **Yes** to realize fixes | ☐ |

---

## Explicitly out of scope here

- Code remediations dispositioned **FIXED**
- **ACCEPTED_RISK_WITH_REASON** Meta/CM workflows (SEC-018…024)
- Archive-only destructive CLI (SEC-017)
- Freeze gate remediation (dashboard vitest) — fix in repo first; not an activation item

---

## Smoke after activation (draft)

1. `GET /api/ready` ok with Cloud WhatsApp env  
2. Rate-limit hits shared across ≥2 workers (Redis)  
3. `/oauth/meta/callback` + `/meta/deauthorize` reach app  
4. Live Chat queries no missing-index errors  
5. Worker not root on new hosts  
6. Operator without elevation → live-chat debug/rebuild/status **403**

---

## Notes

- Branch must not be pushed/deployed until Mahmoud approves **and** freeze gates are green.  
- Current freeze: **NOT_READY** — see `FINAL_FREEZE_VERIFICATION.md`.
