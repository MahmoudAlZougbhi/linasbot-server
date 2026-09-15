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
- Unprefixed Instagram/Facebook/TikTok ids are unscoped unless `tenant_id` is stamped on the payload or the id is `{tenant}:{channel}:{asset}:{sender}`.
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

- Smart Follow-Up live backend (`services/smart_followup`, `services/integrations/whatsapp/smart_followup`, `/api/whatsapp/smart-followup/*`)
- WA Cloud + Live Chat template id aliases live in `services/live_chat/template_ids.py` (WAVE X2)
- `owner_ai_tools*` (WAVE B git-mv into `services/owner_copilot/`)
- `owner_copilot/creative_policy.py` KEEP as refusal
- Disabled API prefixes in `product_features.py` stay fail-closed even after HTTP modules are gone

## WAVE 2 — Customer Brain slim

- Voyage entity + knowledge indexes skip Voyage calls when `content_hash` is unchanged (`services/brain/search/reuse_vectors.py`).
- Expense records count only newly embedded rows.
- Title helpers used by CM save go through `search_metadata.title_fields`.
- FAQ/Brain retrieve is Voyage-only. CM OpenAI `semantic_index` is not used on publish.

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

This wave does **not** flip `MESSAGE_BILLING_ENABLED`. Credit ledger and leftover_reserve stay until Mahmoud approves message-meter cutover.

WAVE D executed the cutover: live meter is **credits** (plan allowance + IAP `com.linasai.credits.*`). Message billing, token-wallet AI gate, and draft message catalog are not live.

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

## WAVE 7 — Zero-legacy freeze

Live product paths must not import deleted Creative / Owner Lab / smart_retrieval / archive modules. Monty names stay only on the refuse list. Customer retrieval is Voyage (`voyage-4-large` / Brain). `title_fields` is the title helper. CM publish does not build an OpenAI file semantic_index.

| Wave | What KEEP / done |
| --- | --- |
| 0 | Live Chat `live_chat_index` is tenant-scoped and fail-closed |
| 1 | Proven-dead Creative / Lab / archive / retrieval-debug deleted |
| 2 | Voyage incremental publish (`reuse_vectors`) |
| 3 | Brain comment history is per-author; hub tiles KEEP allowlist |
| 4 | Mobile Subscription compose is billing SoT (`overlay_message_fields`) — flag not flipped |
| 5 | Web = marketing + portal; guest FAB on; store URLs unset |
| 6 | Mobile Screen union reachable-only; owner screen kept |
| 7 | This freeze + matrix |

Still not deleted (KEEP or import-graph blocked): Smart Follow-Up live backend, `creative_policy.py` refusal, disabled API prefixes in `product_features.py`. Museum `smart_messaging_*` is gone (WAVE X2).

## WAVE C — Voyage-only index; Luna names purged from retrieval

- CM publish builds the Brain Voyage index only (`schedule_tenant_index` + `content_hash` reuse). It does not call OpenAI `semantic_index.build_index`.
- FAQ/knowledge semantic hits in `runtime_pipeline` go through `services/ai_setup/voyage_search.py` → Brain retrieve.
- `model_policy` customer retrieval = `voyage-4-large`, not an LLM.
- Deleted `luna_titles.py` and `luna_title_resolver.py`. Product match is deterministic title search. Search-metadata generation uses Sol.
- Keep #677 media analysis (`brain/media`).

## WAVE A — fail-closed tenants + delete clinic/BOC/v1/lab/train

MUST 1–8 executed:

1. Missing tenant is 403 / skip / empty. No live `or "linas"` / `DEFAULT_TENANT_ID="linas"` fallback. `require_tenant_id` raises. Unprefixed IG/FB/TikTok ids are unscoped.
2. Clinic `data/qa_database.json` + marwa rules deleted. `published_mode` always true. Clinic file corpus is not injected.
3. `services/booking/**` and `api_integrations*` deleted. Runtime callers fail-closed via `services/saas_no_boc.py`. Doc: `docs/BOC_NOT_IN_SAAS.md`.
4. Mobile Copilot HTTP is `modules/owner_copilot_api.py` (CRUD) + Sol stream (`owner_copilot_stream_api`). `main.py` does not mount `owner_ai_api`. Owner turn is v2-only.
5. WA `/train` handlers unhooked from webhook/text/voice/photo paths.
6. Lab allowlist is `lab` / `lab_*` only — linas is not a lab tenant.
7. Creative flags purged from `plan_catalog`. Copilot Creative refusal stays in `owner_copilot/creative_policy.py`.
8. Comment Brain ids are always `comment:{tenant}:{channel}:{post}:{author}`. Post-scoped conversation_id is ignored. Two authors on one post load two histories.

