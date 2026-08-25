# Meta Developer Support — Comments not delivered for tester accounts

> **Use this document to open a ticket in Meta Developer Support** (Help → Contact
> Support → App → Linas AI). Paste the **Subject** and **Description** below.
> Attach redacted server log excerpts if requested. **Never attach access tokens,
> app secrets, or webhook verify tokens.**

Last updated: **2026-08-26 (UTC+3)** — includes live production repro the same night,
official webhook docs (Advanced Access / Live mode), and filing-path notes.

---

## Subject (paste)

Instagram/Facebook Comments not delivered to webhooks or Graph API for Unpublished app with tester accounts — need delivery path for App Review screencast

---

## Description (paste)

### Summary

We are preparing App Review for customer-initiated **Instagram DMs and public
comment replies** on Linas Clinic AI Social Bot. **Instagram DMs work** (webhook
delivery + Send API acceptance verified August 2026). **Public comments do not
work**: Graph API reads return HTTP **200** with **`"data": []`**, and our servers
receive **no comment webhook payloads** despite subscribed fields and tester
Webhook Subscription **On**.

We need Meta to confirm why comment events/data are absent for our tester setup
and what is required (Advanced Access, app mode, tester role, product config) to
obtain comment delivery for App Review evidence.

### App and assets (no secrets)

| Item | Value |
|------|-------|
| Top-level Meta app name | **Linas AI** |
| Top-level Meta app ID | `2963733803971681` |
| Instagram API with Instagram Login product app ID | `1035856539045307` |
| Facebook Login for Business config ID | `1021840664011530` |
| Business Portfolio | **linalaser** (`2185164171581229`) — Business Verification **Verified** |
| Facebook Page | **Lina's Laser Clinics** — Page ID `378696005334409` |
| Connected Instagram professional account ID | `17841413184256533` |
| Instagram username (production binding) | `@linaslaser` |
| Instagram tester usernames (Roles) | `@linaslaser`, `@boc_system` |
| App mode | **Unpublished** |
| Permission status (all desired social scopes) | **Ready for testing** (not Advanced Access) |
| Runtime Graph API version (server) | `v24.0` |
| Dashboard webhook subscription version | `v26.0` |
| Server Instagram Login Graph version | `v26.0` (`INSTAGRAM_LOGIN_GRAPH_API_VERSION`) |
| `subscribed_apps` fields (live GET, Aug 2026) | `comments`, `messages`, `messaging_postbacks` |
| Comment-related stored scopes | include `instagram_business_manage_comments` |
| Comments enforcement (our side) | `allow=True` for tenant `linas` |

### Live production repro — 2026-08-25 ~21:00 UTC / 2026-08-26 ~00:00 Asia/Beirut

A visitor/tester comment was posted on an **older** `@linaslaser` IMAGE (not the newest media; newest Graph media is several days old).

Observed on both production nodes (no tokens attached):

1. Graph `GET graph.instagram.com/{ig-user-id}/media` showed that IMAGE’s **`comments_count` increased** (example: `0` → `1`).
2. Immediate `GET graph.instagram.com/{media-id}/comments` still returned **HTTP 200** with **`"data": []`**. Nested `comments` expansion on media was also empty.
3. **Zero** inbound durable `meta_comment` + `instagram` events in `/opt/linasbot_data/logs/inbound_events` in the following ~20 minutes on **both** nodes.
4. Instagram **DM** webhooks continued: `[instagram-login] webhook_authenticated object=instagram ... comments=0`.
5. Facebook Page comments exist in our ledger (some `sent`, some failed for unrelated reply/AI reasons). Instagram comments remain absent.

**Tester identity:** connected username is `@linaslaser`. Comments from `@linaslaser` on `@linaslaser` media are **self-comments** and our product skips them even if Meta delivered. Correct tester for comments is **`@boc_system` (or another Roles tester) commenting on `@linaslaser` posts**. The Graph `comments_count` bump + empty comments edge still happens **before** our skip logic: Meta is not returning the comment object.

### Official Meta docs vs what we see (cite in ticket)

