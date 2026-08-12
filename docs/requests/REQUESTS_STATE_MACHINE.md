# Requests State Machine

Server enforces all transitions. Clients may only request allowed actions; arbitrary status assignment is rejected.

---

## 1. Status vocabulary

| Status | UI group (optional) |
|--------|---------------------|
| `NEW` | Pending |
| `IN_REVIEW` | In Review |
| `WAITING_FOR_CUSTOMER` | Pending |
| `CONFIRMED` | In Review |
| `READY` | In Review |
| `COMPLETED` | Done |
| `CANCELLED` | Done |

---

## 2. Type-specific flows

### Appointment (`APPOINTMENT`)

```
NEW → IN_REVIEW → WAITING_FOR_CUSTOMER → CONFIRMED → COMPLETED
```

- Cancellation allowed from: `NEW`, `IN_REVIEW`, `WAITING_FOR_CUSTOMER`, `CONFIRMED` (not from `COMPLETED`).
- Final business action: **Confirm Appointment** → `CONFIRMED` (then later `COMPLETED` when done).
- AI wording before confirm: preferred/requested date-time; **pending owner confirmation**. Never promise availability.

### Order (`ORDER`)

```
NEW → IN_REVIEW → WAITING_FOR_CUSTOMER → CONFIRMED → READY → COMPLETED
```

- Cancellation from: `NEW`, `IN_REVIEW`, `WAITING_FOR_CUSTOMER`, `CONFIRMED`, `READY`.
- Final readiness action: **Mark as Ready** → `READY`.
- Do not promise stock/price/ETA unless configured.

### Other (`OTHER`)

```
NEW → IN_REVIEW → WAITING_FOR_CUSTOMER → COMPLETED
```

- Cancellation from: `NEW`, `IN_REVIEW`, `WAITING_FOR_CUSTOMER`.
- Final action: **Complete Request** → `COMPLETED`.

---

## 3. Shared transition rules

1. Every transition increments `row_version` (optimistic concurrency). Stale version → 409.
2. Actor must hold the required permission for the action.
3. Required fields for type-specific final actions must be present server-side.
4. `CANCELLED` / `COMPLETED` are terminal (no further status moves except notification retry metadata).
5. Moving to `WAITING_FOR_CUSTOMER` may be used when owner needs customer clarification; AI may continue only if manual mode is not active.

---

## 4. Notification vs status

| Outcome | Persistence |
|---------|-------------|
| Status change | Always committed first when valid |
| Customer notification | Separate outbox row + `notification_status` |

If notify fails after status success:

- keep new status
- set `notification_status=failed`
- store redacted `last_notification_error`
- expose Retry with idempotency key
- never auto-resend without idempotency protection

Platform policy block → `notification_status=blocked` / `DELIVERY_BLOCKED_BY_PLATFORM` event; do not switch channels silently.

---

## 5. Manual mode (conversation-scoped)

Independent of request status:

- Enter: first authorized manual send → pause AI, audit event
- Exit: Resume AI → clear pause, audit event
- In-flight AI must not send if manual mode won the race (server concurrency)
