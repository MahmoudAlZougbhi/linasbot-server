# Lina’s Laser — Agent API & booking IDs (reference)

This document complements `AGENT_API_DOCUMENTATION.pdf` and matches the **strict booking pipeline** in `services/booking/`.

## HTTP base

- Config: `LINASLASER_API_BASE_URL`, `LINASLASER_API_TOKEN` (Bearer).
- Client: `services/api_integrations.py` → `httpx.AsyncClient`.

### Body-parts GET (path quirks)

Some hosts return HTML 404 for `GET body-parts` while other routes work. The client tries **`LINASLASER_GET_BODY_PARTS_PATH`** (if set), then `body-parts`, then `body_parts`.

For **laser tattoo removal (service 13)** only, if the list stays unavailable, you may set **`LINASLASER_TATTOO_BODY_SYNONYMS_JSON`** so the booking resolver can map user phrases to a CRM id, e.g. `{"ra2be":5,"رقبة":5,"neck":5,"عنق":5}` (replace `5` with the real id from your CRM).

## Endpoints used for booking

| Method | Path | Role |
|--------|------|------|
| GET | `branches` | Resolve `branch_id` / names |
| GET | `services` | Resolve `service_id` / names |
| GET | `machines` | Resolve `machine_id` / names |
| GET | `body-parts?service_id=` | Map body area → `body_part_id` |
| GET | `customers/...` (by phone) | Ensure customer exists before create |
| POST | `customers/create` (via `create_customer`) | New file when needed — **`branch_id` always sent** (callers may omit arg → `config.DEFAULT_BRANCH_ID`; invalid/missing resolved id → no HTTP call, structured error) |
| POST | `appointments/create` | **Authoritative** booking creation |

## Reschedule + clearing **Paused** status

`POST appointments/update/date` may only change the datetime while the CRM row stays **Paused**. After a **successful** date update, this bot calls **`resume_appointment`** (same phone + `appointment_id` as `appointments/pause`):

- **Default POST path:** `appointments/resume` (when `LINASLASER_APPOINTMENT_RESUME_PATH` is unset).
- **Override path:** set `LINASLASER_APPOINTMENT_RESUME_PATH` (e.g. `appointments/unpause`) if your Agent API uses a different route.
- **Disable follow-up:** set `LINASLASER_APPOINTMENT_RESUME_PATH=off` (or `0` / `false` / `none`).
- **Same-request alternative (CRM-dependent):** set `LINASLASER_UPDATE_DATE_SET_STATUS_AVAILABLE=1` to add `"status": "Available"` to the `appointments/update/date` JSON (only if your API accepts it).

The tool result for `update_appointment_date` includes **`resume_appointment`**: `attempted`, `success`, `path`, `message` — the model uses this to tell the user whether the slot should now show as active.

## POST `appointments/create` — payload shape (this bot)

The Python client in `api_integrations.create_appointment` sends JSON with at least:

- `phone`, `service_id`, `machine_id`, `branch_id`, `date` (strings/ints as today)
- Optional `user_code`
- **`body_part_ids`**: top-level array of integers (PDF contract). All selected areas from **`get_body_parts`** are included here for multi-area bookings.

**Legacy fallback:** If `LINASLASER_CREATE_APPOINTMENT_LEGACY_BODY_PARTS=1` (env), or if callers pass `body_parts_with_sessions` with any **`session_number` ≠ 1**, the client sends **`body_parts`** instead so session metadata is preserved.

## POST `appointments/branch/move`

This bot’s `move_client_branch` sends `phone`, `from_branch_id`, `to_branch_id`, `response`, optional `user_code`, and includes **`new_date` only when** a non-empty date string is provided (omitted otherwise).

### Not exposed as a dedicated “slot search” call

- **Real-time free-slot search** is **not** implemented as a separate GET in this bot. Availability is enforced by:
  1. Local **`validate_booking_slot`** (`utils/appointment_slot_rules.py`) — day/time/gender/branch/service/machine rules in **Asia/Beirut–aligned** fixed offset (`BOT_FIXED_TZ`, UTC+02:00 as used in code).
  2. **CRM response** from `POST appointments/create` (success / error message).

If you need explicit “list free slots” for a resource, the Agent API would need a new endpoint; until then, treat **`appointments/create`** as the final availability check.

## Canonical IDs (bot-side constants)

Defined in `services/booking/constants.py` and `utils/appointment_slot_rules.py` (keep in sync):

| Concept | IDs / notes |
|---------|-------------|
| Branch Beirut | `1` |
| Branch Antelias | `2` |
| Laser hair removal — men | `1` |
| Laser hair removal — women | `12` |
| Laser tattoo removal | `13` |
| CO2 (scars / stretch marks / acne scars) | `2`, `11` |
| Whitening / DPL | `4`, `5`, `14` |

## Machine IDs (hair vs tattoo)

- **Hair-class devices** (Neo / Quadro / Candela / Trio mapping in CRM) are tracked in code as **`HAIR_REMOVAL_MACHINE_IDS`** (`services/chat_response_service.py` / `services/booking/constants.py`): default set `{9, 10, 13, 15}` — **verify against live `GET machines` on your CRM**; IDs can change.
- **Tattoo** should use a **Pico**-labeled machine when present in `GET machines` (`pick_pico_or_default_machine` in `services/booking/resolver.py`).
- **Candela-only branch rules** for women’s hair: see `APPOINTMENT_CANDELA_MACHINE_IDS` env in `utils/appointment_slot_rules.py`.

## Strict pipeline (`submit_booking_intent`)

1. Model calls **`submit_booking_intent`** with extraction JSON (IDs optional).
2. **`handle_submit_booking_intent`** (`services/booking/intent_pipeline.py`):
   - Merges gender from intent or session.
   - Loads **live** branches/services/machines from API.
   - Resolves names → IDs (deterministic fuzzy match).
   - Resolves **`body_part_ids`** via `GET body-parts`.
   - Builds datetime from `date` / `date_components` / normalized / raw text + `calendar_day_intent`.
   - Ensures customer record (`get_customer_by_phone` → `create_customer` if needed + name).
   - Runs **`validate_booking_slot`**.
   - Optional CO2 vs whitening text guard (`booking_service_mapping`).
   - If all pass and **`execute_booking`**: **`POST appointments/create`**.
3. **Logging**: each attempt logs `[BOOKING_PIPELINE] { ... }` with user text, extraction, normalized payload, validation outcome, endpoint payload/response.

## Booking state (`config.user_booking_state[user_id]`)

- `booking_flow_state`: `ready_for_validation` | `needs_clarification` | `validation_failed` | `ready_to_book` | `booked`
- `last_booking_intent`, `last_validation_error`, `last_booking_success` (on success)

## Timezone

- User-facing policy: **Asia/Beirut**.
- Implementation: fixed **`BOT_FIXED_TZ`** (`utils/datetime_utils.py`, UTC+02:00). No DST transition in this layer—align with clinic operations if you need historical DST correctness.