From [Setup Webhooks Subscriptions](https://developers.facebook.com/docs/instagram-platform/webhooks/) (updated Mar 3, 2026):

- “Your app must be set to **Live** in the App Dashboard for Meta to send webhook notifications.”
- Access-level table: **Advanced Access** for Business Login for Instagram; **Advanced Access for `comments` and `live_comments`** for Facebook Login for Business; **Advanced Access** for Instagram Messaging via Messenger Platform.
- Explicit: “**Advanced Access is required to receive `comments` and `live_comments` webhook notifications.**”

**Contradiction we need Meta to resolve for App Review:** the same Unpublished app, same Instagram Login callback, same tester Webhook Subscription **On**, **does receive `messages` webhooks** (DMs verified). If Live mode + Advanced Access are strictly required for *all* Instagram webhooks, DMs should also be absent. They are not. Comments are absent, and Graph `{media-id}/comments` is empty even when `comments_count` increments.

### Webhook configuration (confirmed in Dashboard snapshot 2026-08-14)

**Instagram product** (`1035856539045307`):

- Callback URL: `https://www.linasaibot.com/webhook/instagram-login`
- Subscribed app-level fields: `comments`, `messages`, `messaging_postbacks`
- Per-tester **Webhook Subscription: On** for `@linaslaser` and `@boc_system`

**Facebook Page** (`378696005334409`):

- Callback URL: `https://www.linasaibot.com/webhook/meta-messaging`
- Subscribed fields: `feed`, `messages`, `messaging_postbacks`

Our server authenticates Instagram webhooks with the Instagram product secret on
the dedicated callback (not the Facebook Page callback). DM webhooks on the
Instagram callback are received and processed.

### What works (evidence, no tokens)

1. **Instagram DM (Instagram Login auth flow)**
   - Inbound `messages` webhooks arrive at `/webhook/instagram-login`.
   - Outbound DM Send API returns provider acceptance (message ID) — verified
     after webhook signature fix (August 2026).
   - Server log marker (redacted): `[instagram-login] webhook_authenticated
     object=instagram ... comments=0` (comments count stays zero even when DMs
     arrive).

2. **Facebook Messenger DM**
   - Inbound `messages` webhooks arrive at `/webhook/meta-messaging`.
   - Outbound replies accepted by Graph Send API.

3. **Internal gates**
   - Comment automation toggles, CM actions, binding, and stored credential scopes
     are enabled for the active `@linaslaser` binding (`instagram_login`).

### What fails — Comments

#### A) Graph API returns empty comment lists (HTTP 200, `data: []`)

After posting test comments from tester accounts on Instagram media and on the
Facebook Page feed, read-only Graph probes (using app-scoped tokens with comment
scopes present in our credential store — **not attached here**) return success
with empty arrays:

**Instagram Login / professional account**

```
GET https://graph.instagram.com/v26.0/{ig-user-id}/media?fields=id,caption,timestamp,comments
→ HTTP 200
→ {"data":[ ... media rows ... ]}   (media may be present)

GET https://graph.instagram.com/v26.0/{media-id}/comments
→ HTTP 200
→ {"data":[]}
```

**Facebook Page**

```
GET https://graph.facebook.com/v24.0/{page-id}/feed?fields=id,message,comments
→ HTTP 200

GET https://graph.facebook.com/v24.0/{post-id}/comments
→ HTTP 200
→ {"data":[]}
```

(Replace `{ig-user-id}` with `17841413184256533` for our connected account; use the
test media/post ID where the tester comment was posted.)

#### B) No comment webhook delivery

During controlled tests (August 2026, Asia/Beirut timezone windows):

| Time window (approx.) | Action | Expected | Observed |
|----------------------|--------|----------|----------|
| 2026-08-20 – 2026-08-24 | Tester posts IG media comment | `comments` webhook to `/webhook/instagram-login` | **No** comment payload; DM webhooks still arrive |
| 2026-08-20 – 2026-08-24 | Tester posts FB Page feed comment | `feed` webhook to `/webhook/meta-messaging` | **No** comment/feed change payload for the new comment |
| 2026-08-25 ~21:00 UTC | Comment on older `@linaslaser` IMAGE | `comments` webhook + Graph comment list | `comments_count` +1; `{media-id}/comments` = `[]`; no inbound 20m; DMs still arrive |
| Same windows | Server poll of Graph comments | Ingest new comments via Graph | **No rows** because Graph `comments` edge is `data:[]` |

Redacted nginx/journal patterns from production probe (`scripts/prod_meta_comment_runtime_probe.py`):

- `POST /webhook/instagram-login` — **present** (DM traffic)
- `[instagram-login] webhook_authenticated ... comments=0` — **always zero**
- `[meta-comment] webhook_authenticated` — **absent** in comment test windows
- `[meta-comment] ig_login_comments` — **never triggered**

### Permissions requested for App Review (not yet Advanced Access)

**Instagram Login (3):** `instagram_business_basic`,
`instagram_business_manage_messages`, `instagram_business_manage_comments`

**Facebook (7):** `business_management`, `pages_show_list`, `pages_manage_metadata`,
`pages_read_engagement`, `pages_messaging`, `pages_read_user_content`,
`pages_manage_engagement`

Stored credential scope audit on our side shows the comment-related scopes for
the active binding; the blocker appears to be **Meta-side delivery**, not missing
server subscription fields.

### Questions for Meta Support

1. For an **Unpublished** app with permissions **Ready for testing**, should
   `instagram_business_manage_comments` / Page comment scopes allow:
   - comment webhooks to tester accounts with Webhook Subscription **On**, and/or
   - Graph `{media-id}/comments` / `{post-id}/comments` to return tester-authored
     comments?
2. If not, what is the supported path to record an App Review screencast for
   **public comment reply** when Graph returns `data:[]` and webhooks never fire?
3. Is Advanced Access required **before** comment data is visible to testers, even
   when the app is Unpublished and testers are added under Roles?
4. Please inspect app `2963733803971681` / Instagram product `1035856539045307`
   for misconfiguration blocking comment delivery while DMs work on the same
   callback and subscriptions.
5. Official docs (Mar 2026) say Live mode + Advanced Access are required for
   `comments` / `live_comments` webhooks. **Messages already arrive** on this
   Unpublished app with permissions **Ready for testing**. Please confirm:
   - whether testers should still get `comments` webhooks / Graph comment lists
     for App Review evidence without Advanced Access, and
   - why `{media-id}/comments` is `data:[]` while `comments_count` on that media
     increments after a real comment.

### Compliance / privacy (for context)

Public URLs (live on our domain):

- Privacy: `https://www.linasaibot.com/privacy-policy`
- Terms: `https://www.linasaibot.com/terms`
- Data deletion: `https://www.linasaibot.com/data-deletion`
- Instagram deauthorize callback (code ready): `https://www.linasaibot.com/oauth/instagram/deauthorize`
- Instagram data-deletion callback (code ready): `https://www.linasaibot.com/oauth/instagram/data-deletion`

We are populating the two Instagram Business Login Dashboard compliance URL fields
before App Review submission.

### Contact

- Developer contact: Mahmoud Zougbhi (App Administrator)
- Support email on compliance pages: `support@linasai.com`

Thank you.

---

## Where to file (2026-08-26 attempt)

Private **Report a Bug** (`https://developers.facebook.com/support/bugs/report/`)
logged in as app admin, app **Linas AI** (`2963733803971681`):

- **Messenger Platform → Instagram Messaging → Webhooks:** “We regret that
  support is unavailable for this product” — Meta redirects to the
  [Developer Community Forum](https://developers.facebook.com/community/).
- **Developer Tools → App Dashboard → App Review → general question:** Meta
  says they will **not** answer App Review process questions or look into
  individual cases via the bug tool.

**Remaining official channel:** Community Forum → **Ask a Question**, category
**Instagram Graph API** or **Webhooks**. Paste Subject + Description above.
Optional attachments: redacted journal/nginx excerpts showing DM webhooks but
`comments=0`; screenshot of Dashboard webhook fields (no secrets).

App Dashboard **Help** → “Need more help?” only opens
`https://developers.facebook.com/support/` (AI assistant), not a private case.

---

## Internal references (do not paste tokens)

- App Review package: `docs/META_APP_REVIEW_SOCIAL_PACKAGE.md`
- Compliance checklist: `docs/META_DASHBOARD_COMPLIANCE_AND_DRAFT_CHECKLIST.md`
- Comment permission hardening (server-side, does not fix Meta delivery):
  `docs/META_COMMENT_PERMISSION_HARDENING.md`
