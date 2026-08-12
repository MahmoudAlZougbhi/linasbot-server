# Requests System Design

**Module (EN):** Requests  
**Module (AR):** طلبات العملاء  
**Branch:** `chore/project-cleanup-reorg`  
**Decision date:** 2026-08-12

---

## 1. Purpose

Give each tenant an optional, publishable customer-request workflow for:

- **Orders**
- **Appointment Requests** (preference until owner Confirm)
- **Other** configurable request types

Operators manage work items in the Expo app. Customer AI captures structured requests only after the tenant publishes Requests configuration. Manual chat can pause AI for a conversation without auto-handover.

---

## 2. Canonical stores (existing conventions)

| Concern | Store | Why |
|---------|-------|-----|
| Request entities, audits, outbox, idempotency | **PostgreSQL** (Alembic) | Structured work items: status, assignee, filters, concurrency, indexes — same pattern as WhatsApp Cloud SoT |
| Conversation transcripts / Live Chat index | **Firestore** | Existing Live Chat SoT; Requests **links** to conversation IDs, does not duplicate message bodies |
| Publishable Requests & Appointments setup | **Filesystem CM** under `LINASBOT_DATA_ROOT` | Same draft → version → publish pointer as other CM sections |
| BOC / LinasLaser Agent API | External HTTP (runtime **OFF**) | Isolated; no Requests status action calls BOC in this release |

**No second source of truth:** Postgres owns request rows; CM owns published config; Firestore owns chat messages.

---

## 3. High-level components

```
Customer channels (IG DM / FB / WA Cloud / comment→DM)
        │
        ▼
Customer Reply / request capture engine
        │  (structured tool only; after customer confirm)
        ▼
PostgreSQL Requests domain
        │
        ├── Operator APIs (/api/requests*)
        ├── Notification outbox → channel delivery
        └── Link → Live Chat conversation (Firestore / WA PG control)

AI Setup CM section: requests_appointments (draft→publish)
Expo: Requests module + Live Chat manual mode
```

---

## 4. Product rules (locked)

1. **Optional per tenant** — AI capture inactive until published config; UI may show Setup required.
2. **No forced wa.me booking handoff** for order/appointment intent.
3. **Appointment = preference** until `Confirm Appointment`.
4. **Orders** — no stock/price/ETA promises unless configured.
5. **Manual chat** — explicit action only; server-authoritative pause/resume; never AI+owner simultaneous.
6. **BOC** — code-ready, default OFF, zero network when disabled.
7. **Landing-only web** — no operator SPA restore; Expo is operator product.
8. **No hidden fallbacks** between providers or booking systems.

---

## 5. Package layout (backend)

All hand-written files ≤500 LOC.

```
db/models/requests.py              # core ORM
db/models/requests_support.py      # audit/outbox/idempotency ORM
alembic/versions/*_customer_requests.py
services/requests/
  constants.py
  state_machine.py
  permissions.py
  schemas.py
  repository.py
  service.py
  outbox.py
  ai_tool.py
  config_loader.py                 # reads published CM section
modules/requests_api.py            # FastAPI routes (thin)
```

---

## 6. Configuration lifecycle

1. Owner configures **Requests & Appointments** in CM (draft).
2. Preview / diff / approve / publish (existing CM gate).
3. Published version id stamped on each new request (`configuration_version`).
4. Disable or unpublish → new AI capture stops; existing requests remain manageable.

---

## 7. Out of scope this release

- Activating BOC booking in production
- TikTok connector
- Restoring operator web Live Chat SPA
- Inventing unsupported channel media types
