# WhatsApp Cloud API + Embedded Signup v4 + Business App Coexistence

Production two-phase package for Mahmoud. **Do not execute Meta Console mutations from this doc as an agent task** — human/operator only.

## Architecture (data flow)

1. Mobile Integrations → `POST /api/whatsapp/cloud/connect/start` (authz: owner/admin + pilot entitlement **or** public switch + flags).
2. Bridge page `/integrations/whatsapp/embedded-signup` (noindex) launches Meta Embedded Signup with `featureType=whatsapp_business_app_onboarding` and dedicated `META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID` (never FB/IG Login config).
3. Callback `/oauth/whatsapp/callback` exchanges code server-side, verifies WABA/phone ownership, encrypts token (AES-GCM), persists PostgreSQL binding, subscribes WABA webhooks.
4. Mobile returns to `linasai://integrations?wa_connection=…` (never Operator Login / `/settings`).
5. Inbound: `GET/POST /webhook/whatsapp-cloud` — App A `X-Hub-Signature-256` on raw body → resolve tenant by `phone_number_id` → durable claim → process.
6. Customer inbound → Customer Reply V2 (published CM) → outbound intent → Graph send with tenant credential.
7. `smb_message_echoes` → persist BUSINESS_APP outbound + pause AI (`HUMAN_PAUSED`, control epoch++) until explicit Resume AI.
8. History / app-state / status / self → zero AI / credits / outbound.

**SoT:** PostgreSQL (`LINAS_WHATSAPP_DATABASE_URL`). FB/IG file registry unchanged. No Cloud→Monty fallback.

## Two-phase rollout (ops)

### Phase 1 — Before Meta approval (NOW)

| Control | How |
|---------|-----|
| Public availability | Keep `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false` (default) |
| Operational flags | Turn ON: `WHATSAPP_CLOUD_CONNECTION_UI_ENABLED`, `WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED`, `WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED`, `WHATSAPP_CLOUD_AI_REPLIES_ENABLED` |
| Internal pilot | Audited row in `whatsapp_pilot_entitlements` — **never** hardcode tenant/email in code |
| Grant pilot | Owner Portal (platform_owner) **or** `POST /api/whatsapp/cloud/pilot/grant` with `{ "tenant_id": "<real>", "reason": "…" }` |
| List / revoke | `GET /api/whatsapp/cloud/pilot/list`, `POST /api/whatsapp/cloud/pilot/revoke` |
| Non-entitled UX | Honest “Awaiting Meta App Review approval” — cannot complete Connect |

### Phase 2 — After Meta approval (config-only)

| Control | How |
|---------|-----|
| Central switch | Set `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=true` on the production server env, then restart `linasbot` |
| Code / mobile | **No new deploy of feature code and no new mobile build required** for the switch itself |
| Effect | All eligible tenants can open Integrations → Connect WhatsApp Business (pilot row no longer required) |
| Rollback | Set `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false` and restart |

Keep Advanced Access / App Review submission as human Meta Console work. Do not flip public until Meta grants what you need.

## Owner Portal — grant internal pilot

1. Sign in as `platform_owner` in Linas AI mobile.
2. Open **Owner Control Center**.
3. Enter the real `tenant_id` (ops-time argument — not hardcoded) + reason → **Grant pilot entitlement**.
4. Confirm the tenant appears as `active` in the pilot list.
5. Sign into that tenant → Integrations → Connect WhatsApp should be available.

Equivalent API (audited):

```http
POST /api/whatsapp/cloud/pilot/grant
{ "tenant_id": "<tenant>", "reason": "Internal App Review pilot" }
```

## Threat model (short)

| Threat | Mitigation |
|--------|------------|
| Cross-tenant send/leak | Unique active `phone_number_id`; tenant checks on every API |
| Token theft | AES-GCM at rest; never returned to client; logs redacted |
| Webhook forgery | Constant-time App A signature on raw body before parse |
| Duplicate AI replies | Durable event + message + outbound idempotency keys; epoch race check |
| Dual provider reply | Monty blocked for Cloud-bound source; startup fail-closed on overlap |
| Client-simulated Connected | Status only from server binding + health |
| Hardcoded bypass | Forbidden — only audited pilot rows or the public env switch |

