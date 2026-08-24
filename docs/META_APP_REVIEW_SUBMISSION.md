# Meta App Review submission — DMs and comments

> **One top-level draft; not approved for submission.** Linas AI app ID
> `2963733803971681` has one live App Review draft, `2964793000532428`. Its
> Facebook and Instagram permission/evidence sections must remain clearly
> separated inside that one submission. Operational blockers are defined in
> `docs/META_APP_REVIEW_SOCIAL_PACKAGE.md`.

Product: **Linas Clinic AI Social Bot**

Business Portfolio: **linalaser** (`2185164171581229`; Business Verification and
Access Verification both confirmed **Verified** in the live Dashboard)

Facebook Page: **Lina's Laser Clinics** (`378696005334409`)

Instagram professional account: `17841413184256533`

Credentials, customer messages, owner passwords, 2FA, and reviewer-access
details must never be committed here. Linas AI is currently **Unpublished**, has
no Required Actions, and every desired permission is only **Ready for testing**,
not Advanced Access. Those facts block public use and submission readiness.

## Evidence section A — Facebook review

**Top-level Meta app:** Linas AI, app ID `2963733803971681`

**Product/auth flow:** Facebook Login for Business

**Review surface:** Facebook Messenger DMs and Facebook Page comments only. The
top-level app's `instagram` object is configured on the dedicated Instagram
callback and belongs to evidence section B, not this Facebook section.

### Use case

A person voluntarily sends Lina's Laser Clinics a Facebook Messenger message or
comments on its Facebook Page. Linas AI answers clinic questions from
tenant-approved information. For a public comment, it sends one relevant public
reply; an approved comment rule may instead use Meta's supported
customer-initiated private-reply path.

When a person asks to book or contact a human for supported laser hair removal,
the assistant asks only for the branch and gender still needed, one field at a
time, then supplies the matching public WhatsApp handoff number/link. It does not
claim that an appointment was booked, changed, confirmed, or cancelled inside
Meta or a CRM. This review does not request Instagram, content-publishing,
advertising, commerce, mass-outreach, or unsolicited-message permissions.

### Requested permissions

- `business_management`: resolve the previously recorded business's eligible
  Page assets; current business verification/ownership is a pre-submission
  Dashboard gate.
- `pages_show_list`: let an authorized administrator select the clinic Page.
- `pages_manage_metadata`: create and maintain the Page webhook subscription.
- `pages_read_engagement`: read Page engagement context required by the connected
  Page flow.
- `pages_messaging`: receive and answer customer-initiated Messenger DMs.
- `pages_read_user_content`: receive customer-authored Page comment content.
- `pages_manage_engagement`: reply to those Page comments.

Keep these Facebook requests and evidence separate from the Instagram permission
section in the same top-level draft.

### Facebook reviewer steps

#### Messenger DM

1. Use the dedicated reviewer/tester role supplied through Meta's private review
   mechanism; no owner password or 2FA is supplied.
2. Open Messenger for **Lina's Laser Clinics** and send:
   `Hello, what laser services do you offer?`
3. Verify exactly one relevant reply is visible to the reviewer.
4. Send: `I want to book an appointment with a human for laser hair removal.`
5. Answer the branch question with `Beirut`, then the gender question with
   `Women`.
6. Verify exactly one assistant reply supplies `+96178847527` with the matching
   `wa.me` handoff and does not claim an appointment was booked.

#### Page comment

1. Add a test comment to the designated reviewer post:
   `What should I know before a laser hair removal session?`
2. Verify exactly one relevant public reply appears below that comment.
3. Verify the reply is a service answer, not an unsolicited promotion, and that
   no unrelated comment is processed.

### Facebook evidence set

Create two short, timestamped recordings: Facebook DM and Facebook Page comment.
Each recording must show the controlled inbound action and exactly one
recipient-visible reply, with enough time afterward to show that no duplicate is
created. Attach these recordings only to the matching Facebook permission
requests in the Linas AI form.

The time-bounded runtime probe may accompany the packet as a supporting
operational signal. Its DM marker proves that Meta accepted a send and returned a
message ID; it is not a delivery receipt and it does not by itself correlate the
controlled event or prove no duplicate. The recording is the delivery and
one-in/one-out evidence.

### Facebook URLs

- OAuth redirect: `https://www.linasaibot.com/oauth/meta/callback`
- Webhook callback: `https://www.linasaibot.com/webhook/meta-messaging`
- Data deletion: `https://www.linasaibot.com/oauth/meta/data-deletion`
- Deauthorization: `https://www.linasaibot.com/oauth/meta/deauthorize`

The live Dashboard confirms all four Facebook URLs above. The Page callback is
`/webhook/meta-messaging`, and `feed`, `messages`, and `messaging_postbacks` are
subscribed at webhook version `v26.0`.

