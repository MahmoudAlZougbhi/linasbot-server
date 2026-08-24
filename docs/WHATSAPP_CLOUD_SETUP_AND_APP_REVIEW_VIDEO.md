# WhatsApp Cloud — إعداد كامل + فيديو App Review

> **Coexistence فقط:** `whatsapp_business_app_onboarding` — WhatsApp Business يضل فاتح عالتلفون.  
> **Tenant pilot:** `linas` (subscription-exempt — ما بيحتاج plan upgrade).  
> **Public availability:** يضل `false` لحد ما Meta توافق + Mahmoud يفتح Phase 2.

---

## Code audit summary (2026-08-24)

| Path | Module | Guard |
|------|--------|-------|
| Embedded Signup start | `services/whatsapp_cloud/embedded_signup.py` | pilot or `PUBLIC_AVAILABILITY`; `whatsapp_business_app_onboarding` only |
| OAuth callback | `modules/whatsapp_cloud_api.py` `/oauth/whatsapp/callback` | server-side token exchange; AES-GCM seal |
| Webhook | `modules/whatsapp_cloud_webhook.py` | App A `X-Hub-Signature-256`; side-effects flag |
| Outbound (ops + AI) | `graph_client.py`, `ai_bridge.py`, ops API | tenant token from PG; outbound flag |
| Inbound AI | `webhook_processor.py` → `ai_bridge.py` | eligibility + epoch + pause state |
| Business App manual reply | `smb_message_echoes` | `pause_conversation` → `HUMAN_PAUSED` |
| Pause / Resume | ops API + repository | control epoch bump on resume |
| Test Message | ops API | owner/admin + connected binding |
| Pilot entitlement | `entitlement.py` + `whatsapp_pilot_entitlements` | required when `PUBLIC_AVAILABILITY=false` |
| Public gate | `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY` | Phase 2 only; pilot bypasses connect block |
| Monty isolation | `legacy_isolation.py` + startup | dual-bind fail-closed; Monty send blocked |
| Credentials | `crypto.py` | AES-GCM AAD `whatsapp:{tenant}:{connection}` |

Public probe (`verify_whatsapp_cloud_readiness.py`) **cannot** prove Phase 1 flags or pilot rows — only routing, DB presence, and bridge copy.

---

## 1) شو جاهز على Production (read-only — 2026-08-24)

| Asset | Value |
|-------|-------|
| Meta App A | `2963733803971681` |
| Embedded Signup config | `1430599348520127` |
| Bridge | `https://www.linasaibot.com/integrations/whatsapp/embedded-signup` |
| OAuth callback | `https://www.linasaibot.com/oauth/whatsapp/callback` |
| Webhook | `https://www.linasaibot.com/webhook/whatsapp-cloud` |
| Graph API (runtime) | `v24.0` |
| WhatsApp PG | `LINAS_WHATSAPP_DATABASE_URL` present (ready probe) |
| Legacy Monty inbound AI | **off** (`whatsapp_inbound_ai.enabled=false`) |

Verify anytime:

```bash
python scripts/verify_whatsapp_cloud_readiness.py
```

---

## 2) Server — Phase 1 flags (Mahmoud / guarded two-node)

**Blocked** on single-node GitHub workflow until a reviewed two-node env transaction exists.  
Run from production guarded runner (same guard as other env mutations):

```bash
# On cluster (EXPECTED_RELEASE_SHA must match deployed main):
MODE=APPLY_WHATSAPP_CLOUD_PHASE1_FLAGS_ONLY \
  bash scripts/prod_whatsapp_cloud_phase1_ops.sh
```

Or migrate + flags (first time on a fresh WA PG):

```bash
MODE=APPLY_WHATSAPP_CLOUD_PHASE1 \
  bash scripts/prod_whatsapp_cloud_phase1_ops.sh
```

**Sets (never prints secrets):**

| Key | Value |
|-----|-------|
| `WHATSAPP_CLOUD_CONNECTION_UI_ENABLED` | `true` |
| `WHATSAPP_CLOUD_WEBHOOK_SIDE_EFFECTS_ENABLED` | `true` |
| `WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED` | `true` |
| `WHATSAPP_CLOUD_AI_REPLIES_ENABLED` | `true` |
| `WHATSAPP_CLOUD_HISTORY_SYNC_ENABLED` | `false` |
| `WHATSAPP_CLOUD_REQUIRE_PILOT_ENTITLEMENT` | `true` |
| `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY` | **`false`** |

After restart: re-run `python scripts/verify_whatsapp_cloud_readiness.py` (public signals only).

**Two-node note:** `prod_apply_whatsapp_cloud_phase1_flags.sh` calls `systemctl restart linasbot` on the executing node. The entrypoint is listed in `TWO_NODE_ENV_TRANSACTION_REQUIRED` — run only through the guarded HA mutation path so both nodes receive the same canonical env before restart.

---

## 3) Pilot entitlement — tenant `linas`

**Option A — Mobile (recommended):**

