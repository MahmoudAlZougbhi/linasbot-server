# Message subscriptions — decision and readiness log

Branch: `cleanup/ai-setup-runtime`. Contract: `linas ai 333.md` revision 1.1 (2026-09-10).

Activation of `CUSTOMER_BRAIN_ENABLED` and `MESSAGE_BILLING_CUTOVER` is authorized only
after gates pass. They remain **off** in `.env.example`, `docker-compose.yml`, and
`docker-compose.prod.yml`. `MESSAGE_BILLING_ENABLED` is also off: enabling it without
period grants would block generative AI.

## Unresolved owner decisions (section 2)

| Decision | Status | Safe behavior |
|---|---|---|
| Free AI message allowance + renewal | Unconfigured | Free `included_messages=null`; publish blocked |
| Knowledge line budget (1000 vs 1500) | Unconfigured | Not enforced |
| Services/Products shared vs separate 1000-line budget | Unconfigured | Slot caps 5/5 recorded; line budget not enforced |
| Content-line definition | Unconfigured | No line counter activation |
| Message top-up prices | Unconfigured | Draft packs 100/300/500/1000/5000, `sale_ready=false` |
| Credit → message conversion | Unconfigured | Historical credits preserved; no numeric relabel |
| Tenant-visible internal USD costs | Default hidden | Platform-admin only |

## Recorded implementation assumptions

- Paid matrix: Lite $10/550, Starter $29/1,200, Growth $59/3,000, Pro $120/10,000, Max $279/25,000.
- First paid tier unlocks Smart FAQ and Smart Follow-Up. Free locks both.
- Daily AI Setup edits: 30/tenant/UTC day. Zero means blocked, not unlimited.
- One Message = one accepted generative Customer AI reply or sent AI follow-up. FAQ/static/resource-only/no_reply = 0.
- Customer AI Limits owner screen stays removed. Backend safety defaults remain.
- Live IAP/credit checkout stays on `membership-v1` until `MESSAGE_BILLING_CUTOVER`.
- Public `price_usd` is the intended message price. `live_store_price_usd` / `included_credits` stay for checkout compatibility.

## Release controls

- `CUSTOMER_BRAIN_ENABLED` default false
- `MESSAGE_BILLING_ENABLED` default false
- `MESSAGE_BILLING_CUTOVER` default false
- `FREE_PLAN_ENFORCEMENT_ENABLED` default false
- `LINAS_CUSTOMER_AI_LAB` default false; lab tenants must be `lab` / `lab_*`

## Additional wiring this continuation

