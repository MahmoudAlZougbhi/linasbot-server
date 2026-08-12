# BOC / LinasLaser Agent booking — future integration

**Status:** Code preserved, **runtime DISABLED by default**. Do **not** enable in production without explicit owner approval.

## Single gate

| Item | Value |
|------|--------|
| Env flag | `LINASLASER_BOC_BOOKING_ENABLED` |
| Default | **off** (`false` / unset) |
| Source of truth | `services/product_features.py` → `boc_booking_enabled()` |
| Related helpers | `legacy_booking_tools_disabled()`, `boc_appointment_jobs_allowed()`, `boc_booking_readiness()`, `boc_disabled_response()` |

Truthy values only: `1`, `true`, `yes`, `on` (case-insensitive).

## When OFF (default)

Honest zero network — no silent fallback to another booking system:

- No BOC HTTP (`services/api_integrations_http._make_api_request` and update-status POST)
- No BOC appointment scheduler populate work / job start
- No customer AI booking/CRM tools offered or executed
- No token or booking-ID requirement for process health
- `GET /api/ready` reports `checks.boc_booking.enabled=false`, `ok=true`, `booking_ids_required=false`, `token_required=false`

Disabled call sites return `error: boc_booking_disabled` with an explicit message (not an alternate provider).

## When ON (future / non-prod only)

Set:

```bash
LINASLASER_BOC_BOOKING_ENABLED=true
LINASLASER_API_BASE_URL=https://<boc-agent-host>/agent/
LINASLASER_API_TOKEN=<token>
# optional aliases: EXTERNAL_API_BASE_URL / EXTERNAL_API_TOKEN
```

Then:

- Booking tools may be exposed to the model
- `_make_api_request` performs real HTTP
- Appointment populate jobs may run
- `/api/ready` requires base URL + token (`booking_ids_required=true`)

Contract tests should mock HTTP — never point CI at live BOC servers.

## Preserved code (do not delete)

- `services/api_integrations*`
- `services/booking/*`
- `services/appointment_scheduler*`
- Tool schemas under `utils/utils_tools_*`
- Docs such as `docs/BOOKING_AGENT_API_REFERENCE.md`

## Out of scope for this gate

- Editing the separate BOC repository or live BOC hosts
- Production activation
- Customer Requests domain (`services/requests/*`) — Requests must not call BOC while this gate is OFF

## Activation checklist (owner only)

1. Approve non-prod enablement (never silent).
2. Set credentials + `LINASLASER_BOC_BOOKING_ENABLED=true` in that environment only.
3. Confirm `/api/ready` `boc_booking.ok=true`.
4. Run mocked + staging contract tests.
5. Do **not** enable on production until a separate owner-approved release.
