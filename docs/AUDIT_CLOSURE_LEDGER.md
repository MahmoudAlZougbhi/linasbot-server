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


## Wave 3 — Metrics / UI honesty / RBAC UX

| ID | Status | Evidence |
|---|---|---|
| V2-MET-001 fake neutral sentiment | CLOSED | No default `sentiment="neutral"` logging; aggregate ignores unlabeled neutral |
| V2-MET-002 satisfaction mapping | CLOSED | like/dislike type sets in `analytics_events.py` |
| V2-MET-003 analytics errors as zeros | CLOSED | Analytics UI error+retry; aggregate returns `success:false` |
| V2-MET-004 Smart Messaging counts fail-open | CLOSED | `countsError` + dash display |
| V2-UI-001 client-only RBAC gaps | CLOSED | contentManagers/activityFlow in FE+BE; chatHistory removed |
| V2-UI-002 Live Chat mock / operator | CLOSED | mock fabrication removed; operator from session |
| Dead Register | CLOSED | route removed; `Register.js` deleted |
| Orphan Chat History | CLOSED | route/permission removed; page deleted |
| Fake API-key test | CLOSED | redacted `/api/settings/integrations` + health check |
| Dead language toggles | CLOSED | read-only language list |
| Fake All Systems Online | CLOSED | Sidebar polls `/api/health` |
| Duplicate /analytics | CLOSED | redirects to `/` |
| Ungated APK | CLOSED (W1) | session + liveChat permission |
| Activity Flow naming | CLOSED | Interaction Logs |
| Catch-all 404 | CLOSED | `NotFound.js` |
| Forgot-password fake | CLOSED | removed from Login |

Tests: `tests/test_wave3_metrics.py` (+ waves 1–2) — 38+ passed with `OPENAI_API_KEY` set for app import.


## Wave 4 — Reliability / concurrency / privacy / readiness

| ID | Status | Evidence |
|---|---|---|
| V2-REL-001 process-local state | CLOSED (partial→durable) | `durable_event_claim.py` + pending smart queue file + scheduler locks |
| Meta MID claim-before-success | CLOSED | claim + complete/release in `meta_messaging_webhook.py` |
| Message array RMW | CLOSED | Firestore transactional append in `utils.py` |
| Smart Messaging RAM queue | CLOSED | `PENDING_SMART_MESSAGES_FILE` persist/reload |
| Preview-mode bypass | CLOSED | empty exempt set; monitor returns when preview on |
| Campaign freeform send | CLOSED | `deliver_scheduled_smart_whatsapp` + template required |
| Scheduler multi-instance | CLOSED | file job locks for monitor/dispatcher |
| Fail-open claims | CLOSED | file fallback fail-closed for AI turn + webhook claims |
| Health readiness | CLOSED | public `/api/ready` with dependency checks |
| PII logging | CLOSED | flow logger masks phone; full prompts opt-in only |
| Unbounded rate map | CLOSED | prune empty trackers in moderation_service |

Tests: `tests/test_wave4_reliability.py` — 7 passed.

External still required: provider Monty key rotation; Redis/Postgres remain unused (no new infra introduced).


## Wave 5 — QA / CI / cleanup

| ID | Status | Evidence |
|---|---|---|
| V2-QA-001 no CI quality gate | CLOSED | `.github/workflows/quality-gates.yml` |
| Baseline pytest failures | CLOSED | conftest + pytest-asyncio; manual Monty/appointment probes moved to `scripts/` |
| Language detection assertion | CLOSED | match `clean()` normalize spaces |
| Frontend tests | CLOSED | MobileLiveChat mock + permissions tests |
| Frontend build / code split | CLOSED | lazy routes in `App.js` (multiple chunks) |
| Formatter/lint/typecheck | CLOSED | ruff + mypy scoped gates on security/reliability core |
| Dead `frontend/` stub | CLOSED | removed |
| Dead unmounted `routes/` | CLOSED | removed (live chat uses `modules/live_chat_api`) |
| Unused PermissionGate | CLOSED | removed |
| Unused Compose Redis/Postgres | CLOSED | removed from compose + prod compose |
| npm vulns | CLOSED (critical) | overrides + audit-level=critical gate; CRA transitive high leftovers remain tooling-only |
| Secret scan | CLOSED | quality-gates + security-checks |

Backend suite: **175 passed**, 0 failed, 0 errors (local).
Frontend: **3 passed**, production build OK with route chunks.