Keep #677 media analysis.

## WAVE B — domain packages match the mobile drawer

| App surface | Package |
|-------------|---------|
| AI Setup | `services/ai_setup/` |
| Dashboard | `services/dashboard/` |
| Follow up | `services/smart_followup/` |
| FAQ | `services/faq/` |
| Live Chat | `services/live_chat/` |
| Requests | `services/requests/` |
| Integrations | `services/integrations/` |
| Team | `services/team/` |
| Subscription | `services/billing/` |
| Owner Copilot | `services/owner_copilot/` |
| Customer Brain | `services/brain/` (`brain/comments`, `brain/media`) |

`main.py` imports are grouped by those domains. `modules/owner_copilot_api.py` is the Copilot HTTP mount; `modules/owner_ai_api.py` stays gone. Channel capability status copy lives in `services/integrations/channel_capability_status.py` so the matrix file stays under 500 lines.

## WAVE D — one billing meter = mobile Subscription credits

- Live meter is credits: `plan_catalog` included credits + IAP `com.linasai.credits.*` (`services/iap_product_catalog.py`).
- `message_billing_enabled` / `message_billing_cutover` are always false. Overlay `message_billing_active` is always false.
- Token wallet does not gate or debit live AI (`token_metering` is a credit-ledger preflight only).
- Duplicate `TenantEntitlementRow.pending_plan_*` columns removed.
- Feature flags on plans come from `plan_catalog`, not the draft message catalog.

## WAVE E — hub tiles only; one services SoT

- AI Setup hub tiles are Knowledge, AI Basics, Locations/hours, Services (`prices`), Comments, Requests + Products. FAQ stays as a drawer screen.
- Brain and runtime read **CM `prices.catalog` only**. CM `services` is not a live section (`CM_SECTIONS`).
- Postgres `/api/mobile/services` and `services/service_catalog` are deleted. No dual PG/CM writes.
- Knowledge redistribution upserts derived service rows into `prices.catalog`.

## WAVE F — web marketing+portal; mobile drawer-only

- Web KEEP: public marketing, owner portal (Overview / Users / Message flow / Message catalog / Costs), auth recovery, web-chat widget. Lab, Creative, and operator SPA pages stay gone.
- Portal sidebar is those five items only (`dashboard/src/pages/owner/OwnerPortalShell.jsx`).
- Mobile screen union is drawer tiles + Copilot chat + auth + notifications + nested AI Setup / products / services + deep links. `owner` remains the platform_owner WA pilot (not a tenant drawer tile).
- Snapchat is not a live Integrations row (no coming-soon stub). Connectable channels: Instagram, Facebook, WhatsApp, Website, TikTok.
- KEEP hub tiles stay `mobileSupported: true`. Creative types stay refused under Owner Copilot only.

## WAVE G — zero-legacy freeze + acceptance matrix

CI fails when live mounts still have: Monty as a runtime WhatsApp path, Luna title resolver / Luna customer retrieval, Creative enabled on plans, `smart_retrieval`, live `/api/test*` routers, Owner AI v1, dual OpenAI `semantic_index` on publish, BOC booking, clinic `data/qa_database.json` corpus, or `DEFAULT_TENANT` / `or "linas"` prod fallback.

Matrix (see `tests/test_wave_g_acceptance_matrix.py`): every drawer tile; Live Chat tenant A≠B; two commenters = two histories + #677 media; AI Setup publish → Voyage; Requests; Integrations without Snapchat; Subscription credits SoT; web marketing + portal + widget; Copilot Sol + Creative refused; domain folders ≤500.

Scale job-progress still uses historical Redis stage labels (`luna_started`). Those are stuck-threshold keys, not the customer Luna engine. Renaming them would change env/histogram names (infra — needs Mahmoud).

## WAVE X1 — founder / Laser special-cases

