# Meta two-app provider architecture

## Provider boundary

The platform recognizes exactly two server-side Meta app keys:

| Key | Classification | Purpose |
| --- | --- | --- |
| `linas_first_party` | Own Business | Lina's Page `378696005334409` and Instagram `17841413184256533` only |
| `saas_tech_provider` | Tech Provider | Future independent businesses using Facebook Login for Business |

App secrets and webhook verification credentials remain environment-only. Page tokens are
stored as AES-256-GCM envelopes under the persistent data root. Dashboard APIs return only
redacted configuration flags, binding metadata, permission names, and token expiry status.
Normal dashboard users cannot enter or retrieve an App Secret, Page token, verification token,
configuration ID, or app key.

## Minimum permission boundary

Facebook bindings require `pages_show_list`, `pages_manage_metadata`,
`pages_read_engagement`, and `pages_messaging`. Instagram bindings additionally require
`instagram_basic` and `instagram_manage_messages`. The registry rejects credentials containing
known comments, publishing, advertising, commerce, WhatsApp, or `business_management` scopes.
Webhook subscription fields are exactly `messages` and `messaging_postbacks`.

## Connection and activation sequence

1. The authenticated dashboard session supplies the tenant. Request bodies cannot select a
   different tenant or App ID.
2. The server creates a high-entropy, one-time OAuth state and invokes App B's Facebook Login
   for Business configuration using the authorization-code flow. No permissions are added by
   the browser; the Meta configuration is the scope source.
3. The server exchanges the code, inspects the integration and Page tokens, verifies App ID,
   authorization owner, Page profile, granular targets, scopes, expiry, and the linked
   professional Instagram ID. The App Secret is sent only in a form body or authorization
   header, never in an outbound URL.
4. Exactly one eligible Page must be selected. The Page token is encrypted immediately and a
   `testing` binding is recorded. OAuth codes and tokens never reach the dashboard.
5. Activation is separate. It requires App B Advanced Access to be recorded, tenant-specific
   published AI content, a successful DM-only webhook subscription, and an exclusive registry
   transaction. Lina's assets additionally require the separate
   `META_APP_B_LINAS_CUTOVER_APPROVED` action-time cutover flag.

Active indexes enforce both `(tenant, channel)` and `(channel, asset_id)` uniqueness. The
receiving app signature must match the binding's app key before a webhook can reach the
canonical AI processor. Message IDs are namespaced by app key and binding ID and claimed durably, preventing
duplicate replies across redeliveries or provider changes.

## Isolation and audit

Future tenant customer IDs use `tenant:channel:sender` namespaces. Tenant ID, app key, and
binding ID follow each event into the canonical AI state. Published content is loaded for that
tenant. A SaaS tenant never inherits Lina's deterministic WhatsApp routing matrix; external
handoff contacts must be published in that tenant's own content.

Registry audit lines contain action, a truncated actor hash, tenant, channel, app key, binding
ID, result, and a truncated asset hash. They do not contain access tokens, App Secrets,
verification credentials, OAuth codes, customer message bodies, raw user IDs, email addresses,
or raw asset IDs.

App B's deauthorization callback is `https://www.linasaibot.com/meta/deauthorize`. It verifies
Meta's HMAC-signed request against the single matching app, identifies only credentials whose
encrypted authorization-owner ID matches, marks those bindings disconnected, and deletes the
local encrypted token. App A is never mutated by an App B deauthorization request. The data
deletion callback remains `https://www.linasaibot.com/data-deletion`.

## Approval outcomes

- Both approved: App A remains active for Lina's; App B can activate future tenant assets.
- Only App A approved: Lina's remains on App A; every App B connection stays `testing`.
- Only App B approved: no automatic Lina switch. App B may stage Lina's assets, but activation
  still requires an explicit action-time cutover flag and the normal exclusivity transaction.
- Neither approved: preserve the current provider/rollback configuration and tester-only
  bindings; record Meta's exact rejection reasons and resubmit compliant corrections.

## Production migration and rollback

The canonical multi-app apply workflow first writes aliases with registry routing disabled,
restarts the legacy App A route, validates App A's Page token against Graph v24.0, and seeds
encrypted Facebook and Instagram App A bindings. Registry routing is enabled only after both
bindings exist. `/api/ready` then verifies the encryption key, App A credentials, both Lina
bindings, exclusive indexes, token expiry/scopes, and that App B is not active on Lina's.

If startup or readiness fails, the apply script restores
`META_MULTI_APP_REGISTRY_ENABLED=false`, restarts the legacy route, and exits unsuccessfully.
Provider rollback subscribes the previous binding, unsubscribes the current provider, and
commits the registry rollback; on failure it restores the current subscription. The retired
app and encrypted rollback artifacts are never deleted or revoked by this workflow.
