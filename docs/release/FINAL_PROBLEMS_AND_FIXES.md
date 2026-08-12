# FINAL_PROBLEMS_AND_FIXES — Phase 11

**Branch:** `chore/project-cleanup-reorg`  
**Started SHA:** `b2333e0a244716e5083902646e0e168ad657dd87`  
**Deep-fix commits:** `9c300ed`, `10e4912`, `5ad2e5a`, `adb0a5c`, `067c6fc`  
**Date:** 2026-08-12

---

## Automated scan baseline

| Scan | Result |
|------|--------|
| App source >500 LOC | **NONE** |
| BOC default | OFF via `LINASLASER_BOC_BOOKING_ENABLED` (default false) |
| Monty runtime fallback | Factory refuses legacy providers (fail-closed) |
| Hardcoded secrets in app src | None found |
| Phone prints | Mostly redacted `***last4` (prior remediation) |

---

## Fixed this phase

| ID | Severity | Area | Finding | Fix SHA / note |
|----|----------|------|---------|----------------|
| P11-001 | MEDIUM | Requests list | Mobile date filter was client-only | Server `created_after` / `created_on_or_before`; mobile `createdAfterForPreset` (`adb0a5c`) |
| REQ-P11-A | HIGH | Requests | `create_from_ai` serialized with `include_sensitive=True` | Respect `requestsSensitive` (`adb0a5c`) |
| REQ-P11-B | HIGH | Requests | `final_action` idempotency replay ignored path `request_id` | Bind replay to request id (`adb0a5c`) |
| REQ-P11-C | MEDIUM | Requests | List `q` matched `phone_normalized` without sensitive flag | Gate phone search (`adb0a5c`) |
| REQ-P11-D | MEDIUM | Requests | `comment_linked_dm` forced Instagram channel | Resolve FB/IG binding (`adb0a5c`) |
| REQ-P11-E | MEDIUM | Requests | Unlocked `allocate_request_number` race | Lock / safe allocate (`adb0a5c`) |
| AUTH-P11-001 | MEDIUM | Auth | Timing/error prints leaked email/exception | Redact (`9c300ed`) |
| AUTH-P11-002 | MEDIUM | Auth | `.env.example` missing Redis fail-closed notes | Docs (`9c300ed`) |
| AUTH-P11-003 | LOW | Auth | Duplicate entitlements tenant allowlist | Deduped (`9c300ed`) |
| LC-P11-001 | HIGH | Live Chat | Image send reported success on delivery failure | Honest failure (`10e4912`) |
| LC-P11-002 | HIGH | Live Chat | `operator-status` trusted body `operator_id` | Session actor (`10e4912`) |
| LC-P11-003 | HIGH | Live Chat | release/end left WA Cloud pause uncleared | Clear pause (`10e4912`) |
| LC-P11-004 | MEDIUM | Live Chat | takeover delayed WA Cloud pause | Pause on takeover (`10e4912`) |
| LC-P11-005 | MEDIUM | Live Chat | mark-read lacked `require_session` | Require session (`10e4912`) |
| P11-CMAI-001 | HIGH | CM/AI | `comment_linked_dm` misclassified as public comment | `is_public_comment_channel()` only (`5ad2e5a`) |
| P11-CMAI-002 | MEDIUM | CM/AI | Public comment handoff posted phone/wa.me | DM invite only (`5ad2e5a`) |
| P11-CMAI-003 | MEDIUM | CM/AI | Capture-active guard claimed request recorded | Honest reconfirm (`5ad2e5a`) |
| P11-MOB-001 | HIGH | Mobile | Action/chat errors unmounted detail | Banner vs load error (`067c6fc`) |
| P11-MOB-002 | MEDIUM | Mobile | Sensitive PII not gated client-side | `requestsSensitive` gate (`067c6fc`) |
| P11-MOB-003 | MEDIUM | Mobile | setup `errorKind` → generic load error | Setup empty state (`067c6fc`) |

---

## Accepted (freeze) — not blocking Phase 12

| ID | Severity | Area | Finding | Rationale |
|----|----------|------|---------|-----------|
| P11-002 | LOW | Outbox | No continuous outbox worker — drain on final-action/notify-retry only | Document Phase 13 ops; foundations callable |
| P11-003 | INFO | Tenant env | `DEFAULT_TENANT_ID` / exempt lists env-default `linas` | Prior accepted platform-ops pattern; not Requests path |
| P11-004 | LOW | config_loader | Broad `except Exception` on CM publish read → None | Capture stays inactive (fail-closed for capture) |
| P11-CMAI-004 | LOW | CM/AI | Capture gate `except Exception` can fail open to wa.me | Accepted low residual; prefer honest capture inactive |
| P11-CMAI-005 | LOW | CM/AI | Tool failure may include exception text to model | Model-only; no customer leak |
| LC-P11-006 | LOW | Live Chat | Body still requires `operator_id` on some schemas | Actor from session; body field residual |
| P11-MOB-005 | LOW | Mobile | Static theme colors import | Style only |
| P11-MOB-006 | LOW | Mobile | Status chip tone always ok on detail | UX polish |
| REQ-P11-F | LOW | Requests API | manual-chat/send always obtains WA factory; Meta DM via Live Chat | Pre-existing coupling; not changed |

---

## Open actionable CRITICAL / HIGH / MEDIUM

**None.**

---

## Phase 11 exit

Inventory COMPLETE for all 1397 hand-written files. Fix loop closed for actionable findings. Proceed to Phase 12 freeze on one candidate SHA after docs commit + push.
