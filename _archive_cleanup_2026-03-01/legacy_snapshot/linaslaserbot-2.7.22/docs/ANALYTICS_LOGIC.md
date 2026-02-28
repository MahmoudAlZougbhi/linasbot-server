# Analytics Counting Logic & Checklist

## Data Sources

| Source | Path | Purpose |
|--------|------|---------|
| Events | `data/analytics_events.jsonl` | Append-only event log (messages, service_request, appointment, gender, feedback, escalation) |
| Conversation log | `data/conversation_log.jsonl` | Legacy Q&A log (not used for analytics aggregation) |

## Event Types

| Type | Fields | When Logged |
|------|--------|-------------|
| `message` | source, msg_type, user_id, language, tokens, cost_usd, response_time_ms | Every user/bot message (text_handlers_respond, voice_handlers, photo_handlers) |
| `service_request` | user_id, service | When user/bot text mentions service keywords (text_handlers_respond) |
| `appointment` | user_id, service, status, messages_count | When create_appointment or update_appointment_date tool succeeds (chat_response_service) |
| `gender` | user_id, gender | When GPT detects gender |
| `feedback` | user_id, feedback_type, reason | User feedback |
| `escalation` | user_id, escalation_type, reason | Human handover, complaint, etc. |

## New Client Metrics (Counting Logic)

### Definition: "New Client"
- **New client** = User whose **first event** (across all event types) in the entire history falls **within the selected time range**.
- Built from `first_seen_by_user` index: for each user, the earliest `timestamp` across all events.

### Metrics

| Metric | Logic | Source |
|--------|-------|--------|
| **# new clients booked** | Count of new clients who have at least one `appointment` event with `status="booked"` | `booked_users` |
| **# new clients asked but did not book** | Count of new clients who have at least one `service_request` event AND no `appointment` with `status="booked"` | `asked_users - booked_users` |
| **Total new clients** | Count of users with `first_seen` in range | `all_new_users` |
| **Who booked** | List of new clients with `status=booked`, with services discussed/booked | `booked_details` |
| **Who asked but did not book** | List of new clients with `service_request` but no `booked` | `asked_not_booked_details` |

### Services Discussed Today

| Metric | Logic |
|--------|-------|
| **Services discussed today** | All `service_request` events where `event_date.date() == today` |
| **By service** | Group by `service`, count mentions and unique `user_id` |
| **Unique clients** | Distinct users who had any service_request today |

## User ID Normalization

- `+9613000001`, `9613000001`, `961 30 000 01` → normalized to `9613000001`
- Ensures same person is not double-counted across sessions.

## Consistency Checklist

- [ ] **Events file exists** – `data/analytics_events.jsonl` is created on first write
- [ ] **User ID normalization** – All events use `_normalize_user_id()` before storage/dedup
- [ ] **First-seen index** – Built from **all** events (not filtered by days) for accurate "new client" detection
- [ ] **service_request** – Logged in `text_handlers_respond` when keywords match
- [ ] **appointment booked** – Logged in `chat_response_service` when `create_appointment` tool succeeds
- [ ] **appointment rescheduled** – Logged when `update_appointment_date` tool succeeds
- [ ] **Services today** – Filtered by `dt.date() == today_date` (server local date)

## API Response Structure

```json
{
  "success": true,
  "overview": { "total_messages", "total_users", "new_users", ... },
  "conversions": {
    "new_clients_booked": 0,
    "new_clients_asked_not_booked": 0,
    ...
  },
  "new_clients": {
    "total_new_clients": 0,
    "booked_count": 0,
    "asked_not_booked_count": 0,
    "booked_details": [{ "user_id", "services" }],
    "asked_not_booked_details": [{ "user_id", "services" }],
    ...
  },
  "services_discussed_today": {
    "date": "YYYY-MM-DD",
    "total_mentions": 0,
    "unique_clients": 0,
    "by_service": [{ "service", "mentions", "unique_clients" }]
  },
  ...
}
```

## Dashboard Display

- **New Clients: Booked vs Asked (Not Booked)** – Shows `booked_count`, `asked_not_booked_count`, and sample lists (user IDs masked)
- **Services Discussed Today** – Shows date, unique clients, total mentions, and per-service breakdown