## Evidence section B — Instagram Login review

**Top-level Meta app:** Linas AI, app ID `2963733803971681`

**Instagram product app ID:** `1035856539045307` with a separate product secret,
redirect, callback, verify token, and access token inside Linas AI

**Product/auth flow:** Instagram API with Instagram Login

**Review surface:** Instagram DMs and comments on the connected professional
account only.

### Use case

A person voluntarily sends the connected Lina's Laser Clinics professional
account an Instagram DM or comments on its media. Linas AI answers clinic
questions from tenant-approved information and may send one relevant public
comment reply. For a supported laser-hair-removal booking or human request, it
collects only the missing branch/gender and supplies the matching public WhatsApp
handoff. It does not claim a booking. This review does not request Facebook,
content-publishing, advertising, commerce, mass-outreach, or unsolicited-message
permissions.

### Requested permissions

- `instagram_business_basic`: resolve the connected professional identity.
- `instagram_business_manage_messages`: receive and answer
  customer-initiated Instagram DMs.
- `instagram_business_manage_comments`: receive and answer comments on the
  connected professional account.

Do not request `instagram_basic`, `instagram_manage_messages`,
`instagram_manage_comments`, `instagram_business_content_publish`, or
`instagram_business_manage_insights` for this use case. The first three belong to
a legacy flow; publishing and insights are separate capabilities. The generated
Instagram embed sample currently includes the last two extras, but the
application requests only the three permissions above. Do not expand the runtime
or review merely to match that sample.

### Instagram reviewer steps

#### Direct message

1. Open the connected Lina's Laser Clinics professional account in Instagram
   DMs and send: `Hi, how should I prepare before a laser hair removal session?`
2. Verify exactly one relevant reply is visible to the reviewer.
3. Send: `Please connect me to someone for laser hair removal.`
4. Answer the branch question with `Beirut`, then the gender question with
   `Women`.
5. Verify exactly one assistant reply supplies `+96178847527` with the matching
   `wa.me` handoff and does not claim a booking.

#### Media comment

1. Add a test comment to the designated reviewer media:
   `How should I prepare before a laser hair removal session?`
2. Verify exactly one relevant public reply appears below that comment.
3. If the review demonstrates a configured private-reply rule, verify it uses
   the original comment ID and only one supported response path.

### Instagram evidence set

Create two short, timestamped recordings: Direct IG DM and Instagram media
comment. Each recording must show the controlled inbound action and exactly one
recipient-visible reply, with enough time afterward to show that no duplicate is
created. Attach these recordings only to the matching Instagram permission
requests in the Linas AI form.

The time-bounded runtime probe is supporting evidence only. Its Direct IG DM
marker proves Send API acceptance with a message ID, and its comment marker proves
reply-send acceptance; neither substitutes for the recipient-visible recording.
The Direct IG packet must also contain a separate live profile/token check and a
read-only `subscribed_apps` result showing one row for app `1035856539045307` with
`messages,messaging_postbacks,comments`. The registry scope audit alone does not
prove those live facts.

### Instagram URLs

- OAuth redirect: `https://www.linasaibot.com/oauth/instagram/callback`
- Webhook callback: `https://www.linasaibot.com/webhook/instagram-login`
- Data deletion: `https://www.linasaibot.com/oauth/instagram/data-deletion`
  (**populate before submit —** `docs/META_DASHBOARD_COMPLIANCE_AND_DRAFT_CHECKLIST.md`)
- Deauthorization: `https://www.linasaibot.com/oauth/instagram/deauthorize`
  (**populate before submit —** same checklist)

If Instagram/Facebook comment Graph reads return HTTP 200 with `"data": []` and no
comment webhooks arrive for tester accounts, file Meta Support using
`docs/META_SUPPORT_TICKET_COMMENTS_NOT_DELIVERED.md` before attempting comment
App Review recordings.

The live Dashboard confirms the Instagram OAuth redirect and dedicated webhook
callback. `comments`, `messages`, and `messaging_postbacks` are subscribed at
webhook version `v26.0`. Tester accounts `linaslaser` and `boc_system` are present,
and each shows **Webhook Subscription: On**. The two empty Instagram compliance
URLs must be populated and their signed callbacks tested before submission.

The generic Webhooks selector also shows an unexpected `User` object subscription
pointing to `/webhook/instagram-login`; all visible User fields are Unsubscribed.
Do not call it harmless or remove it during a read-only audit. The owner must
approve the Meta mutation, and the strict reconciler must fail closed until the
extra-object decision is recorded and the resulting state is verified. Expected
objects are Page on the Facebook callback, Instagram on the dedicated callback,
and the preserved WhatsApp Business Account object.

## Shared app-level policy answers

