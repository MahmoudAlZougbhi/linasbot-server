# Meta App Review package — App A social features

**App:** `2963733803971681` (App A only)  
**Facebook Connect Login Configuration (Pages only):** `1369663304545819`  
**Legacy mixed FB+IG Login Configuration (do not delete yet; not used for new Facebook Connect):** `1057282070324984`  
**WhatsApp Embedded Signup Configuration (unchanged):** `1430599348520127`  
**Callback:** `https://www.linasaibot.com/webhook/meta-messaging`  
**Instagram Login callback:** `https://www.linasaibot.com/webhook/instagram-login`  
**OAuth redirect (Facebook Business Login):** `https://www.linasaibot.com/oauth/meta/callback`

Forbidden: App B disconnect, token reset, bundling Instagram into Facebook Connect, Submit for Review without approval.

---

## Manual Meta Dashboard steps (you must do these)

### 1) Facebook Login for Business Configuration `1369663304545819` (Facebook Connect)

1. Meta Developer Dashboard → App A → **Facebook Login for Business** → Configurations → open `1369663304545819`.
2. Under **Permissions / capabilities**, ensure these are present (Pages only — no Instagram assets):
   - `business_management`
   - `pages_show_list`
   - `pages_manage_metadata`
   - `pages_messaging`
   - `pages_read_engagement`
   - `pages_read_user_content`
   - `pages_manage_engagement`
3. Do **not** add `instagram_*` or `instagram_business_*` permissions to this configuration.
4. Save configuration. Do **not** delete `1057282070324984` yet.

### 2) Instagram Connect (independent Instagram Login)

Connect Instagram uses `/api/meta/connections/instagram-login/start` with:
- `instagram_business_basic`
- `instagram_business_manage_messages`
- `instagram_business_manage_comments`

Do **not** route Instagram Connect through either Facebook Login for Business configuration.

### 3) App-level webhooks (idempotent)

Run workflow **Meta App Webhooks Reconcile** (DM fields only) — already on `main`.

For comment fields, run (after deploy) on production:

```bash
META_APP_ID=2963733803971681 META_GRAPH_API_VERSION=v24.0 \
  python3 scripts/reconcile_meta_comment_webhooks.py
```

This merges:
- **page:** `messages`, `messaging_postbacks`, `feed`
- **instagram:** `messages`, `messaging_postbacks`, `comments`

DM fields are never removed.

### 4) Page-level `subscribed_apps` (per Page, when comment replies enabled)

When a business enables **Enable AI replies to Facebook comments** in Settings → Integrations, the server calls:

`POST /{page-id}/subscribed_apps` with `subscribed_fields=messages,messaging_postbacks,feed`

For DM-only Pages, keep `messages,messaging_postbacks` via existing page-subscribe workflow.

### 5) Reauthorization (no Disconnect)

Settings → Integrations → **Manage Meta Access** for Facebook (Facebook-only config).  
Instagram: use Connect Instagram / Instagram Login.  
Existing assets remain; tokens refresh in place. No duplicate bindings when reauthorizing the same Meta user.

---

## OAuth permission list

### Facebook Connect (`1369663304545819`)

| Permission | Purpose |
|---|---|
| `business_management` | Business asset selection for Pages |
| `pages_show_list` | List Pages user can connect |
| `pages_manage_metadata` | Page metadata for binding |
| `pages_read_engagement` | Engagement context (dependency) |
| `pages_messaging` | Facebook Messenger DMs |
| `pages_read_user_content` | Receive Page comment content |
| `pages_manage_engagement` | Reply publicly to Page comments |

### Instagram Login (separate flow)

| Permission | Purpose |
|---|---|
| `instagram_business_basic` | IG professional identity |
| `instagram_business_manage_messages` | Instagram DMs |
| `instagram_business_manage_comments` | Instagram comments |

Linas AI does **not** request content publishing (`pages_manage_posts` / `instagram_content_publish` / `instagram_business_content_publish`) for this Connect Facebook switch.

---

## Architecture

```
Dashboard / Mobile
  ├─ Connect Facebook → /api/meta/connections/start {channel:facebook}
  │     → Facebook Login for Business config 1369663304545819 (Pages only)
  ├─ Connect Instagram → /api/meta/connections/instagram-login/start
  │     → Instagram Login (instagram_business_*)
  └─ WhatsApp → Embedded Signup config 1430599348520127 (unchanged)
```

---

## Environment variables

| Variable | Role |
|---|---|
| `META_APP_A_FACEBOOK_LOGIN_CONFIG_ID` | Active Facebook Connect config (`1369663304545819`) |
| `META_APP_A_LOGIN_CONFIG_ID` | Legacy mixed config (`1057282070324984`) — keep; not used for new FB Connect |
| `META_WHATSAPP_EMBEDDED_SIGNUP_CONFIG_ID` | WhatsApp only (`1430599348520127`) |

---

## Retiring the legacy mixed configuration

Do **not** delete `1057282070324984` until:
1. Production Facebook Connect has used `1369663304545819` successfully.
2. No in-flight OAuth states reference the mixed config.
3. Ops confirms no Meta console dependency remains.

It is **not** safe to retire yet solely because this code change landed.
