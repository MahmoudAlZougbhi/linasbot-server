# KEEP surface freeze (WAVE 0)

Frozen from the WAVE 0 KEEP list (AUDIT-06 mobile drawer + required backends).
Audit files `AUDIT-00` … `AUDIT-10` were not in this workspace at freeze time; the lists below match the WAVE 0 prompt and were checked against `mobile/linas-ai/src/features/nav/drawerModules.ts` and `mobile/linas-ai/src/features/cm/cmSections.ts`.

This file is inventory only. WAVE 0 did not delete product code. WAVE 1 executed the proven-dead DELETE list below.

Do not revive Luna customer engine, Monty, or Creative.

## KEEP product UI (mobile)

Drawer:

- AI Setup (CM hub tiles: Knowledge, AI Basics, Locations/hours, Services/prices, Comments rules, Requests rules + Products)
- Dashboard
- Smart Follow-Up
- FAQ (indexed + FAQ screen; may sit outside the hub mosaic)
- Live Chat (+ Comments)
- Requests
- Integrations (IG/FB DM+comments, WA Cloud, TikTok comments if enabled, Web Chat widget)
- Team/users
- Subscription/billing/IAP
- Footer Settings / New Chat
- Owner Copilot chat (Sol / owner_copilot_v2)
- Notifications
- Auth gates / SubscriptionGate
- Deep links: livechat + Meta OAuth
- platform_owner mobile WA pilot

## KEEP web

- Marketing: `/`, `/about`, `/contact`, `/pricing`, `/features`
- Auth recovery: forgot / reset / verify
- portal.linasaibot.com `/owner/*` (analytics/users/messages/catalog/costs)
- Guest chat FAB
- `/web-chat/*` widget (configured from mobile Integrations)
- Compliance: privacy / terms / data-deletion
- Thin `/app` → get-app CTA
- Webhooks / OAuth callbacks

## KEEP backend

- Customer Brain + CM publish/index
- Meta / WA / TikTok / web_chat live webhooks
- Membership / IAP
- Redis queues
- Postgres SoT for products / requests / billing
- owner_copilot_v2 (non-creative)
- customer_reply_v2 as facade only until renamed

## Live Chat isolation (WAVE 0)

- `live_chat_index` documents require `tenant_id`. Unscoped writes are skipped.
- Inbox, waiting queue, counters, thread reads, and operator mutations filter by session `tenant_id`.
- Missing tenant on a row or session is fail-closed (hidden / 403), not inferred as another workspace.
- WhatsApp phone-only user ids do **not** inherit tenant `linas`. Tenant must be on the conversation/index payload (inbound save stamps it when known).
- Unprefixed Instagram/Facebook/TikTok ids still map to `linas` only because `compose_social_user_id` omits the tenant prefix for that workspace.
- Unified inbox memory/disk cache is per-tenant. Legacy unscoped disk cache is refused.
- Firestore composite: `tenant_id` ASC + `last_message_at` DESC (owner-activated deploy; see `docs/FIRESTORE_INDEXES.md`). If the composite is missing, recency is scanned then foreign rows are dropped.

## DELETE candidates (WAVE 1 executed proven-dead items)

WAVE 1 deleted:

- `archive/**` (Meta webhook contract inlined to `scripts/meta_webhook_contract.py`)
- Creative HTTP/tools: `modules/creative_api.py`, `services/creative_studio_service.py`, `services/owner_ai_tools_creative.py`, `services/providers/openai_media.py`; leftover `creative_image`/`creative_video` jobs fail-closed (`creative_studio_cancelled`)
- `services/smart_retrieval_service.py`, `services/retrieval_debug.py`, `GET /api/retrieval-debug/logs`
- Owner Lab: `modules/customer_ai_lab_api.py`, `dashboard/src/pages/owner/OwnerLab.jsx`, `/owner/lab`, `/owner/copilot-setup`
- Mobile CreativeDraft type + unused Create Post i18n
- Marketing copy: Creative Studio / Scheduling on `/features`