- FAQ/follow-up catalog limits are published; live follow-up lock waits for billing or Free enforcement flags
- Included lots expire at UTC month boundary; purchased lots do not
- Owner setup-chat patches and request-graph publish/delete consume daily-edit slots
- Channel eligibility (web, WhatsApp, TikTok, reserve, token metering) uses the shared generative gate
- Semantic FAQ runs after exact miss; visual retrieval is recorded as disabled/resource-by-id
- Daily-edit policies persist when billing PG is up; media upload, unpublish, and diagnosis FAQ count
- Lab classify + offline eval runner are capture-only
- Paid `set_plan` issues the current included lot when message billing is on
- Conversion dry-run inventories stored entitlements and stays blocked
- Platform ledger snapshot/health is admin-only
- Free slot caps exist behind `FREE_PLAN_ENFORCEMENT_ENABLED` (still off)
- Service create/update consume daily-edit slots
- Catalog exposes honest Apple/Google/Stripe/annual readiness
- Platform conversion dry-run API stays blocked
- Cost dashboard accepts today/yesterday/last_7_days/last_30_days
- Branch weekly schedules hydrate hours evidence
- Mobile yearly toggle cannot sell the monthly USD as `/year`
- Landing FAQ counts come from `/api/public/plans`; copy no longer hardcodes quotas
- `set_plan("free")` is a valid stored plan id without inventing a message grant
- Purchased lots require a verified transaction id and spend after included
- Comment senders honor `outbound_messages`; public DM claims wait for the private send
- Tenant remaining/alerts never copy credit quantities as Messages while billing is off
- Cost dashboard includes feature totals and daily-edit utilization; Growth Plan hides remaining until billing is on
- AI Setup hub and `/api/cm/meta` expose today's edit used/limit/reset
- Free branch/service CM growth is capped when `FREE_PLAN_ENFORCEMENT_ENABLED` (still off)
- WhatsApp Cloud PG history loads when Firestore has no rows
- FAQ language fan-out consumes the daily processing-attempt budget
- Owner portal has a capture-only Brain lab page
- Cost dashboard rolls up provider/model; landing no longer labels included as remaining
- Public `/api/public/plans` `faq_capacity` comes from the message catalog (published overlays only)
- Admin can draft paid plan price/messages/FAQ without changing live checkout
- Verified IAP consumables call `maybe_grant_purchased_from_verified_txn` (no-op until cutover + sale-ready pack)
- Cost dashboard splits generative vs FAQ/static ledger classes
- Admin force-reindex uses the publish-time index job and processing budgets
- Provider expenses record when Brain calls OpenAI/Voyage, even if message billing is off
- `mixed_faq_ai` / `faq_semantic` classify correctly; product and service deletes consume daily edits
- Comment AI loads history-50 plus parent comment; Lite comments use the live Meta comment gate
- Channel gates (comments / WhatsApp / web / TikTok) and `/me` feature flags read the message catalog
- Credit `price_usd` / checkout stay on the credit catalog until cutover
- Ledger health and cost dashboards report `store` (`memory` / `postgres` / `memory_fallback`)
- Verified Apple ASSN credit restore also calls the message-grant hook (no-op until cutover + sale-ready pack)
- Catalog admin drafts persist under LINASBOT_DATA_ROOT when the message store is not memory
- FAQ paid-plan detection uses the message catalog paid ids, not the credit price table
- Public `/api/public/plans` channel flags, web, and seats come from the message catalog
- Seat adds, `/me` additional_seats, and tenant dashboard team capacity read the message catalog when the plan exists there
- Landing How-it-works subscription copy says included monthly messages, not remaining
- Owner catalog can map draft top-up store product ids without inventing prices or sale-ready
- Verified Google Play notifications attach the same message-grant hook as Apple (no-op until cutover + sale-ready pack)
- Offline lab evals include billing/gate contract cases (FAQ 0, mixed/generated 1, Lite locks, visual disabled)
- Message ledger / daily-edit / expense tables are registered on the SQLAlchemy Base and exercised through sqlite billing sessions (`store=postgres` adapters, no credit conversion)
- Verified refunds zero unused purchased remaining and release held reservations; lot rows stay
- Included lots expire immediately on refunded/revoked/expired plans when billing is on
- Stripe `linas_message_pack` never credits token wallets; token packs never become messages
- Google RTDN grants only on ACTIVE and revokes on REVOKED/REFUND
- Read-only preflight fails if any activation flag is on; reports message-table readiness without failing when tables are missing
- Provider expenses stamp `prod` / `staging` / `test` from ENVIRONMENT; cost APIs default to all environments
- Owner metrics keep live checkout MRR on membership-v1 and add intended message-catalog MRR beside it
- Owner Users no longer labels leftover credits as Messages; catalog included/month sits beside leftover credits
- Offline eval contract cases cover Free FAQ lock, Lite web/TikTok locks, Starter/Growth unlocks, and default-off flags
- Brain greetings prepend on generated DMs, not only FAQ; comments and follow-up do not greet
- Tenant usage progress is ledger-only; credit quantities stay labeled credits on Owner Copilot and channel activity
- Public plan overlay applies catalog seat caps; greeting language follows inbound text and does not repeat in-session
- Owner Copilot publish consumes the same daily-edit slot as `/api/cm/publish`
- Zero leftover credits no longer surface as Messages depleted while billing is off
- Tenant included/month is the catalog allowance; remaining comes from the ledger after `ensure_included_grant`
- Restricted topics return the published refuse template; stale message reservations are released after one hour
- Pending request confirmation and greeted state persist across turns; Website Chat history-50 falls back to the visitor store
- Owner Copilot approve returns `AI_SETUP_DAILY_LIMIT` instead of a generic exception when the daily-edit slot is spent
- `/api/entitlements/me` and `/api/mobile/usage` overlay ledger message fields; Current Plan remaining stays hidden until billing is on
- Brain human-control reads the shared Redis takeover flag and does not keep a released chat blocked from stored state
- Product image upload consumes the same daily-edit slot as CM media upload
- Owner Copilot `read_usage` / system prompt keep leftover credits labeled credits
- Diagnosis approve returns `AI_SETUP_DAILY_LIMIT` when the daily-edit slot is spent
- Request confirm persists through the requests DB when capture is published; setup-required is honest
- Cost dashboards stamp `message_billing_active` and issue included lots only while billing is on
- TikTok / omnichannel DMs now pass conversation ids so Brain history and pending confirm can load
- Comment generate paths pass thread ids, caption, and parent text so comment history-50 is not empty
- Instagram/Facebook DMs and comments reuse conversation-store history-50 when Firestore is empty; no new PG table
- Instagram/Facebook inbound mids now reach Brain so yes-to-submit is not dropped as confirmation_required
- WhatsApp Cloud and Website Chat inbound ids now reach Brain for the same confirmation bind
- Website Chat request persist keeps `web_chat`; unknown channels (including TikTok DMs) are rejected instead of stored as Instagram
- Website Chat follow-up send no longer requires a credit reservation once message billing is on; the worker still settles the message unit after send
- WhatsApp Cloud skips the extra credit reserve when message billing is on so one reply is not double-charged
- Reservation inserts write `created_at` so stale holds can be GC’d
- Current Plan leftover credits stay labeled credits; remaining messages stay hidden until billing is on
- Instagram/Facebook `try_reserve_for_ai` skips leftover-credit reserve once message billing is on
- Website Chat live turns use a sentinel reservation instead of charging leftover credits
- Smart Follow-Up preview skips leftover credits and does not hold a customer message unit
- Growth Plan membership/used math uses ledger remaining and granted lots, not catalog allowance plus purchased remaining
- Request persist stamps published CM `content_version_id`, not the conversation draft revision
- Omnichannel generate/deliver skip leftover-credit capture once message billing is on
- Owner Lab can send conversation id, channel, inbound id, and history for confirmation checks
- Request-rule save/delete write the CM draft and compiled graph under one daily-edit slot
- Request-graph publish/delete require contentManagers, same as CM draft
- Confirm persist re-merges published request-graph keys; incoming values win
- Meta/combine Brain turns bind an existing conversation or social user id when Firestore left the thread empty
- Isolated lab echoes conversation/channel/inbound id plus receipts; owner form sends user id
- Current Plan summary never labels catalog allowance as remaining; empty catalog daily-limit input does not save 0
- Public `/pricing` no longer invents `0` included messages when the catalog field is empty
- Live IAP credit packs stay leftover credits; they are not labeled as AI messages (no 1 credit = 1 message)
- Smart Follow-Up leftover-credit reserves release on fence loss, send failure, and unused paths; a confirmed send with failed capture stays held as pending-settlement and is retried, not released
- WhatsApp image Brain turns reserve leftover credits through `run_reserved_customer_turn` (existing inbound mid / media id)
- Public `/api/public/plans` keeps `topup_unit: credits` and `sale_ready: false`; cutover returns no invented message packs
- Mobile FAQ / products / request-graph publish / Smart Follow-Up surface `aiSetupDailyEditLimit` on 429
- Delayed text leftover-credit reserve now settles on phase-1 halt and exceptions
- Omnichannel / TikTok DMs reserve leftover credits before Brain while billing is off; inbound row ids hydrate the payload
- Owner Copilot / Website Chat credit-pause copy stays leftover credits until message billing is on
- Confirmed-send leftover/message capture failures persist as pending-settlement and retry; they do not release the hold
- Bounded reservation reconcile runs even when message billing is off; stale unknown holds become unresolved, not refunds
- New message policy charges one unit for AI comment / AI DM / AI both / mixed FAQ+AI; static/ignore/FAQ-only stay 0; legacy comments stay uncharged while billing is off
- `cm:unpublish` and `faq:archive` remain available after the daily AI Setup limit; ordinary publish/edit still consume the slot
- Cost dashboards expose used/reserved messages, pending settlements, and processing-budget status
- Cost APIs filter by model; planner spend is journaled as feature=planning, not generation
- `/api/platform/activation-readiness` reports blockers and never enables flags
- Pending settlements persist on the billing SQL store when the table exists; Brain outbox recovers the same envelope without regenerating
- Brain billing persists the accepted envelope before return; leftover capture, follow-up settle, Omni delivery, and reconcile mark sent; failed capture marks pending-settlement
- Owner Costs shows activation readiness (never enables flags) and accepted/pending outbox counts
- Safety-blocked inbound media cannot generate; file extract and voice transcript join planner task text
- Inbound STT journals pending `stt` expense without inventing USD
- Website Chat completion acknowledges the Brain outbox without a second leftover reserve
- Generative message units stay reserved until confirmed send; failed sends release; capture failures stay pending-settlement
- WhatsApp Cloud uses leftover reserve + post-send finalize settle (queued deliver included)
- Comment Graph send and Omni/TikTok/web completion settle the same way
- Follow-up revalidate blocks when the customer inbound is newer than the trigger
- TikTok comment publish settles the Brain reservation after confirmed send, never-submitted skip, or exhausted/failed publish; in-flight retries keep the hold
- Legacy WhatsApp voice STT journals pending `stt` expense and no longer invents $0.006/min USD
- Leftover-credit known-tenant scan includes ledger jsonl plus pending-settlement / leftover-index files, not only `*.balance.json`
- Meta public-only comment send now settles after confirmed send; skip / hard-fail / missing client release; ambiguous provider outcomes keep the hold
- Meta/delayed WhatsApp settle the inbound mid (and extra ids) instead of minting a second hold on the logical reply id; never-submitted fails release even after `_reply_ready`
- Omni settle uses the Brain provider mid, not only the inbound row UUID; Website Chat settle uses `web_inbound_message_id` plus the operation key
- Website Chat fence/fail releases the Brain message hold when leftover release wins; missing conversation/text does not invent an inbound id
- TikTok DMs bind and settle the same inbound id generate reserved, including a minted hash when provider_message_id is empty; skip/never-submitted paths release
- WhatsApp Cloud never-submitted / failed-send paths release the Brain message hold, not only leftover credits; ambiguous sends still keep the hold
- Queued WhatsApp intent delivery releases the same hold on never-submitted fail/suppress; post-send finalization failures stay reserved
- Flag-off photo vision journals pending visual expense and no longer invents $0.01/$0.03 USD
- Smart Follow-Up generate and settle share canonical/minted ids; generation failure releases the message hold
- Leftover known-tenant scan includes in-memory settlement and leftover-index tenants, not only disk files
- Website Chat follow-up settles the message hold after durable visibility; web jobs are no longer forced into leftover reconcile when billing is on
- Leftover re-seed keeps the reserved `operation_type`; `ai_limits` CM writes consume a daily-edit slot even though the Limits screen stays removed
- Activation readiness now reports unpublished catalog, unsaleable packs, cutover off, memory store, unresolved settlements, and stale leftover holds without flipping flags
- Omnichannel generate/fail and WhatsApp generate-stop release the Brain message hold, not only leftover credits
- Pending-settlement rows keep candidate ids; reconcile settles the reserved inbound/provider alias without minting a second unit
- Isolated lab always releases the capture-only hold; request-graph preview and per-asset comment-reply writes consume a daily-edit slot
- Owner Costs / Catalog / public Pricing keep intended USD and leftover credits labeled separately from live message checkout
- Meta social never-submitted fail now releases the Brain hold via finalize_delivery, not leftover credits only
- Tenant dashboard overlay always labels leftover wallet as credits; buy_credits stays off once message billing is on because packs are not sale-ready
- Owner Copilot pause stays leftover-credit language even when message billing is on; buy_credits stays off because leftover IAP must not sell as messages
- Tenant Growth Plan and Copilot pause sell leftover credits only while billing is off; they do not label leftover IAP as Add messages
- Website Chat settings, channel DM/comment enable, and WhatsApp AI enable consume a daily-edit slot; widget/channel/WhatsApp AI disable stay safety writes after the cap
- Live Chat takeover / release / end stay `safety:handoff` after the daily-edit cap
- Activation readiness now names the missing 800-eval suite, live channel proof, and Voyage/pgvector proof without flipping flags
- How-it-works dashboard mock no longer shows Add messages while remaining stays hidden
- Meta social processor stays under the 500-line cap; display-name and retry helpers live beside finalize_delivery
- Apple self-service and tenant-admin account deletes stay `privacy:delete` after the daily-edit cap
- Comment webhook repair and Instagram Login webhook retry stay `safety:webhook` after the cap; per-asset comment-reply disable stays a safety toggle
- Meta connection rollback stays `safety:rollback` after the daily-edit cap
- Website Chat widget-key rotate stays `safety:web-chat-rotate` after the daily-edit cap
- Workspace leftover-zero status is leftover credits, not Messages depleted; live message depletion points to See plans because packs are not sale-ready
- Current Plan leftover IAP stays hidden once message billing is on
- Leftover IAP sheet stays leftover-credit language and does not open after message billing is on
- Chat and Dashboard leftover IAP sheets stay closed after message billing is on; Current Plan does not invent catalog included counts when the API field is empty
- Ambiguous WhatsApp / Smart Follow-Up / TikTok holds use leftover policy only when a leftover reservation exists; message billing tags `message_units` and does not mark unknown sends as captured
- WhatsApp / Meta photo Brain turns wrap send so leftover and message units settle only after delivery evidence
- Owner Catalog can draft Free section-2 values without inventing them, and can set a per-tenant daily-edit override
- Owner Costs shows ledger `by_class` and per-tenant daily-edit rows already returned by the cost API
- Owner Lab can classify capture-only message units without a live send
- Brain outbox envelopes persist on `customer_ai_outbox` in the existing `20260910_msg_billing` revision; recover prefers SQL and does not regenerate text
- Disk-only outbox rows are copied into SQL only when that outbox id is missing; existing SQL state is not overwritten
- Official Alembic head stays `20260910_req_web_chat`; missing outbox table does not disable the message ledger store
- Failed sends mark the Brain outbox failed so recover does not list a released envelope as unsent
- Pending-settlement policy and tenant ids load from SQL after a memory clear so a leftover hold cannot be retagged as message units
- Leftover known-tenant scan includes outbox tenants already present on rows; it still does not invent ids
- Brain conversation state/pending/history persist on `customer_ai_conversations` in the same `20260910_msg_billing` revision so yes-to-submit survives another worker; official Alembic head stays `20260910_req_web_chat`
- Catalog admin drafts persist on `customer_ai_catalog_admin` in that same revision; publish stays gated and sale_ready stays false
- Leftover-credit reservation index rows persist on `customer_ai_credit_reservation_index` without hooking `credit_ledger_service.reserve()`
- Processing daily attempts and in-flight jobs persist on the same `20260910_msg_billing` revision so cost dashboards and index/FAQ budgets survive another worker; stale jobs older than one hour do not keep the concurrency slot
- Activation readiness and preflight now report optional durable tables (outbox, conversations, catalog, leftover index, processing, pending settlements) without adding them to `pg_store._TABLES` or flipping flags
- Leftover pin aliases persist as settlement `candidate_ids` so a leftover hold cannot be retagged as message units after a memory clear
- Leftover conversation/event pins apply only while the hold is reserved or pending-settlement; release/settle unpins so a later turn can use message units
- Cost dashboards include processing-only and daily-edit tenants already present on those rows; they still do not invent tenant ids
- FAQ language save keeps purge and batch translate inside the same daily-edit slot
- Legacy WhatsApp `reserve_before_ai` persists leftover pin aliases on settlement `candidate_ids`
- Settlement upserts union `candidate_ids` so capture-failure and send-settle cannot drop conversation aliases
- Catalog admin reads through SQL on each lookup when the billing store is up so another worker's draft is not stale
- `settle_after_outbound` captures only after send evidence or `_delivery_succeeded`; missing evidence keeps the hold
- Cost dashboards include conversation-only tenants already present on `customer_ai_conversations`
- Pending-settlement hydrate prefers SQL rows and only promotes missing disk ids after a memory clear
- Brain outbox and leftover-credit index hydrate prefer SQL the same way; disk rows promote only when that id is missing
- Leftover IAP sheet says leftover credits do not expire; it does not label leftover packs as purchased messages
- File and Postgres leftover-hold scans share one leftover-op matcher so WhatsApp Cloud / TikTok leftover rows are not dropped after restart
- Conversation store load/save prefer SQL when persist is on so another worker's greeted/pending/history is not overwritten by stale process memory
- Leftover policy reads SQL first when the settlement table is up; stale process pins unpin so a later turn can use message units
- Brain outbox and leftover-credit index lookups prefer SQL so another worker's sent/closed row is not overwritten from stale memory
- Daily-edit and policy SQL run only when those tables exist; missing optional tables fall back to memory instead of failing the edit
- Cost dashboards union memory + SQL processing and settlement tenants; leftover-credit scan still does not invent conversation-only tenants
- Generate reserve records pending-settlement aliases (including conversation id) so settle can find the hold after a crash
- Leftover conversation pins skip message-unit reserve so leftover credits and messages stay off the same turn
- Failed generate / not-accepted apply mark the message hold released
- Leftover-credit scan includes tenants that already have a Postgres credit reserve row
- Cost dashboards union memory + SQL ledger tenants and reservations, and memory + SQL expense events
- WhatsApp confirmed-send / unsent-release prefer the intent inbound mid and conversation id so an empty provider mid does not mint a second unit
- TikTok and Meta comment settle pass the Brain thread id as an extra candidate so the generate hold is not abandoned
- Ledger snapshot unions memory lots/reservations into cost-dashboard remaining when SQL is up but those rows are process-local
- `settle()` uses the memory hold when SQL has no reservation so accepted send does not mint a second unit after tables come up
- Reconcile lists union memory + SQL pending settlements, stale message reservations, and leftover-credit opens so another worker's SQL page cannot hide this process's holds
- Cost dashboards union memory + SQL pending, leftover-open, outbox, and processing-budget counts without double-counting persisted rows
- Daily-edit status and reserve count process-local slots after SQL is up so the 30-edit UTC cap cannot be bypassed
- Message reserve uses a memory lot when SQL remaining is 0; included expiry and purchased refunds also zero process-local lots
- Leftover policy still treats SQL "no active hold" as authoritative and does not revive stale memory leftover pins
- Leftover-credit scan uses the Postgres credit ledger as SoT when billing PG is on, even if the open list is empty
- Leftover-index close keeps a SQL row so another worker's memory reserved copy cannot look open again
- Leftover scan treats a capture/release keyed by the original request id as closed, not a new open hold
- Pending-settlement lookup matches conversation/event aliases so leftover release can find the hold
- Brain recover_unsent / recover_pending_settlement include process-local envelopes after SQL is up
- `reverse()` uses the memory reservation when SQL has no row, same as settle
- Delayed leftover capture now settles the pending row and unpins leftover policy, same as `capture_leftover_reply`
- Leftover-index seed can reopen a settled/released row when the credit ledger still has that hold reserved; pending-settlement rows stay closed
- Website Chat leftover reserve now records the leftover hold and pins so a later Brain turn cannot add message units on the same leftover
- Leftover reconcile capture finishes through `complete_leftover_capture` so leftover policy cannot linger after retry
- Conversation load/save treat SQL-ready miss as empty and do not revive stale process greeted/pending/history
- Outbox recover and pending-settlement lists skip memory copies of SQL-known ids so a sent/settled SQL row cannot look unsent again
- Leftover-index lookup treats SQL-ready miss as absent and only persists a process-local reserved hold when record_open runs again
- Leftover-index hydrate skips disk reserved rows whose id already exists in SQL, including closed rows
- Outbox and pending-settlement hydrate skip disk rows whose id is already in SQL, even if the SQL page missed them
- Website Chat leftover holds pin the conversation id so a later Brain turn cannot add message units on the same leftover
- Processing `end_job` closes only this process's SQL job id; it does not end another worker's latest job
- Accepted send does not mint a message unit when leftover policy already owns that turn
- Smart Follow-Up leftover pins include conversation and minted `sfu:` ids; a leftover already on the job is remembered after cutover

