# Meta app and product credential-domain architecture

This document separates concepts that must not be conflated:

1. **Linas AI** is the one current top-level Meta app, app ID
   `2963733803971681`. The registry calls its Facebook provider
   `linas_first_party` / App A.
2. App B (`saas_tech_provider`) is the future Facebook provider for independent
   SaaS tenants.
3. Instagram product app ID `1035856539045307` belongs to the Instagram API with
   Instagram Login product inside Linas AI. It is not a second current top-level
   Meta app, but it has its own secret, OAuth redirect, webhook callback, verify
   token, token host, compliance callbacks, and fail-closed approval gate.
4. Linas AI has one App Review draft/submission, `2964793000532428`, with separate
   Facebook and Instagram permission/evidence sections.

## Trust boundaries

| Surface | Auth flow | Signature/callback boundary | Intended permissions |
|---|---|---|---|
| Lina Facebook Page | `facebook_login` / Linas AI Facebook domain | `/webhook/meta-messaging`, Facebook secret | Page DM + Page comments |
| Lina Instagram | `instagram_login` / Linas AI Instagram product domain | `/webhook/instagram-login`, Instagram product secret | IG DM + IG comments |
| Future Facebook tenant | `facebook_login` / App B | `/webhook/meta-messaging`, App B secret | Approved tenant capabilities only |

The main callback must not accept a Direct IG signature. The dedicated Instagram
callback must not accept App A/App B signatures. Outbound Graph host, asset ID,
product identifier, credential, and auth flow are all derived from the same
binding; a token must never be debugged, subscribed, or sent through the other
product domain's host/secret.

## Current Lina permission contracts

The Linas AI Facebook permission family requires:

- `business_management`
- `pages_show_list`
- `pages_manage_metadata`
- `pages_read_engagement`
- `pages_messaging`
- `pages_read_user_content`
- `pages_manage_engagement`

The Linas AI Instagram Login permission family requires:

- `instagram_business_basic`
- `instagram_business_manage_messages`
- `instagram_business_manage_comments`

The DM/comment flow does not request content publishing, insights, advertising,
commerce, or unrelated scopes. The Dashboard's generated Instagram embed sample
currently includes `instagram_business_content_publish` and
`instagram_business_manage_insights`; the application does not request them and
must not be expanded merely to match the sample. App B's future permission set is
a separate product/review decision and must not weaken the current credential
boundaries.

All ten desired permissions currently show **Ready for testing**, not Advanced
Access. The top-level app is **Unpublished**. Business Verification and Access
Verification are both **Verified**, and there are no Required Actions; those
positive facts do not override the permission or publication gates.

## Subscription contracts

- Linas AI Page object on `/webhook/meta-messaging`:
  `messages,messaging_postbacks,feed`
- Linas AI Instagram object on `/webhook/instagram-login`:
  `messages,messaging_postbacks,comments`
- Lina Page `subscribed_apps`: `messages,messaging_postbacks,feed`
- Instagram account `subscribed_apps`: exactly the Instagram product row with
  `messages,messaging_postbacks,comments`
- App A `whatsapp_business_account`: preserve unchanged on its own WhatsApp
  callback; social reconcilers never replace or delete it

All reconciliation is read → validate safe repair boundary → POST merged approved
fields → GET → strict exact verification. Missing/inactive/wrong-callback social
rows are repairable; duplicates, unknown objects, or unknown social fields fail
closed.

The live Dashboard shows the expected Page callback with
`feed,messages,messaging_postbacks` and the expected Instagram callback with
`comments,messages,messaging_postbacks`, both at webhook version `v26.0`.
Instagram tester accounts `linaslaser` and `boc_system` each show Webhook
Subscription On. It also shows an unexpected generic `User` object subscription
pointing to `/webhook/instagram-login`, with all visible User fields Unsubscribed.
That extra object is an owner-approved cleanup decision and a strict-reconciler
fail-closed condition; do not remove it or call it harmless during a read-only
audit. The expected object set is Page, Instagram, and the preserved
`whatsapp_business_account` object.

## Connection and activation

1. The authenticated dashboard session supplies the tenant; request bodies do
   not choose an arbitrary tenant or app.
2. A high-entropy one-time OAuth state binds the browser callback to the tenant,
   app, channel, and intended auth flow.
3. The server exchanges the code, verifies token app/owner/scopes/target/expiry,
   encrypts the credential, and creates a fresh `testing` binding for both new
   connects and reconnects.
4. Facebook requires all seven review scopes, a successful Page
   `subscribed_apps` POST, a GET-after whose unique App-A row exactly matches
   `feed,messages,messaging_postbacks`, and fail-closed readiness persistence.
   Direct IG requires a versioned live `/{ig-user-id}/subscribed_apps` GET whose
   unique row ID matches `1035856539045307` and whose fields match its required
   contract.
5. Only after the matching checks does the registry atomically activate the
   selected local binding set with its versioned rollback lineage. Before that
   cutover, every selected Page's `MESSAGING`/`MODERATE` tasks are enforced and its
   subscription is snapshotted; a later failure restores the exact prior external
   subscription state. A failed callback therefore leaves the prior active
   binding set in place, or fails closed with retained inactive staging state if
   external compensation itself cannot be verified.