1. Sign in as **platform_owner**.
2. Owner Control Center → **Grant pilot entitlement**.
3. `tenant_id` = **`linas`**
4. Reason example: `Internal WhatsApp coexistence pilot — App Review filming`

**Option B — API (audited):**

```http
POST /api/whatsapp/cloud/pilot/grant
Authorization: Bearer <owner session>
{ "tenant_id": "linas", "reason": "Internal WhatsApp coexistence pilot" }
```

Confirm: Integrations → WhatsApp shows **Connect** (not “Awaiting Meta App Review”).

---

## 4) Meta Dashboard checklist (App A — human only)

1. **WhatsApp → Embedded Signup** config `1430599348520127`:
   - Feature: **WhatsApp Business App onboarding** (coexistence).
   - Callback: `https://www.linasaibot.com/oauth/whatsapp/callback`
   - Allowed domains include `www.linasaibot.com`.
2. **Permissions** (least privilege):
   - `whatsapp_business_management`
   - `whatsapp_business_messaging`
   - `business_management` only if builder requires it.
3. **Webhooks** object `whatsapp_business_account`:
   - URL: `https://www.linasaibot.com/webhook/whatsapp-cloud`
   - Fields: `messages`, `smb_message_echoes`, `history`, `smb_app_state_sync`, `message_template_status_update`, `account_update`, `phone_number_quality_update`
4. **Do not** reuse Facebook Login for Business config `1021840664011530` for WhatsApp.
5. **Monty overlap:** `MONTYMOBILE_SOURCE_NUMBER` must stay **disjoint** from the Cloud-bound number.

---

## 5) Connect + test (Mahmoud — بعد ما flags + pilot جاهزين)

**الرقم:** WhatsApp Business **coexistence** — التطبيق فاتح عالتلفون (مش API-only migration).  
Pilot line للعيادة — **مش** رقم Monty. رقم تاني لمحاكاة العميل.

**Steps:**

1. Linas AI mobile → tenant **linas** → **Integrations** → **Connect WhatsApp**.
2. Embedded Signup → اختار **WhatsApp Business App** (coexistence).
3. بعد **Connected**:
   - **Test Message** → wa_id المستلم (أرقام فقط).
   - رسالة عميل من تلفون تاني → **AI reply** (CM منشور + credits).
   - رد يدوي من WhatsApp Business App → AI **paused** (`smb_message_echoes`).
   - **Resume AI** → inbound جديد يرد AI.
4. Return path: `linasai://integrations` — **مش** Operator Login.

**Optional — App Review bind API** (platform_owner, token in env only):

- `GET /api/whatsapp/cloud/app-review/status`
- `POST /api/whatsapp/cloud/app-review/bind` with `tenant_id=linas`, `waba_id`, `phone_number_id`, `dry_run=true` first
- Token: `META_WHATSAPP_APP_REVIEW_BIND_TOKEN` on server (never commit)

---

## 6) Meta App Review — فيديو جاهز (بعد Connect شغّال)

Record **both screens** where noted. No secrets on camera.

### Scene 1 — Connect (coexistence)

- Integrations → Connect WhatsApp → Meta flow → **Connected**.
- Show coexistence hint + verified name / last-4.
- Narration: business keeps WhatsApp Business App open; Linas AI uses published CM only.

### Scene 2 — `whatsapp_business_messaging` (Test Message)

- Integrations ops panel → **Send test message** → Meta accepts.
- Show message arriving on recipient WhatsApp client.

### Scene 3 — Message template

- Create template from app → show Meta status (pending/approved) — **no fake status**.

### Scene 4 — AI inbound reply

- Customer sends WhatsApp to business number.
- Linas AI sends one AI reply (published CM).

### Scene 5 — Pause on manual Business App reply

- Reply manually from WhatsApp Business App on phone.
- Show conversation **AI paused** in app (echo webhook).

### Scene 6 — Resume AI

- Tap **Resume AI** → new customer message gets AI again.

### Reviewer notes (paste in submission)

- App: Linas AI `2963733803971681`
- Coexistence onboarding only — not Monty, not public SaaS until approved
- Test credentials: Meta tester accounts (no tokens in notes)
- Deauthorize/data-deletion: separate Facebook/Instagram URLs already in package

**Submit permissions separately from Instagram comments** unless owner intentionally bundles evidence.  
See `docs/META_DASHBOARD_COMPLIANCE_AND_DRAFT_CHECKLIST.md` § WhatsApp.

---

## 7) Phase 2 — بعد موافقة Meta (config only)

```bash
# Two-node env transaction when available:
WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=true
# restart linasbot on both nodes
```

No mobile rebuild required for the switch itself.

---

## 8) Rollback

1. Flags OFF + `WHATSAPP_CLOUD_PUBLIC_AVAILABILITY=false`
2. Optional: owner **Disconnect** — Business App stays usable
3. Do not delete PG history unless retention policy requires

Full architecture: `archive/docs/whatsapp_cloud/WHATSAPP_CLOUD_COEXISTENCE.md`
