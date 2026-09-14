# FINAL CLEANUP — Phase 1 hard verify

Scanned tip: `036d3857a8a7b37f33426bb1689f4cf8e9f763be` (`origin/main`, merge of #699).
Date: 2026-09-14.

`POST-CLEANUP-STATUS.md` is **not in the repo**. Baseline used instead: `docs/KEEP_SURFACE.md` (WAVE 0–G) plus a fresh import-graph on live Python (`services/`, `modules/`, `handlers/`, `utils/`, `storage/`, `db/`, `main.py`, `config.py`). Do not treat WAVE 0–G as already complete.

**Wave X1:** founder `linas` env/analytics/Meta/API exemptions removed; Laser `INITIAL_RESTRICTED` and clinic WhatsApp matrix emptied; prod lab scripts write `false`; KEEP Live Chat/Requests/WhatsApp on the shared tenant API allowlist.

**Wave X2:** museum `smart_messaging_*`, appointment scheduler, daily dispatcher, training handlers, clinic holidays, `qa_database_service`, and 410 content-files/instructions HTTP are **deleted**. `normalize_template_id` moved to `services/live_chat/template_ids.py`. SFU worker stays on the runtime scheduler. Laser `prod_migration` seed still writes `laser_hair_removal`.

**Wave X3:** `customer_reply_v2` → `services/brain/reply/`; comments inbox → `services/live_chat/comments_inbox/`; WA/TikTok/web_chat/omnichannel → `services/integrations/`. Meta `services/meta_*.py` still flat.

**Wave X4:** KEEP APIs stay enabled (comments media included on the tenant allowlist); museum prefixes stay disabled. Marketing + owner portal routes frozen.



## Method

Verdict: **FAIL overall.** Freeze (Creative/Luna/BOC/Owner Lab **source**) is PASS. Founder/Laser leftovers, museum files, and flat sprawl remain. Do not delete UNKNOWN.

## Method

- Targeted live patterns: `or "linas"`, `tenant_id == "linas"`, `INITIAL_RESTRICTED`, `LINAS_CUSTOMER_AI_LAB=true`, invent-tenant.
- AST import graph (not filename guesses) for museum modules.
- Git-tracked `services/*.py` with `NF==2` = **263** flat modules.
- Local `__pycache__` trees under deleted packages are **not** git-tracked; they make `Path.exists()` true until cleaned.

---

## A) Founder / Laser — **FAIL**

### PASS

| Check | Evidence |
| --- | --- |
| No live `or "linas"` / `getenv(..., "linas")` | WAVE G `test_wave_g_no_live_test_lab_or_monty_or_linas_fallback`. Re-scan: 0 hits. |
| `DEFAULT_TENANT_ID` empty unless env | `services/ai_setup/constants.py` `os.getenv("LINASBOT_TENANT_ID", "").strip()`; `require_tenant_id` raises. |
| Subscription exempt default empty | `DEFAULT_SUBSCRIPTION_EXEMPT_TENANTS = frozenset()`; only `SUBSCRIPTION_EXEMPT_TENANT_IDS` env. |
| Lab tenants not `linas` | WAVE A: lab allowlist is `lab` / `lab_*`. |
| Laser social **HTTP live path** unhooked | `tenant_allows_legacy_bridge()` always `False`. `handlers/text_handlers_respond_phase1.py` only calls `route_social_contact_request` when that is true **and** tenant has no published CM. |
| Invent-tenant | Live hits are **refusals** (`Never invent tenant_id` in requests/billing), not inventors. |

### FAIL (live or shippable leftovers)

| Leftover | Where | Proof | Wave |
| --- | --- | --- | --- |
| `tenant == "linas"` env WhatsApp override | `services/social_contact_routing_detect.py:200` | `override = getenv(env_name) if tenant == "linas" else ""` | X1 |
| After CM miss, defaults only for `linas` | same file `:231–234` | `if tenant != "linas": return None` then `DEFAULT_SOCIAL_WHATSAPP_CONTACTS` | X1 |
| Hardcoded clinic WhatsApp numbers | same file `:25–30` | Beirut/Antelias ±961… | X1 empty; X2 delete Laser router |
| Historical Meta deletion IDs only for `linas` | `services/meta_claim_data_deletion.py:110` | extra `{channel}:{sender}` shapes | X1 |
| Unlabeled analytics attributed to `linas` | `services/wallet_spend_analytics.py:86` | unlabeled row matches iff `tid == "linas"` | X1 skip unlabeled |
| Laser `INITIAL_RESTRICTED_*` | `services/ai_setup/constants.py:33–61` | tattoo/co2/pigmentation/facial | X1 empty |
| Prod scripts **write** `LAB=true` | `scripts/prod_apply_customer_brain_flags.sh:12`, `scripts/prod_stage_customer_brain_env.sh:111` | `LINAS_CUSTOMER_AI_LAB: "true"` | X1 `false` |
| Startup Laser branding | `main.py:171` | `Lina's Laser AI Bot is ready!` | X1 |
| Seed script founder page | `scripts/seed_meta_app_a_registry.py:98` | `binding.tenant_id == "linas"` | **UNKNOWN** (ops Meta App A) |
| Laser classifier corpus | `services/ai_setup/section_classifier.py` `_SERVICE_SPECS` | tattoo/co2/DPL/laser hair… | X2 (KEEP redistribution needs generic classifier) |
| Migration Beirut/Antelias/tattoo keys | `services/ai_setup/migration.py:239–246` | `_classify_contact_key` | X2 |
| `LINASLASER_API_*` in `config.py` | `config.py:48–50` | clinic API env still loaded | **UNKNOWN** (read by `saas_no_boc`?) |

Reserved slug `"linas"` in `tenant_registration_service.py` / `admin_provisioning_service.py` is **KEEP** (refuse invent). Not a live fallback.

---

## B) Museum — **FAIL**

### smart_messaging vs Smart Follow-Up

**SFU does not import `smart_messaging_*`.** Only `services/smart_followup/generation.py` → `customer_reply_v2`.

`smart_messaging*` still imported by:

- `modules/event_handlers_scheduler.py`, `event_handlers_monitor_jobs.py`
- `services/appointment_scheduler*` (BOC gate always skip: `boc_appointment_jobs_allowed()` is False)
- `daily_template_dispatcher*`
- `whatsapp_cloud_template_service*` (**KEEP WA templates** — MOVE catalog helpers, do not blind-delete)
- `services/live_chat/service_templates.py` → `smart_messaging_catalog.normalize_template_id` (KEEP Live Chat send-log lookup)

HTTP `/api/smart-messaging` is **flag-disabled** (`product_features.DISABLED_API_PREFIXES`), not deleted.

| File | Classification |
| --- | --- |
| `smart_messaging_catalog.py` (`normalize_template_id`) | **MOVE** into `live_chat/` or `integrations/whatsapp/` |
| remaining `smart_messaging_*.py`, `smart_messaging.py` | **DELETE** after MOVE |
| `appointment_scheduler*.py` | **DELETE** (only populate jobs; BOC always skip) |
| `chatted_no_crm_lead_campaign_service.py`, `missed_paused_campaign_service.py`, `scheduled_messages_collector.py` | **DELETE** (0 live importers) |

### Billing wallet / message_catalog

| Module | Importers | Classification |
| --- | --- | --- |
| `modules/wallet_api.py` | `main.py` Stripe webhook | **KEEP** Subscription/Stripe credits webhook (not the old `/wallet` SPA) |
| `services/billing/token_wallet_*` | wallet_api + Copilot `account_state`/`tools_read` | **UNKNOWN** — WAVE D: does not gate AI; Copilot still reads it |
| `services/billing/membership/message_catalog.py` | portal Owner Catalog + admin | **KEEP** portal Message catalog page (draft catalog, not live meter) |
| `services/stripe_checkout_service.py` | wallet_api | **KEEP** with webhook |
| `services/wallet_spend_analytics.py` | dashboard activity/usage | **KEEP** after X1 unlabeled skip |
| `services/token_metering.py` | credit preflight only | **KEEP** (WAVE D) |

### customer_reply_v2 vs brain/

**KEEP live facade** (20 files, 38+ importers: handlers, web_chat, WA, TikTok, comments, Brain runtime). WAVE 0: “facade until renamed”. **MOVE** into `services/brain/` (shim one PR max). Do not delete until imports retargeted.

### training_*

| File | Live imports | Classification |
| --- | --- | --- |
| `handlers/training_handlers.py` | **0** (webhook `start_training_mode` already gone) | **DELETE** |
| `services/training_mode.py` | **0** | **DELETE** |
| `services/training_response_service.py` | training_handlers only | **DELETE** |
| `config.load_training_data()` | `main.py` still calls; body disabled | X1 stop calling; X2 delete training state on `config` |
| `services/photo_analysis_service.py` | training_handlers only | **DELETE** |

### clinic-ish + data crumbs

| Path | Graph | Classification |
| --- | --- | --- |
| `services/clinic_holidays_service.py` | **0 importers** | **DELETE** |
| `services/booking_service_mapping.py` | **0** | **DELETE** |
| `services/qa_database_service.py` (+ `_match`) | tests + FAQ **mocks**; live FAQ uses `local_qa_service` | **DELETE** after dropping test mocks |
| `data/qa_database.json` | GONE | PASS |
| `data/message_templates.json`, `sent_smart_messages.json`, `service_template_mapping.json`, `phone_to_room_mapping.json`, `analytics_daily.json` | museum JSON | **DELETE** if no KEEP reader after SFU MOVE |
| `data/app_settings.json` | **UNKNOWN** | do not delete |
| `services/gender_recognition_service.py` | re-exported from `text_handlers_firestore` barrel | **UNKNOWN** until call-sites confirmed unused |
| `modules/content_files_api.py`, `modules/instructions_api.py` | mounted; return 410 | **DELETE** mounts + files (product is `/api/cm`) |
| `modules/flow_api.py` | `main.py` activity logs | **UNKNOWN** (not KEEP portal pages; may still be Dashboard) |
| `services/content_files_service.py` | **0** | **DELETE** |
| `services/social_contact_routing*.py` Laser phones / tattoo / Beirut | live text path **does not** call (legacy bridge False) | **DELETE** in X2; X1 empty contacts + drop `linas` branch |

### Hidden CM_SECTIONS vs Brain

`CM_SECTIONS` (constants.py:123–141): ai_basics, languages, style, dynamic_messages, branches, opening_hours, prices, care, knowledge, faq, handoff, restricted, actions, comments, ai_limits, off_days, requests_appointments. **No `services`.**

Hub tiles (KEEP): knowledge, ai_basics, branches, prices, comments, requests_appointments + FAQ drawer.

Brain **does** read (do not stop persisting): ai_basics, style, dynamic_messages, faq, prices, branches, opening_hours, off_days, requests_appointments, restricted, knowledge, care (title cards `family=care`), comments (comment_rules), handoff, actions/ai_limits (capability_gates).

| Hidden (`showInCmHub: false`) | Brain? | Classification |
| --- | --- | --- |
| languages, style, dynamic_messages, opening_hours, handoff, restricted, off_days, ai_limits | yes | **KEEP** persist |
| `care` | yes (`brain/retrieve/cards.py`) | **KEEP** |
| `default_section_payload["services"]` | not in `CM_SECTIONS` | **DELETE** builder key only (X2) |

---

## C) Sprawl — **FAIL**

### Flat `services/*.py`

**263** git-tracked files directly under `services/` (excluding packages). Target: domain packages; flat count must drop sharply (Meta/WA/Apple/museum).

### Packages vs drawer map

| Package | Files (git) | Classification |
| --- | --- | --- |
| `ai_setup`, `dashboard`, `smart_followup`, `faq`, `live_chat`, `requests`, `integrations`, `team`, `billing`, `owner_copilot`, `brain` (+ comments/media) | present | **KEEP** |
| `comments_inbox/` (6) | `modules/comments_inbox_api` + TikTok repo | **MOVE** → `live_chat/` or `brain/comments` |
| `whatsapp_cloud/` (37), `whatsapp_adapters/` (7) | Integrations | **MOVE** → `services/integrations/whatsapp/` |
| `tiktok_business/` (38) | Integrations | **MOVE** → `services/integrations/tiktok/` |
| `web_chat/` (39) | KEEP widget | **MOVE** → `services/integrations/web_chat/` |
| `omnichannel/` (29) | Integrations | **MOVE** under integrations |
| `customer_reply_v2/` (20) | facade | **MOVE** → brain |
| `products/` (23), `search_metadata/` (11) | AI Setup / Brain | **KEEP** (not drawer; supporting) |
| `scale/` (55), `queues/` (13) | ops | **KEEP** |
| `request_drafts/`, `request_graphs/` | Requests | **KEEP** (could fold into `requests/`) |
| `welcome_pool/` (4) | **UNKNOWN** | |
| `providers/` (3) | **KEEP** LLM | |
| Empty dirs `cm/`, `customer_ai/`, `service_catalog/`, `owner_copilot_v2/`, `membership/`, `tenant_mobile_dashboard/` | git **0** files; local pycache only | **DELETE** local trees so freeze `exists()` stays green |

`services/integrations/` today is **channel capability only** (6 files). Meta/WA/TikTok still live as flat `meta_*.py` + sibling packages.

### Web

`dashboard/src/App.jsx`: marketing `/` about contact pricing features; auth recovery; `/owner` Overview/Users/Messages/Catalog/Costs; obsolete operator paths redirect `#get-app`. **PASS for routes.**

Leftover: `AppEntry.jsx` catch-all CTA (**KEEP**), `OwnerActivationBanner.jsx` still mentions `LINAS_CUSTOMER_AI_LAB` (X1 copy). No operator SPA page files under `pages/` besides public + owner + auth.

`main.py`: 193 lines, domain-grouped mounts. Still mounts 410 museum (`content_files_api`, `instructions_api`), `flow_api`, `wallet_api` (KEEP webhook). Startup print Laser. **FAIL polish.**

---

## D) Freeze — **PASS** (source)

WAVE 7 / WAVE G `GONE` paths **not git-tracked**:

- `archive/`, Creative HTTP, `smart_retrieval_service`, Owner Lab UI/API, `qa_database.json`, `owner_ai` v1 APIs, `luna_titles` / `luna_title_resolver`, `services/booking`, `modules/mobile_services_api.py`

Monty: factory refuse list only. `boc_booking_enabled()` always False.

Local clone may still have pycache-only trees named `services/cm` etc. — not a git FAIL; wipe before relying on `Path.exists()`.

---

## Lists

### KEEP (must survive)

- Mobile drawer backends: AI Setup, Dashboard, Follow-up, FAQ, Live Chat (+ comments API), Requests, Integrations, Team, Subscription
- Owner Copilot → `services/owner_copilot/` only (`creative_policy.py` refusal)
- Customer Brain → `services/brain/` including comments/media (#677)
- `customer_reply_v2` until folded into brain
- Web marketing + owner portal + guest FAB + web-chat widget + webhooks/oauth
- Smart Follow-Up `services/smart_followup/` + `modules/whatsapp_smart_followup_api.py`
- Reserved tenant slug refuse (`linas` cannot be registered)
- Fail-closed `require_tenant_id`; Live Chat tenant A≠B
- IAP/Stripe webhook path used by Subscription credits
- `product_features` disabled prefixes for **already-removed** HTTP (testing lab / smart-messaging HTTP / clinic settings) — not used to hide KEEP drawers

### DELETE (proven; import-graph first)

Training trio + `photo_analysis_service`; appointment_scheduler*; campaign services with 0 importers; `clinic_holidays_service`; `booking_service_mapping`; `qa_database_service*`; `content_files_service`; remaining `smart_messaging_*` after catalog MOVE; Laser `INITIAL_RESTRICTED` catalog; `LAB=true` prod writes; `linas`-only analytics/Meta/env branches; data JSON crumbs listed above; 410-only `content_files_api` / `instructions_api` after unmount.

### MOVE (do not blind-delete)

- `smart_messaging_catalog.normalize_template_id` → live_chat or integrations
- `customer_reply_v2` → `brain/`
- `comments_inbox` → live_chat or `brain/comments`
- Meta / WA Cloud / TikTok / Apple Sign-In? Apple IAP stays billing. Channels → `services/integrations/...`
- `web_chat`, `omnichannel` under integrations

### UNKNOWN (do not delete)

- `scripts/seed_meta_app_a_registry.py` founder page check (production Meta App A)
- `data/app_settings.json`
- `modules/flow_api.py` (activity flow)
- token_wallet stores (Copilot read vs dead meter)
- `gender_recognition_service` call-sites beyond barrel export
- `welcome_pool/`
- `LINASLASER_API_*` env reads
- `system_knowledge_*` (guest FAB + Copilot)
- `local_qa_service` (FAQ SoT JSONL — **KEEP** despite museum name; rename later)
- Owner portal Message catalog vs non-live message billing overlay (already false)

---

## A–D scoreboard

| Area | Result at `036d3857` | After X1 | After X2 | After X3 |
| --- | --- | --- | --- | --- |
| A Founder/Laser | **FAIL** | live special-cases **PASS**; Laser classifier/prod_migration seed remain | same | same |
| B Museum | **FAIL** | still present | **PASS** for proven-dead list | `customer_reply_v2` folded into `brain/reply` |
| C Sprawl | **FAIL** (263 flat; channels not under `integrations/`) | unchanged | museum files gone | WA/TikTok/web_chat/omnichannel under `integrations/`; Meta `meta_*.py` still flat |
| D Freeze GONE | **PASS** (source) | PASS | PASS | PASS |

Phase 2 order: **X1 → X2 → X3 → X4**. X4: extend freeze tests; KEEP backends enabled; merge stacked PRs.
