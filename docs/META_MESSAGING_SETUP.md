# Facebook and Instagram AI messaging setup

> The former single-credential, Page-linked, DM-only instructions in this file
> are retired. The Dashboard has one top-level **Linas AI** app, but its Facebook
> and Instagram products use separate credential/callback domains. Do not share
> their secrets or callbacks, and do not run DM-only subscription commands. The
> canonical operational contract is `docs/META_APP_REVIEW_SOCIAL_PACKAGE.md`.

## Current product-domain split

| Surface | Product | OAuth redirect | Webhook callback |
|---|---|---|---|
| Facebook Messenger + Page comments | Linas AI app ID `2963733803971681` / Facebook Login for Business | `https://www.linasaibot.com/oauth/meta/callback` | `https://www.linasaibot.com/webhook/meta-messaging` |
| Instagram DMs + comments | Instagram product app ID `1035856539045307` inside Linas AI / Instagram Login | `https://www.linasaibot.com/oauth/instagram/callback` | `https://www.linasaibot.com/webhook/instagram-login` |

The two rows have different app secrets, verify tokens, access tokens, app-scoped
IDs, and Graph hosts. They must never be mixed or configured to use the other
row's callback. Permission-family approval state is separate too:
`META_APP_A_ADVANCED_ACCESS_APPROVED` cannot unlock Instagram, which uses the
fail-closed `META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED` gate selected by
binding `auth_flow`. Linas AI has one top-level App Review draft/submission,
`2964793000532428`, with separate Facebook and Instagram evidence sections.

Required review permissions:

- Facebook: `business_management`, `pages_show_list`,
  `pages_manage_metadata`, `pages_read_engagement`, `pages_messaging`,
  `pages_read_user_content`, `pages_manage_engagement`.
- Direct Instagram: `instagram_business_basic`,
  `instagram_business_manage_messages`,
  `instagram_business_manage_comments`.

This package does not request content publishing or insights. The generated
Instagram embed sample includes `instagram_business_content_publish` and
`instagram_business_manage_insights`, but the code requests only the three
Instagram permissions above. Linas AI also hosts an existing WhatsApp Cloud
webhook object; every social reconcile must preserve it unchanged.

## Required subscription fields

- Linas AI `page` on `/webhook/meta-messaging`:
  `messages,messaging_postbacks,feed`
- Linas AI `instagram` on `/webhook/instagram-login`:
  `messages,messaging_postbacks,comments`
- Page `378696005334409` `subscribed_apps`:
  `messages,messaging_postbacks,feed`
- Instagram account `17841413184256533` Direct IG app row ID
  `1035856539045307`: `messages,messaging_postbacks,comments`

Only the recovered reconcilers may mutate these fields. They must preserve
approved existing fields, repair a missing/inactive/wrong-callback social row,
and GET-verify exact post-state. The unexpected `User` object is a fail-closed
condition, not an implicit deletion target. A successful POST alone is not
readiness.

## Live Dashboard status — 2026-08-14

- Business Verification and Access Verification are **Verified**; no Required
  Actions are shown.
- Linas AI is **Unpublished**, and every desired Facebook/Instagram permission is
  only **Ready for testing**, not Advanced Access.
- Facebook redirect, deauthorization, data deletion, callback, and Page fields
  are correct. The Page fields are subscribed at webhook version `v26.0`.
- Instagram OAuth redirect and dedicated callback are correct; its three fields
  are subscribed at webhook version `v26.0`. Testers `linaslaser` and `boc_system`
  both show Webhook Subscription On.
- Instagram Business Login's Deauthorize callback URL and Data deletion request
  URL are empty. Configure them as `/oauth/instagram/deauthorize` and
  `/oauth/instagram/data-deletion` on `https://www.linasaibot.com`, then test the
  signed flows before App Review.
- An unexpected generic `User` webhook object points to
  `/webhook/instagram-login`; all visible User fields are Unsubscribed. This needs
  an owner-approved cleanup decision and strict read-after-write verification.
  Do not remove it during a read-only audit or claim it is harmless.
- Draft `2964793000532428` mixes the ten desired permissions with legacy
  `instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`,
  and unrelated WhatsApp requests. Clean the one draft before submission.

The runtime's supported Graph API `v24.0` and Dashboard webhook version `v26.0`
are an intentional two-version boundary, not an immediate review blocker.

## Customer behavior

The AI answers customer-initiated service, pricing, preparation, branch, and
policy questions in DMs and, when explicitly enabled and reviewed, replies to
Facebook/Instagram comments. It does not create, edit, confirm, reschedule, or
cancel appointments on Meta or in a CRM.

When a customer requests booking or a human, the assistant collects only the
missing branch/gender fields and returns the applicable public WhatsApp handoff:

| Use | Number |
|---|---|
| Laser — women — Beirut / Ramlet El Bayda | `+96178847527` |
| Laser — women — Antelias | `+96170707354` |
| Laser — men — Beirut / Ramlet El Bayda | `+96171534928` |
| Laser — men — Antelias | `+96171226082` |

Customer-facing links use `https://wa.me/<digits>`, never a short-link service.
Tattoo removal is not currently offered and must return the approved refusal
without any WhatsApp handoff. Social DMs do not activate the dashboard
human-takeover queue.

## Release verification

Local tests are necessary but not live proof. Before App Review or enabling
public traffic, complete every gate in
`docs/META_APP_REVIEW_SOCIAL_PACKAGE.md`, including:

1. approved SHA deployed and production SHA verified;
2. historical credential snapshots sanitized, pre-lineage rows audited, affected
   credentials rotated, and the implemented scheduled retention job deployed and
   count-only apply/clean verified;
3. exact Dashboard redirects/callbacks/scopes/subscriptions and separate
   permission-family approval decisions verified inside Linas AI, including the
   two currently empty Instagram compliance URLs and the extra `User` object;
4. Facebook and Direct IG reauthorization/reseeding completed through their separate
   flows; and
5. four timestamped recordings, each showing one controlled inbound action and
   exactly one recipient-visible reply with no duplicate; and a time-bounded
   runtime probe used only as supporting send-acceptance evidence.

Facebook and Instagram require separate permission lists, reviewer instructions,
recordings, declarations, secrets, callbacks, and approval gates inside the one
Linas AI review. Do not press **Submit for Review** from an audit session. The one
final submission requires the owner's explicit approval after both evidence
sections and every operational gate are complete.

## Official Meta references

- [Create an Instagram app](https://developers.facebook.com/documentation/instagram-platform/create-an-instagram-app)
- [Instagram Business Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Graph API versions](https://developers.facebook.com/docs/graph-api/changelog/versions/)
