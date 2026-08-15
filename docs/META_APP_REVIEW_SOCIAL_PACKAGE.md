# Meta social recovery and App Review package

> **The single App Review submission is BLOCKED.** Do not submit draft
> `2964793000532428` until every release gate at the end of this document is
> checked with live, redacted evidence.

The Dashboard has one top-level Meta app: **Linas AI**, app ID
`2963733803971681`. Its Instagram API with Instagram Login product exposes
Instagram App ID `1035856539045307` and its own secret, OAuth redirect, webhook
callback, verify token, access token, and signature boundary inside that same
top-level app. Those Facebook and Instagram product credential domains must never
be mixed, but they are not two top-level Meta apps.

| Surface | Identifier and credential domain | OAuth redirect | Webhook callback |
|---|---|---|---|
| Facebook Page / Messenger | Linas AI app ID `2963733803971681` / Facebook secret | `https://www.linasaibot.com/oauth/meta/callback` | `https://www.linasaibot.com/webhook/meta-messaging` |
| Instagram API with Instagram Login | Instagram product app ID `1035856539045307` / Instagram secret inside Linas AI | `https://www.linasaibot.com/oauth/instagram/callback` | `https://www.linasaibot.com/webhook/instagram-login` |

Meta's official Instagram setup guide adds the Instagram product to the existing
Meta app, and App Review is submitted from that top-level app. Prepare one review
submission with two clearly separated permission/evidence sections:

1. Facebook: the seven Facebook permissions, Facebook DM/Page-comment steps,
   Facebook compliance callbacks, and Facebook recordings.
2. Instagram Login: the three `instagram_business_*` permissions, Instagram
   DM/media-comment steps, Instagram-product compliance callbacks, and Instagram
   recordings.

The evidence sections, reviewer access, declarations, secrets, callbacks, and
approval flags stay product-specific even though the owner performs one final
**Submit for Review** action for Linas AI.

Related production assets:

- Facebook Login for Business configuration: `1369663304545819`
- Facebook Page: `378696005334409`
- Instagram professional account: `17841413184256533`
- WhatsApp Embedded Signup configuration: `1430599348520127` (unchanged)
- Runtime Graph API version: `v24.0`
- App Review draft: `2964793000532428` (one top-level draft)

The Linas AI app's `whatsapp_business_account` webhook object belongs to WhatsApp
Cloud.
Social reconciliation must preserve it and must never replace its callback or
fields.

### Live read-only Dashboard snapshot — 2026-08-14

- Business Verification: **Verified**.
- Access Verification: **Verified**.
- Required Actions: none.
- App mode: **Unpublished**.
- Facebook OAuth redirect, deauthorization URL, and data-deletion URL match this
  package.
- Instagram OAuth redirect matches this package, but the Instagram Business Login
  **Deauthorize callback URL** and **Data deletion request URL** are empty. This is
  a submission blocker; populate them with the Instagram URLs below and test both
  signed flows before review.
- Facebook Page webhook callback is `/webhook/meta-messaging`; `feed`, `messages`,
  and `messaging_postbacks` are subscribed at webhook version `v26.0`.
- Instagram webhook callback is `/webhook/instagram-login`; `comments`, `messages`,
  and `messaging_postbacks` are subscribed at webhook version `v26.0`.
- Instagram tester accounts `linaslaser` and `boc_system` are present, and each
  shows **Webhook Subscription: On**.
- The generic Webhooks selector has an unexpected `User` object pointing to
  `/webhook/instagram-login`; all visible User fields are Unsubscribed. It needs
  an owner-approved cleanup decision and strict verification, not an audit-time
  deletion or a claim that it is harmless.
- Every desired Facebook and Instagram permission is only **Ready for testing**,
  not Advanced Access. Public production capability remains blocked.

The runtime remains intentionally pinned to supported Graph API `v24.0`, while
the live Dashboard webhook subscriptions use `v26.0`. This is a supported
two-version boundary, not an immediate App Review blocker; record it and schedule
a controlled runtime migration before `v24.0` expires.

## Required Dashboard configuration

### Facebook product domain — Page and Messenger

In Facebook Login for Business configuration `1369663304545819`, request only:

- `business_management`
- `pages_show_list`
- `pages_manage_metadata`
- `pages_read_engagement`
- `pages_messaging`
- `pages_read_user_content`
- `pages_manage_engagement`

Do not put `instagram_*` or `instagram_business_*` permissions in this Facebook
configuration. Existing Page tokens must be reauthorized after the two comment
permissions are added.

Facebook social webhook contract:

- Callback: `https://www.linasaibot.com/webhook/meta-messaging`
- `page`: `messages,messaging_postbacks,feed`
- Page `378696005334409` `subscribed_apps`:
  `messages,messaging_postbacks,feed`

Facebook compliance callbacks, confirmed present in the live Dashboard:

- Data deletion: `https://www.linasaibot.com/oauth/meta/data-deletion`
- Deauthorization: `https://www.linasaibot.com/oauth/meta/deauthorize`

### Instagram product domain — Instagram Login

The Instagram connection starts at
`/api/meta/connections/instagram-login/start` and requests exactly:

- `instagram_business_basic`
- `instagram_business_manage_messages`
- `instagram_business_manage_comments`

Do not request `instagram_business_content_publish` or
`instagram_business_manage_insights` in this DM-and-comments review. The
Dashboard's generated Instagram embed sample currently includes both extras, but
the application code requests only the three permissions above. Do not expand
the review or runtime merely to match that sample.

Direct IG contract:

- OAuth redirect: `https://www.linasaibot.com/oauth/instagram/callback`
- Webhook callback: `https://www.linasaibot.com/webhook/instagram-login`
- Webhook signatures: verify only with the Instagram product secret
- App-level `instagram` object: `messages,messaging_postbacks,comments` at
  webhook version `v26.0`
- Professional-account `subscribed_apps` row: app ID `1035856539045307`
  with exactly `messages,messaging_postbacks,comments`
- Data deletion: `https://www.linasaibot.com/oauth/instagram/data-deletion`
  (**currently empty in Instagram Business Login settings**)
- Deauthorization: `https://www.linasaibot.com/oauth/instagram/deauthorize`
  (**currently empty in Instagram Business Login settings**)

The Direct IG callback must not be configured as `/webhook/meta-messaging`.
That route deliberately trusts App A/App B Facebook signatures, not the Direct
IG secret.

### One App Review draft — cleanup required

Live draft `2964793000532428` currently mixes the desired Facebook and Instagram
permission families with legacy `instagram_basic`, `instagram_manage_messages`,
`instagram_manage_comments`, and unrelated WhatsApp permissions. Before the one
top-level submission:

1. Keep the seven Facebook permissions and three Instagram Business permissions
   listed above.
2. Remove the three legacy Instagram permissions.
3. Remove unrelated WhatsApp permissions from this social review unless the owner
   intentionally prepares and evidences that separate capability in the same
   top-level review.
4. Attach separate Facebook and Instagram reviewer instructions and recordings
   to their matching permission requests.

## Safe reconciliation order

After the approved recovery SHA, including the staged Facebook reconnect
hardening, is broad-CI green and deployed:

1. Keep both comment actions and per-asset switches off. Quiesce inbound writers
   for the historical-ledger apply pass. Resolve the exact deployed `APP_DIR` and
   run the sanitizer dry/apply/dry with an explicit `--env-file`; do not rely on
   the current working directory or implicit dotenv discovery. Let active rows
   complete or dead-letter, then run `scripts/redact_meta_inbound_retention.py`
   dry/apply/dry from the same deployed application lineage and preserve its
   count-only clean verification.
2. Before rotating the App A secret, inventory outstanding social-post preview
   and media links that are signed with it. Expire/reissue them or migrate them
   to a dedicated signing key. Coordinate App A secret/verify-token rotation
   atomically with the Facebook callback, the existing WhatsApp Cloud callback,
   WhatsApp Embedded Signup, the protected runtime, and a tested rollback.
3. Rotate the Direct IG secret/verify token in its own trust domain. Revalidate
   both social challenges/signatures and the WhatsApp Cloud challenge/signature
   path; also revalidate Embedded Signup before leaving the maintenance window.
4. Reauthorize Facebook through **Manage Meta Access** to mint a replacement Page
   token with all seven permissions. Reconnect Instagram through **Connect
   Instagram** to mint a replacement Direct IG token and live-verify the unique
   app-ID subscription row with all three fields. Revoke the old access tokens
   only after their replacements pass.
5. After the owner-approved disposition of the unexpected `User` object, run
   **Meta App Webhooks Reconcile**. It repairs and verifies the Page row, strictly
   validates Instagram on its dedicated callback, preserves WhatsApp, and fails
   closed on every unknown object.
6. Run **Meta Comment Webhooks Reconcile** with Page reconciliation enabled. It
   GET-verifies both app-level rows and Page `subscribed_apps` after POST. Then
   run the Page live scope/token audit and the separate Direct IG live
   profile/token/subscription checks.