## Configuration keys (presence only)

See `whatsapp_config_key_presence()` / `.env.example` WhatsApp section. Never paste values into tickets.

Required for production Phase 1: `LINAS_WHATSAPP_DATABASE_URL`, `META_CREDENTIAL_ENCRYPTION_KEY`, `META_APP_A_ID/SECRET/VERIFY`, `META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID`, rollout flags, `PUBLIC_URL`, and `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false`.

## Meta Console checklist (App A only — `2963733803971681`)

1. Separate **WhatsApp Embedded Signup** configuration (do not reuse Facebook Login for Business config used by FB/IG).
2. Permissions (least privilege): `whatsapp_business_management`, `whatsapp_business_messaging` (+ `business_management` only if builder requires).
3. Callback / allowed domains: bridge host + `/oauth/whatsapp/callback`.
4. WABA webhook fields: messages, smb_message_echoes, history, smb_app_state_sync, message_template_status_update, account_update, phone_number_quality_update.
5. Webhook URL: `https://<host>/webhook/whatsapp-cloud`.
6. Mobile return: deep link `linasai://integrations` (handled by app; not Console).
7. Test assets for App Review videos under Standard Access / App role as Meta permits.

## Staging / internal film plan

1. Use Meta test phone / App-role assets first (not the Egyptian real pilot number until Mahmoud connects it manually).
2. Enable Phase 1 flags; keep public availability false.
3. Grant pilot via Owner Portal for the internal test tenant_id.
4. Connect via mobile → verify Connected from `/api/whatsapp/cloud/status`.
5. Film: Connect → Connected → Test Message → Template create → AI on → AI reply → Business App manual reply pauses AI → Resume AI.
6. Return path must land in Linas AI Integrations — never Web Operator Login.

## Real-number Coexistence pilot

- Dedicated WhatsApp Business **pilot** number only (human connects after Meta assets ready).
- Must use `whatsapp_business_app_onboarding` — **never** ordinary API Setup / migration.
- If Advanced Access gates the coexistence choice: complete App Review videos first; mark real Coexistence as post-approval verification.
- Second sender number for customer simulation.
- Keep Monty source number disjoint; startup fails if overlap detected.

## E2E matrix

| Case | Expected |
|------|----------|
| Customer inbound | One CM AI reply |
| Business App manual reply (echo) | Pause AI; no AI invoke |
| Customer while paused | Stored; no AI |
| Authorized Resume AI | Next inbound can AI |
| Retries/duplicates | Idempotent |
| Media unsupported | Honest representation; no retry storm |
| Meta send failure | Honest failed / reconciliation_required; no Connected lie |
| Non-pilot before public | Honest Meta-approval wait; Connect blocked |

## Rollback / disable

1. Turn flags OFF: `WHATSAPP_CLOUD_*_ENABLED=false` and/or `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false`.
2. Optionally revoke connection (owner `DISCONNECT`) — WhatsApp Business App remains usable.
3. Do not delete tenant PG history unless retention policy requires.
4. Legacy Monty stays disabled for inbound AI.

## App Review recording script

1. **Messaging:** Linas AI sends a message via Test Message / `whatsapp_business_messaging`; WhatsApp client receives it. Record both screens.
2. **Templates:** Linas AI creates a message template; show real Meta status/result (pending/approved/rejected).
3. **AI + Pause/Resume:** Show AI reply, then Business App manual reply → AI paused, then Resume AI restores.

Reviewer instructions: no secrets; do not claim public SaaS WhatsApp or Coexistence Advanced Access until Meta grants it.

## External blockers (honest)

- `META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID` must be created in Meta Console (human).
- WhatsApp Advanced Access / App Review may gate real-number coexistence onboarding.
- Public availability remains **false** until Meta approval + Mahmoud flips `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY`.
