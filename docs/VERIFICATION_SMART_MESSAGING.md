# Smart Messaging / Dashboard – Verification Guide

## Current Business Rules

All customer selection comes from external/calendar APIs only (single source of truth). Counts = `len(customers)` for that category; count and list always match.

| Category | Rule | API / Filter |
|----------|------|--------------|
| **Reminders (Daily)** | Appointments for **tomorrow**, status **Available** | `send_appointment_reminders(date=tomorrow, status=Available)` |
| **Post-session Feedback** | Appointments that happened **yesterday**, status **Done**; send at end-of-day | `send_appointment_reminders(date=yesterday, status=Done)` |
| **Missed Yesterday** | **appointment_date = yesterday**, **status = Available** (NOT Done). Customers who had an appointment yesterday but it was not completed. | `send_appointment_reminders(date=yesterday, status=Available)` |
| **20-day Follow-up** | **appointment_date = today − 20 days**, **status = Done**. Include all such customers; **do not** exclude those with future appointments. | `send_appointment_reminders(date=target_day, status=Done)` |
| **Thank You** | **Removed.** No template, no scheduling, no sending, no logging. | — |

All date logic uses **Asia/Beirut** timezone.

---

## Verification Steps

### 1. Counts and lists (dashboard)

1. Open **Smart Messaging** → **Sent Messages** tab.
2. **Counts:** Category buttons (24h Reminder, Feedback, 20-Day, Missed Yesterday) show counts from the API. Counts must be **≥ 0** and never negative.
3. Click **Refresh Counts**; counts reload from the same source as the customer lists.
4. **Lists:** Click a category (e.g. **24h Reminder**). The table must show: Status | Customer | Reason | Type | Date & Time | Details | Actions.
5. **Consistency:** For each category, `count` must equal the number of rows in the list. If count > 0, the list must not be empty; if the list is empty, count must be 0.

### 2. Missed Yesterday

- In the external system, have appointments with **date = yesterday** and **status = Available** (not Done).
- Open dashboard → **Missed Yesterday**. Count and list must include exactly those customers (yesterday + Available).
- Run the daily template dispatcher at the configured time; only those customers should receive the missed-yesterday message (with idempotency via `message_logs_service`).

### 3. 20-day Follow-up

- In the external system, have appointments with **date = today − 20 days** and **status = Done** (include customers even if they have future appointments).
- Open dashboard → **20-Day**. Count and list must include all such customers (no exclusion for future bookings).
- Run the dispatcher at the configured time; those customers should receive the 20-day message.

### 4. Thank You removed

- Dashboard: **Thank You** category/button must not appear.
- API: `GET /api/smart-messaging/counts` must not return `attended_yesterday`.
- API: `GET /api/smart-messaging/customers-by-category?category=attended_yesterday` returns empty or invalid category (no thank-you list).
- No scheduling or sending of thank-you from: `daily_template_dispatcher`, `event_handlers`, `scheduled_messages_collector`, `appointment_scheduler`.
- No thank-you–specific logging.

### 5. Backend / logs

- Trigger **Refresh Counts** or open a category; logs should show API calls to `send_appointment_reminders` with the correct `date` and `status` (no `get_missed_appointments` for Missed Yesterday).
- After the daily dispatcher runs: logs show only reminder_24h, post_session_feedback, missed_yesterday, twenty_day_followup (no attended_yesterday).
- `data/message_logs.json`: no new entries with `template_type=attended_yesterday`.

---

## Test Data Summary

| Scenario | Setup | Expected |
|----------|--------|----------|
| Reminders | 3 appointments **tomorrow**, status **Available** | Count = 3, list has 3 rows |
| Feedback | 2 appointments **yesterday**, status **Done** | Count = 2, list has 2 rows |
| Missed Yesterday | 2 appointments **yesterday**, status **Available** (not Done) | Count = 2, list has 2 rows |
| 20-day | 4 appointments **today − 20 days**, status **Done** (may have future appointments) | Count = 4, list has 4 rows |
| Thank You | — | No category, no counts, no sending |

---

## Files Touched (this update)

- **Source of truth:** `services/smart_messaging_customers_service.py` (Missed Yesterday = yesterday + Available; 20-day = today−20 + Done, no future exclusion; Thank You removed)
- **Dispatcher:** `services/daily_template_dispatcher.py` (missed_yesterday via reminders API + Available; attended_yesterday removed)
- **Catalog:** `services/smart_messaging_catalog.py` (attended_yesterday removed from DAILY_TEMPLATE_IDS, TEMPLATE_METADATA, DEFAULT_TEMPLATE_SCHEDULES)
- **API:** `modules/smart_messaging_api.py` (attended_yesterday removed from counts and message_type_names)
- **Event handlers:** `modules/event_handlers.py` (thank-you job and no-op removed)
- **Scheduler:** `services/appointment_scheduler.py` (Phase 2 thank-you block removed)
- **Dashboard:** `dashboard/src/pages/SmartMessaging.js` (Thank You category and all references removed)
