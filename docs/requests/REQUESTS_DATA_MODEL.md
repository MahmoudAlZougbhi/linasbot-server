# Requests Data Model

**Store:** PostgreSQL (WhatsApp Cloud DB URL / `DATABASE_URL` via Alembic)  
**Migration:** additive after head `20260811_wa_app_review_source`  
**Production apply:** deferred to Phase 13 (not in Phase 1)

---

## 1. Core table: `customer_requests`

| Column | Type | Notes |
|--------|------|-------|
| `id` | String(36) PK | `request_id` UUID |
| `tenant_id` | String(64) | indexed; always from auth/channel binding |
| `request_number` | String(32) | human-readable, unique per tenant |
| `request_type` | String(16) | `ORDER` \| `APPOINTMENT` \| `OTHER` |
| `status` | String(32) | see state machine |
| `source_channel` | String(32) | `instagram_dm` \| `facebook_messenger` \| `whatsapp_cloud` \| `comment_linked_dm` |
| `source_account_id` | String(128) | page / IG / WABA identity |
| `external_customer_id` | String(128) | platform PSID / WA user |
| `platform_username` | String(256) | nullable |
| `customer_display_name` | String(256) | nullable |
| `customer_name` | String(256) | nullable |
| `phone_normalized` | String(32) | nullable; E.164-ish digits |
| `email` | String(320) | nullable |
| `conversation_id` | String(128) | link to Live Chat / WA conversation |
| `originating_message_id` | String(128) | nullable |
| `originating_comment_id` | String(128) | nullable |
| `title` | String(512) | summary |
| `collected_fields` | JSON/JSONB | structured answers |
| `requested_items` | JSON/JSONB | products/services |
| `requested_branch` | String(256) | nullable |
| `preferred_date` | String(32) | nullable ISO date preference |
| `preferred_time` | String(64) | nullable preference / range |
| `fulfillment_preference` | String(32) | nullable pickup/delivery |
| `delivery_address` | Text | nullable; sensitive |
| `customer_notes` | Text | nullable |
| `assigned_user_id` | String(128) | nullable |
| `configuration_version` | String(64) | published CM version id |
| `row_version` | Integer | optimistic concurrency |
| `notification_status` | String(32) | `none` \| `pending` \| `sent` \| `failed` \| `blocked` |
| `last_notification_error` | String(512) | redacted |
| `completion_message` | Text | nullable outgoing copy |
| `cancellation_reason` | Text | nullable |
| `manual_mode_conversation_ref` | String(128) | nullable |
| `created_at` / `submitted_at` / `updated_at` | timestamptz | |
| `confirmed_at` / `ready_at` / `completed_at` / `cancelled_at` | timestamptz | nullable |

**Indexes (list/filter):**

- `(tenant_id, status, created_at DESC)`
- `(tenant_id, request_type, created_at DESC)`
- `(tenant_id, assigned_user_id, created_at DESC)`
- `(tenant_id, source_channel, created_at DESC)`
- `(tenant_id, request_number)` unique
- `(tenant_id, phone_normalized)` where phone not null
- `(tenant_id, conversation_id)`

---

## 2. Supporting tables

### `customer_request_events` (audit / timeline)

- `id`, `tenant_id`, `request_id` FK
- `event_type` (status_change, assignment, note, notification, manual_pause, manual_resume, customer_confirm, create, cancel, …)
- `actor_user_id`, `actor_kind` (`system` \| `ai` \| `operator` \| `customer`)
- `payload` JSON (no raw secrets; PII minimized)
- `created_at`
- Index `(tenant_id, request_id, created_at)`

### `customer_request_notes`

- `id`, `tenant_id`, `request_id`, `author_user_id`, `body`, `created_at`
- Internal only; never sent to customer automatically

### `customer_request_outbox`

- Durable notification jobs: `id`, `tenant_id`, `request_id`, `idempotency_key` (unique), `channel`, `payload`, `status`, `attempts`, `last_error`, `created_at`, `sent_at`
- Status update and notification are separate outcomes

### `customer_request_idempotency`

- `id`, `tenant_id`, `scope`, `key` (unique with tenant+scope), `request_id`, `response_fingerprint`, `created_at`
- Covers AI create, confirm actions, notification send/retry

### `customer_request_counters` (optional sequence)

- `tenant_id` PK, `next_number` Integer — allocate human-readable request numbers without full-table scan

---

## 3. CM published config (filesystem, not Postgres)

Section key: `requests_appointments`

Published JSON (illustrative):

```json
{
  "module_enabled": false,
  "enabled_types": [],
  "type_labels": {},
  "fields": [],
  "services": [],
  "products": [],
  "branches": [],
  "messages": {
    "acknowledgment": "",
    "appointment_confirmed": "",
    "order_ready": "",
    "completed": "",
    "cancelled": ""
  },
  "notification_language": "auto",
  "push_enabled": true
}
```

Draft must not affect customer AI until publish.

---

## 4. Why not Firestore for request rows

Firestore remains conversation SoT. Request list/filter/assign/audit needs relational indexes, check constraints, and optimistic concurrency already used by WhatsApp Cloud Postgres models. Linking by `conversation_id` avoids duplicating transcripts.