- Live Python must not treat tenant slug `linas` as an env override, analytics default, Meta deletion extra-id, or WhatsApp number matrix.
- `INITIAL_RESTRICTED_TOPIC_IDS` / `INITIAL_RESTRICTED_LABELS` are empty. Owners add Restricted Topics themselves.
- `DEFAULT_SOCIAL_WHATSAPP_CONTACTS` is empty. Unpublished tenants resolve no clinic WhatsApp numbers.
- Prod apply/stage scripts write `LINAS_CUSTOMER_AI_LAB=false` (never `true`).
- Authenticated KEEP APIs (Live Chat, Requests, WhatsApp, Copilot, CM, billing, …) use one allowlist for every tenant. Founder slug `linas` is not exempt. Missing session tenant is 403. Meta connection activate requires published CM for every tenant.
- Evidence: `docs/FINAL_CLEANUP_VERIFY.md`. Tests: `tests/test_wave_x1_founder_cleanup.py`.

## WAVE X2 — museum delete

- `normalize_template_id` lives in `services/live_chat/template_ids.py` (Live Chat logs + WA Cloud templates).
- Remaining `smart_messaging_*`, appointment scheduler, daily template dispatcher, training handlers, BOC campaign jobs, `qa_database_service`, clinic holidays, and 410 content-files/instructions HTTP are deleted.
- Smart Follow-Up worker stays on the runtime scheduler.

## WAVE X3 — domain packages

- Customer reply facade: `services/brain/reply/` (was `customer_reply_v2`; no shim).
- Operator comments inbox: `services/live_chat/comments_inbox/`.
- Channel packages under `services/integrations/`: `whatsapp/` (includes `adapters/` + Cloud `smart_followup/`), `tiktok/`, `web_chat/`, `omnichannel/`.
- HTTP mounts stay in `modules/*`. Meta `services/meta_*.py` and Apple IAP/Sign-In stay as sibling modules this wave (Apple stays billing/auth; Meta fold is a follow-up).
- Web stays marketing `pages/public/*` + owner portal `pages/owner/*` (no leftover operator SPA pages).

## WAVE X4 — freeze + KEEP enabled

- KEEP drawer APIs (`/api/cm`, Live Chat, comments, Requests, WhatsApp, Copilot, web-chat, billing, …) stay off `product_features` disabled prefixes and on the tenant allowlist.
- `/api/comments` covers operator comments media + inbox (not only `/api/comments/inbox`).
- Museum prefixes (`/api/smart-messaging`, `/api/test*`, clinic settings) stay 403.
- Marketing `/` `/about` `/contact` `/pricing` `/features` and `/owner/*` portal routes remain in `App.jsx`.

## WAVE X5 — remaining Laser / lab ops

- `customer-brain-env-apply-ha.yml` writes and asserts `LINAS_CUSTOMER_AI_LAB=false` (same as X1 prod scripts).
- `customer-brain-live-lab-ha.yml` is retired: no production SSH, dispatch refuses.
- `prod_migration` does not seed `laser_hair_removal`, shave-before-laser, or clinic Beirut/Antelias branches.
- `section_classifier` `_SERVICE_SPECS` are generic SaaS fixtures only (no Laser/tattoo/CO2/DPL catalog).
- `LINASLASER_API_*` aliases are gone from `config.py`. `LINASLASER_BOC_BOOKING_ENABLED` stays the fail-closed BOC env name in `product_features.py`.
- Tests: `tests/test_wave_x5_lab_ops.py`.

## WAVE X6 — data / preview crumbs

- WhatsApp template IMAGE header URL lives in `services/integrations/whatsapp/template_header_image.py`. `message_preview_service*` and `data/message_preview_queue.json` are deleted (queue was unused after X2).
- Git no longer ships `data/phone_to_room_mapping.json`. Missing file resolves empty (fail-closed). No founder phones in the repo.
- `data/app_settings.json` has no smartMessaging schedules, booking body-part map, or `enableTraining`.
- `gender_recognition_service` deleted (barrel re-export only; no live callers).
- Brain evals: `real_tenant_index` / `golden_pack` / `shop_a_qa_sections`. Live-lab tenant ids are `eval-lab-a` / `eval-lab-b`. Production readiness does not overlay `live_lab_latest.json`.
- **Retired in X9:** `services/billing/token_wallet_*`. Owner Catalog is `services/billing/membership/message_catalog.py`.
- Tests: `tests/test_wave_x6_data_crumbs.py`.

## WAVE X7 — Meta + Apple fold