7. Publish the two comment actions and enable replies per asset:
   `respond_facebook_comments` and `respond_instagram_comments`.
8. Record timestamped controlled tests on all four surfaces, showing one inbound
   action and exactly one recipient-visible reply with no duplicate. Run the
   time-bounded Meta runtime probe in the same window as supporting evidence.

The recovery worktree now stages every Facebook connect/reconnect in a fresh
`testing` binding, requires the integration-token business scope and all six
Page-token social scopes, validates explicit granular targets for both DM and
comment permissions, POSTs and GET-verifies the exact App-A Page subscription,
persists readiness fail-closed, enforces the selected Page's `MESSAGING` and
`MODERATE` tasks, snapshots and compensates every changed Page subscription on a
multi-Page failure, and then atomically activates the selected local registry set
with versioned rollback lineage. Those Facebook reconnect boundaries and per-turn
DM evidence rotation are implemented and locally tested. A cancelled same-sender
waiter now follows the replacement combine task, removes only the exact completed
task it awaited, and has concurrent regression coverage. The scoped fresh review
found no remaining actionable blocker in these local Facebook activation or DM
evidence paths. The recovery is now based on current `origin/main`
`3f5bb73764ffed83c996354661c92bb572b912d6`. The post-sync backend suite is green:
**1,638 passed, two warnings, zero failures**. Mobile verification is **144/144**
for the merged-locale suite plus **41/41** targeted tests. Ruff check and format
are clean across all 82 changed Python files; all 15 changed YAML files parse; two
changed shell scripts pass bash syntax; and the secret scans are clean.
Repository-wide Ruff still has 33 pre-existing errors and repository-wide format
still reports 23 pre-existing files, so the repository as a whole is not claimed
clean. These results are not a production claim.
The approved deployed SHA, Meta Dashboard/live Graph state, sanitation/retention and
lineage closure, and four recipient-visible tests must prove the corrected
behavior or Facebook reconnect and the single App Review submission stay blocked.

Do not use the old DM-only Page/app reconciliation commands. They can remove
`feed` or `comments` on an unrecovered deployment.

## Environment contract

No secret value belongs in documentation, logs, source control, or a support
message.

| Variable | Required role |
|---|---|
| `META_APP_ID` / `META_APP_A_ID` | Linas AI top-level app `2963733803971681` |
| `META_APP_SECRET` / `META_APP_A_SECRET` | Facebook product signature/OAuth secret |
| `META_WEBHOOK_VERIFY_TOKEN` / `META_APP_A_WEBHOOK_VERIFY_TOKEN` | Facebook webhook challenge token |
| `META_APP_A_FACEBOOK_LOGIN_CONFIG_ID` | `1369663304545819` |
| `META_OAUTH_REDIRECT_URI` | `https://www.linasaibot.com/oauth/meta/callback` |
| `META_APP_A_ADVANCED_ACCESS_APPROVED` | Facebook permission-family review gate |
| `META_INSTAGRAM_LOGIN_APP_ID` | Instagram product app ID `1035856539045307` inside Linas AI |
| `META_INSTAGRAM_LOGIN_APP_SECRET` | Direct IG signature/OAuth secret |
| `META_INSTAGRAM_LOGIN_REDIRECT_URI` | `https://www.linasaibot.com/oauth/instagram/callback` |
| `META_INSTAGRAM_LOGIN_WEBHOOK_VERIFY_TOKEN` | Direct IG challenge token |
| `META_INSTAGRAM_LOGIN_WEBHOOK_PATH` | `/webhook/instagram-login` |
| `META_INSTAGRAM_LOGIN_REFRESH_LEAD_DAYS` | Direct IG token refresh lead time |
| `META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED` | Instagram permission-family review gate; keep false until Advanced Access is evidenced |
| `META_INBOUND_PAYLOAD_RETENTION_DAYS` | Terminal inbound-payload retention interval |
| `META_GRAPH_API_VERSION` | `v24.0` |
| `META_MULTI_APP_REGISTRY_ENABLED` | Encrypted registry routing gate |
| `META_CREDENTIAL_ENCRYPTION_KEY` | Registry credential encryption key |

`META_APP_A_LOGIN_CONFIG_ID` is obsolete and must not be set.

