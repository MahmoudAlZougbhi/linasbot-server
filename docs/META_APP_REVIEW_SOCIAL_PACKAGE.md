# Meta App Review package — App A social features

**App:** `2963733803971681` (App A only)  
**Login Configuration:** `1057282070324984` (Facebook Login for Business)  
**Callback:** `https://www.linasaibot.com/webhook/meta-messaging`  
**OAuth redirect:** `https://www.linasaibot.com/oauth/meta/callback`

Forbidden: App B, `instagram_business_*`, Disconnect, token reset, Meta Publish, Submit for Review.

---

## Manual Meta Dashboard steps (you must do these)

### 1) Facebook Login for Business Configuration `1057282070324984`

1. Meta Developer Dashboard → App A → **Facebook Login for Business** → Configurations → open `1057282070324984`.
2. Under **Permissions**, ensure these are added (in addition to existing DM permissions):
   - `pages_read_user_content`
   - `pages_manage_engagement`
   - `pages_manage_posts`
   - `instagram_manage_comments`
   - `instagram_content_publish`
3. Do **not** add `instagram_business_*` permissions.
4. Save configuration. Do **not** publish the app or submit for review from this task.

### 2) App-level webhooks (idempotent)

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

### 3) Page-level `subscribed_apps` (per Page, when comment replies enabled)

When a business enables **Enable AI replies to Facebook comments** in Settings → Integrations, the server calls:

`POST /{page-id}/subscribed_apps` with `subscribed_fields=messages,messaging_postbacks,feed`

For DM-only Pages, keep `messages,messaging_postbacks` via existing page-subscribe workflow.

### 4) Reauthorization (no Disconnect)

Settings → Integrations → **Add / Manage Facebook & Instagram** (same Login Config).  
Existing assets remain; tokens refresh in place. No duplicate bindings when reauthorizing the same Meta user.

---

## OAuth permission list (App A Login Config)

| Permission | Purpose |
|---|---|
| `public_profile` | Identify authorizing Meta user |
| `pages_show_list` | List Pages user can connect |
| `pages_manage_metadata` | Page metadata for binding |
| `pages_read_engagement` | Engagement context (dependency) |
| `pages_messaging` | Facebook Messenger DMs |
| `instagram_basic` | IG account identity |
| `instagram_manage_messages` | Instagram DMs |
| `pages_read_user_content` | Receive Page comment content |
| `pages_manage_engagement` | Reply publicly to Page comments |
| `pages_manage_posts` | Publish Page posts after user confirmation |
| `instagram_manage_comments` | Reply publicly to IG comments |
| `instagram_content_publish` | Publish IG posts after user confirmation |

---

## Architecture

```
Dashboard
├── Settings → Integrations (per-asset comment reply switches, default OFF)
└── Create Post (caption AI → edit → preview → confirm → publish)

POST /webhook/meta-messaging
├── entry.messaging[] → DM pipeline (unchanged)
└── entry.changes[]
    ├── field=feed, item=comment → comment AI reply (if enabled)
    └── field=comments (instagram) → comment AI reply (if enabled)

/api/meta/social-posts/*
├── generate-caption (KB-grounded, no auto-publish)
├── upload-media
├── preview (signed preview_token)
└── publish (requires confirmed=true + valid preview_token)
```

---

## Webhook fields

| Level | Object | Fields |
|---|---|---|
| App | `page` | `messages`, `messaging_postbacks`, `feed` |
| App | `instagram` | `messages`, `messaging_postbacks`, `comments` |
| Page | `subscribed_apps` | `messages`, `messaging_postbacks` (+ `feed` when comments ON) |

---

## Per-permission App Review text

### `pages_read_user_content`

**Explanation:** Linas AI reads public comment text on a connected Facebook Page so the business can optionally enable AI replies. Comments are only processed when the Page owner turns on “Enable AI replies to Facebook comments” in Settings. We do not read private messages through this permission.

**Dependencies:** `pages_show_list`, `pages_manage_metadata`, `pages_read_engagement`

**API / webhooks:** Page webhook `feed` with `item=comment`; Graph read of comment context when needed.

**Reproduction:** Connect test Page → enable comment switch → post external comment → show webhook payload → show optional AI reply.

**Screencast script:** (1) Login to dashboard. (2) Settings → Integrations → enable Facebook comments on test Page. (3) From a personal account, comment on a Page post. (4) Show comment appears in Meta webhook debugger. (5) Show public AI reply under comment. (6) Disable switch; new comment gets no AI reply.

---

### `pages_manage_engagement`

**Explanation:** Post one public reply under a new Page comment when the business enabled optional AI comment replies. No hide/delete, no DMs to commenters, max one AI reply per comment.

**Dependencies:** `pages_read_user_content`, `pages_show_list`

**API:** `POST /{comment-id}/comments` with Page access token.

**Reproduction:** Same as above; highlight Graph API reply call in logs (redacted).

**Screencast:** Show reply posted as Page; show setting OFF prevents replies.

---

### `pages_manage_posts`

**Explanation:** Allow a business user to create and publish a Facebook Page post from the dashboard **only after** reviewing AI-generated caption, previewing, and explicitly confirming Publish. AI never publishes autonomously.

**Dependencies:** `pages_show_list`, `pages_read_engagement`

**API:** `POST /{page-id}/feed` or `POST /{page-id}/photos` with `message` and optional image.

**Reproduction:** Create Post → Generate caption → edit → Preview → check confirmation → Publish → show post on Page.

**Screencast:** Full Create Post flow; narrate that Publish button requires confirmation checkbox.

---

### `instagram_manage_comments`

**Explanation:** Receive new comments on media of a connected professional Instagram account and optionally post one public AI reply when enabled per account in Settings. No private replies, no delete/hide.

**Dependencies:** `instagram_basic`

**API / webhooks:** App webhook `instagram` field `comments`; `POST /{comment-id}/replies`

**Reproduction:** Enable IG comments switch → comment on IG media → show public reply.

**Screencast:** Settings toggle → external IG comment → AI reply → toggle OFF → no reply.

---

### `instagram_content_publish`

**Explanation:** Publish an Instagram image post only after the business user reviews caption, previews, and confirms. Uses container create → status (if needed) → publish. No autonomous publishing.

**Dependencies:** `instagram_basic`

**API:** `POST /{ig-user-id}/media` → `POST /{ig-user-id}/media_publish`

**Reproduction:** Create Post with Instagram checked → upload image → generate caption → preview → confirm → publish.

**Screencast:** Narrate explicit confirmation; show post on Instagram.

---

## Existing DM permissions (scripts still valid)

### `pages_messaging` / `instagram_manage_messages`

**Explanation:** Answer customer-initiated Messenger and Instagram DMs using the business knowledge base.

**Webhooks:** `messages`, `messaging_postbacks` on app and Page `subscribed_apps`.

**Screencast:** Send DM → AI reply in thread → show Live Chat in dashboard.

---

## Test coverage

- `tests/test_meta_comment_replies.py` — OFF/ON, duplicate, self-reply, isolation
- `tests/test_meta_social_posts.py` — preview token, confirmation required, workspace isolation, publish scopes, media store

---

## Production defaults

- Comment reply switches: **OFF**
- No Disconnect, token reset, App B, Meta Publish, or Submit for Review performed by this change set.