## Implemented this completion pass

- Optional Postgres ledger/daily-edits/expense path when billing PG + tables exist (`LINAS_MESSAGE_STORE=memory` for tests)
- Period grants from the current paid plan when `MESSAGE_BILLING_ENABLED` (no credit conversion)
- Customer Brain reserve/settle; follow-up settles only after send
- Daily-edit idempotent commit; no-op CM saves; FAQ / follow-up / publish / owner FAQ / product import guards
- Processing concurrency + daily attempt + import size budgets
- Knowledge heading chunks in the publish-time index; query-only hybrid (no document re-embed on turn)
- `ai_both` public placeholder after private DM
- Isolated lab API (`POST /api/platform/customer-ai-lab/turn`) when lab flag is on
- Platform cost dashboard filters + allocated/used/remaining messages; translation not folded into LLM
- Tenant dashboard message fields never copy credit quantities into `available_messages`

## Still blocked for activation

- Free offer + top-up prices + credit→message conversion (owner decisions)
- Live IAP/Google/Stripe message SKUs and payment-provider price agreement
- Approved conversion dry-run and existing-tenant balance migration
- Durable PG path against a provisioned production billing DB
- Live Voyage/pgvector/OpenAI planner-generate on a real tenant
- Full 800–1,500 eval suite
- Isolated lab is an owner portal page plus API; still capture-only and 404 unless `LINAS_CUSTOMER_AI_LAB`

## Rollback if a flag is ever enabled

- Set the flag back to false. Flag-off Customer Brain remains `engine_removed`.
- Do not revive Luna/Terra. Do not delete ledger reservations, expense events, or credit history.
- Search pointer supports `rollback_version` when a ready index exists.
