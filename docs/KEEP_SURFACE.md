# KEEP surface freeze (WAVE 0)

Frozen from the WAVE 0 KEEP list (AUDIT-06 mobile drawer + required backends).
Audit files `AUDIT-00` … `AUDIT-10` were not in this workspace at freeze time; the lists below match the WAVE 0 prompt and were checked against `mobile/linas-ai/src/features/nav/drawerModules.ts` and `mobile/linas-ai/src/features/cm/cmSections.ts`.

This file is inventory only. WAVE 0 does not delete product code. Later waves execute DELETE candidates.

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

## DELETE candidates (list only — execute in WAVE 1+)

- `archive/**`
- Creative stack: `modules/creative_api.py`, `services/creative_studio_service.py`, `services/owner_ai_tools_creative.py`, mobile Creative dead types/UI, DISABLED `create_post` / social-posts implementations
- `services/smart_retrieval_service.py`
- `retrieval_debug.py` + `GET /api/retrieval-debug/logs`; `SMART_RETRIEVAL_DEBUG`
- `smart_messaging_*` (~8 files) + testing_lab + `/api/test*` + `/api/debug` + `/api/switch-provider` + `/api/analytics` product implementations
- `modules/customer_ai_lab_api.py` unmount from prod; dashboard `OwnerLab.jsx` / `/owner/lab`
- Monty transport leftovers / adapters not needed for WA Cloud-only
- Clinic corpus `data/*` (qa_database, marwa rules, empty kb/style) after confirming CM published is SoT
- Owner AI v1 (`services/owner_ai_*`, `modules/owner_ai_api.py`) if routing proves mobile/portal → owner_copilot_v2 only
- Dead web operator SPA remnants behind get-app redirects
- Orphan booking FSM / `api_integrations_*` if the SaaS app does not use BOC booking (leave a note: BOC not in SaaS app)
- Unused CM fields; dual `semantic_index` if Voyage-only
- Luna customer-retrieval engine leftovers
