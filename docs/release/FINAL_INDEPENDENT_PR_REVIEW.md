# FINAL INDEPENDENT PR REVIEW — PR #240

**Reviewer context:** Fresh review after Requests feature implementation (did not author Phase 3–8 feature agents).  
**PR:** https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240  
**Base:** `main`  
**Head (at review draft):** `be8d82d37f7ca11870309729c23bd7a3c853f145`  
**Date:** 2026-08-12

---

## Scope

Diff `main...HEAD` includes the full project cleanup reorg **plus** Customer Requests (Phases 1–9 foundations). ~771 files touched historically on the branch; Requests-specific surface is concentrated under:

- `docs/requests/*`, `docs/release/*`
- `alembic/versions/20260812_customer_requests.py`
- `db/models/requests*.py`
- `services/requests/*`
- `modules/requests_api.py`
- CM `requests_appointments` section
- mobile Requests module
- BOC default-OFF gate
- Live Chat manual mode / outbox delivery

---

## Classification summary

| Class | Count (actionable) | Notes |
|-------|-------------------:|-------|
| BLOCKING | 0 open after CI inventory/progress fixes | CI must stay green |
| NON_BLOCKING_ACTIONABLE | see below | continue in Phase 11–12 if needed |
| FALSE_POSITIVE | several | optional CM defaults counting as complete is intentional |
| ACCEPTED_LOW_INFO_RISK | see below | |

### NON_BLOCKING_ACTIONABLE (track; fix before freeze if medium+)

1. **Phase 11 full file-by-file inventory** of entire tree not yet regenerated under `docs/release/FINAL_FILE_BY_FILE_*` for post-Requests tip — prior audit covered pre-feature tree.
2. **Outbox worker scheduling** — delivery/outbox modules exist; ensure a production-safe runner/job is documented in Phase 13 (no silent Monty).
3. **Permission UI completeness** — Requests keys mirrored; confirm UserFormModal + i18n on all locales in freeze.
4. **Channel delivery depth** — Meta IG/FB + WA template-outside-window paths need live smoke in Phase 15 (cannot complete without deploy).

### ACCEPTED_LOW_INFO_RISK

- Requests Postgres shares WhatsApp Cloud DB URL (documented domain convention).
- Capture inactive until published config (safe default).
- BOC remains code-present but runtime OFF.

### FALSE_POSITIVE

- “New CM section increases complete count” — `requests_appointments` intentionally optional-complete when disabled defaults.
- Route inventory bump — expected with new `/api/requests*` (+ resume if counted).

---

## Security spot-check (Requests)

- Tenant from session only for operator APIs — **OK**
- AI tool strips model-supplied tenant/channel/PII fields — **OK**
- Public comment create refused — **OK**
- Optimistic concurrency on status — **OK**
- BOC HTTP gated default OFF — **OK**
- No forced wa.me when capture active — **OK**

---

## Merge / deploy

**Do not merge** until Phase 13 production prep is READY (Redis, migration apply plan, Meta VERIFY_AND_PRESERVE, rollback). Merging triggers Quality Gates → Production Deploy.

---

## Verdict of this review document

`READY_FOR_CI_GREEN_THEN_PHASE_13` — no open BLOCKING code findings in the Requests feature surface reviewed; remaining work is CI confirmation, freeze gates, and owner-only production actions.