App-review approval remains permission-family scoped inside the one top-level
app. Facebook uses `META_APP_A_ADVANCED_ACCESS_APPROVED`; Instagram Login uses
`META_INSTAGRAM_LOGIN_ADVANCED_ACCESS_APPROVED`. Capability state derives the
approval domain from `auth_flow` and fails closed, so Facebook approval cannot
unlock Instagram. This separation is implemented locally but is not deployed or
live-proven. Both flags remain false while the Dashboard reports only Ready for
testing.

The recovery now uses current `origin/main`
`3f5bb73764ffed83c996354661c92bb572b912d6`. The post-sync backend suite is green:
**1,638 passed, two warnings, zero failures**. Mobile verification is **144/144**
for the merged-locale suite plus **41/41** targeted tests. Ruff check and format
are clean across all 82 changed Python files; all 15 changed YAML files parse; two
changed shell scripts pass bash syntax; and the secret scans are clean.
Repository-wide Ruff retains 33 pre-existing errors and repository-wide format
reports 23 pre-existing files, so whole-repository cleanliness is not claimed.
Page-token scope provenance, explicit comment targets, Page-task
eligibility, multi-Page compensation, versioned rollback visibility, and per-turn
DM evidence rotation are covered by the local recovery. A cancelled same-sender
waiter follows the replacement combine task and compare-removes only the exact
completed task it awaited; concurrent regression coverage exercises that path.
The scoped fresh review found no remaining actionable blocker in those local
paths. Production and the single App Review submission remain blocked on the
approved deployed SHA, historical-lineage and data-hygiene closure, and live
task/scope/subscription and recipient-visible verification. The empty Instagram
Business Login compliance URLs and unexpected User webhook object are additional
Dashboard blockers.

Active indexes enforce tenant/channel and channel/asset uniqueness. Durable
provider event IDs and claims prevent duplicate replies across redelivery and
worker retries. Terminal no-text/quota outcomes complete once; transient Graph or
delivery failures release their claim for retry.

## Credential and event storage

App secrets and verify tokens are environment-only. Access tokens live in the
encrypted credential registry. The inbound ledger's **settings snapshot** is an
allowlisted, credential-free routing snapshot; workers rehydrate current
credentials from the registry/environment. The ledger still stores the
normalized DM/comment payload and conversation identifiers needed for durable
processing. It is not a routing-metadata-only store.

Historical ledgers created before this rule must be sanitized while writers are
coordinated, re-scanned to zero, and followed by rotation of every potentially
exposed secret/token. Logs and audit output contain only fixed labels, counts,
suffixes, and status—not token values or customer content.

Terminal-event retention/redaction helpers, the on-request authorization deletion
path, `scripts/redact_meta_inbound_retention.py`, and a scheduled/manual production
workflow exist in the recovery worktree. A recurring automatic-retention claim is
not allowed until that workflow is deployed, monitored, and count-only
apply/clean-verify evidence covers local and Firestore stores.

Bindings created before authorization-owner lineage was persisted can contain an
empty or overwritten owner reference. Current/future OAuth and reseeding preserve
versioned lineage, but already-overwritten historical lineage cannot be safely
reconstructed. Reauthorize/reseed both flows and explicitly remediate pre-lineage
ledger rows before claiming complete signed-deletion coverage; active rows must
finish or dead-letter before retention redacts their payloads.

## Compliance callbacks

Facebook product callback family, confirmed configured in the live Dashboard:

- Data deletion: `/oauth/meta/data-deletion`
- Deauthorization: `/oauth/meta/deauthorize`

Instagram product callback family, currently **empty in Instagram Business Login
settings** and therefore blocked until configured and signed-test verified:

- Data deletion: `/oauth/instagram/data-deletion`
- Deauthorization: `/oauth/instagram/deauthorize`

Each signed request is verified only with its originating product secret and may
revoke/delete only credentials in the matching auth flow. App-scoped authorizer
IDs are not treated as public message sender IDs.

## Release rule

Do not switch providers, submit App Review, or claim production readiness from
local tests alone. The required proof is: approved/deployed SHA; clean scope and
subscription gates; sanitized historical ledgers plus rotation; read-only Meta
Dashboard verification; and timestamped recordings showing one controlled
inbound action and exactly one recipient-visible reply on Facebook DM, Direct-IG
DM, Facebook comment, and Instagram comment. The time-bounded runtime probe is a
supporting send-acceptance signal, not a delivery receipt or duplicate-proof
mechanism. Draft `2964793000532428` must be cleaned of legacy
`instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`, and
unrelated WhatsApp requests. Linas AI then requires one owner-authorized App
Review submission with separate Facebook and Instagram evidence sets and
permission-family declarations.

The runtime uses supported Graph API `v24.0`; the Dashboard's webhook field
subscriptions use `v26.0`. Treat this as an intentional two-version boundary and
future migration check, not an immediate App Review blocker.

## Official Meta references

- [Create an Instagram app](https://developers.facebook.com/documentation/instagram-platform/create-an-instagram-app)
- [Instagram Business Login](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/business-login)
- [Graph API versions](https://developers.facebook.com/docs/graph-api/changelog/versions/)
