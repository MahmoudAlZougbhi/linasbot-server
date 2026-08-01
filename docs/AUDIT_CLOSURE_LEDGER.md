# Audit Closure Ledger

Baseline: `main` @ `709c296`. Branch: `fix/audit-closure-waves`.

## Explicit exclusions (not fixed)

| ID | Status |
|---|---|
| V2-AI-001 dual FAQ/content SoT | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |
| Dead FAQ top-three knowledge-store redesign | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |
| conversation_log training architecture redesign | USER-EXCLUDED — KNOWLEDGE ARCHITECTURE DECISION PENDING |

## Wave 1 — Security

| ID | Status | Evidence |
|---|---|---|
| V2-SEC-001 | CLOSED | `modules/api_security.py` deny-by-default middleware + RBAC |
| V2-SEC-002 | CLOSED | `services/ssrf_guard.py` + `modules/media_api.py` |
| V2-SEC-003 | CLOSED | `services/safe_path.py` + restore handlers |
| V2-SEC-004 | CLOSED | simulate-webhook disabled unless explicit non-prod flag |
| V2-SEC-005 | CLOSED | Auth middleware on smart-messaging |
| V2-SEC-006 | CLOSED | Auth + social mutation reject + Live Chat UI read-only social |
| V2-SEC-007 | CLOSED | No default admin123; bootstrap token only |
| V2-SEC-008 | CLOSED | `/api/auth/session` cookie-bound; path IDOR denied |
| V2-SEC-009 | CLOSED | Monty key removed from tracked JSON; env `MONTYMOBILE_API_KEY` |
| V2-SEC-010 | CLOSED | docs/redoc/openapi disabled in production |
| V2-SEC-011 | CLOSED | WhatsApp webhook requires signature or ingest secret (prod) |
| Client RBAC gaps | CLOSED | PATH_TO_PERMISSION + server permissions |
| Rate limits | CLOSED | `services/rate_limit_service.py` |
| CSRF/session cookies | CLOSED | HttpOnly session + CSRF header |
| False delivery success (send) | CLOSED | adapter failure returns success:false |
| Tracked default password UI/docs | CLOSED | removed |

Tests: `tests/test_wave1_security.py` — 20 passed.


## Wave 2 — Social AI / channel / Testing Lab

| ID | Status | Evidence |
|---|---|---|
| V2-AI-002 hours/مواعيد | CLOSED | `is_appointment_request` hours exclusion |
| V2-AI-003 personal care | CLOSED | bare `person` keyword removed + personal guard |
| V2-AI-004 Arabic human | CLOSED | patterns + keywords for احكي مع حدا |
| V2-AI-005 Arabizi booking | CLOSED | `bade a7jez` patterns |
| V2-AI-006 Testing Lab parity | CLOSED | `channel=instagram\|facebook` → `process_meta_social_event(simulation=True)` |
| V2-OPS-001 false delivery | CLOSED (W1) | adapter-bound success |
| force_intent leak scrub | CLOSED | clear booking-flavored reply when declined |
| Contact matrix | CLOSED | tests assert exact wa.me numbers |

Tests: `tests/test_wave2_social_routing.py` + wave1 — 31 passed.
