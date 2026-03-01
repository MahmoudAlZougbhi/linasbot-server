# Analytics Logic & Counting Rules

This document describes how analytics metrics are computed from stored events and logs. Metrics must be **accurate and consistent** with `data/analytics_events.jsonl` and `data/conversation_log.jsonl`.

---

## Data Sources

| Source | Path | Purpose |
|--------|------|---------|
| Events | `data/analytics_events.jsonl` | Append-only event log (messages, service_request, appointment, gender, feedback, escalation) |
| Conversations | `data/conversation_log.jsonl` | Q&A pairs for training; not used for analytics counts |
| Daily cache | `data/analytics_daily.json` | Legacy; analytics are computed live from events |

---

## Event Types

| Event | Fields | Logged From |
|-------|--------|-------------|
| `message` | source, msg_type, user_id, language, tokens, cost_usd, model | `text_handlers_respond`, `voice_handlers`, `photo_handlers` |
| `service_request` | user_id, service | `text_handlers_respond` when keywords match |
| `appointment` | user_id, service, status, messages_count | `chat_response_service` on create/update |
| `gender` | user_id, gender | `text_handlers_respond` when detected |
| `feedback` | user_id, feedback_type, reason | (when implemented) |
| `escalation` | user_id, escalation_type, reason | `text_handlers_respond` |

---

## New Client Metrics (Counting Logic)

### Definition: New Client

A **new client** is a user whose **first event** in the entire event history falls within the selected time range.

- `first_seen_by_user[user_id]` = earliest `timestamp` across all events for that user
- New client if: `range_start <= first_seen <= now`
- Excluded: `training`, `test`, `debug`, `internal` (test user IDs)

### # New Clients Booked

- **Count**: New clients who have at least one `appointment` event with `status="booked"`.
- **Source**: `new_client_metrics.booked_users` (set of user_ids)
- **Formula**: `len(booked_users)` where each user is in `all_new_users` and has `appointment` status=booked

### # New Clients Asked But Did Not Book

- **Count**: New clients who have at least one `service_request` event AND no `appointment` with `status="booked"`.
- **Source**: `asked_users - booked_users`
- **Formula**: `len(asked_not_booked_users)`

### Services Discussed Today

- **Count**: All `service_request` events where `event_date.date() == today`.
- **Metrics**:
  - `total_mentions`: Sum of service_request events today
  - `unique_clients`: Distinct users who had any service_request today
  - `by_service`: Per-service mentions and unique clients

### Who Booked vs Who Did Not (New Clients Only)

| List | Definition |
|------|------------|
| **Booked** | New clients with `appointment` status=booked. Each entry: `user_id_masked`, `services` (discussed + booked) |
| **Asked but not booked** | New clients with `service_request` but no `appointment` status=booked. Each entry: `user_id_masked`, `services` |
| **Not booked (all)** | New clients without any `appointment` status=booked (includes those who never asked) |

User IDs are masked for privacy: `...XXXX` (last 4 chars).

---

## Consistency Checklist

- [x] **service_request** – Logged in `text_handlers_respond` when keywords match (laser_hair_removal, tattoo_removal, co2_laser, skin_whitening, botox, fillers)
- [x] **appointment booked** – Logged in `chat_response_service` when `create_appointment` tool succeeds
- [x] **appointment rescheduled** – Logged when `update_appointment_date` tool succeeds
- [x] **first_seen** – Computed from full event history (all events, not just time range)
- [x] **new client** – First event in time range; test IDs excluded
- [x] **services_today** – Filtered by `dt.date() == today_date`
- [x] **user_id normalization** – Strip spaces, dashes; remove leading `+` for deduplication

---

## API Response Structure

```json
{
  "conversions": {
    "new_clients_booked": 5,
    "new_clients_asked_not_booked": 12
  },
  "new_clients": {
    "total_new_clients": 20,
    "booked_count": 5,
    "not_booked_count": 15,
    "asked_not_booked_count": 12,
    "booked_details": [{"user_id": "...", "user_id_masked": "...1234", "services": ["laser_hair_removal"]}],
    "asked_not_booked_details": [...]
  },
  "services_discussed_today": {
    "date": "2026-03-01",
    "total_mentions": 15,
    "unique_clients": 8,
    "by_service": [{"service": "tattoo_removal", "mentions": 10, "unique_clients": 5}]
  }
}
```

---

## Dashboard Location

Analytics is available in the **sidebar** under **Analytics** (ChartBarIcon), with permission key `analytics`. Route: `/analytics`.
