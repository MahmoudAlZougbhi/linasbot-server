# Meta Dashboard — Compliance URLs and App Review draft cleanup

> Owner action checklist for **Linas AI** (`2963733803971681`).  
> **No App Review Submit yet.** File Meta Support for comment delivery first.

Rollout/deploy gates (merge → CI main → HA deploy → backfill):  
`docs/META_PERMISSION_HARDENING_ROLLOUT.md`

Support ticket text: `docs/META_SUPPORT_TICKET_COMMENTS_NOT_DELIVERED.md`

---

## Part 1 — Compliance URLs (paste exactly)

### A) App settings → Basic (shared)

| Field | Value |
|-------|-------|
| App domains | `linasaibot.com` |
| Privacy Policy URL | `https://www.linasaibot.com/privacy-policy` |
| Terms of Service URL | `https://www.linasaibot.com/terms` |
| User data deletion | `https://www.linasaibot.com/data-deletion` |

### B) Facebook Login → Settings (confirmed 2026-08-14)

| Field | Value |
|-------|-------|
| Valid OAuth redirect URI | `https://www.linasaibot.com/oauth/meta/callback` |
| Deauthorize callback URL | `https://www.linasaibot.com/oauth/meta/deauthorize` |
| Data deletion request URL | `https://www.linasaibot.com/oauth/meta/data-deletion` |

### C) Instagram API with Instagram Login → API setup (**BLOCKER — was empty**)

| Field | Paste this URL |
|-------|----------------|
| **Deauthorize callback URL** | `https://www.linasaibot.com/oauth/instagram/deauthorize` |
| **Data deletion request URL** | `https://www.linasaibot.com/oauth/instagram/data-deletion` |

Also confirm:

| Field | Value |
|-------|-------|
| OAuth redirect URI | `https://www.linasaibot.com/oauth/instagram/callback` |
| Webhook callback URL | `https://www.linasaibot.com/webhook/instagram-login` |
| Webhook fields | `comments`, `messages`, `messaging_postbacks` |

### D) Verification — not just HTTP 200

**Step 1 — Live routing + signed rejection (safe on production):**

```bash
python scripts/verify_meta_compliance_urls.py
```

Checks: public pages 200, callback health GET, POST missing/bad `signed_request` → **400**.

**Step 2 — Full Meta contract (CI/local; proves valid signed_request + confirmation JSON):**

```bash
python scripts/verify_meta_compliance_urls.py --pytest-contract
```

Equivalent: `pytest tests/test_meta_compliance.py -q`

This proves:

- Valid `signed_request` → deletion returns `url` + `confirmation_code`
- Wrong signature → **400**, no side effects
- Deauthorize → **200** `{"success": true}` with correct signing domain per product
- Instagram callbacks use Instagram product secret only (not Facebook secret)

---

## Part 2 — App Review draft cleanup (no Submit yet)

**Draft ID:** `2964793000532428` — **BLOCKED**

### Permission strategy (corrected)

Do **not** treat “exactly 10 permissions” as a fixed rule. For each submission or
evidence section, request only permissions that are:

1. **Actually used** by the runtime for that surface, and  
2. **Demonstrated** in the screencast attached to that permission request.

**Prefer separating Facebook and Instagram** when test paths differ (Page/Messenger
vs Instagram Login callback, different secrets, different recordings). One top-level
Meta app can still host **two evidence sections** — or two submissions if Meta requires
split review.

### Remove from draft (unless separately evidenced)

**Legacy Instagram (wrong auth flow for our runtime):**

- `instagram_basic`
- `instagram_manage_messages`
- `instagram_manage_comments`

**WhatsApp** — separate review unless owner intentionally bundles WhatsApp evidence.

**Out of scope unless video proves them:**

- `instagram_business_content_publish`
- `instagram_business_manage_insights`

### Typical permission sets (adjust to what you record)

**Facebook evidence section** (Page + Messenger + Page comments) — example set:

- `business_management`
- `pages_show_list`
- `pages_manage_metadata`
- `pages_read_engagement`
- `pages_messaging`
- `pages_read_user_content`
- `pages_manage_engagement`

**Instagram Login evidence section** (DM + media comments) — example set:

- `instagram_business_basic`
- `instagram_business_manage_messages`
- `instagram_business_manage_comments`

Drop any permission from the draft that has **no** matching recording or runtime use.

### Pre-submit gates

- [ ] Instagram Business Login Deauthorize + Data deletion URLs populated (Part 1C)
- [ ] `verify_meta_compliance_urls.py` live checks PASS
- [ ] `verify_meta_compliance_urls.py --pytest-contract` PASS
- [ ] Meta Support ticket filed if comment Graph/webhooks still empty
- [ ] Comment screencasts exist (may require Meta Support resolution first)
- [ ] **Do not Submit** until owner approves rollout doc gates

---

## Part 3 — Unexpected `User` webhook object

Dashboard snapshot shows a **`User`** object on `/webhook/instagram-login` (all fields
Unsubscribed). Owner must approve disposition; run Meta App Webhooks Reconcile after
decision. Do not delete during read-only audit.