Still not deleted (import-graph blocked or KEEP):

- Smart Follow-Up live backend (`services/smart_followup`, `services/whatsapp_cloud/smart_followup`, `/api/whatsapp/smart-followup/*`)
- `smart_messaging_*` files still used by scheduler/catalog/WA templates (HTTP already disabled)
- Clinic corpus `data/*` — prompt path still injects when `published_mode` is false
- Owner AI v1 HTTP CRUD (`modules/owner_ai_api.py`) — mobile conversations/profile still depend on it
- Booking / `api_integrations_*` — BOC is not in the SaaS app; gate stays OFF (`LINASLASER_BOC_BOOKING_ENABLED`); stack still imported
- `owner_copilot_v2/creative_policy.py` KEEP as refusal
- Disabled API prefixes in `product_features.py` stay fail-closed even after HTTP modules are gone

## WAVE 2 — Customer Brain slim

- Voyage entity + knowledge indexes skip Voyage calls when `content_hash` is unchanged (`services/customer_ai/search/reuse_vectors.py`).
- Expense records count only newly embedded rows.
- Title helpers used by CM save go through `search_metadata.title_fields` (not Luna-named imports).
- CM OpenAI `semantic_index` remains for `runtime_pipeline` FAQ semantic search (live handler). Brain retrieve stays Voyage-only. Do not treat CM OpenAI as a Brain fallback.

## WAVE 3 — Comments / hub

- Brain comment history is per-author: `comment:{tenant}:{channel}:{post}:{author}`. Missing author does not fall back to a shared post thread.
- Operator comments inbox stays post-scoped (Live Chat Comments UI).
- AI Setup hub tiles stay the KEEP allowlist (Knowledge, AI Basics, Locations, Services, Comments, Requests + Products).

## WAVE 4 — Billing SoT (mobile Subscription)

Tenant-visible billing is the mobile Subscription screen (`mobile/linas-ai/src/features/billing/useBillingData.ts`).

Compose (both overlay the same helper):

- `GET /api/entitlements/me` → `get_tenant_entitlement_public` + `overlay_message_fields`
- `GET /api/mobile/usage` → credit buckets + the same `overlay_message_fields`

Fields the Subscription UI reads:

- `message_billing_active`
- `included_messages` (catalog allowance even when billing is off)
- `available_messages` / `included_remaining` / `purchased_messages` only when `message_billing_active` is true
- leftover credit quantities stay labeled credits (`wallet_unit=credits`). Credits are not Messages remaining.

This wave does **not** flip `MESSAGE_BILLING_ENABLED`. Credit ledger, leftover_reserve, and token_wallet stay until Mahmoud approves cutover.

## WAVE 5 — Web = marketing + portal

- KEEP marketing routes, thin auth recovery, portal `/owner/*` (overview, users, messages, catalog, costs — not Lab).
- Former operator SPA bookmarks (`OBSOLETE_OPERATOR_PATHS`) redirect to `/#get-app`. Catch-all unknown paths still render the `/app` CTA (`AppEntry`).
- `/wallet` is not a public-site path. Store listing URLs stay `null` until ASC / Play listings are live.
- Guest chat FAB is on the marketing landing. `#talk-to-linas` opens the panel.

## WAVE 6 — Mobile reachable screens

- Screen union is reachable-only. Dead `resource` screen, `RESOURCE_MAP`, and `SimpleResourceScreen` are gone.
- Unused `CONTROL_ITEMS` / `GROUP_LABELS` catalog is gone. `ControlArea` stays (drawer + AppShell).
- `owner` screen / `OwnerPortalScreen` / `area === 'owner'` stay for the platform_owner WA pilot (nav-unreachable from the tenant drawer).
- `usage` still aliases to Dashboard in AppShell. Notifications stay reachable from Settings.


