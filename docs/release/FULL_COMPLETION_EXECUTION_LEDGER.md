# FULL COMPLETION EXECUTION LEDGER

**Owner authorization:** Master Execution Prompt (2026-08-12)  
**Repo:** `/Users/alzoughbi/linasbot-server`  
**Branch:** `chore/project-cleanup-reorg`  
**PR:** [#240](https://github.com/MahmoudAlZougbhi/linasbot-server/pull/240) → `main`  
**Last green app baseline (pre-Requests):** `72d1d439b589f4d111b0a4cc7cd61030ceaca677`  
**Ledger started:** 2026-08-12

---

## Phase status overview

| Phase | Name | Status |
|------:|------|--------|
| 0 | Finish PR #240 CI | **DONE** |
| 1 | Requests architecture + data model | **DONE** (prod migration not applied) |
| 2 | Backend domain + APIs | **IN_PROGRESS** (core APIs + tests landed) |
| 3 | AI Setup Requests & Appointments | **DONE** |
| 4 | Customer AI request flow | PENDING |
| 5 | Mobile Requests module | **DONE** |
| 6 | Chat with customer / manual mode | PENDING |
| 7 | Channel delivery | PENDING |
| 8 | BOC isolation (default OFF) | **DONE** |
| 9 | Security/correctness/performance tests | PENDING |
| 10 | Independent review + PR closeout | PENDING |
| 11 | Full file-by-file reinspection | PENDING |
| 12 | Final freeze | PENDING |
| 13 | Production preparation | PENDING |
| 14 | Merge PR #240 + deploy | PENDING |
| 15 | Live post-deploy smoke | PENDING |
| 16 | Mobile distribution (EAS) | PENDING |
| 17 | Final live revalidation | PENDING |
| 20 | Final deliverables `docs/release/*` | PENDING |
| 21 | Verdict | PENDING |

---

## Phase 0 — Finish PR #240 CI

| Field | Value |
|------|-------|
| Starting SHA | `027047f24cf21a011799340628063fe41e475e1f` |
| Ending SHA | `027047f24cf21a011799340628063fe41e475e1f` |
| Status | **DONE** (no CI fix required) |

All Quality Gates + Security Checks SUCCESS on PR head. No merge.

---

## Phase 1 — Requests architecture + data model

| Field | Value |
|------|-------|
| Starting SHA | `027047f24cf21a011799340628063fe41e475e1f` |
| Status | **DONE** |
| Store | PostgreSQL (Alembic after `20260811_wa_app_review_source`); CM config filesystem; chat remains Firestore |

### Artifacts

- `docs/requests/REQUESTS_SYSTEM_DESIGN.md`
- `docs/requests/REQUESTS_DATA_MODEL.md`
- `docs/requests/REQUESTS_STATE_MACHINE.md`
- `docs/requests/REQUESTS_SECURITY_MODEL.md`
- `alembic/versions/20260812_customer_requests.py` (additive; **not applied to prod**)
- `db/models/requests.py`, `db/models/requests_support.py`

### Production migration

- **Not applied** (Phase 13).

---

## Phase 2 — Backend domain + APIs

| Field | Value |
|------|-------|
| Status | **IN_PROGRESS** |
| Tests | `tests/test_customer_requests.py` — 5 passed |

### Landed

- `services/requests/*` (constants, state_machine, repository, service, schemas, serialize, config_loader, permissions)
- `modules/requests_api.py` mounted from `main.py`
- RBAC keys mirrored: backend + dashboard + mobile
- Path gate: `/api/requests*` → `requests`

### Still needed in Phase 2–7

- AI create tool wiring, outbox delivery workers, channel send adapters
- Mobile Requests UI
- Manual chat pause/resume server authority
- Remove forced wa.me appointment/order handoff when Requests capture active

---

## Phase 3 — AI Setup Requests & Appointments

| Field | Value |
|------|-------|
| Starting SHA | `b90861f` (Phase 2 head) |
| Ending SHA | `c93ec455edda605460289bf16e1053aa9792176c` |
| Status | **DONE** |
| Tests | `tests/test_cm_requests_appointments.py` + related CM guides — 37 passed |

### Landed

- CM section key `requests_appointments` in `CM_SECTIONS` (defaults: `module_enabled=false`, `enabled_types=[]`)
- Schema: `services/cm/schemas_requests.py` → re-exported via `services/cm/schemas.py`
- Draft → preview/diff → approval → publish path via existing CM machinery (`SECTION_MODELS`, section guide, setup chat prompt, progress optional-done)
- Mobile AI Setup hub registration + `RequestsAppointmentsEditor`
- Capture remains inactive for missing/unpublished/disabled published config (`config_loader.requests_capture_active`)

### Not changed

- `services/requests/service.py` APIs
- BOC / booking
- Mobile Requests list screens (other ownership)

---

## Phase 5 — Mobile Requests module

| Field | Value |
|------|-------|
| Starting SHA | `41f8f7853357a1d9c31976e186b4c7fc26b9d845` |
| Ending SHA | `62ce92d658970f5e0b6a5dd7c8d0d8ed72abc7a7` |
| Status | **DONE** |
| Tests | `mobile/linas-ai`: `npm run typecheck` + `npm test` — **103 passed** |

### Landed

- Expo module `features/requests/*` against `/api/requests*` (list, get, assign, notes, final-action, notify-retry, setup-status)
- Drawer tile **Requests / طلبات العملاء** with keep-mounted screen + permission gate (`requests`)
- Home: status counters, type/status/platform/assignee/date filters, search, cursor pagination, pull-to-refresh, loading/empty/error/offline/setup-required
- Cards omit full phone/address; detail shows permitted fields, timeline, notes, assign, type-specific final actions with message preview, notify retry
- Chat with Customer → existing Live Chat (`external_customer_id` + `conversation_id`)
- i18n EN/AR/FR (`requestsEn|Ar|Fr`); UserFormModal permission labels for Requests keys

### Not changed

- Operator web SPA (not restored)
- Server/infra/migrations
- Manual chat pause/resume authority (Phase 6)
- Channel delivery / outbox workers (Phase 7)

---

## Phase 8 — BOC isolation (default OFF)

| Field | Value |
|------|-------|
| Starting SHA | (pre-Phase-8 branch head) |
| Ending SHA |  |
| Status | **DONE** |
| Gate | `LINASLASER_BOC_BOOKING_ENABLED` default **false** via `services/product_features.boc_booking_enabled()` |
| Production | **Not enabled** |

### Files

- `services/product_features.py` — single gate + readiness/disabled payloads
- `services/api_integrations_http.py` — zero HTTP when OFF
- `modules/dashboard_api_health.py` — `/api/ready` `boc_booking` check
- `services/chat_response_runtime_gpt.py` / `*_tool_execute.py` / `*_tool_submit.py` — tools withheld/refused
- `services/booking/intent_pipeline.py`, `intent_pipeline_crm.py` — submit/create refuse when OFF
- `services/appointment_scheduler*.py`, `modules/event_handlers_populate_jobs.py` — no job start
- `docs/requests/BOC_FUTURE_INTEGRATION.md`, `.env.example`, `docs/PREDEPLOY_ENV_CHECKLIST.md`
- `tests/test_boc_booking_isolation.py`

### Tests

```text
.venv/bin/python -m pytest tests/test_boc_booking_isolation.py \
  tests/test_wave3_saas_generics.py tests/test_dashboard_api_loc_split.py \
  tests/test_appointment_scheduler_loc_split.py \
  tests/test_wave4_reliability.py::TestReadyEndpoint \
  tests/test_product_modules_disabled.py -q
# → 25 passed
```

### Not changed

- BOC repository / live BOC servers
- Production migrations
- `services/requests/*` domain
- Mobile UI / CM section schemas

---

## Resume notes

Continue Phase 2 remaining + Phases 4–7, 9+. Do not merge until Phase 13 ready.
Do not enable `LINASLASER_BOC_BOOKING_ENABLED` in production.