`META_APP_A_ADVANCED_ACCESS_APPROVED` records the Facebook permission family,
while `META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED` records the Instagram
permission family in the same top-level app. The recovery runtime selects the
approval domain from each binding's `auth_flow` and fails closed, so a Facebook
decision cannot unlock Instagram DMs or comments. That separation is implemented
and tested locally but is not deployed or live-proven. The Dashboard currently
shows every desired permission as **Ready for testing**, so both flags must stay
false. The strict
`.github/workflows/instagram-login-secrets-apply.yml` workflow is pinned to the
exact deployed SHA, defaults the Direct IG approval input to false, and requires
the exact `CONFIRM_DIRECT_IG_META_APPROVAL` confirmation before it can apply true.
The strict scope audit live-validates the six Facebook **Page-token** permissions.
`business_management` is instead proven on the user/integration token during the
OAuth callback and must also remain selected in the Facebook Login configuration;
requiring it on the Page token would be a false failure. The Direct IG portion reads
registry snapshots and intentionally skips Facebook `debug_token`; it does not by
itself prove a live Direct IG token/profile or current `subscribed_apps`. Record
those Direct IG live checks separately in the Direct IG evidence set.

The count-only retention command `scripts/redact_meta_inbound_retention.py` and
the scheduled/manual `Meta Inbound Payload Retention` workflow are implemented in
the recovery worktree. They are not yet deployed, monitored, or proved against
both production stores. Historical bindings may also predate durable
authorization-owner lineage; already-overwritten owner lineage cannot be safely
reconstructed. Before App Review, deploy and reauthorize/reseed both auth flows,
complete sanitation and retention apply-plus-clean verification, and explicitly
audit/remediate remaining pre-lineage ledger rows. Active rows must first finish
or dead-letter before payload redaction.

## Release and App Review gates

All boxes are mandatory. A green unit-test suite alone is not live proof.

- [ ] Recovery commit is reviewed, committed, and deployed; production SHA
  equals the approved SHA.
- [ ] Historical local and Firestore inbound ledgers are sanitized while writers
  are safely coordinated using the deployed `APP_DIR` and explicit `--env-file`;
  a second dry-run reports zero unsafe records/errors.
- [ ] Every Meta app secret, verify token, Page token, and Direct IG token that
  could have appeared in historical snapshots is replaced, the old value is
  revoked only after its replacement passes, and every affected social/WhatsApp
  trust path is revalidated.
- [ ] Linas AI remains the one top-level app; the Dashboard has the exact
  product-specific redirects, callbacks, permissions, subscribed fields, and
  compliance URLs above. In particular, both currently empty Instagram Business
  Login compliance URLs are populated and tested.
- [ ] App A Page token live scope audit passes all seven Facebook permissions.
- [ ] Direct IG OAuth activation verifies the exact app-ID subscription row and
  all three fields; a separate live Direct IG profile/token check also passes.
- [ ] Facebook and Instagram approval flags reflect their own freshly evidenced
  permission-family decisions from the one top-level review; the capability
  response reports the matching `approval_domain`, and Facebook approval cannot
  enable an Instagram binding. Both remain false while access is only Ready for
  testing.
- [ ] The time-bounded probe shows recent DM send acceptance (Meta message ID),
  recent comment-reply send acceptance, and the dedicated Instagram callback. It
  is supporting evidence only and is not described as a delivery receipt.
- [ ] Four timestamped recordings show one controlled inbound action and exactly
  one recipient-visible Facebook DM, Direct IG DM, Facebook comment reply, and
  Instagram comment reply, with no duplicate.
- [ ] The implemented scheduled/manual terminal-event retention job is present in
  the approved deployed SHA, runs with the exact deployed `APP_DIR` and explicit
  `--env-file`, and produces a successful apply followed by a clean count-only
  verification for local and Firestore stores; its schedule/monitoring is proved.
- [ ] Pre-lineage historical rows are explicitly audited/remediated after both
  flows are reauthorized/reseeded; no claim of complete person-level deletion is
  made for already-overwritten owner lineage that cannot be reconstructed.
- [ ] Signed data-deletion and deauthorization tests pass separately for the
  Facebook and Instagram product callback families without crossing credential
  or auth-flow boundaries.
- [ ] Reviewer recordings contain no credentials, private customer data,
  unrelated accounts, terminals, password prompts, or notification previews.
- [ ] Draft `2964793000532428` contains only intentionally requested permissions;
  legacy Instagram and unrelated WhatsApp requests are removed or separately
  justified with complete evidence.
- [ ] The owner reviews both product-specific evidence sections and explicitly
  authorizes the one top-level declaration and **Submit for Review** action. Do
  not submit during an audit session.

## Official Meta references

- [Create an Instagram app](https://developers.facebook.com/documentation/instagram-platform/create-an-instagram-app)
- [Instagram Business Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Graph API versions](https://developers.facebook.com/docs/graph-api/changelog/versions/)