- `services/meta_*.py` → `services/integrations/meta/` (no shims; HTTP stays `modules/meta_*`).
- `services/apple_*.py` → `services/billing/apple/` including Sign-In (`apple_sign_in_service`) because it shares Apple secrets with IAP. HTTP stays `modules/apple_*`.
- WhatsApp Cloud template helper → `services/integrations/whatsapp/cloud_template_service.py` + `cloud_template_payload.py` (not the Cloud API coexistence package).
- `social_contact_routing*` moved to `services/integrations/social/` (still live: published CM WhatsApp handoff, SFU `is_social_channel`). Not deleted.
- HA preflight/admission and prod apply scripts read the packaged Meta registry / secret-separation modules. A SHA that still only has the old flat path stays tenant-gated (fail-closed).
- Tests: `tests/test_wave_x7_structure.py`.

## WAVE X8 — safe deletes + naming scrub + web/mobile crumbs

- Comment Graph poll stubs `modules/meta_social_comment_sync_job.py` and `modules/tiktok_sync_job.py` are deleted. Leftover queue job types still skip webhook-only.
- `services/moderation_service.py` deleted (zero importers; Laser-context museum).
- Empty `data/knowledge_base.txt`, `data/style_guide.txt`, and git `phone_to_room_mapping.json` removed. Live Chat still fail-closed if the mapping file is missing.
- `main.py` no longer mounts `local_qa_api` (helpers stay for FAQ/CM) and has no APK download route.
- `config.py` has no `LINASLASER_*` bindings. Booking FSM/training keyword museum stripped. `user_booking_state` / `user_in_training_mode` stay as HA session snapshot fields.
- Retired founder/lab workflows: live-lab, copilot-v2-flags-apply, cm-linas-content-audit, linas-index-ha, prod-brain-linas-smoke.
- **Kept on purpose:** `prod_cm_linas_*` / bridge scripts still invoked by `cm-production-cutover.yml`. `contentManagers` permission (live CM). `PricesEditor` (reachable from ServicesScreen). `message_catalog` (Owner Catalog).
- Web: orphan AI-limits screenshot gone; landing demo copy de-clinicked; AuthContext.register removed; museum LiveChat types stripped.
- Mobile: runtime-unreachable dashboard/billing/CM/nav orphans deleted. Drawer module list unchanged.
- Tests: `tests/test_wave_x8_radical_safe.py`.

## WAVE X9 — kill token_wallet dual

- Live AI meter is the **credit ledger** (`credit_ai_gate` / Copilot + Subscription).
- Copilot `account_state` / `tools_read` expose `credits.remaining`, not a prepaid token wallet.
- Stripe `/api/billing/stripe/webhook` keeps the credits/`message_pack` path. `token_pack` is skipped (`token_pack_retired`).
- `services/billing/token_wallet_*.py` deleted. SQLAlchemy `token_wallets` tables stay in alembic/HA models (no schema drop).
- **Kept:** `message_catalog` + Owner Catalog + `platform_message_api`. Credit IAP `com.linasai.credits.*`.
- Tests: `tests/test_wave_x9_kill_token_wallet.py`.

## WAVE X10 — legacy bridge + booking museum

- Inbound text path is CM-only: no `route_social_contact_request` from handlers. Unpublished tenants get the unpublished message (`tenant_allows_legacy_bridge` stays False).
- `is_social_channel` stays in `social_contact_routing_detect.py` for Smart Follow-Up + Meta DM identity.
- Clinic OpenAI booking/CRM tool schemas (`utils_tools_booking.py`, `utils_tools_lookup.py`) deleted. `get_openai_tools_schema()` returns `[]`.
- Creative schedule list deleted: `services/schedule_service.py` gone. Copilot `read_scheduled_posts` handler gone. Queue `publish_scheduled` fail-closes.
- **Kept:** CM publish runtime, Meta DM reply, `creative_policy.py` refusal (includes `read_scheduled_posts` name).
- Tests: `tests/test_wave_x10_legacy_bridge_booking.py`.

## WAVE X11 — evals out of runtime + domain folds

- `services/brain/evals/**` moved to `tests/brain_evals/` (no runtime shim). Production `brain/readiness.py` does not overlay eval artifacts.
- Folds (no shims): `welcome_pool` → `services/owner_copilot/welcome_pool/`; `local_qa_service*` → `services/faq/`; `request_graphs` + `request_drafts` → `services/requests/`; `search_metadata` → `services/ai_setup/search_metadata/`.
- **Kept:** Brain reply/media/comments; HA scale core; Owner Catalog; credit ledger; marketing + portal + drawer.
- Tests: `tests/test_wave_x11_evals_domain_fold.py`.


