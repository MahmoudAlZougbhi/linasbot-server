# Requests Security Model

---

## 1. Tenant authority

- `tenant_id` comes only from authenticated session or verified channel binding.
- Client-supplied tenant is never authoritative.
- Every query filters by `tenant_id`; wrong-tenant IDs return 404 (no oracle).

---

## 2. Permission keys (RBAC)

Extend existing camelCase `PERMISSION_KEYS` (backend / mobile / web mirrors):

| Key | Capability |
|-----|------------|
| `requests` | View list/details (non-sensitive fields) |
| `requestsManage` | Assign, notes, status transitions, cancel |
| `requestsNotify` | Preview/edit/send/retry customer notifications |
| `requestsManualChat` | Chat with customer; pause/resume AI |
| `requestsSensitive` | View raw phone, email, delivery address, technical IDs |

Role defaults:

- `admin` / `platform_owner`: all true
- `operator`: `requests`, `requestsManage`, `requestsNotify`, `requestsManualChat` true; `requestsSensitive` false (unless custom)
- `viewer`: all false (or `requests` view-only if tenant grants custom)

UI hiding is not security. APIs call `require_permission` / domain checks.

---

## 3. AI tool security

Customer AI creates requests only via a server-side structured tool that enforces:

- verified tenant + channel ownership
- conversation ownership
- published configuration version
- required fields
- customer confirmation flag
- idempotency + webhook event dedupe
- no cross-tenant writes
- no direct arbitrary storage writes from the model

---

## 4. PII and comments

- Never collect or echo phone/email/address/private order details in public IG/FB comments.
- Public reply: safe invite to continue in DM only.
- Private fields only in DM; link comment id + conversation id on the request.
- List cards omit full phone/address; details require `requests` (+ `requestsSensitive` for raw contact).

---

## 5. Manual chat

- Authenticated actor identity only (no spoofed operator ids).
- Server owns pause/resume; no local-only takeover SoT.
- Prevent AI and operator simultaneous send (epoch / lock).
- Cross-tenant conversation access denied.

---

## 6. Audit

All create/status/assign/note/notify/manual events append to `customer_request_events` with actor and timestamp. Audit payloads redact secrets and minimize PII.

---

## 7. Export / deletion

Tenant data export and Meta/user deletion flows must include Requests rows (and notes/events/outbox) scoped to that tenant/customer, consistent with existing privacy tooling.