- **Data received:** app/product-scoped authorizer identifiers; platform-scoped sender,
  destination, message/comment/media IDs; voluntarily submitted DM/comment text;
  timestamps; postbacks; and attachment metadata for that app's surfaces.
- **Purpose:** authenticate and deduplicate webhook events, route them to the
  connected business asset, maintain conversation continuity, answer from
  tenant-approved knowledge, enforce reply policy, and provide a requested human
  handoff.
- **Processors:** Meta for delivery, OpenAI for response generation, Google
  Cloud/Firebase for operational storage, and DigitalOcean for hosting.
- **Retention/deletion:** according to the published Privacy Policy. Signed Meta
  deletion/deauthorization callbacks are verified with the secret for the exact
  originating product credential domain, mapped through the authorization owner
  and auth flow, and
  remove or redact records under Linas AI's control. Terminal-event
  retention/redaction primitives plus a scheduled/manual count-only job exist in
  the recovery worktree, but automatic production retention may not be claimed
  until that workflow is deployed, monitored, and proved against local and
  Firestore stores. Historical rows whose authorization-owner lineage was already
  overwritten require a separate remediation audit and must not be described as
  reconstructable.
- **Security:** HTTPS; per-product HMAC-SHA256 verification; exact asset/auth-flow
  routing; encrypted credential registry; durable deduplication; credential-free
  settings snapshots; and least-privilege operator access. Inbound ledgers still
  contain the DM/comment payload needed for processing; they are not
  metadata-only stores.
- **Sale/advertising:** social data is not sold or used for third-party ads.

Shared public URLs in the one form:

- Website: `https://www.linasaibot.com/`
- Privacy: `https://www.linasaibot.com/privacy-policy`
- Terms: `https://www.linasaibot.com/terms`
- User deletion instructions/status: `https://www.linasaibot.com/data-deletion`
- App domain: `linasaibot.com`

## One-draft pre-submission authorization

Live draft `2964793000532428` currently mixes the ten desired social permissions
with legacy `instagram_basic`, `instagram_manage_messages`,
`instagram_manage_comments`, and unrelated WhatsApp requests. Do not submit it in
that state. **Cleanup steps:** `docs/META_DASHBOARD_COMPLIANCE_AND_DRAFT_CHECKLIST.md` § Part 2.

Facebook evidence section:

- [x] Business Verification and Access Verification are Verified; there are no
  Required Actions.
- [ ] App mode remains Unpublished and all seven desired Facebook permissions are
  only Ready for testing until Advanced Access is granted.
- [ ] Exact Facebook callback/Page subscription and Facebook compliance URLs are
  preserved as live-read facts in the evidence packet.
- [ ] The Facebook live scope/token audit passes, and the two Facebook recordings
  show timestamped one-in/one-out behavior with no duplicate.

Instagram evidence section:

- [ ] All three desired Instagram permissions remain only Ready for testing until
  Advanced Access is granted; the two tester accounts and their per-account
  Webhook Subscription On state are recorded.
- [ ] Dedicated callback, exact live profile/token, and exact `subscribed_apps`
  are freshly evidenced in Meta Dashboard/Graph.
- [ ] The currently empty Instagram Business Login data-deletion and deauthorize
  URLs are populated with the routes above and both signed flows pass.
- [ ] `META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED` reflects only the Instagram
  permission family's evidenced decision and runtime capability output reports
  `approval_domain=instagram_login`; the Facebook flag cannot unlock it.
- [ ] The two Direct IG recordings show timestamped one-in/one-out behavior with
  no duplicate.

- [ ] Remove the three legacy Instagram requests from the draft and remove
  unrelated WhatsApp requests unless they have separately authorized, complete
  evidence. Do not add the embed sample's publishing or insights permissions.
- [ ] The unexpected `User` webhook object has an owner-approved cleanup decision
  and strict read-after-write verification; no audit session mutates it.
- [ ] The owner reviews both product-specific evidence sections and explicitly
  authorizes the single declaration and **Submit for Review** action in Linas AI
  app `2963733803971681`.

For the one submission, production SHA, sanitation/rotation, token health, signed
deletion/deauthorization isolation, Privacy/Terms/deletion pages, and all release
blockers in the operational package must pass first. Recordings must contain no
App Secret, access token, webhook verify token, terminal, environment file,
password prompt, 2FA, private customer data, unrelated account, or notification
preview. Store them only in the private evidence location and attach each to the
matching permission request in the one Linas AI review form.

The runtime uses supported Graph API `v24.0`; live webhook subscriptions use
`v26.0`. Preserve this intentional boundary and schedule a controlled migration
before `v24.0` expires rather than treating it as a present review blocker.

## Official Meta references

- [Create an Instagram app](https://developers.facebook.com/documentation/instagram-platform/create-an-instagram-app)
- [Instagram Business Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Graph API versions](https://developers.facebook.com/docs/graph-api/changelog/versions/)
